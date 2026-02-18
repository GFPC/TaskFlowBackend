from typing import Optional

from peewee import *
from datetime import datetime, timedelta
import json
from ...db.base import BaseModel
from .user import User
from .project import Project, ProjectMember


# ------------------- 1. Статусы задач -------------------

class TaskStatus(BaseModel):
    """Статусы задач"""
    id = AutoField()
    name = CharField(max_length=50, unique=True)
    display_name = CharField(max_length=100)
    color = CharField(max_length=7, default='#1976d2')
    order = IntegerField(default=0, index=True)
    is_final = BooleanField(default=False)
    is_blocking = BooleanField(default=False)

    class Meta:
        table_name = 'task_statuses'

    @classmethod
    def get_default_statuses(cls):
        statuses = [
            {
                'name': 'todo',
                'display_name': 'К выполнению',
                'color': '#757575',
                'order': 10,
                'is_final': False,
                'is_blocking': False
            },
            {
                'name': 'in_progress',
                'display_name': 'В работе',
                'color': '#1976d2',
                'order': 20,
                'is_final': False,
                'is_blocking': False
            },
            {
                'name': 'review',
                'display_name': 'На проверке',
                'color': '#ed6c02',
                'order': 30,
                'is_final': False,
                'is_blocking': False
            },
            {
                'name': 'completed',
                'display_name': 'Выполнена',
                'color': '#2e7d32',
                'order': 40,
                'is_final': True,
                'is_blocking': False
            },
            {
                'name': 'blocked',
                'display_name': 'Заблокирована',
                'color': '#d32f2f',
                'order': 5,
                'is_final': False,
                'is_blocking': True
            }
        ]
        return statuses


# ------------------- 2. Типы действий на зависимостях -------------------

class DependencyActionType(BaseModel):
    """Типы действий, которые можно выполнить при срабатывании зависимости"""
    id = AutoField()
    name = CharField(max_length=50, unique=True)
    code = CharField(max_length=50, unique=True)
    description = TextField(null=True)

    requires_target_user = BooleanField(default=False)
    requires_template = BooleanField(default=False)
    supports_delay = BooleanField(default=False)

    class Meta:
        table_name = 'dependency_action_types'

    @classmethod
    def get_default_types(cls):
        types = [
            {
                'name': 'Уведомить исполнителя целевой задачи',
                'code': 'notify_assignee',
                'description': 'Отправить уведомление в Telegram исполнителю задачи',
                'requires_target_user': False,
                'requires_template': True,
                'supports_delay': False
            },
            {
                'name': 'Уведомить создателя исходной задачи',
                'code': 'notify_creator',
                'description': 'Отправить уведомление в Telegram создателю задачи',
                'requires_target_user': False,
                'requires_template': True,
                'supports_delay': False
            },
            {
                'name': 'Уведомить конкретного пользователя',
                'code': 'notify_custom',
                'description': 'Отправить уведомление конкретному пользователю',
                'requires_target_user': True,
                'requires_template': True,
                'supports_delay': True
            },
            {
                'name': 'Изменить статус задачи',
                'code': 'change_status',
                'description': 'Автоматически изменить статус целевой задачи',
                'requires_target_user': False,
                'requires_template': False,
                'supports_delay': True
            },
            {
                'name': 'Создать подзадачу',
                'code': 'create_subtask',
                'description': 'Создать подзадачу в целевой задаче',
                'requires_target_user': True,
                'requires_template': False,
                'supports_delay': False
            }
        ]
        return types


# ------------------- 3. Задачи -------------------

class Task(BaseModel):
    """Задачи в проекте"""
    id = AutoField()
    project = ForeignKeyField(Project, backref='tasks', on_delete='CASCADE')

    # Основная информация
    name = CharField(max_length=500)
    description = TextField(null=True)

    # Статус
    status = ForeignKeyField(TaskStatus, on_delete='RESTRICT', index=True)

    # Участники
    assignee = ForeignKeyField(User, backref='assigned_tasks', on_delete='SET NULL', null=True, index=True)
    creator = ForeignKeyField(User, backref='created_tasks', on_delete='RESTRICT', index=True)

    # Временные метки
    created_at = DateTimeField(default=datetime.now, index=True)
    updated_at = DateTimeField(default=datetime.now)
    started_at = DateTimeField(null=True)
    completed_at = DateTimeField(null=True)
    deadline = DateTimeField(null=True, index=True)

    # Приоритет
    priority = IntegerField(default=0, index=True)

    # Позиция на графе
    position_x = FloatField(default=0)
    position_y = FloatField(default=0)

    # Метаданные
    metadata = TextField(null=True)

    class Meta:
        table_name = 'tasks'
        indexes = (
            (('project', 'id'), True),  # Уникальная связь project + id
            (('project', 'status'), False),
            (('project', 'assignee'), False),
            (('project', 'creator'), False),
            (('project', 'deadline'), False),
            (('assignee', 'status'), False),
        )

    def __str__(self):
        return f"[{self.project.slug}] #{self.id}: {self.name}"

    @property
    def metadata_dict(self):
        if self.metadata:
            return json.loads(self.metadata)
        return {}

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        if self.status.name == 'in_progress' and not self.started_at:
            self.started_at = datetime.now()
        elif self.status.name == 'completed' and not self.completed_at:
            self.completed_at = datetime.now()
        return super(Task, self).save(*args, **kwargs)


# ------------------- 4. Зависимости задач -------------------

class TaskDependency(BaseModel):
    """Зависимости между задачами (рёбра графа)"""
    id = AutoField()

    project = ForeignKeyField(Project, backref='dependencies', on_delete='CASCADE')
    source_task = ForeignKeyField(Task, backref='outgoing_dependencies', on_delete='CASCADE')
    target_task = ForeignKeyField(Task, backref='incoming_dependencies', on_delete='CASCADE')

    dependency_type = CharField(max_length=50, default='simple', index=True)
    description = TextField(null=True)
    edge_style = TextField(null=True)
    edge_label = CharField(max_length=255, null=True)

    created_at = DateTimeField(default=datetime.now)
    created_by = ForeignKeyField(User, on_delete='RESTRICT')

    class Meta:
        table_name = 'task_dependencies'
        indexes = (
            (('project', 'source_task'), False),
            (('project', 'target_task'), False),
            (('source_task', 'target_task'), True),
        )


# ------------------- 5. Действия на зависимостях -------------------

class DependencyAction(BaseModel):
    """Действия, выполняемые при срабатывании зависимости"""
    id = AutoField()

    dependency = ForeignKeyField(TaskDependency, backref='actions', on_delete='CASCADE')
    action_type = ForeignKeyField(DependencyActionType, on_delete='RESTRICT')

    target_user = ForeignKeyField(User, null=True, on_delete='SET NULL')
    target_status = ForeignKeyField(TaskStatus, null=True, on_delete='SET NULL')

    message_template = TextField(null=True)
    delay_minutes = IntegerField(default=0)
    execute_order = IntegerField(default=0)
    is_active = BooleanField(default=True, index=True)

    class Meta:
        table_name = 'dependency_actions'
        indexes = (
            (('dependency', 'execute_order'), False),
            (('action_type', 'is_active'), False),
        )


# ------------------- 6. События задач -------------------

class TaskEvent(BaseModel):
    """События, происходящие с задачами"""
    id = AutoField()

    project = ForeignKeyField(Project, backref='task_events', on_delete='CASCADE')
    task = ForeignKeyField(Task, backref='events', on_delete='CASCADE')
    user = ForeignKeyField(User, backref='task_events', on_delete='RESTRICT')

    event_type = CharField(max_length=50, index=True)
    old_value = TextField(null=True)
    new_value = TextField(null=True)
    metadata = TextField(null=True)

    created_at = DateTimeField(default=datetime.now, index=True)

    class Meta:
        table_name = 'task_events'
        indexes = (
            (('task', 'created_at'), False),
            (('project', 'created_at'), False),
        )

    @classmethod
    def log(cls, task, user, event_type, old_value=None, new_value=None, metadata=None):
        """Быстрое логирование события задачи"""
        return cls.create(
            project=task.project,
            task=task,
            user=user,
            event_type=event_type,
            old_value=str(old_value) if old_value else None,
            new_value=str(new_value) if new_value else None,
            metadata=json.dumps(metadata) if metadata else None
        )


# ------------------- 7. Запланированные действия -------------------

class ScheduledAction(BaseModel):
    """Отложенные действия (уведомления о дедлайнах и т.д.)"""
    id = AutoField()

    project = ForeignKeyField(Project, backref='scheduled_actions', on_delete='CASCADE')
    task = ForeignKeyField(Task, backref='scheduled_actions', on_delete='CASCADE')

    action_type = CharField(max_length=50, index=True)
    scheduled_for = DateTimeField(index=True)
    executed_at = DateTimeField(null=True)
    payload = TextField(null=True)
    dependency_action = ForeignKeyField(DependencyAction, null=True, on_delete='SET NULL')

    status = CharField(max_length=20, default='pending', index=True)
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'scheduled_actions'
        indexes = (
            (('scheduled_for', 'status'), False),
            (('task', 'action_type', 'status'), False),
        )

    @classmethod
    def schedule_deadline_notification(cls, task: Task, hours_before: int = 24) -> Optional['ScheduledAction']:
        """Запланировать уведомление о приближении дедлайна"""
        if not task.deadline:
            return None

        notify_time = task.deadline - timedelta(hours=hours_before)
        if notify_time < datetime.now():
            return None

        return cls.create(
            project=task.project,
            task=task,
            action_type='deadline_approaching',
            scheduled_for=notify_time,
            payload=json.dumps({'hours_before': hours_before})
        )