import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import secrets

from peewee import *
from peewee import logger

from ..db.models.project import (
    Project, ProjectRole, ProjectMember, ProjectInvitation
)
from ..db.models.user import User
from ..db.models.team import Team, TeamMember


class ProjectService:
    """Сервис для работы с проектами"""

    # Константы
    PROJECT_NAME_MIN_LENGTH = 2
    PROJECT_NAME_MAX_LENGTH = 200

    def __init__(self):
        self.project_model = Project
        self.role_model = ProjectRole
        self.member_model = ProjectMember
        self.invitation_model = ProjectInvitation

    # ------------------- Инициализация и валидация -------------------

    def _validate_project_name(self, name: str) -> 'Tuple[bool, Optional[str]]':
        """Валидация названия проекта"""
        if not name:
            return False, "Project name is required"

        if len(name) < self.PROJECT_NAME_MIN_LENGTH:
            return False, f"Project name must be at least {self.PROJECT_NAME_MIN_LENGTH} characters"

        if len(name) > self.PROJECT_NAME_MAX_LENGTH:
            return False, f"Project name must be at most {self.PROJECT_NAME_MAX_LENGTH} characters"

        return True, None

    def _generate_slug(self, name: str) -> str:
        """Генерация URL-friendly slug из названия"""
        import re
        slug = name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')

    def _get_unique_slug(self, base_slug: str, team_id: int) -> str:
        """Генерация уникального slug в рамках команды"""
        slug = base_slug
        counter = 1
        while self.project_model.select().where(
            (self.project_model.slug == slug) &
            (self.project_model.team_id == team_id)
        ).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    # ------------------- Роли в проекте -------------------

    def ensure_default_roles(self) -> Dict[str, ProjectRole]:
        """Создание стандартных ролей при первом запуске"""
        roles = {}
        for role_data in self.role_model.get_default_roles():
            role, created = self.role_model.get_or_create(
                name=role_data['name'],
                defaults=role_data
            )
            roles[role.name] = role
        return roles

    def get_role_by_name(self, name: str) -> Optional[ProjectRole]:
        """Получение роли по имени"""
        try:
            return self.role_model.get(self.role_model.name == name)
        except self.role_model.DoesNotExist:
            return None

    # ------------------- Создание проектов -------------------

    def create_project(self,
                      team: Team,
                      name: str,
                      created_by: User,
                      description: Optional[str] = None,
                      initial_graph_data: Optional[str] = None) -> Dict[str, Any]:
        """
        Создание нового проекта в команде
        """
        # Проверяем права на создание проекта в команде
        from .TeamService import TeamService
        team_service = TeamService()
        if not team_service.can_manage_projects(created_by, team):
            raise PermissionError("You don't have permission to create projects in this team")

        # Валидация
        valid, error = self._validate_project_name(name)
        if not valid:
            raise ValueError(f"Invalid project name: {error}")

        # Генерация slug
        base_slug = self._generate_slug(name)
        slug = self._get_unique_slug(base_slug, team.id)

        # Получаем роль владельца проекта
        owner_role = self.get_role_by_name('owner')
        if not owner_role:
            roles = self.ensure_default_roles()
            owner_role = roles['owner']

        # Создаем проект
        project = self.project_model.create(
            name=name.strip(),
            slug=slug,
            description=description.strip() if description else None,
            team=team,
            created_by=created_by,
            graph_data=initial_graph_data or json.dumps({
                'nodes': [],
                'edges': []
            }),
            settings=json.dumps({
                'default_task_status': 'todo',
                'notifications_enabled': True,
                'allow_guest_comments': False
            })
        )

        # Добавляем создателя как владельца проекта
        member = self.member_model.create(
            project=project,
            user=created_by,
            role=owner_role,
            created_by=created_by,
            is_active=True
        )

        # Обновляем счетчики
        project.members_count = 1
        project.tasks_count = 0
        project.save()

        return {
            'project': project,
            'member': member
        }

    # ------------------- Управление участниками -------------------

    def add_member(self,
                  project: Project,
                  user: User,
                  role_name: str,
                  added_by: User) -> ProjectMember:
        """
        Добавление участника в проект
        """
        # Проверяем права
        if not self.can_manage_members(added_by, project):
            raise PermissionError("You don't have permission to add members to this project")

        # Проверяем, что пользователь - участник команды
        from .TeamService import TeamService
        team_service = TeamService()
        if not team_service.is_member(user, project.team):
            raise ValueError("User must be a team member to be added to project")

        # Проверяем, не участник ли уже
        existing = self.member_model.select().where(
            (self.member_model.project == project) &
            (self.member_model.user == user) &
            (self.member_model.is_active == True)
        ).first()

        if existing:
            raise ValueError("User is already a member of this project")

        # Получаем роль
        role = self.get_role_by_name(role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' not found")

        # Добавляем участника
        member = self.member_model.create(
            project=project,
            user=user,
            role=role,
            created_by=added_by,
            is_active=True
        )

        # Обновляем счетчик
        project.members_count = self.member_model.select().where(
            (self.member_model.project == project) &
            (self.member_model.is_active == True)
        ).count()
        project.save()

        return member

    def remove_member(self,
                     project: Project,
                     user: User,
                     removed_by: User) -> bool:
        """
        Удаление участника из проекта
        """
        # Проверяем права
        if not self.can_manage_members(removed_by, project):
            raise PermissionError("You don't have permission to remove members from this project")

        # Нельзя удалить владельца
        member = self.member_model.get(
            (self.member_model.project == project) &
            (self.member_model.user == user) &
            (self.member_model.is_active == True)
        )

        if member.role.name == 'owner':
            raise ValueError("Cannot remove project owner")

        # Деактивируем участника
        member.is_active = False
        member.left_at = datetime.now()
        member.save()

        # Обновляем счетчик
        project.members_count = self.member_model.select().where(
            (self.member_model.project == project) &
            (self.member_model.is_active == True)
        ).count()
        project.save()

        return True

    def change_member_role(self,
                          project: Project,
                          user: User,
                          new_role_name: str,
                          changed_by: User) -> ProjectMember:
        """
        Изменение роли участника в проекте
        """
        # Проверяем права
        if not self.can_manage_members(changed_by, project):
            raise PermissionError("You don't have permission to change roles in this project")

        member = self.member_model.get(
            (self.member_model.project == project) &
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
                          project: Project,
                          new_owner: User,
                          current_owner: User) -> Dict[str, Any]:
        """
        Передача прав владельца проекта
        """
        # Проверяем, что текущий пользователь - владелец
        current_member = self.member_model.get(
            (self.member_model.project == project) &
            (self.member_model.user == current_owner) &
            (self.member_model.is_active == True)
        )

        if current_member.role.name != 'owner':
            raise PermissionError("Only the owner can transfer ownership")

        # Проверяем, что новый владелец - участник проекта
        new_member = self.member_model.get(
            (self.member_model.project == project) &
            (self.member_model.user == new_owner) &
            (self.member_model.is_active == True)
        )

        # Меняем роли
        owner_role = self.get_role_by_name('owner')
        manager_role = self.get_role_by_name('manager')

        new_member.role = owner_role
        new_member.save()

        current_member.role = manager_role
        current_member.save()

        return {
            'new_owner': new_member,
            'old_owner': current_member
        }

    # ------------------- Приглашения в проект -------------------

    def create_invitation(self,
                         project: Project,
                         invited_by: User,
                         proposed_role_name: str,
                         team_member: TeamMember) -> ProjectInvitation:
        """
        Создание приглашения в проект (приглашаем участника команды)
        """
        # Проверяем права
        if not self.can_manage_members(invited_by, project):
            raise PermissionError("You don't have permission to invite members to this project")

        # Проверяем, что приглашаемый - участник команды
        if team_member.team.id != project.team.id:
            raise ValueError("User must be a member of the team that owns this project")

        # Получаем роль
        role = self.get_role_by_name(proposed_role_name)
        if not role:
            raise ValueError(f"Role '{proposed_role_name}' not found")

        # Проверяем, не участник ли уже проекта
        existing = self.member_model.select().where(
            (self.member_model.project == project) &
            (self.member_model.user == team_member.user) &
            (self.member_model.is_active == True)
        ).first()

        if existing:
            raise ValueError("User is already a member of this project")

        # Проверяем, нет ли активного приглашения
        existing_invite = self.invitation_model.select().where(
            (self.invitation_model.project == project) &
            (self.invitation_model.team_member == team_member) &
            (self.invitation_model.status == 'pending')
        ).first()

        if existing_invite:
            raise ValueError("Active invitation already exists for this user")

        # Создаем приглашение
        invitation = self.invitation_model.create_invitation(
            project=project,
            invited_by=invited_by,
            proposed_role=role,
            team_member=team_member,
            invited_user=team_member.user
        )

        return invitation

    def accept_invitation(self, invitation: ProjectInvitation, user: User) -> Dict[str, Any]:
        """
        Принятие приглашения в проект
        """
        # Проверяем валидность
        if invitation.status != 'pending':
            raise ValueError("Invitation is already processed")

        if invitation.expires_at < datetime.now():
            invitation.status = 'expired'
            invitation.save()
            raise ValueError("Invitation has expired")

        # Проверяем, что приглашение адресовано этому пользователю
        if invitation.invited_user.id != user.id:
            raise PermissionError("This invitation was sent to another user")

        # Принимаем приглашение
        invitation.accept()

        return {
            'project': invitation.project,
            'member': ProjectMember.get(
                (ProjectMember.project == invitation.project) &
                (ProjectMember.user == user) &
                (ProjectMember.is_active == True)
            )
        }

    def decline_invitation(self, invitation: ProjectInvitation, user: User) -> bool:
        """
        Отклонение приглашения
        """
        if invitation.invited_user.id != user.id:
            raise PermissionError("You cannot decline this invitation")

        invitation.status = 'declined'
        invitation.responded_at = datetime.now()
        invitation.save()

        return True

    # ------------------- Получение данных -------------------

    def get_user_projects(self, user: User, include_archived: bool = False) -> List[Project]:
        """
        Получение всех проектов пользователя
        """
        query = self.member_model.select().where(
            (self.member_model.user == user) &
            (self.member_model.is_active == True)
        )

        projects = []
        for member in query:
            if include_archived or member.project.status == 'active':
                projects.append(member.project)

        return projects

    def get_project_members(self,
                          project: Project,
                          include_inactive: bool = False) -> List[ProjectMember]:
        """
        Получение участников проекта
        """
        query = self.member_model.select().where(
            self.member_model.project == project
        )

        if not include_inactive:
            query = query.where(self.member_model.is_active == True)

        return list(query.order_by(
            self.member_model.role_id.desc(),
            self.member_model.joined_at
        ))

    def get_user_role_in_project(self, user: User, project: Project) -> Optional[ProjectRole]:
        """
        Получение роли пользователя в проекте
        """
        try:
            member = self.member_model.get(
                (self.member_model.project == project) &
                (self.member_model.user == user) &
                (self.member_model.is_active == True)
            )
            return member.role
        except self.member_model.DoesNotExist:
            return None

    def get_project_by_slug(self, slug: str, team: Team) -> Optional[Project]:
        """
        Получение проекта по slug в рамках команды
        """
        try:
            return self.project_model.get(
                (self.project_model.slug == slug) &
                (self.project_model.team == team)
                # НЕ ФИЛЬТРУЕМ ПО status!
            )
        except self.project_model.DoesNotExist:
            return None

    # ------------------- Проверка прав -------------------

    def is_member(self, user: User, project: Project) -> bool:
        """
        Проверка, является ли пользователь участником проекта
        """
        try:
            self.member_model.get(
                (self.member_model.project == project) &
                (self.member_model.user == user) &
                (self.member_model.is_active == True)
            )
            return True
        except self.member_model.DoesNotExist:
            return False

    def can_manage_members(self, user: User, project: Project) -> bool:
        """
        Может ли пользователь управлять участниками проекта
        """
        role = self.get_user_role_in_project(user, project)
        if not role:
            return False
        return role.can_manage_members

    def can_edit_project(self, user: User, project: Project) -> bool:
        """
        Может ли пользователь редактировать проект
        """
        role = self.get_user_role_in_project(user, project)
        if not role:
            return False
        return role.can_edit_project

    def can_delete_project(self, user: User, project: Project) -> bool:
        """
        Может ли пользователь удалить проект
        """
        role = self.get_user_role_in_project(user, project)
        if not role:
            return False
        return role.can_delete_project

    def can_create_tasks(self, user: User, project: Project) -> bool:
        """
        Может ли пользователь создавать задачи в проекте
        """
        role = self.get_user_role_in_project(user, project)
        if not role:
            logger.warning(f"User {user.username} has no role in project {project.id}")
            return False

        logger.info(f"User {user.username} role: {role.name}, can_create_tasks: {role.can_create_tasks}")

        # Если роль не имеет права - возвращаем False, НЕ ВЫБРАСЫВАЕМ ИСКЛЮЧЕНИЕ!
        if not role.can_create_tasks:
            return False

        return True

    def can_edit_task(self, user: User, task) -> bool:
        """
        Может ли пользователь редактировать конкретную задачу

        - owner/manager: могут редактировать любые задачи (все поля)
        - developer: может редактировать ТОЛЬКО статус задачи, НО НЕ название!
        """
        role = self.get_user_role_in_project(user, task.project)
        if not role:
            return False

        # Owner/Manager могут редактировать любые задачи
        if role.can_edit_any_task:
            return True

        # Developer может редактировать только свои задачи
        if role.can_edit_own_task:
            # Проверяем, является ли пользователь создателем или исполнителем
            is_creator = task.creator_id == user.id
            is_assignee = task.assignee_id == user.id

            # ВАЖНО: Developer может менять только статус, но не название!
            # Эта логика должна быть в эндпоинте, а не здесь
            return is_creator or is_assignee

        return False

    def can_delete_task(self, user: User, task) -> bool:
        """
        Может ли пользователь удалить задачу

        - owner/manager: могут удалять любые задачи
        - developer: может удалять ТОЛЬКО свои задачи (созданные им)
        """
        role = self.get_user_role_in_project(user, task.project)
        if not role:
            return False

        # Owner/Manager могут удалять любые задачи
        if role.can_delete_any_task:
            return True

        # Developer может удалять только свои задачи
        if role.can_delete_own_task:
            return task.creator_id == user.id

        return False

    def can_create_dependencies(self, user: User, task) -> bool:
        """
        Может ли пользователь создавать зависимости для задачи
        """
        role = self.get_user_role_in_project(user, task.project)
        if not role:
            return False

        # Owner/Manager могут создавать любые зависимости
        if role.can_create_dependencies and role.can_edit_any_task:
            return True

        # Developer может создавать зависимости, если задача его
        if role.can_create_dependencies:
            return task.creator.id == user.id or task.assignee.id == user.id

        return False

    # ------------------- Управление проектом -------------------

    def update_project(self,
                      project: Project,
                      updated_by: User,
                      name: Optional[str] = None,
                      description: Optional[str] = None,
                      settings: Optional[Dict[str, Any]] = None) -> Project:
        """
        Обновление информации о проекте
        """
        if not self.can_edit_project(updated_by, project):
            raise PermissionError("You don't have permission to update this project")

        if name is not None:
            valid, error = self._validate_project_name(name)
            if not valid:
                raise ValueError(f"Invalid project name: {error}")
            project.name = name.strip()
            project.slug = self._get_unique_slug(
                self._generate_slug(name),
                project.team.id
            )

        if description is not None:
            project.description = description.strip() if description else None

        if settings is not None:
            current_settings = project.settings_dict
            current_settings.update(settings)
            project.settings = json.dumps(current_settings)

        project.save()
        return project

    def save_graph_data(self,
                       project: Project,
                       graph_data: Dict[str, Any],
                       saved_by: User) -> Project:
        """
        Сохранение данных графа
        """
        # Все участники могут сохранять граф (они же работают с задачами)
        if not self.is_member(saved_by, project):
            raise PermissionError("You don't have permission to edit this project")

        project.graph_data = json.dumps(graph_data)
        project.save()

        return project

    def archive_project(self, project: Project, archived_by: User) -> bool:
        """
        Архивация проекта - мягкое удаление, проект остается в БД
        """
        # Проверяем права
        if not self.can_delete_project(archived_by, project):
            raise PermissionError("You don't have permission to archive this project")

        # Меняем статус, НЕ УДАЛЯЕМ!
        project.status = 'archived'
        project.archived_at = datetime.now()
        project.save()

        # Логируем событие (если есть)
        # from ..models.task import TaskEvent
        # TaskEvent.log(...)

        return True

    def delete_project(self, project: Project, deleted_by: User) -> bool:
        """
        Удаление проекта (мягкое удаление)
        """
        if not self.can_delete_project(deleted_by, project):
            raise PermissionError("You don't have permission to delete this project")

        project.status = 'deleted'
        project.save()

        # Деактивируем всех участников
        self.member_model.update(
            is_active=False,
            left_at=datetime.now()
        ).where(
            (self.member_model.project == project) &
            (self.member_model.is_active == True)
        ).execute()

        return True

    # ------------------- Статистика -------------------

    def get_project_stats(self, project: Project) -> Dict[str, Any]:
        """
        Статистика по проекту
        """
        from .TaskService import TaskService
        task_service = TaskService()

        total_members = self.member_model.select().where(
            (self.member_model.project == project) &
            (self.member_model.is_active == True)
        ).count()

        # Статистика по ролям
        role_stats = {}
        for role in self.role_model.select():
            count = self.member_model.select().where(
                (self.member_model.project == project) &
                (self.member_model.role == role) &
                (self.member_model.is_active == True)
            ).count()
            if count > 0:
                role_stats[role.name] = count

        # Статистика по задачам
        task_stats = task_service.get_task_stats(project)

        return {
            'project_id': project.id,
            'project_name': project.name,
            'total_members': total_members,
            'by_role': role_stats,
            'tasks': task_stats,
            'created_at': project.created_at,
            'created_by': project.created_by.username,
            'team': project.team.name
        }