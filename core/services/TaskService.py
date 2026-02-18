import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import asyncio

from peewee import *
from peewee import logger

from ..db.models.task import (
    Task, TaskStatus, TaskDependency, DependencyAction,
    DependencyActionType, TaskEvent, ScheduledAction
)
from ..db.models.project import Project, ProjectMember
from ..db.models.user import User
from .ProjectService import ProjectService
from .TeamService import TeamService
from .UserService import UserService


class TaskService:
    """Сервис для работы с задачами и графом зависимостей"""

    def __init__(self):
        self.task_model = Task
        self.status_model = TaskStatus
        self.dependency_model = TaskDependency
        self.action_type_model = DependencyActionType
        self.action_model = DependencyAction
        self.event_model = TaskEvent
        self.scheduled_model = ScheduledAction

    # ------------------- Инициализация -------------------

    def ensure_default_statuses(self) -> Dict[str, TaskStatus]:
        """Создание стандартных статусов задач"""
        statuses = {}
        for status_data in self.status_model.get_default_statuses():
            status, created = self.status_model.get_or_create(
                name=status_data['name'],
                defaults=status_data
            )
            statuses[status.name] = status
        return statuses

    def ensure_default_action_types(self) -> Dict[str, DependencyActionType]:
        """Создание стандартных типов действий"""
        action_types = {}
        for type_data in self.action_type_model.get_default_types():
            action_type, created = self.action_type_model.get_or_create(
                code=type_data['code'],
                defaults=type_data
            )
            action_types[type_data['code']] = action_type
        return action_types

    def get_status_by_name(self, name: str) -> Optional[TaskStatus]:
        """Получение статуса по имени"""
        try:
            return self.status_model.get(self.status_model.name == name)
        except self.status_model.DoesNotExist:
            return None

    def get_action_type_by_code(self, code: str) -> Optional[DependencyActionType]:
        """Получение типа действия по коду"""
        try:
            return self.action_type_model.get(self.action_type_model.code == code)
        except self.action_type_model.DoesNotExist:
            return None

    # ------------------- Создание задач -------------------

    def create_task(self,
                   project: Project,
                   name: str,
                   creator: User,
                   description: Optional[str] = None,
                   assignee: Optional[User] = None,
                   deadline: Optional[datetime] = None,
                   priority: int = 0,
                   position_x: float = 0,
                   position_y: float = 0,
                   metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Создание новой задачи
        """
        from .ProjectService import ProjectService
        project_service = ProjectService()

        # Проверяем права на создание задач
        if not project_service.can_create_tasks(creator, project):
            raise PermissionError("You don't have permission to create tasks in this project")

        # Получаем статус по умолчанию (todo)
        todo_status = self.get_status_by_name('todo')
        if not todo_status:
            statuses = self.ensure_default_statuses()
            todo_status = statuses['todo']

        # Проверяем, что исполнитель - участник проекта
        if assignee:
            if not project_service.is_member(assignee, project):
                raise ValueError("Assignee must be a member of the project")

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
            metadata=json.dumps(metadata) if metadata else None
        )

        # Обновляем счетчик задач в проекте
        project.tasks_count = self.task_model.select().where(
            (self.task_model.project == project) &
            (self.task_model.status_id.in_(
                self.status_model.select(self.status_model.id).where(
                    self.status_model.is_final == False
                )
            ))
        ).count()
        project.save()

        # Логируем событие
        self.event_model.log(
            task=task,
            user=creator,
            event_type='created'
        )

        # Планируем уведомления о дедлайне
        if deadline:
            self.scheduled_model.schedule_deadline_notification(task, 24)
            self.scheduled_model.schedule_deadline_notification(task, 1)

        return {
            'task': task,
            'status': task.status
        }

    # ------------------- Обновление задач -------------------

    def update_task(self,
                   task: Task,
                   updated_by: User,
                   name: Optional[str] = None,
                   description: Optional[str] = None,
                   assignee: Optional[User] = None,
                   deadline: Optional[datetime] = None,
                   priority: Optional[int] = None,
                   position_x: Optional[float] = None,
                   position_y: Optional[float] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> Task:
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
                    raise ValueError("Assignee must be a member of the project")

            old = task.assignee
            task.assignee = assignee
            changes.append(('assignee', old.username if old else None,
                          assignee.username if assignee else None))

        if deadline is not None:
            old = task.deadline
            task.deadline = deadline
            changes.append(('deadline', old, deadline))

            # Перепланируем уведомления
            if deadline:
                # Удаляем старые
                self.scheduled_model.delete().where(
                    (self.scheduled_model.task == task) &
                    (self.scheduled_model.action_type == 'deadline_approaching')
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
                metadata={'field': change[0]}
            )

        return task

    def change_task_status(self,
                           task: Task,
                           new_status_name: str,
                           changed_by: User) -> Dict[str, Any]:
        """
        Изменение статуса задачи
        """
        from .ProjectService import ProjectService
        project_service = ProjectService()

        # Проверяем права
        if not project_service.can_edit_task(changed_by, task):
            raise PermissionError("You don't have permission to change this task status")

        new_status = self.get_status_by_name(new_status_name)
        if not new_status:
            raise ValueError(f"Status '{new_status_name}' not found")

        old_status = task.status

        # Если статус не меняется - просто возвращаем успех
        if old_status.id == new_status.id:
            return {
                'task': task,
                'status_changed': False,
                'old_status': old_status,
                'new_status': new_status,
                'actions_executed': []
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
                new_value=new_status.name
            )
        except Exception as e:
            logger.error(f"Error logging status change: {e}")

        result = {
            'task': task,
            'status_changed': True,
            'old_status': old_status,
            'new_status': new_status,
            'actions_executed': []
        }

        # Если задача выполнена - обрабатываем зависимости
        if new_status.is_final and not old_status.is_final:
            try:
                actions = self.handle_task_completed(task, changed_by)
                result['actions_executed'] = actions
            except Exception as e:
                logger.error(f"Error handling task completion: {e}")

        return result

    # ------------------- Работа с зависимостями -------------------

    def create_dependency(self,
                         source_task: Task,
                         target_task: Task,
                         created_by: User,
                         dependency_type: str = 'simple',
                         description: Optional[str] = None) -> TaskDependency:
        """
        Создание зависимости между задачами
        """
        from .ProjectService import ProjectService
        project_service = ProjectService()

        # Проверяем права на создание зависимости
        if not project_service.can_create_dependencies(created_by, source_task):
            raise PermissionError("You don't have permission to create dependencies for this task")

        # Проверяем, что задачи из одного проекта
        if source_task.project_id != target_task.project_id:
            raise ValueError("Tasks must be in the same project")

        # Проверяем на циклическую зависимость
        if self.would_create_cycle(source_task, target_task):
            raise ValueError("This dependency would create a cycle")

        # Проверяем, не существует ли уже такая зависимость
        existing = self.dependency_model.select().where(
            (self.dependency_model.project == source_task.project) &
            (self.dependency_model.source_task == source_task) &
            (self.dependency_model.target_task == target_task)
        ).first()

        if existing:
            raise ValueError("Dependency already exists")

        # Создаем зависимость
        dependency = self.dependency_model.create(
            project=source_task.project,
            source_task=source_task,
            target_task=target_task,
            dependency_type=dependency_type,
            description=description,
            created_by=created_by
        )

        # Логируем событие
        self.event_model.log(
            task=source_task,
            user=created_by,
            event_type='dependency_added',
            metadata={
                'dependency_id': dependency.id,
                'target_task_id': target_task.id,
                'target_task_name': target_task.name
            }
        )

        # Если исходная задача уже выполнена - выполняем действия сразу
        if source_task.status.is_final:
            self.execute_dependency_actions(dependency, 'task_completed', created_by)

        return dependency

    def delete_dependency(self,
                         dependency: TaskDependency,
                         deleted_by: User) -> bool:
        """
        Удаление зависимости
        """
        from .ProjectService import ProjectService
        project_service = ProjectService()

        # Проверяем права (только менеджеры/владельцы могут удалять зависимости)
        role = project_service.get_user_role_in_project(deleted_by, dependency.project)
        if not role or not role.can_delete_dependencies:
            raise PermissionError("You don't have permission to delete dependencies")

        # Логируем событие
        self.event_model.log(
            task=dependency.source_task,
            user=deleted_by,
            event_type='dependency_removed',
            metadata={
                'target_task_id': dependency.target_task_id,
                'target_task_name': dependency.target_task.name
            }
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
                (self.dependency_model.project == source.project) &
                (self.dependency_model.source_task_id == task_id)
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
        incoming = list(self.dependency_model.select().where(
            (self.dependency_model.project == task.project) &
            (self.dependency_model.target_task == task)
        ))

        outgoing = list(self.dependency_model.select().where(
            (self.dependency_model.project == task.project) &
            (self.dependency_model.source_task == task)
        ))

        return {
            'incoming': incoming,
            'outgoing': outgoing
        }

    # ------------------- Действия на зависимостях -------------------

    def add_dependency_action(self,
                            dependency: TaskDependency,
                            action_type_code: str,
                            created_by: User,
                            target_user: Optional[User] = None,
                            target_status_name: Optional[str] = None,
                            message_template: Optional[str] = None,
                            delay_minutes: int = 0,
                            execute_order: int = 0) -> DependencyAction:
        """
        Добавление действия к зависимости
        """
        from .ProjectService import ProjectService
        project_service = ProjectService()

        # Проверяем права (только менеджеры/владельцы могут добавлять действия)
        role = project_service.get_user_role_in_project(created_by, dependency.project)
        if not role or not role.can_edit_any_task:
            raise PermissionError("You don't have permission to add dependency actions")

        action_type = self.get_action_type_by_code(action_type_code)
        if not action_type:
            raise ValueError(f"Action type '{action_type_code}' not found")

        # Валидация в зависимости от типа действия
        if action_type.requires_target_user and not target_user:
            raise ValueError(f"Action type '{action_type_code}' requires target_user")

        if action_type.requires_template and not message_template:
            # Для notify_assignee используем шаблон по умолчанию
            if action_type_code == 'notify_assignee':
                message_template = f"Задача {dependency.target_task.name} готова к выполнению!"
            else:
                raise ValueError(f"Action type '{action_type_code}' requires message_template")

        target_status = None
        if action_type_code == 'change_status' and target_status_name:
            target_status = self.get_status_by_name(target_status_name)
            if not target_status:
                raise ValueError(f"Status '{target_status_name}' not found")

        action = self.action_model.create(
            dependency=dependency,
            action_type=action_type,
            target_user=target_user,
            target_status=target_status,
            message_template=message_template,
            delay_minutes=delay_minutes,
            execute_order=execute_order
        )

        return action

    def remove_dependency_action(self,
                               action: DependencyAction,
                               removed_by: User) -> bool:
        """
        Удаление действия с зависимости
        """
        from .ProjectService import ProjectService
        project_service = ProjectService()

        role = project_service.get_user_role_in_project(removed_by, action.dependency.project)
        if not role or not role.can_edit_any_task:
            raise PermissionError("You don't have permission to remove dependency actions")

        action.delete_instance()
        return True

    # ------------------- Обработка событий -------------------

    def handle_task_completed(self, task: Task, completed_by: User) -> List[Dict[str, Any]]:
        """
        Обработка завершения задачи - выполнение действий на исходящих ребрах
        """
        executed_actions = []

        # Находим все исходящие зависимости
        outgoing = self.dependency_model.select().where(
            (self.dependency_model.project == task.project) &
            (self.dependency_model.source_task == task)
        )

        for dependency in outgoing:
            # Выполняем действия
            actions = self.execute_dependency_actions(dependency, 'task_completed', completed_by)
            executed_actions.extend(actions)

            # Проверяем готовность целевой задачи
            self.check_task_readiness(dependency.target_task)

        return executed_actions

    def execute_dependency_actions(self,
                                 dependency: TaskDependency,
                                 trigger_event: str,
                                 triggered_by: User) -> List[Dict[str, Any]]:
        """
        Выполнение всех действий на зависимости
        """
        executed = []

        # Получаем активные действия
        actions = self.action_model.select().where(
            (self.action_model.dependency == dependency) &
            (self.action_model.is_active == True)
        ).order_by(self.action_model.execute_order)

        for action in actions:
            if action.delay_minutes > 0:
                # Отложенное действие
                scheduled = self.scheduled_model.create(
                    project=dependency.project,
                    task=dependency.target_task,
                    action_type='delayed_notification',
                    scheduled_for=datetime.now() + timedelta(minutes=action.delay_minutes),
                    payload=json.dumps({
                        'action_id': action.id,
                        'trigger_event': trigger_event,
                        'triggered_by': triggered_by.username
                    }),
                    dependency_action=action
                )
                executed.append({
                    'action_id': action.id,
                    'type': action.action_type.code,
                    'status': 'scheduled',
                    'scheduled_for': scheduled.scheduled_for
                })
            else:
                # Немедленное выполнение
                result = self.execute_single_action(action, trigger_event, triggered_by)
                executed.append(result)

        return executed

    def execute_single_action(self,
                            action: DependencyAction,
                            trigger_event: str,
                            triggered_by: User) -> Dict[str, Any]:
        """
        Выполнение одного действия
        """
        result = {
            'action_id': action.id,
            'type': action.action_type.code,
            'status': 'executed',
            'timestamp': datetime.now()
        }

        try:
            if action.action_type.code == 'notify_assignee':
                # Уведомить исполнителя целевой задачи
                target_task = action.dependency.target_task
                if target_task.assignee:
                    self.send_task_notification(
                        user=target_task.assignee,
                        notification_type='task_ready',
                        task_data={
                            'task_id': target_task.id,
                            'task_name': target_task.name,
                            'project_name': target_task.project.name,
                            'message': action.message_template or f"Задача готова к выполнению: {target_task.name}"
                        }
                    )
                    result['target_user'] = target_task.assignee.username

            elif action.action_type.code == 'notify_creator':
                # Уведомить создателя исходной задачи
                source_task = action.dependency.source_task
                self.send_task_notification(
                    user=source_task.creator,
                    notification_type='task_completed',
                    task_data={
                        'task_id': source_task.id,
                        'task_name': source_task.name,
                        'project_name': source_task.project.name,
                        'message': action.message_template or f"Задача выполнена: {source_task.name}"
                    }
                )
                result['target_user'] = source_task.creator.username

            elif action.action_type.code == 'notify_custom' and action.target_user:
                # Уведомить конкретного пользователя
                self.send_task_notification(
                    user=action.target_user,
                    notification_type='custom',
                    task_data={
                        'task_id': action.dependency.target_task.id,
                        'task_name': action.dependency.target_task.name,
                        'project_name': action.dependency.project.name,
                        'message': action.message_template or "Уведомление о задаче"
                    }
                )
                result['target_user'] = action.target_user.username

            elif action.action_type.code == 'change_status' and action.target_status:
                # Изменить статус целевой задачи
                target_task = action.dependency.target_task
                old_status = target_task.status
                target_task.status = action.target_status
                target_task.save()

                self.event_model.log(
                    task=target_task,
                    user=triggered_by,
                    event_type='status_changed',
                    old_value=old_status.name,
                    new_value=action.target_status.name,
                    metadata={'triggered_by_action': action.id}
                )
                result['new_status'] = action.target_status.name

        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)

        return result

    def check_task_readiness(self, task: Task) -> bool:
        """
        Проверка, готова ли задача к выполнению

        Задача готова ТОЛЬКО если:
        1. Статус задачи 'todo' (не in_progress, не completed, не blocked, не review)
        2. У задачи нет входящих зависимостей, ИЛИ
        3. Все задачи, от которых она зависит, выполнены (status = 'completed')
        """
        # ========== 1. ПРОВЕРКА СТАТУСА ==========
        # Только задачи со статусом 'todo' могут быть готовы
        if task.status.name != 'todo':
            return False

        # ========== 2. ПРОВЕРКА ЗАВИСИМОСТЕЙ ==========
        # Получаем все входящие зависимости (задачи, от которых зависит текущая)
        incoming = list(self.dependency_model.select().where(
            (self.dependency_model.project == task.project) &
            (self.dependency_model.target_task == task)
        ))

        # Если нет зависимостей - задача готова
        if not incoming:
            return True

        # Проверяем каждую зависимость
        for dep in incoming:
            source_task = dep.source_task

            # Если хотя бы одна исходная задача не выполнена - задача НЕ готова
            if source_task.status.name != 'completed':
                return False

        # Все зависимости выполнены - задача готова
        return True

    def check_downstream_tasks(self, task: Task):
        """
        Проверка готовности всех задач, которые зависят от данной
        """
        outgoing = self.dependency_model.select().where(
            (self.dependency_model.project == task.project) &
            (self.dependency_model.source_task == task)
        )

        for dep in outgoing:
            self.check_task_readiness(dep.target_task)

    # ------------------- Уведомления -------------------

    def send_task_notification(self,
                              user: User,
                              notification_type: str,
                              task_data: Dict[str, Any]) -> bool:
        """
        Отправка уведомления пользователю
        """
        # Проверяем настройки уведомлений
        settings = user.notification_settings_dict

        if notification_type == 'task_ready' and not settings.get('dependency_ready', True):
            return False
        if notification_type == 'task_completed' and not settings.get('task_completed', True):
            return False
        if notification_type == 'task_assigned' and not settings.get('task_assigned', True):
            return False

        # Отправляем через UserService
        from .UserService import UserService
        user_service = UserService()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            asyncio.create_task(
                user_service.send_telegram_notification(
                    user_id=user.id,
                    notification_type=notification_type,
                    data=task_data
                )
            )
            return True
        else:
            return loop.run_until_complete(
                user_service.send_telegram_notification(
                    user_id=user.id,
                    notification_type=notification_type,
                    data=task_data
                )
            )

    # ------------------- Получение данных -------------------

    def get_project_tasks(self,
                         project: Project,
                         status_name: Optional[str] = None,
                         assignee_id: Optional[int] = None,
                         creator_id: Optional[int] = None,
                         limit: int = 100,
                         offset: int = 0) -> List[Task]:
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
                self.task_model.created_at.desc()
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
                (self.task_model.project == project) &
                (self.task_model.id == task_id)
            )
        except self.task_model.DoesNotExist:
            return None

    def get_project_graph(self, project: Project) -> Dict[str, Any]:
        """Получение полного графа проекта для ReactFlow"""
        tasks = self.get_project_tasks(project, limit=1000)
        dependencies = list(self.dependency_model.select().where(
            self.dependency_model.project == project
        ))

        nodes = []
        for task in tasks:
            # ВАЖНО: вычисляем is_ready для каждой задачи
            is_ready = self.check_task_readiness(task)

            nodes.append({
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
                    'deadline': task.deadline.isoformat() if task.deadline else None,
                    'is_ready': is_ready,  # <-- ИСПОЛЬЗУЕМ МЕТОД!
                },
                'position': {
                    'x': task.position_x,
                    'y': task.position_y
                }
            })

        edges = []
        for dep in dependencies:
            actions = list(dep.actions.where(DependencyAction.is_active == True))
            edges.append({
                'id': f"e{dep.source_task_id}-{dep.target_task_id}",
                'source': str(dep.source_task_id),
                'target': str(dep.target_task_id),
                'type': dep.dependency_type,
                'data': {
                    'description': dep.description,
                    'actions': [
                        {
                            'type': action.action_type.code,
                            'delay': action.delay_minutes
                        } for action in actions
                    ]
                },
                'animated': dep.dependency_type != 'simple'
            })

        return {
            'nodes': nodes,
            'edges': edges,
            'viewport': {
                'x': 0,
                'y': 0,
                'zoom': 1
            }
        }

    # ------------------- Отложенные действия -------------------

    def process_scheduled_actions(self) -> List[Dict[str, Any]]:
        """
        Обработка запланированных действий (вызывается воркером раз в минуту)
        """
        processed = []
        now = datetime.now()

        actions = self.scheduled_model.select().where(
            (self.scheduled_model.scheduled_for <= now) &
            (self.scheduled_model.status == 'pending')
        ).limit(100)

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
                                'deadline': task.deadline.isoformat() if task.deadline else None,
                                'hours_left': hours_left
                            }
                        )
                    scheduled.status = 'completed'

                elif scheduled.action_type == 'delayed_notification' and scheduled.dependency_action:
                    result = self.execute_single_action(
                        scheduled.dependency_action,
                        'delayed',
                        scheduled.dependency_action.dependency.created_by
                    )
                    scheduled.status = 'completed'
                    scheduled.payload = json.dumps({
                        **json.loads(scheduled.payload or '{}'),
                        'result': result
                    })

                scheduled.executed_at = now
                scheduled.save()
                processed.append({
                    'id': scheduled.id,
                    'type': scheduled.action_type,
                    'status': 'completed'
                })

            except Exception as e:
                scheduled.status = 'failed'
                scheduled.save()
                processed.append({
                    'id': scheduled.id,
                    'type': scheduled.action_type,
                    'status': 'failed',
                    'error': str(e)
                })

        return processed

    # ------------------- Статистика -------------------

    def get_task_stats(self, project: Project) -> Dict[str, Any]:
        """
        Статистика по задачам проекта
        """
        total = self.task_model.select().where(
            self.task_model.project == project
        ).count()

        by_status = {}
        for status in self.status_model.select():
            count = self.task_model.select().where(
                (self.task_model.project == project) &
                (self.task_model.status == status)
            ).count()
            if count > 0:
                by_status[status.name] = {
                    'count': count,
                    'display_name': status.display_name,
                    'color': status.color
                }

        by_assignee = {}
        assignees = self.task_model.select(
            self.task_model.assignee,
            fn.COUNT(self.task_model.id).alias('count')
        ).where(
            (self.task_model.project == project) &
            (self.task_model.assignee.is_null(False))
        ).group_by(self.task_model.assignee)

        for row in assignees:
            if row.assignee:
                by_assignee[row.assignee.username] = row.count

        overdue = self.task_model.select().where(
            (self.task_model.project == project) &
            (self.task_model.deadline < datetime.now()) &
            (self.task_model.status_id.in_(
                self.status_model.select(self.status_model.id).where(
                    self.status_model.is_final == False
                )
            ))
        ).count()

        return {
            'total': total,
            'by_status': by_status,
            'by_assignee': by_assignee,
            'overdue': overdue
        }

    def get_user_task_stats(self, user: User, project: Optional[Project] = None) -> Dict[str, Any]:
        """
        Статистика по задачам пользователя
        """
        base_conditions = []
        if project:
            base_conditions.append(self.task_model.project == project)

        assigned_query = self.task_model.select().where(
            self.task_model.assignee == user,
            *base_conditions
        )
        assigned = assigned_query.count()

        created_query = self.task_model.select().where(
            self.task_model.creator == user,
            *base_conditions
        )
        created = created_query.count()

        completed_query = self.task_model.select().where(
            (self.task_model.assignee == user) &
            (self.task_model.status_id.in_(
                self.status_model.select(self.status_model.id).where(
                    self.status_model.is_final == True
                )
            )),
            *base_conditions
        )
        completed = completed_query.count()

        in_progress_status = self.get_status_by_name('in_progress')
        in_progress_query = self.task_model.select().where(
            (self.task_model.assignee == user) &
            (self.task_model.status == in_progress_status),
            *base_conditions
        )
        in_progress = in_progress_query.count()

        overdue_query = self.task_model.select().where(
            (self.task_model.assignee == user) &
            (self.task_model.deadline < datetime.now()) &
            (self.task_model.status_id.not_in(
                self.status_model.select(self.status_model.id).where(
                    self.status_model.is_final == True
                )
            )),
            *base_conditions
        )
        overdue = overdue_query.count()

        return {
            'assigned': assigned,
            'created': created,
            'completed': completed,
            'in_progress': in_progress,
            'overdue': overdue,
            'completion_rate': round(completed / assigned * 100, 1) if assigned > 0 else 0
        }