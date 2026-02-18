import json
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta
import secrets
import re

from peewee import *
from peewee import logger

from ..db.models.team import (
    Team, TeamMember, TeamMemberRole, TeamInvitation
)
from ..db.models.user import User


class TeamService:
    """Сервис для работы с командами"""

    # Константы
    INVITE_CODE_EXPIRY_MINUTES = 60
    INVITATION_EXPIRY_DAYS = 7
    TEAM_NAME_MIN_LENGTH = 2
    TEAM_NAME_MAX_LENGTH = 100

    def __init__(self):
        self.team_model = Team
        self.member_model = TeamMember
        self.role_model = TeamMemberRole
        self.invitation_model = TeamInvitation

    # ------------------- Инициализация и валидация -------------------

    def _validate_team_name(self, name: str) -> 'Tuple[bool, Optional[str]]':
        """Валидация названия команды"""
        if not name:
            return False, "Team name is required"

        if len(name) < self.TEAM_NAME_MIN_LENGTH:
            return False, f"Team name must be at least {self.TEAM_NAME_MIN_LENGTH} characters"

        if len(name) > self.TEAM_NAME_MAX_LENGTH:
            return False, f"Team name must be at most {self.TEAM_NAME_MAX_LENGTH} characters"

        return True, None

    def _generate_slug(self, name: str) -> str:
        """Генерация URL-friendly slug из названия"""
        import re
        slug = name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')

    def _get_unique_slug(self, base_slug: str) -> str:
        """Генерация уникального slug"""
        slug = base_slug
        counter = 1
        while self.team_model.select().where(self.team_model.slug == slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    # ------------------- Роли в команде -------------------

    def ensure_default_roles(self) -> Dict[str, TeamMemberRole]:
        """Создание стандартных ролей при первом запуске"""
        roles = {}
        for role_data in self.role_model.get_default_roles():
            role, created = self.role_model.get_or_create(
                name=role_data['name'],
                defaults=role_data
            )
            roles[role.name] = role
        return roles

    def get_role_by_name(self, name: str) -> Optional[TeamMemberRole]:
        """Получение роли по имени"""
        try:
            return self.role_model.get(self.role_model.name == name)
        except self.role_model.DoesNotExist:
            return None

    # ------------------- Создание команд -------------------

    def create_team(self,
                    name: str,
                    owner: User,
                    description: Optional[str] = None) -> Dict[str, Any]:
        """
        Создание новой команды
        """
        # Валидация
        valid, error = self._validate_team_name(name)
        if not valid:
            raise ValueError(f"Invalid team name: {error}")

        # Генерация slug
        base_slug = self._generate_slug(name)
        slug = self._get_unique_slug(base_slug)

        # Получаем роль владельца
        owner_role = self.get_role_by_name('owner')
        if not owner_role:
            roles = self.ensure_default_roles()
            owner_role = roles['owner']

        # Создаем команду
        team = self.team_model.create(
            name=name.strip(),
            slug=slug,
            description=description.strip() if description else None,
            owner=owner
        )

        # Генерируем код приглашения
        team.generate_invite_code()
        team.save()

        # Добавляем владельца в участники
        member = self.member_model.create(
            team=team,
            user=owner,
            role=owner_role,
            created_by=owner,
            is_active=True
        )

        # Обновляем счетчик
        team.members_count = 1
        team.save()

        return {
            'team': team,
            'member': member,
            'invite_code': team.invite_code
        }

    # ------------------- Управление участниками -------------------

    def add_member(self,
                   team: Team,
                   user: User,
                   role_name: str,
                   created_by: User) -> TeamMember:
        """
        Добавление участника в команду (прямое добавление)
        """
        # Проверяем права
        if not self.can_manage_team(created_by, team):
            raise PermissionError("You don't have permission to add members")

        # Проверяем, не участник ли уже (даже неактивный)
        existing = self.member_model.select().where(
            (self.member_model.team == team) &
            (self.member_model.user == user)
        ).first()

        if existing:
            if existing.is_active:
                raise ValueError("User is already a member of this team")
            else:
                # Реактивируем существующего участника
                existing.is_active = True
                existing.left_at = None
                existing.role = self.get_role_by_name(role_name) or existing.role
                existing.save()

                # Обновляем счетчик
                team.members_count = self.member_model.select().where(
                    (self.member_model.team == team) &
                    (self.member_model.is_active == True)
                ).count()
                team.save()

                return existing

        # Получаем роль
        role = self.get_role_by_name(role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' not found")

        # Добавляем участника
        member = self.member_model.create(
            team=team,
            user=user,
            role=role,
            created_by=created_by,
            is_active=True
        )

        # Обновляем счетчик
        team.members_count = self.member_model.select().where(
            (self.member_model.team == team) &
            (self.member_model.is_active == True)
        ).count()
        team.save()

        return member

    def remove_member(self,
                      team: Team,
                      user: User,
                      removed_by: User) -> bool:
        """
        Удаление участника из команды
        """
        # Проверяем права
        if not self.can_manage_team(removed_by, team):
            raise PermissionError("You don't have permission to remove members")

        # Нельзя удалить владельца
        member = self.member_model.get(
            (self.member_model.team == team) &
            (self.member_model.user == user) &
            (self.member_model.is_active == True)
        )

        if member.role.name == 'owner':
            raise ValueError("Cannot remove team owner")

        # Деактивируем участника
        member.is_active = False
        member.left_at = datetime.now()
        member.save()

        # Обновляем счетчик
        team.members_count = self.member_model.select().where(
            (self.member_model.team == team) &
            (self.member_model.is_active == True)
        ).count()
        team.save()

        return True

    def change_member_role(self,
                           team: Team,
                           user: User,
                           new_role_name: str,
                           changed_by: User) -> TeamMember:
        """
        Изменение роли участника
        """
        # Проверяем права
        if not self.can_manage_team(changed_by, team):
            raise PermissionError("You don't have permission to change roles")

        member = self.member_model.get(
            (self.member_model.team == team) &
            (self.member_model.user == user) &
            (self.member_model.is_active == True)
        )

        # Нельзя изменить роль владельца (кроме передачи владения)
        if member.role.name == 'owner' and changed_by.id != member.user.id:
            raise ValueError("Only the owner can transfer ownership")

        new_role = self.get_role_by_name(new_role_name)
        if not new_role:
            raise ValueError(f"Role '{new_role_name}' not found")

        member.role = new_role
        member.save()

        return member

    def transfer_ownership(self,
                           team: Team,
                           new_owner: User,
                           current_owner: User) -> Dict[str, Any]:
        """
        Передача прав владельца команды
        """
        # Проверяем, что текущий пользователь - владелец
        current_member = self.member_model.get(
            (self.member_model.team == team) &
            (self.member_model.user == current_owner) &
            (self.member_model.is_active == True)
        )

        if current_member.role.name != 'owner':
            raise PermissionError("Only the owner can transfer ownership")

        # Проверяем, что новый владелец - участник команды
        new_member = self.member_model.get(
            (self.member_model.team == team) &
            (self.member_model.user == new_owner) &
            (self.member_model.is_active == True)
        )

        # Меняем роли
        owner_role = self.get_role_by_name('owner')
        admin_role = self.get_role_by_name('admin')

        new_member.role = owner_role
        new_member.save()

        current_member.role = admin_role
        current_member.save()

        team.owner = new_owner
        team.save()

        return {
            'new_owner': new_member,
            'old_owner': current_member
        }

    # ------------------- Коды приглашений -------------------

    def refresh_invite_code(self, team: Team, requested_by: User) -> str:
        """
        Обновление кода приглашения
        """
        if not self.can_manage_team(requested_by, team):
            raise PermissionError("You don't have permission to manage invite codes")

        return team.generate_invite_code()

    def get_invite_code(self, team: Team, requested_by: User) -> str:
        """
        Получение актуального кода приглашения
        """
        if not self.can_view_team(requested_by, team):
            raise PermissionError("You don't have permission to view invite codes")

        # Проверяем, не истек ли код
        if team.invite_code_expires and team.invite_code_expires < datetime.now():
            return team.generate_invite_code()

        return team.invite_code

    def join_by_code(self, code: str, user: User) -> Dict[str, Any]:
        """
        Вступление в команду по коду приглашения
        """
        try:
            team = self.team_model.get(self.team_model.invite_code == code)
        except self.team_model.DoesNotExist:
            raise ValueError("Invalid invite code")

        if not team.is_invite_code_valid(code):
            raise ValueError("Invite code expired or invalid")

        # Проверяем, не участник ли уже
        existing = self.member_model.select().where(
            (self.member_model.team == team) &
            (self.member_model.user == user)
        ).first()

        if existing:
            if existing.is_active:
                raise ValueError("You are already a member of this team")
            else:
                # Реактивируем
                existing.is_active = True
                existing.left_at = None
                existing.save()

                team.members_count = self.member_model.select().where(
                    (self.member_model.team == team) &
                    (self.member_model.is_active == True)
                ).count()
                team.save()

                return {
                    'team': team,
                    'member': existing
                }

        # Получаем роль по умолчанию (member)
        member_role = self.get_role_by_name('member')
        if not member_role:
            roles = self.ensure_default_roles()
            member_role = roles['member']

        # Создаем участника
        member = self.member_model.create(
            team=team,
            user=user,
            role=member_role,
            created_by=team.owner,
            is_active=True
        )

        # Обновляем счетчик
        team.members_count = self.member_model.select().where(
            (self.member_model.team == team) &
            (self.member_model.is_active == True)
        ).count()
        team.save()

        return {
            'team': team,
            'member': member
        }

    # ------------------- Приглашения -------------------

    def create_invitation(self,
                          team: Team,
                          invited_by: User,
                          proposed_role_name: str,
                          invitee_username: Optional[str] = None,
                          invitee_email: Optional[str] = None,
                          invited_user: Optional[User] = None,
                          message: Optional[str] = None) -> TeamInvitation:
        """
        Создание приглашения в команду
        """
        # Проверяем права
        if not self.can_invite_members(invited_by, team):
            raise PermissionError("You don't have permission to invite members")

        # Проверяем, что указан хотя бы один способ идентификации
        if not invitee_username and not invitee_email and not invited_user:
            raise ValueError("Must specify username, email or user")

        # Получаем роль
        role = self.get_role_by_name(proposed_role_name)
        if not role:
            raise ValueError(f"Role '{proposed_role_name}' not found")

        # Проверяем, не существует ли уже активное приглашение
        query = self.invitation_model.select().where(
            (self.invitation_model.team == team) &
            (self.invitation_model.status == 'pending')
        )

        if invited_user:
            query = query.where(self.invitation_model.invited_user == invited_user)
        elif invitee_username:
            query = query.where(self.invitation_model.invitee_username == invitee_username)
        elif invitee_email:
            query = query.where(self.invitation_model.invitee_email == invitee_email)

        existing = query.first()
        if existing:
            raise ValueError("Active invitation already exists for this user")

        # Создаем приглашение
        invitation = self.invitation_model.create_invitation(
            team=team,
            invited_by=invited_by,
            proposed_role=role,
            invitee_username=invitee_username,
            invitee_email=invitee_email,
            invited_user=invited_user,
            message=message
        )

        return invitation

    def accept_invitation(self, invitation: TeamInvitation, user: User) -> Dict[str, Any]:
        """
        Принятие приглашения
        """
        # Проверяем валидность
        if not invitation.is_valid():
            raise ValueError("Invitation is expired or already processed")

        # Проверяем, что приглашение адресовано этому пользователю
        if invitation.invited_user and invitation.invited_user.id != user.id:
            raise PermissionError("This invitation was sent to another user")

        if invitation.invitee_username and invitation.invitee_username != user.username:
            raise PermissionError("This invitation was sent to another username")

        # Принимаем приглашение
        invitation.accept()

        # Получаем или создаем участника
        member, created = self.member_model.get_or_create(
            team=invitation.team,
            user=user,
            defaults={
                'role': invitation.proposed_role,
                'created_by': invitation.invited_by,
                'is_active': True,
                'joined_at': datetime.now()
            }
        )

        if not created and not member.is_active:
            member.is_active = True
            member.left_at = None
            member.role = invitation.proposed_role
            member.save()

        # Обновляем счетчик
        invitation.team.members_count = self.member_model.select().where(
            (self.member_model.team == invitation.team) &
            (self.member_model.is_active == True)
        ).count()
        invitation.team.save()

        return {
            'team': invitation.team,
            'member': member
        }

    def decline_invitation(self, invitation: TeamInvitation, user: User) -> bool:
        """
        Отклонение приглашения
        """
        # Проверяем права
        if invitation.invited_user and invitation.invited_user.id != user.id:
            raise PermissionError("You cannot decline this invitation")

        invitation.status = 'declined'
        invitation.responded_at = datetime.now()
        invitation.save()

        return True

    def cancel_invitation(self, invitation: TeamInvitation, cancelled_by: User) -> bool:
        """
        Отмена приглашения (создателем)
        """
        if invitation.invited_by.id != cancelled_by.id:
            raise PermissionError("Only the creator can cancel this invitation")

        invitation.status = 'cancelled'
        invitation.save()

        return True

    # ------------------- Получение данных -------------------

    def get_user_teams(self, user: User, active_only: bool = True) -> List[Team]:
        """
        Получение всех команд пользователя
        """
        query = self.member_model.select().where(
            self.member_model.user == user
        )

        if active_only:
            query = query.where(self.member_model.is_active == True)

        return [member.team for member in query]

    def get_team_members(self,
                         team: Team,
                         include_inactive: bool = False) -> List[TeamMember]:
        """
        Получение участников команды
        """
        query = self.member_model.select().where(
            self.member_model.team == team
        )

        if not include_inactive:
            query = query.where(self.member_model.is_active == True)

        return list(query.order_by(
            self.member_model.role_id.desc(),
            self.member_model.joined_at
        ))

    def get_user_role_in_team(self, user: User, team: Team) -> Optional[TeamMemberRole]:
        """
        Получение роли пользователя в команде
        """
        try:
            member = self.member_model.get(
                (self.member_model.team == team) &
                (self.member_model.user == user) &
                (self.member_model.is_active == True)
            )
            return member.role
        except self.member_model.DoesNotExist:
            return None

    def get_team_by_slug(self, slug: str) -> Optional[Team]:
        """
        Получение команды по slug
        """
        try:
            return self.team_model.get(
                self.team_model.slug == slug
                # У Team нет поля status
            )
        except self.team_model.DoesNotExist:
            return None

    def get_team_invitations(self,
                             team: Team,
                             status: Optional[str] = 'pending') -> List[TeamInvitation]:
        """
        Получение приглашений команды
        """
        query = self.invitation_model.select().where(
            self.invitation_model.team == team
        )

        if status:
            query = query.where(self.invitation_model.status == status)

        return list(query.order_by(self.invitation_model.created_at.desc()))

    def get_user_invitations(self, user: User) -> List[TeamInvitation]:
        """
        Получение активных приглашений пользователя
        """
        return list(self.invitation_model.select().where(
            ((self.invitation_model.invited_user == user) |
             (self.invitation_model.invitee_username == user.username)) &
            (self.invitation_model.status == 'pending')
        ).order_by(self.invitation_model.created_at.desc()))

    # ------------------- Проверка прав -------------------

    def is_member(self, user: User, team: Team) -> bool:
        """
        Проверка, является ли пользователь участником команды
        """
        try:
            self.member_model.get(
                (self.member_model.team == team) &
                (self.member_model.user == user) &
                (self.member_model.is_active == True)
            )
            return True
        except self.member_model.DoesNotExist:
            return False

    def can_manage_team(self, user: User, team: Team) -> bool:
        """
        Может ли пользователь управлять командой
        Только owner имеет can_manage_team = True
        """
        role = self.get_user_role_in_team(user, team)
        if not role:
            return False
        logger.info(
            f"User {user.username} role in team {team.slug}: {role.name}, can_manage_team: {role.can_manage_team}")
        return role.can_manage_team

    def can_manage_projects(self, user: User, team: Team) -> bool:
        """
        Может ли пользователь создавать/управлять проектами в команде
        """
        role = self.get_user_role_in_team(user, team)
        if not role:
            return False
        return role.can_manage_projects

    def can_invite_members(self, user: User, team: Team) -> bool:
        """
        Может ли пользователь приглашать участников
        """
        role = self.get_user_role_in_team(user, team)
        if not role:
            return False
        return role.can_invite_members

    def can_remove_members(self, user: User, team: Team) -> bool:
        """
        Может ли пользователь удалять участников
        """
        role = self.get_user_role_in_team(user, team)
        if not role:
            return False
        return role.can_remove_members

    def can_view_team(self, user: User, team: Team) -> bool:
        """
        Может ли пользователь просматривать команду
        """
        return self.is_member(user, team)

    # ------------------- Поиск и фильтрация -------------------

    def search_teams(self,
                     query: Optional[str] = None,
                     user: Optional[User] = None,
                     limit: int = 20,
                     offset: int = 0) -> List[Team]:
        """
        Поиск команд
        """
        # У Team нет поля status, просто выбираем все команды
        conditions = []

        if query:
            search = f"%{query}%"
            conditions.append(
                (self.team_model.name ** search) |
                (self.team_model.slug ** search) |
                (self.team_model.description ** search)
            )

        if user:
            # Команды, в которых состоит пользователь
            team_ids = self.member_model.select(self.member_model.team).where(
                (self.member_model.user == user) &
                (self.member_model.is_active == True)
            )
            conditions.append(self.team_model.id.in_(team_ids))

        query = self.team_model.select()
        if conditions:
            query = query.where(*conditions)

        return list(
            query.order_by(self.team_model.name)
            .limit(limit)
            .offset(offset)
        )

    def get_team_stats(self, team: Team) -> Dict[str, Any]:
        """
        Статистика по команде
        """
        total_members = self.member_model.select().where(
            (self.member_model.team == team) &
            (self.member_model.is_active == True)
        ).count()

        # Статистика по ролям
        role_stats = {}
        for role in self.role_model.select():
            count = self.member_model.select().where(
                (self.member_model.team == team) &
                (self.member_model.role == role) &
                (self.member_model.is_active == True)
            ).count()
            if count > 0:
                role_stats[role.name] = count

        # Количество проектов - опционально, если нет таблицы projects, не используем
        projects_count = 0
        try:
            from ..db.models.project import Project
            projects_count = Project.select().where(
                Project.team == team
            ).count()
        except ImportError:
            # Модель Project не доступна
            pass
        except Exception:
            # Таблица projects не существует
            pass

        # Активные приглашения
        pending_invites = self.invitation_model.select().where(
            (self.invitation_model.team == team) &
            (self.invitation_model.status == 'pending')
        ).count()

        return {
            'team_id': team.id,
            'team_name': team.name,
            'total_members': total_members,
            'by_role': role_stats,
            'projects_count': projects_count,
            'pending_invitations': pending_invites,
            'created_at': team.created_at,
            'owner': team.owner.username
        }

    # ------------------- Обновление команды -------------------

    def update_team(self,
                    team: Team,
                    updated_by: User,
                    name: Optional[str] = None,
                    description: Optional[str] = None,
                    avatar: Optional[str] = None) -> Team:
        """
        Обновление информации о команде
        """
        if not self.can_manage_team(updated_by, team):
            raise PermissionError("You don't have permission to update this team")

        if name is not None:
            valid, error = self._validate_team_name(name)
            if not valid:
                raise ValueError(f"Invalid team name: {error}")
            team.name = name.strip()
            team.slug = self._get_unique_slug(self._generate_slug(name))

        if description is not None:
            team.description = description.strip() if description else None

        if avatar is not None:
            team.avatar = avatar

        team.save()
        return team

    # ------------------- Удаление/Архивация -------------------

    def delete_team(self, team: Team, deleted_by: User) -> bool:
        """
        Удаление команды (мягкое удаление - просто деактивируем участников)
        """
        # Только владелец может удалить команду
        if team.owner.id != deleted_by.id:
            # Проверяем роль
            role = self.get_user_role_in_team(deleted_by, team)
            if not role or not role.can_manage_team:
                raise PermissionError("Only the owner can delete the team")

        # Деактивируем всех участников кроме владельца
        self.member_model.update(
            is_active=False,
            left_at=datetime.now()
        ).where(
            (self.member_model.team == team) &
            (self.member_model.is_active == True) &
            (self.member_model.user != team.owner)
        ).execute()

        # Отменяем все приглашения
        self.invitation_model.update(
            status='cancelled'
        ).where(
            (self.invitation_model.team == team) &
            (self.invitation_model.status == 'pending')
        ).execute()

        # Обновляем счетчик
        team.members_count = 1  # только владелец
        team.save()

        return True

    def get_team_by_id(self, team_id: int) -> Optional[Team]:
        """
        Получение команды по ID
        """
        try:
            return self.team_model.get_by_id(team_id)
        except self.team_model.DoesNotExist:
            return None