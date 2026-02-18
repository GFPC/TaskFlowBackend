from peewee import *
from datetime import datetime, timedelta
import secrets
from ...db.base import BaseModel
from .user import User


# ------------------- 1. Роли участников команды -------------------

class TeamMemberRole(BaseModel):
    """Роли участников внутри команды"""
    id = AutoField()
    name = CharField(max_length=50, unique=True)  # 'owner', 'admin', 'member'
    description = TextField(null=True)
    priority = IntegerField(default=0, index=True)  # Чем выше, тем больше прав
    can_manage_team = BooleanField(default=False)  # Управление командой
    can_manage_projects = BooleanField(default=False)  # Создание/управление проектами
    can_invite_members = BooleanField(default=False)  # Приглашение участников
    can_remove_members = BooleanField(default=False)  # Удаление участников

    class Meta:
        table_name = 'team_member_roles'

    @classmethod
    def get_default_roles(cls):
        """Создание стандартных ролей при инициализации"""
        roles = [
            {
                'name': 'owner',
                'description': 'Владелец команды',
                'priority': 100,
                'can_manage_team': True,
                'can_manage_projects': True,
                'can_invite_members': True,
                'can_remove_members': True
            },
            {
                'name': 'admin',
                'description': 'Администратор команды',
                'priority': 80,
                'can_manage_team': False,
                'can_manage_projects': True,
                'can_invite_members': True,
                'can_remove_members': True
            },
            {
                'name': 'member',
                'description': 'Участник команды',
                'priority': 50,
                'can_manage_team': False,
                'can_manage_projects': False,
                'can_invite_members': False,
                'can_remove_members': False
            }
        ]
        return roles


# ------------------- 2. Команды -------------------

class Team(BaseModel):
    """Команды пользователей"""
    id = AutoField()
    name = CharField(max_length=100, index=True)
    slug = CharField(max_length=100, unique=True, index=True)  # URL-friendly имя
    description = TextField(null=True)
    avatar = TextField(null=True)  # URL аватарки

    # Владелец команды
    owner = ForeignKeyField(User, backref='owned_teams', on_delete='RESTRICT')

    # Код приглашения
    invite_code = CharField(max_length=32, null=True, index=True)
    invite_code_expires = DateTimeField(null=True)

    # Статистика
    members_count = IntegerField(default=0)
    projects_count = IntegerField(default=0)

    # Временные метки
    created_at = DateTimeField(default=datetime.now, index=True)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'teams'

    def __str__(self):
        return self.name

    def generate_invite_code(self):
        """Генерация уникального кода приглашения"""
        self.invite_code = secrets.token_urlsafe(16)
        self.invite_code_expires = datetime.now() + timedelta(hours=1)
        return self.invite_code

    def refresh_invite_code(self):
        """Обновление кода приглашения (если истек или нужен новый)"""
        if not self.invite_code or (self.invite_code_expires and self.invite_code_expires < datetime.now()):
            return self.generate_invite_code()
        return self.invite_code

    def is_invite_code_valid(self, code):
        """Проверка валидности кода приглашения"""
        if not self.invite_code or not self.invite_code_expires:
            return False
        if self.invite_code != code:
            return False
        if self.invite_code_expires < datetime.now():
            return False
        return True

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(Team, self).save(*args, **kwargs)


# ------------------- 3. Участники команд -------------------

class TeamMember(BaseModel):
    """Связь пользователей с командами"""
    id = AutoField()

    team = ForeignKeyField(Team, backref='members', on_delete='CASCADE', index=True)
    user = ForeignKeyField(User, backref='teams', on_delete='CASCADE', index=True)
    role = ForeignKeyField(TeamMemberRole, on_delete='RESTRICT')

    # Кто добавил
    created_by = ForeignKeyField(User, backref='added_team_members', on_delete='RESTRICT')

    # Статус участника
    is_active = BooleanField(default=True, index=True)
    joined_at = DateTimeField(default=datetime.now)
    left_at = DateTimeField(null=True)

    # Кастомные настройки для участника в этой команде
    custom_permissions = TextField(null=True)  # JSON с дополнительными правами
    notification_preferences = TextField(null=True)  # JSON настроек уведомлений

    class Meta:
        table_name = 'team_members'
        indexes = (
            (('team', 'user'), True),  # Уникальная связь
            (('team', 'role'), False),
            (('user', 'is_active'), False),
        )

    def has_permission(self, permission):
        """Проверка прав участника"""
        # Проверяем базовые права роли
        if hasattr(self.role, permission) and getattr(self.role, permission):
            return True

        # Проверяем кастомные права
        if self.custom_permissions:
            import json
            custom = json.loads(self.custom_permissions)
            return custom.get(permission, False)

        return False

    @property
    def is_owner(self):
        return self.role.name == 'owner'

    @property
    def is_admin(self):
        return self.role.name in ['owner', 'admin']


# ------------------- 4. Приглашения -------------------

class TeamInvitation(BaseModel):
    """Приглашения в команду"""
    id = AutoField()

    team = ForeignKeyField(Team, backref='invitations', on_delete='CASCADE', index=True)
    invited_by = ForeignKeyField(User, backref='sent_invitations', on_delete='RESTRICT')
    invited_user = ForeignKeyField(User, backref='received_invitations', null=True, on_delete='SET NULL')

    # Код приглашения (можно использовать как ссылку)
    code = CharField(max_length=32, unique=True, index=True)

    # Email или username для приглашения
    invitee_username = CharField(max_length=50, null=True)  # Если приглашаем по username
    invitee_email = CharField(max_length=255, null=True)  # Если по email

    # Предлагаемая роль
    proposed_role = ForeignKeyField(TeamMemberRole, on_delete='RESTRICT')

    # Статус
    status = CharField(
        max_length=20,
        choices=[
            ('pending', 'Ожидает'),
            ('accepted', 'Принято'),
            ('declined', 'Отклонено'),
            ('expired', 'Истекло'),
            ('cancelled', 'Отменено')
        ],
        default='pending',
        index=True
    )

    # Временные метки
    created_at = DateTimeField(default=datetime.now, index=True)
    expires_at = DateTimeField()
    responded_at = DateTimeField(null=True)

    # Сообщение к приглашению
    message = TextField(null=True)

    class Meta:
        table_name = 'team_invitations'
        indexes = (
            (('team', 'status'), False),
            (('invited_user', 'status'), False),
        )

    @classmethod
    def create_invitation(cls, team, invited_by, proposed_role,
                          invitee_username=None, invitee_email=None,
                          invited_user=None, message=None):
        """Создание приглашения"""
        code = secrets.token_urlsafe(16)
        expires_at = datetime.now() + timedelta(days=7)

        return cls.create(
            team=team,
            invited_by=invited_by,
            invited_user=invited_user,
            code=code,
            invitee_username=invitee_username,
            invitee_email=invitee_email,
            proposed_role=proposed_role,
            expires_at=expires_at,
            message=message
        )

    def accept(self):
        """Принятие приглашения"""
        self.status = 'accepted'
        self.responded_at = datetime.now()
        self.save()

        # Создаем участника команды
        TeamMember.create(
            team=self.team,
            user=self.invited_user or User.get(username=self.invitee_username),
            role=self.proposed_role,
            created_by=self.invited_by
        )

        # Обновляем счетчик участников
        self.team.members_count = self.team.members.count()
        self.team.save()

    def decline(self):
        """Отклонение приглашения"""
        self.status = 'declined'
        self.responded_at = datetime.now()
        self.save()

    def is_valid(self):
        """Проверка валидности приглашения"""
        if self.status != 'pending':
            return False
        if self.expires_at < datetime.now():
            self.status = 'expired'
            self.save()
            return False
        return True