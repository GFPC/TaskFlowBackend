import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from peewee import *
from peewee import logger

from ..db.models.project import Project, ProjectMember
from ..db.models.task import (
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

    def __init__(self):
        self.task_model = Task
        self.status_model = TaskStatus
        self.dependency_model = TaskDependency
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

        # Проверяем права
        if not project_service.can_edit_task(changed_by, task):
            raise PermissionError(
                "You don't have permission to change this task status"
            )

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
        }

        if new_status.is_final and not old_status.is_final:
            try:
                self._refresh_downstream_readiness(task)
            except Exception as e:
                logger.error(f'Error handling task completion: {e}')

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

        # Проверяем на циклическую зависимость
        if self.would_create_cycle(source_task, target_task):
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

    def delete_dependency(self, dependency: TaskDependency, deleted_by: User) -> bool:
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
        2. У задачи нет входящих зависимостей, ИЛИ
        3. Все задачи, от которых она зависит, выполнены (status = 'completed')
        """
        # ========== 1. ПРОВЕРКА СТАТУСА ==========
        # Только задачи со статусом 'todo' могут быть готовы
        if task.status.name != 'todo':
            return False

        # ========== 2. ПРОВЕРКА ЗАВИСИМОСТЕЙ ==========
        # Получаем все входящие зависимости (задачи, от которых зависит текущая)
        incoming = list(
            self.dependency_model.select().where(
                (self.dependency_model.project == task.project)
                & (self.dependency_model.target_task == task)
            )
        )

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
            (self.dependency_model.project == task.project)
            & (self.dependency_model.source_task == task)
        )

        for dep in outgoing:
            self.check_task_readiness(dep.target_task)

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
            # ВАЖНО: вычисляем is_ready для каждой задачи
            is_ready = self.check_task_readiness(task)

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
                        'is_ready': is_ready,  # <-- ИСПОЛЬЗУЕМ МЕТОД!
                    },
                    'position': {'x': task.position_x, 'y': task.position_y},
                }
            )

        edges = []
        for dep in dependencies:
            edges.append(
                {
                    'id': f'e{dep.source_task_id}-{dep.target_task_id}',
                    'source': str(dep.source_task_id),
                    'target': str(dep.target_task_id),
                    'type': dep.dependency_type,
                    'data': {'description': dep.description},
                    'animated': dep.dependency_type != 'simple',
                }
            )

        return {'nodes': nodes, 'edges': edges, 'viewport': {'x': 0, 'y': 0, 'zoom': 1}}

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
