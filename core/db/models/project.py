from peewee import *
from datetime import datetime, timedelta
import json
from ...db.base import BaseModel
from .user import User
from .team import Team, TeamMember


# ------------------- 1. Роли участников проекта -------------------

class ProjectRole(BaseModel):
    """Роли участников внутри проекта"""
    id = AutoField()
    name = CharField(max_length=50, unique=True)  # 'owner', 'manager', 'developer', 'observer'
    description = TextField(null=True)
    priority = IntegerField(default=0, index=True)

    # Права на задачи
    can_create_tasks = BooleanField(default=False)
    can_edit_any_task = BooleanField(default=False)
    can_delete_any_task = BooleanField(default=False)
    can_edit_own_task = BooleanField(default=True)
    can_delete_own_task = BooleanField(default=True)

    # Права на зависимости
    can_create_dependencies = BooleanField(default=False)
    can_delete_dependencies = BooleanField(default=False)

    # Права на управление проектом
    can_manage_members = BooleanField(default=False)
    can_edit_project = BooleanField(default=False)
    can_delete_project = BooleanField(default=False)

    class Meta:
        table_name = 'project_roles'

    @classmethod
    def get_default_roles(cls):
        """Создание стандартных ролей при инициализации"""
        roles = [
            {
                'name': 'owner',
                'description': 'Владелец проекта',
                'priority': 100,
                'can_create_tasks': True,
                'can_edit_any_task': True,
                'can_delete_any_task': True,
                'can_edit_own_task': True,
                'can_delete_own_task': True,
                'can_create_dependencies': True,
                'can_delete_dependencies': True,
                'can_manage_members': True,
                'can_edit_project': True,
                'can_delete_project': True
            },
            {
                'name': 'manager',
                'description': 'Менеджер проекта',
                'priority': 80,
                'can_create_tasks': True,
                'can_edit_any_task': True,
                'can_delete_any_task': True,
                'can_edit_own_task': True,
                'can_delete_own_task': True,
                'can_create_dependencies': True,
                'can_delete_dependencies': True,
                'can_manage_members': True,
                'can_edit_project': True,
                'can_delete_project': False
            },
            {
                'name': 'developer',
                'description': 'Разработчик',
                'priority': 60,
                'can_create_tasks': True,
                'can_edit_any_task': False,
                'can_delete_any_task': False,
                'can_edit_own_task': True,
                'can_delete_own_task': True,
                'can_create_dependencies': True,
                'can_delete_dependencies': False,
                'can_manage_members': False,
                'can_edit_project': False,
                'can_delete_project': False
            },
            {
                'name': 'observer',
                'description': 'Наблюдатель',
                'priority': 40,
                'can_create_tasks': False,
                'can_edit_any_task': False,
                'can_delete_any_task': False,
                'can_edit_own_task': False,
                'can_delete_own_task': False,
                'can_create_dependencies': False,
                'can_delete_dependencies': False,
                'can_manage_members': False,
                'can_edit_project': False,
                'can_delete_project': False
            }
        ]
        return roles


# ------------------- 2. Проекты -------------------

class Project(BaseModel):
    """Проекты"""
    id = AutoField()

    # Основная информация
    name = CharField(max_length=200, index=True)
    slug = CharField(max_length=200, unique=True, index=True)
    description = TextField(null=True)

    # Команда-владелец проекта
    team = ForeignKeyField(Team, backref='projects', on_delete='CASCADE', index=True)

    # Создатель проекта
    created_by = ForeignKeyField(User, backref='created_projects', on_delete='RESTRICT')

    # Данные графа для ReactFlow (полный экспорт)
    graph_data = TextField(null=True)  # JSON для полного рендеринга

    # Настройки проекта
    settings = TextField(null=True, default='{}')  # JSON с настройками

    # Статистика
    tasks_count = IntegerField(default=0)
    members_count = IntegerField(default=0)

    # Статус проекта
    status = CharField(
        max_length=20,
        choices=[
            ('active', 'Активен'),
            ('archived', 'Архив'),
            ('deleted', 'Удален')
        ],
        default='active',
        index=True
    )

    # Временные метки
    created_at = DateTimeField(default=datetime.now, index=True)
    updated_at = DateTimeField(default=datetime.now)
    archived_at = DateTimeField(null=True)

    class Meta:
        table_name = 'projects'
        indexes = (
            (('team', 'status'), False),
            (('created_by', 'created_at'), False),
        )

    def __str__(self):
        return f"{self.team.name} / {self.name}"

    @property
    def settings_dict(self):
        if self.settings:
            return json.loads(self.settings)
        return {
            'default_task_status': 'todo',
            'notifications_enabled': True,
            'allow_guest_comments': False
        }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(Project, self).save(*args, **kwargs)

    def archive(self):
        """Архивирование проекта"""
        self.status = 'archived'
        self.archived_at = datetime.now()
        self.save()


# ------------------- 3. Участники проектов -------------------

class ProjectMember(BaseModel):
    """Участники проекта"""
    id = AutoField()

    project = ForeignKeyField(Project, backref='members', on_delete='CASCADE', index=True)
    user = ForeignKeyField(User, backref='projects', on_delete='CASCADE', index=True)
    role = ForeignKeyField(ProjectRole, on_delete='RESTRICT')

    # Кто добавил
    created_by = ForeignKeyField(User, backref='added_project_members', on_delete='RESTRICT')

    # Статус
    is_active = BooleanField(default=True, index=True)
    joined_at = DateTimeField(default=datetime.now)
    left_at = DateTimeField(null=True)

    class Meta:
        table_name = 'project_members'
        indexes = (
            (('project', 'user'), True),  # Уникальная связь
            (('project', 'role'), False),
            (('user', 'project', 'is_active'), False),
        )

    def has_permission(self, permission):
        """Проверка прав в проекте"""
        return hasattr(self.role, permission) and getattr(self.role, permission)


# ------------------- 4. Приглашения в проект -------------------

class ProjectInvitation(BaseModel):
    """Приглашения в проект"""
    id = AutoField()

    project = ForeignKeyField(Project, backref='invitations', on_delete='CASCADE', index=True)
    invited_by = ForeignKeyField(User, backref='sent_project_invitations', on_delete='RESTRICT')
    invited_user = ForeignKeyField(User, backref='received_project_invitations', null=True, on_delete='SET NULL')

    # Приглашаем участника команды
    team_member = ForeignKeyField(TeamMember, null=True, on_delete='SET NULL')

    # Предлагаемая роль
    proposed_role = ForeignKeyField(ProjectRole, on_delete='RESTRICT')

    # Статус
    status = CharField(
        max_length=20,
        choices=[
            ('pending', 'Ожидает'),
            ('accepted', 'Принято'),
            ('declined', 'Отклонено'),
            ('expired', 'Истекло')
        ],
        default='pending',
        index=True
    )

    created_at = DateTimeField(default=datetime.now, index=True)
    expires_at = DateTimeField()
    responded_at = DateTimeField(null=True)

    class Meta:
        table_name = 'project_invitations'

    @classmethod
    def create_invitation(cls, project, invited_by, proposed_role, team_member=None, invited_user=None):
        """Создание приглашения в проект"""
        expires_at = datetime.now() + timedelta(days=7)

        return cls.create(
            project=project,
            invited_by=invited_by,
            invited_user=invited_user or team_member.user,
            team_member=team_member,
            proposed_role=proposed_role,
            expires_at=expires_at
        )

    def accept(self):
        """Принятие приглашения"""
        self.status = 'accepted'
        self.responded_at = datetime.now()
        self.save()

        # Создаем участника проекта
        ProjectMember.create(
            project=self.project,
            user=self.invited_user,
            role=self.proposed_role,
            created_by=self.invited_by
        )

        # Обновляем счетчик
        self.project.members_count = self.project.members.count()
        self.project.save()