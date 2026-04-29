import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from peewee import *
from peewee import logger

from ..db.models.project import Project, ProjectMember
from ..db.models.task import (
    DependencyAction,
    DependencyActionType,
    ScheduledAction,
    Task,
    TaskDependency,
    TaskEvent,
    TaskStatus,
)
from ..db.models.user import User
from .ProjectService import ProjectService
from .TeamService import TeamService
from .UserService import UserService


class TaskService:
    """Сервис для работы с задачами и графом зависимостей"""

    DEPENDENCY_TYPES = {
        'blocks': {
            'name': 'Блокирует',
            'description': 'Источник должен быть завершен до начала целевой задачи',
            'is_blocking': True,
        },
        'simple': {
            'name': 'Обычная зависимость',
            'description': 'Совместимый исторический тип; участвует в блокировке',
            'is_blocking': True,
        },
        'dependency': {
            'name': 'Зависимость',
            'description': 'Алиас блокирующей зависимости для старого фронта',
            'is_blocking': True,
        },
        'soft': {
            'name': 'Мягкая связь',
            'description': 'Визуальная связь без влияния на готовность',
            'is_blocking': False,
        },
        'relates_to': {
            'name': 'Связана с',
            'description': 'Информационная связь без блокировки',
            'is_blocking': False,
        },
    }

    def __init__(self):
        self.task_model = Task
        self.status_model = TaskStatus
        self.dependency_model = TaskDependency
        self.action_model = DependencyAction
        self.action_type_model = DependencyActionType
        self.event_model = TaskEvent
        self.scheduled_model = ScheduledAction

    # ------------------- Инициализация -------------------

    def ensure_default_statuses(self) -> Dict[str, TaskStatus]:
        """Создание стандартных статусов задач"""
        statuses = {}
        for status_data in self.status_model.get_default_statuses():
            status, created = self.status_model.get_or_create(
                name=status_data['name'], defaults=status_data
            )
            statuses[status.name] = status
        return statuses

    def ensure_default_action_types(self) -> Dict[str, DependencyActionType]:
        """Создание стандартных типов действий на зависимостях"""
        action_types = {}
        for action_data in self.action_type_model.get_default_types():
            action_type, created = self.action_type_model.get_or_create(
                code=action_data['code'], defaults=action_data
            )
            action_types[action_type.code] = action_type
        return action_types

    def get_graph_meta(self) -> Dict[str, Any]:
        """Справочники для фронта по графу задач."""
        self.ensure_default_statuses()
        action_types = self.ensure_default_action_types()
        return {
            'edge_direction': 'A -> B means task A blocks or precedes task B',
            'readiness': {
                'ready_status': 'todo',
                'final_source_statuses': [
                    status.name
                    for status in self.status_model.select().where(
                        self.status_model.is_final == True
                    )
                ],
                'blocked_error_code': 'TASK_NOT_READY',
            },
            'dependency_types': [
                {'code': code, **meta}
                for code, meta in self.DEPENDENCY_TYPES.items()
            ],
            'action_types': [
                {
                    'code': action_type.code,
                    'name': action_type.name,
                    'description': action_type.description,
                    'requires_target_user': action_type.requires_target_user,
                    'requires_template': action_type.requires_template,
                    'supports_delay': action_type.supports_delay,
                }
                for action_type in action_types.values()
            ],
            'errors': {
                'cycle': 'DEPENDENCY_CYCLE',
                'task_not_ready': 'TASK_NOT_READY',
                'unknown_action_type': 'UNKNOWN_ACTION_TYPE',
            },
        }

    def get_status_by_name(self, name: str) -> Optional[TaskStatus]:
        """Получение статуса по имени"""
        try:
            return self.status_model.get(self.status_model.name == name)
        except self.status_model.DoesNotExist:
            return None

    # ------------------- Создание задач -------------------

    def create_task(
        self,
        project: Project,
        name: str,
        creator: User,
        description: Optional[str] = None,
        assignee: Optional[User] = None,
        deadline: Optional[datetime] = None,
        priority: int = 0,
        position_x: float = 0,
        position_y: float = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Создание новой задачи
        """
        from .ProjectService import ProjectService

        project_service = ProjectService()

        # Проверяем права на создание задач
        if not project_service.can_create_tasks(creator, project):
            raise PermissionError(
                "You don't have permission to create tasks in this project"
            )

        # Получаем статус по умолчанию (todo)
        todo_status = self.get_status_by_name('todo')
        if not todo_status:
            statuses = self.ensure_default_statuses()
            todo_status = statuses['todo']

        # Проверяем, что исполнитель - участник проекта
        if assignee:
            if not project_service.is_member(assignee, project):
                raise ValueError('Assignee must be a member of the project')

        # Создаем задачу
        task = self.task_model.create(
            project=project,
            name=name.strip(),
            description=description.strip() if description else None,
            status=todo_status,
            assignee=assignee,
            creator=creator,
            deadline=deadline,
            priority=priority,
            position_x=position_x,
            position_y=position_y,
            metadata=json.dumps(metadata) if metadata else None,
        )

        # Обновляем счетчик задач в проекте
        project.tasks_count = (
            self.task_model.select()
            .where(
                (self.task_model.project == project)
                & (
                    self.task_model.status_id.in_(
                        self.status_model.select(self.status_model.id).where(
                            self.status_model.is_final == False
                        )
                    )
                )
            )
            .count()
        )
        project.save()

        # Логируем событие
        self.event_model.log(task=task, user=creator, event_type='created')

        # Планируем уведомления о дедлайне
        if deadline:
            self.scheduled_model.schedule_deadline_notification(task, 24)
            self.scheduled_model.schedule_deadline_notification(task, 1)

        return {'task': task, 'status': task.status}

    # ------------------- Обновление задач -------------------

    def update_task(
        self,
        task: Task,
        updated_by: User,
        name: Optional[str] = None,
        description: Optional[str] = None,
        assignee: Optional[User] = None,
        deadline: Optional[datetime] = None,
        priority: Optional[int] = None,
        position_x: Optional[float] = None,
        position_y: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """
        Обновление задачи
        """
        from .ProjectService import ProjectService

        project_service = ProjectService()

        # Проверяем права
        if not project_service.can_edit_task(updated_by, task):
            raise PermissionError("You don't have permission to edit this task")

        changes = []

        if name is not None and name != task.name:
            old = task.name
            task.name = name.strip()
            changes.append(('name', old, task.name))

        if description is not None:
            old = task.description
            task.description = description.strip() if description else None
            changes.append(('description', old, task.description))

        if assignee is not None and assignee.id != task.assignee_id:
            # Проверяем, что новый исполнитель - участник проекта
            if assignee:
                if not project_service.is_member(assignee, task.project):
                    raise ValueError('Assignee must be a member of the project')

            old = task.assignee
            task.assignee = assignee
            changes.append(
                (
                    'assignee',
                    old.username if old else None,
                    assignee.username if assignee else None,
                )
            )

        if deadline is not None:
            old = task.deadline
            task.deadline = deadline
            changes.append(('deadline', old, deadline))

            # Перепланируем уведомления
            if deadline:
                # Удаляем старые
                self.scheduled_model.delete().where(
                    (self.scheduled_model.task == task)
                    & (self.scheduled_model.action_type == 'deadline_approaching')
                ).execute()
                # Создаем новые
                self.scheduled_model.schedule_deadline_notification(task, 24)
                self.scheduled_model.schedule_deadline_notification(task, 1)

        if priority is not None:
            old = task.priority
            task.priority = priority
            changes.append(('priority', old, priority))

        if position_x is not None:
            task.position_x = position_x
        if position_y is not None:
            task.position_y = position_y

        if metadata is not None:
            old = task.metadata_dict
            task.metadata = json.dumps(metadata)
            changes.append(('metadata', old, metadata))

        task.save()

        # Логируем изменения
        for change in changes:
            self.event_model.log(
                task=task,
                user=updated_by,
                event_type='updated',
                old_value=str(change[1]),
                new_value=str(change[2]),
                metadata={'field': change[0]},
            )

        return task

    def change_task_status(
        self, task: Task, new_status_name: str, changed_by: User
    ) -> Dict[str, Any]:
        """
        Изменение статуса задачи
        """
        from .ProjectService import ProjectService

        project_service = ProjectService()

        # Проверяем отдельное право на смену статуса
        if not project_service.can_change_task_status(changed_by, task):
            raise PermissionError(
                "You don't have permission to change this task status"
            )

        new_status = self.get_status_by_name(new_status_name)
        if not new_status:
            raise ValueError(f"Status '{new_status_name}' not found")

        old_status = task.status

        if new_status.name == 'in_progress' and not self.check_task_readiness(task):
            blocking_task_ids = self.get_blocking_task_ids(task)
            raise ValueError(
                f"TASK_NOT_READY: Task is blocked by unfinished dependencies: {blocking_task_ids}"
            )

        # Если статус не меняется - просто возвращаем успех
        if old_status.id == new_status.id:
            return {
                'task': task,
                'status_changed': False,
                'old_status': old_status,
                'new_status': new_status,
                'actions_executed': [],
            }

        # Меняем статус
        task.status = new_status
        task.save()

        # Логируем событие
        try:
            self.event_model.log(
                task=task,
                user=changed_by,
                event_type='status_changed',
                old_value=old_status.name,
                new_value=new_status.name,
            )
        except Exception as e:
            logger.error(f'Error logging status change: {e}')

        result = {
            'task': task,
            'status_changed': True,
            'old_status': old_status,
            'new_status': new_status,
            'actions_executed': [],
        }

        if new_status.is_final and not old_status.is_final:
            try:
                result['actions_executed'] = self._handle_task_completion(
                    task, changed_by
                )
            except Exception as e:
                logger.error(f'Error handling task completion: {e}')
            self._refresh_downstream_readiness(task)

        return result

    # ------------------- Работа с зависимостями -------------------

    def create_dependency(
        self,
        source_task: Task,
        target_task: Task,
        created_by: User,
        dependency_type: str = 'simple',
        description: Optional[str] = None,
    ) -> TaskDependency:
        """
        Создание зависимости между задачами
        """
        from .ProjectService import ProjectService

        project_service = ProjectService()

        # Проверяем права на создание зависимости
        if not project_service.can_create_dependencies(created_by, source_task):
            raise PermissionError(
                "You don't have permission to create dependencies for this task"
            )

        # Проверяем, что задачи из одного проекта
        if source_task.project_id != target_task.project_id:
            raise ValueError('Tasks must be in the same project')

        if dependency_type not in self.DEPENDENCY_TYPES:
            allowed = ', '.join(self.DEPENDENCY_TYPES.keys())
            raise ValueError(f"Unknown dependency_type '{dependency_type}'. Allowed: {allowed}")

        # Проверяем на циклическую зависимость для блокирующих типов
        if self.is_blocking_dependency_type(dependency_type) and self.would_create_cycle(
            source_task, target_task
        ):
            raise ValueError('This dependency would create a cycle')

        # Проверяем, не существует ли уже такая зависимость
        existing = (
            self.dependency_model.select()
            .where(
                (self.dependency_model.project == source_task.project)
                & (self.dependency_model.source_task == source_task)
                & (self.dependency_model.target_task == target_task)
            )
            .first()
        )

        if existing:
            raise ValueError('Dependency already exists')

        # Создаем зависимость
        dependency = self.dependency_model.create(
            project=source_task.project,
            source_task=source_task,
            target_task=target_task,
            dependency_type=dependency_type,
            description=description,
            created_by=created_by,
        )

        # Логируем событие
        self.event_model.log(
            task=source_task,
            user=created_by,
            event_type='dependency_added',
            metadata={
                'dependency_id': dependency.id,
                'target_task_id': target_task.id,
                'target_task_name': target_task.name,
            },
        )

        return dependency

    def update_dependency(
        self,
        dependency: TaskDependency,
        updated_by: User,
        dependency_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> TaskDependency:
        """Частичное обновление зависимости без пересоздания ребра."""
        from .ProjectService import ProjectService

        project_service = ProjectService()
        if not project_service.can_manage_task_graph(updated_by, dependency.project):
            raise PermissionError("You don't have permission to update dependencies")

        if dependency_type is not None:
            if dependency_type not in self.DEPENDENCY_TYPES:
                allowed = ', '.join(self.DEPENDENCY_TYPES.keys())
                raise ValueError(
                    f"Unknown dependency_type '{dependency_type}'. Allowed: {allowed}"
                )
            if (
                self.is_blocking_dependency_type(dependency_type)
                and not self.is_blocking_dependency_type(dependency.dependency_type)
                and self.would_create_cycle(dependency.source_task, dependency.target_task)
            ):
                raise ValueError('This dependency would create a cycle')
            dependency.dependency_type = dependency_type

        if description is not None:
            dependency.description = description

        dependency.save()
        self.event_model.log(
            task=dependency.source_task,
            user=updated_by,
            event_type='dependency_updated',
            metadata={'dependency_id': dependency.id},
        )
        return dependency

    def delete_dependency(self, dependency: TaskDependency, deleted_by: User) -> bool:
        """
        Удаление зависимости
        """
        from .ProjectService import ProjectService

        project_service = ProjectService()

        # Проверяем права (только менеджеры/владельцы могут удалять зависимости)
        if not project_service.can_manage_task_graph(deleted_by, dependency.project):
            raise PermissionError("You don't have permission to delete dependencies")

        # Логируем событие
        self.event_model.log(
            task=dependency.source_task,
            user=deleted_by,
            event_type='dependency_removed',
            metadata={
                'target_task_id': dependency.target_task_id,
                'target_task_name': dependency.target_task.name,
            },
        )

        dependency.delete_instance()
        return True

    def would_create_cycle(self, source: Task, target: Task) -> bool:
        """
        Проверка на создание циклической зависимости
        """
        visited = set()

        def dfs(task_id: int) -> bool:
            if task_id == source.id:
                return True
            if task_id in visited:
                return False
            visited.add(task_id)

            deps = self.dependency_model.select().where(
                (self.dependency_model.project == source.project)
                & (self.dependency_model.source_task_id == task_id)
                & (
                    self.dependency_model.dependency_type.in_(
                        self.get_blocking_dependency_types()
                    )
                )
            )

            for dep in deps:
                if dfs(dep.target_task_id):
                    return True
            return False

        return dfs(target.id)

    def get_task_dependencies(self, task: Task) -> Dict[str, List[TaskDependency]]:
        """
        Получение всех зависимостей задачи
        """
        incoming = list(
            self.dependency_model.select().where(
                (self.dependency_model.project == task.project)
                & (self.dependency_model.target_task == task)
            )
        )

        outgoing = list(
            self.dependency_model.select().where(
                (self.dependency_model.project == task.project)
                & (self.dependency_model.source_task == task)
            )
        )

        return {'incoming': incoming, 'outgoing': outgoing}

    def get_blocking_dependency_types(self) -> List[str]:
        """Типы зависимостей, которые участвуют в расчете is_ready."""
        return [
            code
            for code, meta in self.DEPENDENCY_TYPES.items()
            if meta.get('is_blocking')
        ]

    def is_blocking_dependency_type(self, dependency_type: str) -> bool:
        """Проверка, блокирует ли тип зависимости целевую задачу."""
        return self.DEPENDENCY_TYPES.get(dependency_type, {}).get('is_blocking', False)

    def get_blocking_task_ids(self, task: Task) -> List[int]:
        """ID незавершенных задач, блокирующих указанную задачу."""
        incoming = (
            self.dependency_model.select()
            .where(
                (self.dependency_model.project == task.project)
                & (self.dependency_model.target_task == task)
                & (
                    self.dependency_model.dependency_type.in_(
                        self.get_blocking_dependency_types()
                    )
                )
            )
            .order_by(self.dependency_model.id)
        )

        blocking_task_ids = []
        for dep in incoming:
            if not dep.source_task.status.is_final:
                blocking_task_ids.append(dep.source_task_id)
        return blocking_task_ids

    def get_readiness_info(self, task: Task) -> Dict[str, Any]:
        """Готовность задачи и структурированная причина блокировки."""
        blocking_task_ids = self.get_blocking_task_ids(task)
        is_ready = task.status.name == 'todo' and not blocking_task_ids
        return {
            'is_ready': is_ready,
            'blocking_task_ids': blocking_task_ids,
            'blocked_reason': 'blocked_by_dependencies'
            if blocking_task_ids
            else None,
        }

    def _refresh_downstream_readiness(self, task: Task) -> None:
        """После завершения задачи пересчитать готовность зависимых."""
        outgoing = self.dependency_model.select().where(
            (self.dependency_model.project == task.project)
            & (self.dependency_model.source_task == task)
        )
        for dependency in outgoing:
            self.check_task_readiness(dependency.target_task)

    def check_task_readiness(self, task: Task) -> bool:
        """
        Проверка, готова ли задача к выполнению

        Задача готова ТОЛЬКО если:
        1. Статус задачи 'todo' (не in_progress, не completed, не blocked, не review)
        2. У задачи нет входящих блокирующих зависимостей, ИЛИ
        3. Все блокирующие предки находятся в финальном статусе
        """
        # ========== 1. ПРОВЕРКА СТАТУСА ==========
        # Только задачи со статусом 'todo' могут быть готовы
        if task.status.name != 'todo':
            return False

        return not self.get_blocking_task_ids(task)

    def check_downstream_tasks(self, task: Task):
        """
        Проверка готовности всех задач, которые зависят от данной
        """
        outgoing = self.dependency_model.select().where(
            (self.dependency_model.project == task.project)
            & (self.dependency_model.source_task == task)
        )

        for dep in outgoing:
            self.check_task_readiness(dep.target_task)

    # ------------------- Действия на зависимостях -------------------

    def add_dependency_action(
        self,
        dependency: TaskDependency,
        action_type_code: str,
        created_by: User,
        target_user: Optional[User] = None,
        target_status_name: Optional[str] = None,
        message_template: Optional[str] = None,
        delay_minutes: int = 0,
        execute_order: int = 0,
    ) -> DependencyAction:
        """Добавление действия, которое сработает при завершении source_task."""
        from .ProjectService import ProjectService

        project_service = ProjectService()
        if not project_service.can_manage_task_graph(created_by, dependency.project):
            raise PermissionError("You don't have permission to update dependencies")

        action_type = self.get_action_type_or_raise(action_type_code)
        target_status = None

        if action_type.requires_target_user and not target_user:
            raise ValueError(f"Action '{action_type_code}' requires target_user")
        if action_type.requires_template and not message_template:
            raise ValueError(f"Action '{action_type_code}' requires message_template")
        if action_type.code == 'change_status':
            if not target_status_name:
                raise ValueError("Action 'change_status' requires target_status")
            target_status = self.get_status_by_name(target_status_name)
            if not target_status:
                raise ValueError(f"Status '{target_status_name}' not found")

        return self.action_model.create(
            dependency=dependency,
            action_type=action_type,
            target_user=target_user,
            target_status=target_status,
            message_template=message_template,
            delay_minutes=delay_minutes,
            execute_order=execute_order,
            is_active=True,
        )

    def get_action_type_or_raise(self, action_type_code: str) -> DependencyActionType:
        """Получение типа действия с понятной ошибкой для API."""
        self.ensure_default_action_types()
        try:
            return self.action_type_model.get(self.action_type_model.code == action_type_code)
        except self.action_type_model.DoesNotExist:
            allowed = ', '.join(
                row.code for row in self.action_type_model.select().order_by(self.action_type_model.code)
            )
            raise ValueError(
                f"UNKNOWN_ACTION_TYPE: Unknown action_type_code '{action_type_code}'. "
                f'Allowed: {allowed}'
            )

    def remove_dependency_action(
        self, action: DependencyAction, deleted_by: User
    ) -> bool:
        """Мягкое удаление действия на зависимости."""
        from .ProjectService import ProjectService

        project_service = ProjectService()
        if not project_service.can_manage_task_graph(
            deleted_by, action.dependency.project
        ):
            raise PermissionError("You don't have permission to update dependencies")

        action.is_active = False
        action.save()
        return True

    def _handle_task_completion(
        self, task: Task, triggered_by: User
    ) -> List[Dict[str, Any]]:
        """Выполнить действия на исходящих зависимостях завершенной задачи."""
        results = []
        outgoing = (
            self.dependency_model.select()
            .where(
                (self.dependency_model.project == task.project)
                & (self.dependency_model.source_task == task)
            )
            .order_by(self.dependency_model.id)
        )
        for dependency in outgoing:
            results.extend(
                self.execute_dependency_actions(
                    dependency=dependency,
                    trigger_event='task_completed',
                    triggered_by=triggered_by,
                )
            )
        return results

    def execute_dependency_actions(
        self,
        dependency: TaskDependency,
        trigger_event: str,
        triggered_by: User,
    ) -> List[Dict[str, Any]]:
        """Выполнение активных actions зависимости по execute_order."""
        actions = (
            self.action_model.select()
            .where(
                (self.action_model.dependency == dependency)
                & (self.action_model.is_active == True)
            )
            .order_by(self.action_model.execute_order, self.action_model.id)
        )
        return [
            self.execute_single_action(action, trigger_event, triggered_by)
            for action in actions
        ]

    def execute_single_action(
        self,
        action: DependencyAction,
        trigger_event: str,
        triggered_by: User,
    ) -> Dict[str, Any]:
        """Выполнить или запланировать одно действие."""
        if action.delay_minutes > 0:
            scheduled_for = datetime.now() + timedelta(minutes=action.delay_minutes)
            self.scheduled_model.create(
                project=action.dependency.project,
                task=action.dependency.target_task,
                action_type='delayed_notification',
                scheduled_for=scheduled_for,
                payload=json.dumps(
                    {
                        'action_id': action.id,
                        'trigger_event': trigger_event,
                        'triggered_by': triggered_by.username,
                    }
                ),
                dependency_action=action,
            )
            return {
                'action_id': action.id,
                'type': action.action_type.code,
                'status': 'scheduled',
                'scheduled_for': scheduled_for.isoformat(),
            }

        code = action.action_type.code
        if code.startswith('notify_'):
            target_user = self._resolve_notification_user(action)
            if target_user:
                self.send_task_notification(
                    user=target_user,
                    notification_type=code,
                    task_data={
                        'task_id': action.dependency.target_task_id,
                        'task_name': action.dependency.target_task.name,
                        'source_task_id': action.dependency.source_task_id,
                        'source_task_name': action.dependency.source_task.name,
                        'message_template': action.message_template,
                    },
                )
            return {
                'action_id': action.id,
                'type': code,
                'status': 'executed',
                'target_user': target_user.username if target_user else None,
            }

        if code == 'change_status' and action.target_status:
            target_task = action.dependency.target_task
            old_status = target_task.status.name
            target_task.status = action.target_status
            target_task.save()
            self.event_model.log(
                task=target_task,
                user=triggered_by,
                event_type='status_changed_by_dependency',
                old_value=old_status,
                new_value=action.target_status.name,
                metadata={'dependency_action_id': action.id},
            )
            return {
                'action_id': action.id,
                'type': code,
                'status': 'executed',
                'target_status': action.target_status.name,
            }

        return {'action_id': action.id, 'type': code, 'status': 'skipped'}

    def _resolve_notification_user(self, action: DependencyAction) -> Optional[User]:
        """Получатель уведомления для notify_* actions."""
        code = action.action_type.code
        if code == 'notify_assignee':
            return action.dependency.target_task.assignee
        if code == 'notify_creator':
            return action.dependency.source_task.creator
        if code == 'notify_custom':
            return action.target_user
        return None

    # ------------------- Уведомления -------------------

    def send_task_notification(
        self, user: User, notification_type: str, task_data: Dict[str, Any]
    ) -> bool:
        """Зарезервировано под будущие каналы (email / in-app)."""
        return False

    # ------------------- Получение данных -------------------

    def get_project_tasks(
        self,
        project: Project,
        status_name: Optional[str] = None,
        assignee_id: Optional[int] = None,
        creator_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Task]:
        """
        Получение задач проекта с фильтрацией
        """
        conditions = [self.task_model.project == project]

        if status_name:
            status = self.get_status_by_name(status_name)
            if status:
                conditions.append(self.task_model.status == status)

        if assignee_id:
            conditions.append(self.task_model.assignee_id == assignee_id)

        if creator_id:
            conditions.append(self.task_model.creator_id == creator_id)

        return list(
            self.task_model.select()
            .where(*conditions)
            .order_by(
                self.task_model.priority.desc(),
                self.task_model.deadline,
                self.task_model.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

    def get_task_by_id(self, project: Project, task_id: int) -> Optional[Task]:
        """
        Получение задачи по ID
        """
        try:
            return self.task_model.get(
                (self.task_model.project == project) & (self.task_model.id == task_id)
            )
        except self.task_model.DoesNotExist:
            return None

    def get_project_graph(self, project: Project) -> Dict[str, Any]:
        """Получение полного графа проекта для ReactFlow"""
        tasks = self.get_project_tasks(project, limit=1000)
        dependencies = list(
            self.dependency_model.select().where(
                self.dependency_model.project == project
            )
        )

        nodes = []
        for task in tasks:
            readiness = self.get_readiness_info(task)

            nodes.append(
                {
                    'id': str(task.id),
                    'type': 'taskNode',
                    'data': {
                        'id': task.id,
                        'name': task.name,
                        'status': task.status.name,
                        'status_color': task.status.color,
                        'assignee': task.assignee.username if task.assignee else None,
                        'creator': task.creator.username,
                        'priority': task.priority,
                        'deadline': task.deadline.isoformat()
                        if task.deadline
                        else None,
                        'is_ready': readiness['is_ready'],
                        'blocking_task_ids': readiness['blocking_task_ids'],
                        'blocked_reason': readiness['blocked_reason'],
                    },
                    'position': {'x': task.position_x, 'y': task.position_y},
                }
            )

        edges = []
        for dep in dependencies:
            edges.append(
                {
                    'id': f'dep-{dep.id}',
                    'source': str(dep.source_task_id),
                    'target': str(dep.target_task_id),
                    'type': dep.dependency_type,
                    'data': {
                        'dependency_id': dep.id,
                        'description': dep.description,
                        'actions': self._dependency_actions_payload(dep),
                    },
                    'animated': self.is_blocking_dependency_type(dep.dependency_type),
                    'label': dep.edge_label
                    or self.DEPENDENCY_TYPES.get(dep.dependency_type, {}).get('name'),
                }
            )

        viewport = {'x': 0, 'y': 0, 'zoom': 1}
        if project.graph_data:
            try:
                viewport = json.loads(project.graph_data).get('viewport', viewport)
            except (TypeError, json.JSONDecodeError):
                pass

        return {'nodes': nodes, 'edges': edges, 'viewport': viewport}

    def _dependency_actions_payload(
        self, dependency: TaskDependency
    ) -> List[Dict[str, Any]]:
        """Сериализация активных actions для ребра графа."""
        actions = (
            self.action_model.select()
            .where(
                (self.action_model.dependency == dependency)
                & (self.action_model.is_active == True)
            )
            .order_by(self.action_model.execute_order, self.action_model.id)
        )
        return [
            {
                'id': action.id,
                'action_type_code': action.action_type.code,
                'target_user_username': action.target_user.username
                if action.target_user
                else None,
                'target_status': action.target_status.name
                if action.target_status
                else None,
                'message_template': action.message_template,
                'delay_minutes': action.delay_minutes,
                'execute_order': action.execute_order,
            }
            for action in actions
        ]

    # ------------------- Отложенные действия -------------------

    def process_scheduled_actions(self) -> List[Dict[str, Any]]:
        """
        Обработка запланированных действий (вызывается воркером раз в минуту)
        """
        processed = []
        now = datetime.now()

        actions = (
            self.scheduled_model.select()
            .where(
                (self.scheduled_model.scheduled_for <= now)
                & (self.scheduled_model.status == 'pending')
            )
            .limit(100)
        )

        for scheduled in actions:
            scheduled.status = 'processing'
            scheduled.save()

            try:
                if scheduled.action_type == 'deadline_approaching':
                    task = scheduled.task
                    payload = json.loads(scheduled.payload) if scheduled.payload else {}
                    hours_left = payload.get('hours_before', 24)

                    if task.assignee:
                        self.send_task_notification(
                            user=task.assignee,
                            notification_type='deadline_approaching',
                            task_data={
                                'task_id': task.id,
                                'task_name': task.name,
                                'project_name': task.project.name,
                                'deadline': task.deadline.isoformat()
                                if task.deadline
                                else None,
                                'hours_left': hours_left,
                            },
                        )
                    scheduled.status = 'completed'
                else:
                    scheduled.status = 'completed'

                scheduled.executed_at = now
                scheduled.save()
                processed.append(
                    {
                        'id': scheduled.id,
                        'type': scheduled.action_type,
                        'status': 'completed',
                    }
                )

            except Exception as e:
                scheduled.status = 'failed'
                scheduled.save()
                processed.append(
                    {
                        'id': scheduled.id,
                        'type': scheduled.action_type,
                        'status': 'failed',
                        'error': str(e),
                    }
                )

        return processed

    # ------------------- Статистика -------------------

    def get_task_stats(self, project: Project) -> Dict[str, Any]:
        """
        Статистика по задачам проекта
        """
        total = (
            self.task_model.select().where(self.task_model.project == project).count()
        )

        by_status = {}
        for status in self.status_model.select():
            count = (
                self.task_model.select()
                .where(
                    (self.task_model.project == project)
                    & (self.task_model.status == status)
                )
                .count()
            )
            if count > 0:
                by_status[status.name] = {
                    'count': count,
                    'display_name': status.display_name,
                    'color': status.color,
                }

        by_assignee = {}
        assignees = (
            self.task_model.select(
                self.task_model.assignee, fn.COUNT(self.task_model.id).alias('count')
            )
            .where(
                (self.task_model.project == project)
                & (self.task_model.assignee.is_null(False))
            )
            .group_by(self.task_model.assignee)
        )

        for row in assignees:
            if row.assignee:
                by_assignee[row.assignee.username] = row.count

        overdue = (
            self.task_model.select()
            .where(
                (self.task_model.project == project)
                & (self.task_model.deadline < datetime.now())
                & (
                    self.task_model.status_id.in_(
                        self.status_model.select(self.status_model.id).where(
                            self.status_model.is_final == False
                        )
                    )
                )
            )
            .count()
        )

        return {
            'total': total,
            'by_status': by_status,
            'by_assignee': by_assignee,
            'overdue': overdue,
        }

    def get_user_task_stats(
        self, user: User, project: Optional[Project] = None
    ) -> Dict[str, Any]:
        """
        Статистика по задачам пользователя
        """
        base_conditions = []
        if project:
            base_conditions.append(self.task_model.project == project)

        assigned_query = self.task_model.select().where(
            self.task_model.assignee == user, *base_conditions
        )
        assigned = assigned_query.count()

        created_query = self.task_model.select().where(
            self.task_model.creator == user, *base_conditions
        )
        created = created_query.count()

        completed_query = self.task_model.select().where(
            (self.task_model.assignee == user)
            & (
                self.task_model.status_id.in_(
                    self.status_model.select(self.status_model.id).where(
                        self.status_model.is_final == True
                    )
                )
            ),
            *base_conditions,
        )
        completed = completed_query.count()

        in_progress_status = self.get_status_by_name('in_progress')
        in_progress_query = self.task_model.select().where(
            (self.task_model.assignee == user)
            & (self.task_model.status == in_progress_status),
            *base_conditions,
        )
        in_progress = in_progress_query.count()

        overdue_query = self.task_model.select().where(
            (self.task_model.assignee == user)
            & (self.task_model.deadline < datetime.now())
            & (
                self.task_model.status_id.not_in(
                    self.status_model.select(self.status_model.id).where(
                        self.status_model.is_final == True
                    )
                )
            ),
            *base_conditions,
        )
        overdue = overdue_query.count()

        return {
            'assigned': assigned,
            'created': created,
            'completed': completed,
            'in_progress': in_progress,
            'overdue': overdue,
            'completion_rate': round(completed / assigned * 100, 1)
            if assigned > 0
            else 0,
        }
