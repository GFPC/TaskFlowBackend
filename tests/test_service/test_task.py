import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from peewee import SqliteDatabase
from core.db.models.user import User, UserRole
from core.db.models.team import Team, TeamMember, TeamMemberRole
from core.db.models.project import Project, ProjectRole, ProjectMember, ProjectInvitation
from core.db.models.task import (
    Task, TaskStatus, TaskDependency, DependencyAction,
    DependencyActionType, TaskEvent, ScheduledAction
)
from core.services.TeamService import TeamService
from core.services.ProjectService import ProjectService
from core.services.TaskService import TaskService


# ------------------- FIXTURES -------------------

@pytest.fixture(scope='function')
def test_db():
    """Тестовая БД в памяти со всеми таблицами"""
    test_db = SqliteDatabase(':memory:')

    models = [
        User, UserRole,
        Team, TeamMember, TeamMemberRole,
        Project, ProjectRole, ProjectMember, ProjectInvitation,
        TaskStatus, DependencyActionType,
        Task, TaskDependency, DependencyAction, TaskEvent, ScheduledAction
    ]

    test_db.bind(models, bind_refs=False, bind_backrefs=False)
    test_db.connect()
    test_db.create_tables(models)

    yield test_db

    test_db.drop_tables(models)
    test_db.close()


@pytest.fixture
def team_service(test_db):
    service = TeamService()
    service.ensure_default_roles()
    return service


@pytest.fixture
def project_service(test_db):
    service = ProjectService()
    service.ensure_default_roles()
    return service


@pytest.fixture
def task_service(test_db):
    service = TaskService()
    service.ensure_default_statuses()
    service.ensure_default_action_types()
    return service


@pytest.fixture
def user_role(test_db):
    role, _ = UserRole.get_or_create(
        name='Работник',
        defaults={'description': 'Test', 'priority': 1}
    )
    return role


@pytest.fixture
def test_user(test_db, user_role):
    return User.create(
        first_name='Иван',
        last_name='Иванов',
        username='ivanov',
        password_hash='hash',
        email='ivanov@test.com',
        role=user_role,
        is_active=True,
        tg_verified=True,
        tg_chat_id=123456
    )


@pytest.fixture
def second_user(test_db, user_role):
    return User.create(
        first_name='Петр',
        last_name='Петров',
        username='petrov',
        password_hash='hash',
        email='petrov@test.com',
        role=user_role,
        is_active=True,
        tg_verified=True,
        tg_chat_id=123457
    )


@pytest.fixture
def team_owner(test_db, team_service, test_user):
    return test_user


@pytest.fixture
def test_team(test_db, team_service, team_owner):
    result = team_service.create_team(
        name='Test Team',
        owner=team_owner,
        description='Test Description'
    )
    return result['team']


@pytest.fixture
def team_member(test_db, team_service, test_team, team_owner):
    user = User.create(
        first_name='Сергей',
        last_name='Сергеев',
        username='sergeev',
        password_hash='hash',
        email='sergeev@test.com',
        role_id=1,
        is_active=True
    )

    team_service.add_member(
        team=test_team,
        user=user,
        role_name='member',
        created_by=team_owner
    )
    return user


@pytest.fixture
def project_owner(test_db, project_service, test_team, team_owner):
    result = project_service.create_project(
        team=test_team,
        name='Test Project',
        created_by=team_owner,
        description='Test Description'
    )
    return {
        'project': result['project'],
        'user': team_owner
    }


@pytest.fixture
def test_project(project_owner):
    return project_owner['project']


@pytest.fixture
def project_manager(test_db, project_service, test_project, team_owner, second_user):
    project_service.add_member(
        project=test_project,
        user=second_user,
        role_name='manager',
        added_by=team_owner
    )
    return second_user


@pytest.fixture
def project_developer(test_db, project_service, test_project, team_owner, team_member):
    project_service.add_member(
        project=test_project,
        user=team_member,
        role_name='developer',
        added_by=team_owner
    )
    return team_member


@pytest.fixture
def not_team_member_user(test_db, user_role):
    """Пользователь, который не является членом команды"""
    return User.create(
        first_name='Анна',
        last_name='Аннова',
        username='annova',
        password_hash='hash',
        email='annova@test.com',
        role=user_role,
        is_active=True
    )


@pytest.fixture
def todo_status(task_service):
    return task_service.get_status_by_name('todo')


@pytest.fixture
def in_progress_status(task_service):
    return task_service.get_status_by_name('in_progress')


@pytest.fixture
def completed_status(task_service):
    return task_service.get_status_by_name('completed')


@pytest.fixture
def blocked_status(task_service):
    return task_service.get_status_by_name('blocked')


@pytest.fixture
def test_task(task_service, test_project, project_owner, todo_status):
    result = task_service.create_task(
        project=test_project,
        name='Test Task',
        creator=project_owner['user'],
        description='Test Description',
        assignee=project_owner['user'],
        priority=1,
        position_x=100,
        position_y=200
    )
    return result['task']


@pytest.fixture
def second_task(task_service, test_project, project_developer, todo_status):
    result = task_service.create_task(
        project=test_project,
        name='Second Task',
        creator=project_developer,
        description='Second Description',
        assignee=project_developer
    )
    return result['task']


# ------------------- ТЕСТЫ СОЗДАНИЯ ЗАДАЧ -------------------

class TestTaskCreation:
    """Тесты создания задач"""

    def test_create_task_success(self, task_service, test_project, project_owner):
        result = task_service.create_task(
            project=test_project,
            name='New Task',
            creator=project_owner['user'],
            description='Description',
            assignee=project_owner['user'],
            deadline=datetime.now() + timedelta(days=7),
            priority=2,
            position_x=150,
            position_y=250
        )

        task = result['task']
        assert task.name == 'New Task'
        assert task.description == 'Description'
        assert task.status.name == 'todo'
        assert task.creator.id == project_owner['user'].id
        assert task.assignee.id == project_owner['user'].id
        assert task.priority == 2
        assert task.position_x == 150
        assert task.position_y == 250

        events = TaskEvent.select().where(TaskEvent.task == task)
        assert events.count() == 1
        assert events[0].event_type == 'created'

        scheduled = ScheduledAction.select().where(ScheduledAction.task == task)
        assert scheduled.count() == 2

    def test_create_task_without_assignee(self, task_service, test_project, project_owner):
        result = task_service.create_task(
            project=test_project,
            name='Task Without Assignee',
            creator=project_owner['user']
        )

        task = result['task']
        assert task.assignee is None

    def test_create_task_assignee_not_member(self, task_service, test_project, project_owner, not_team_member_user):
        with pytest.raises(ValueError, match='must be a member of the project'):
            task_service.create_task(
                project=test_project,
                name='Task',
                creator=project_owner['user'],
                assignee=not_team_member_user
            )

    def test_create_task_no_permission(self, task_service, test_project, project_developer):
        from core.db.models.project import ProjectRole
        observer_role = ProjectRole.get(ProjectRole.name == 'observer')

        observer_user = User.create(
            first_name='Observer',
            last_name='User',
            username='observer',
            password_hash='hash',
            role_id=1
        )

        ProjectMember.create(
            project=test_project,
            user=observer_user,
            role=observer_role,
            created_by=project_developer
        )

        with pytest.raises(PermissionError, match="You don't have permission to create tasks in this project"):
            task_service.create_task(
                project=test_project,
                name='Task',
                creator=observer_user
            )


# ------------------- ТЕСТЫ ОБНОВЛЕНИЯ ЗАДАЧ -------------------

class TestTaskUpdate:
    """Тесты обновления задач"""

    def test_update_task_success(self, task_service, test_task, project_owner):
        new_deadline = datetime.now() + timedelta(days=14)

        updated = task_service.update_task(
            task=test_task,
            updated_by=project_owner['user'],
            name='Updated Name',
            description='Updated Description',
            priority=3,
            deadline=new_deadline
        )

        assert updated.name == 'Updated Name'
        assert updated.description == 'Updated Description'
        assert updated.priority == 3
        assert updated.deadline == new_deadline

        events = TaskEvent.select().where(
            (TaskEvent.task == test_task) &
            (TaskEvent.event_type == 'updated')
        )
        assert events.count() >= 3

    def test_update_task_no_permission(self, task_service, test_task, project_developer):
        with pytest.raises(PermissionError, match="You don't have permission to edit this task"):
            task_service.update_task(
                task=test_task,
                updated_by=project_developer,
                name='Hacked Name'
            )

    def test_update_task_assignee(self, task_service, test_task, project_owner, project_developer):
        updated = task_service.update_task(
            task=test_task,
            updated_by=project_owner['user'],
            assignee=project_developer
        )

        assert updated.assignee.id == project_developer.id


# ------------------- ТЕСТЫ ИЗМЕНЕНИЯ СТАТУСА -------------------

class TestTaskStatus:
    """Тесты изменения статуса задач"""

    def test_change_status_success(self, task_service, test_task, project_owner, in_progress_status):
        result = task_service.change_task_status(
            task=test_task,
            new_status_name='in_progress',
            changed_by=project_owner['user']
        )

        assert result['status_changed'] is True
        assert result['task'].status.name == 'in_progress'
        assert result['old_status'].name == 'todo'
        assert result['new_status'].name == 'in_progress'

    def test_change_status_same_status(self, task_service, test_task, project_owner):
        result = task_service.change_task_status(
            task=test_task,
            new_status_name='todo',
            changed_by=project_owner['user']
        )

        assert result['status_changed'] is False

    def test_change_status_assignee_can_change(self, task_service, test_task, project_developer):
        test_task.assignee = project_developer
        test_task.save()

        result = task_service.change_task_status(
            task=test_task,
            new_status_name='in_progress',
            changed_by=project_developer
        )

        assert result['status_changed'] is True

    def test_complete_task_triggers_actions(self, task_service, test_task, second_task, project_owner):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user'],
            dependency_type='simple'
        )

        task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='notify_assignee',
            created_by=project_owner['user'],
            message_template='Task {task_name} is ready!'
        )

        with patch.object(task_service, 'send_task_notification', return_value=True) as mock_notify:
            result = task_service.change_task_status(
                task=test_task,
                new_status_name='completed',
                changed_by=project_owner['user']
            )

            assert result['status_changed'] is True
            assert len(result['actions_executed']) == 1
            assert result['actions_executed'][0]['type'] == 'notify_assignee'
            mock_notify.assert_called_once()


# ------------------- ТЕСТЫ ЗАВИСИМОСТЕЙ -------------------

class TestDependencies:
    """Тесты зависимостей между задачами"""

    def test_create_dependency_success(self, task_service, test_task, second_task, project_owner):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user'],
            dependency_type='blocks',
            description='Test dependency'
        )

        assert dependency.source_task.id == test_task.id
        assert dependency.target_task.id == second_task.id
        assert dependency.dependency_type == 'blocks'
        assert dependency.description == 'Test dependency'
        assert dependency.created_by.id == project_owner['user'].id

    def test_create_dependency_cycle(self, task_service, test_task, second_task, project_owner):
        task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        with pytest.raises(ValueError, match='would create a cycle'):
            task_service.create_dependency(
                source_task=second_task,
                target_task=test_task,
                created_by=project_owner['user']
            )

    def test_create_dependency_duplicate(self, task_service, test_task, second_task, project_owner):
        task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        with pytest.raises(ValueError, match='already exists'):
            task_service.create_dependency(
                source_task=test_task,
                target_task=second_task,
                created_by=project_owner['user']
            )

    def test_create_dependency_developer_can(self, task_service, test_task, second_task, project_developer):
        dependency = task_service.create_dependency(
            source_task=second_task,
            target_task=test_task,
            created_by=project_developer,
            dependency_type='simple'
        )

        assert dependency is not None

    def test_delete_dependency(self, task_service, test_task, second_task, project_owner):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        result = task_service.delete_dependency(dependency, project_owner['user'])
        assert result is True

        assert TaskDependency.select().where(TaskDependency.id == dependency.id).count() == 0

    def test_delete_dependency_no_permission(self, task_service, test_task, second_task, project_owner,
                                             project_developer):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        with pytest.raises(PermissionError, match="You don't have permission to delete dependencies"):
            task_service.delete_dependency(dependency, project_developer)

    def test_check_task_readiness(self, task_service, test_task, second_task, project_owner):
        task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        is_ready = task_service.check_task_readiness(second_task)
        assert is_ready is False

        task_service.change_task_status(
            task=test_task,
            new_status_name='completed',
            changed_by=project_owner['user']
        )

        is_ready = task_service.check_task_readiness(second_task)
        assert is_ready is True


# ------------------- ТЕСТЫ ДЕЙСТВИЙ НА ЗАВИСИМОСТЯХ -------------------

class TestDependencyActions:
    """Тесты действий на ребрах графа"""

    def test_add_notify_assignee_action(self, task_service, test_task, second_task, project_owner):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        action = task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='notify_assignee',
            created_by=project_owner['user'],
            message_template='Task {task_name} is ready!',
            execute_order=1
        )

        assert action.action_type.code == 'notify_assignee'
        assert action.message_template == 'Task {task_name} is ready!'
        assert action.execute_order == 1
        assert action.is_active is True

    def test_add_notify_custom_action(self, task_service, test_task, second_task, project_owner, project_developer):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        action = task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='notify_custom',
            created_by=project_owner['user'],
            target_user=project_developer,
            message_template='Custom notification for {user}',
            delay_minutes=30
        )

        assert action.action_type.code == 'notify_custom'
        assert action.target_user.id == project_developer.id
        assert action.delay_minutes == 30

    def test_add_change_status_action(self, task_service, test_task, second_task, project_owner, completed_status):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        action = task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='change_status',
            created_by=project_owner['user'],
            target_status_name='completed'
        )

        assert action.action_type.code == 'change_status'
        assert action.target_status.name == 'completed'

    def test_execute_notify_action(self, task_service, test_task, second_task, project_owner):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        action = task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='notify_assignee',
            created_by=project_owner['user'],
            message_template='Test message'
        )

        with patch.object(task_service, 'send_task_notification', return_value=True) as mock_notify:
            result = task_service.execute_single_action(
                action=action,
                trigger_event='task_completed',
                triggered_by=project_owner['user']
            )

            assert result['status'] == 'executed'
            mock_notify.assert_called_once()

    def test_execute_delayed_action(self, task_service, test_task, second_task, project_owner):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        action = task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='notify_assignee',
            created_by=project_owner['user'],
            message_template='Delayed message',
            delay_minutes=60
        )

        results = task_service.execute_dependency_actions(
            dependency=dependency,
            trigger_event='task_completed',
            triggered_by=project_owner['user']
        )

        assert len(results) == 1
        assert results[0]['status'] == 'scheduled'

        scheduled = ScheduledAction.select().where(
            ScheduledAction.dependency_action == action
        ).first()
        assert scheduled is not None
        assert scheduled.action_type == 'delayed_notification'


# ------------------- ТЕСТЫ ГРАФА -------------------

class TestGraph:
    """Тесты работы с графом"""

    def test_get_project_graph(self, task_service, test_project, test_task, second_task, project_owner):
        task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        dependency = TaskDependency.get(
            (TaskDependency.source_task == test_task) &
            (TaskDependency.target_task == second_task)
        )

        task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='notify_assignee',
            created_by=project_owner['user'],
            message_template='Test message'
        )

        graph = task_service.get_project_graph(test_project)

        assert 'nodes' in graph
        assert 'edges' in graph
        assert len(graph['nodes']) >= 2
        assert len(graph['edges']) == 1


# ------------------- ТЕСТЫ СОБЫТИЙ -------------------

class TestEvents:
    """Тесты логирования событий"""

    def test_task_created_event(self, task_service, test_project, project_owner):
        result = task_service.create_task(
            project=test_project,
            name='Event Test',
            creator=project_owner['user']
        )

        task = result['task']
        events = TaskEvent.select().where(TaskEvent.task == task)
        assert events.count() == 1
        assert events[0].event_type == 'created'

    def test_task_status_changed_event(self, task_service, test_task, project_owner):
        task_service.change_task_status(
            task=test_task,
            new_status_name='in_progress',
            changed_by=project_owner['user']
        )

        event = TaskEvent.select().where(TaskEvent.event_type == 'status_changed').first()
        assert event is not None
        assert event.old_value == 'todo'
        assert event.new_value == 'in_progress'

    def test_dependency_added_event(self, task_service, test_task, second_task, project_owner):
        task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        event = TaskEvent.select().where(TaskEvent.event_type == 'dependency_added').first()
        assert event is not None


# ------------------- ТЕСТЫ ЗАПЛАНИРОВАННЫХ ДЕЙСТВИЙ -------------------

class TestScheduledActions:
    """Тесты отложенных действий"""

    def test_schedule_deadline_notification(self, task_service, test_project, project_owner):
        deadline = datetime.now() + timedelta(days=2)

        result = task_service.create_task(
            project=test_project,
            name='Deadline Task',
            creator=project_owner['user'],
            assignee=project_owner['user'],
            deadline=deadline
        )

        task = result['task']

        scheduled = ScheduledAction.select().where(
            (ScheduledAction.task == task) &
            (ScheduledAction.action_type == 'deadline_approaching')
        )

        assert scheduled.count() == 2

    def test_process_scheduled_actions(self, task_service, test_task, project_owner):
        scheduled = ScheduledAction.create(
            project=test_task.project,
            task=test_task,
            action_type='deadline_approaching',
            scheduled_for=datetime.now() - timedelta(minutes=1),
            payload=json.dumps({'hours_before': 24}),
            status='pending'
        )

        with patch.object(task_service, 'send_task_notification', return_value=True) as mock_notify:
            results = task_service.process_scheduled_actions()

            assert len(results) == 1
            assert results[0]['status'] == 'completed'

            scheduled = ScheduledAction.get_by_id(scheduled.id)
            assert scheduled.status == 'completed'
            assert scheduled.executed_at is not None

            mock_notify.assert_called_once()


# ------------------- ТЕСТЫ СТАТИСТИКИ -------------------

class TestTaskStats:
    """Тесты статистики задач"""

    def test_get_task_stats(self, task_service, test_project, test_task, second_task, project_owner, project_developer):
        task_service.change_task_status(
            task=test_task,
            new_status_name='in_progress',
            changed_by=project_owner['user']
        )

        task_service.change_task_status(
            task=second_task,
            new_status_name='completed',
            changed_by=project_developer
        )

        stats = task_service.get_task_stats(test_project)

        assert stats['total'] == 2
        assert 'in_progress' in stats['by_status']
        assert 'completed' in stats['by_status']
        assert 'todo' not in stats['by_status']

    def test_get_user_task_stats(self, task_service, test_project, test_task, second_task, project_owner,
                                 project_developer):
        task_service.create_task(
            project=test_project,
            name='Another Task',
            creator=project_owner['user'],
            assignee=project_owner['user']
        )

        stats = task_service.get_user_task_stats(
            user=project_owner['user'],
            project=test_project
        )

        assert stats['assigned'] >= 2
        assert stats['created'] >= 2
        assert 'completion_rate' in stats


# ------------------- ТЕСТЫ ГРАНИЧНЫХ СЛУЧАЕВ -------------------

class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_task_without_assignee_readiness(self, task_service, test_task, second_task, project_owner):
        test_task.assignee = None
        test_task.save()

        task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        task_service.change_task_status(
            task=test_task,
            new_status_name='completed',
            changed_by=project_owner['user']
        )

        is_ready = task_service.check_task_readiness(second_task)
        assert is_ready is True

    def test_circular_dependency_detection(self, task_service, test_task, second_task, project_owner):
        third_task = task_service.create_task(
            project=test_task.project,
            name='Third Task',
            creator=project_owner['user']
        )['task']

        task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        task_service.create_dependency(
            source_task=second_task,
            target_task=third_task,
            created_by=project_owner['user']
        )

        with pytest.raises(ValueError, match='would create a cycle'):
            task_service.create_dependency(
                source_task=third_task,
                target_task=test_task,
                created_by=project_owner['user']
            )

    def test_multiple_actions_same_dependency(self, task_service, test_task, second_task, project_owner):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='notify_assignee',
            created_by=project_owner['user'],
            message_template='Task ready!',
            execute_order=1
        )

        task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='notify_creator',
            created_by=project_owner['user'],
            message_template='Task completed!',
            execute_order=2
        )

        actions = dependency.actions.where(DependencyAction.is_active == True)
        assert actions.count() == 2
        assert actions[0].execute_order == 1
        assert actions[1].execute_order == 2

    def test_deactivate_dependency_action(self, task_service, test_task, second_task, project_owner):
        dependency = task_service.create_dependency(
            source_task=test_task,
            target_task=second_task,
            created_by=project_owner['user']
        )

        action = task_service.add_dependency_action(
            dependency=dependency,
            action_type_code='notify_assignee',
            created_by=project_owner['user'],
            message_template='Test message'
        )

        action.is_active = False
        action.save()

        with patch.object(task_service, 'send_task_notification') as mock_notify:
            task_service.execute_dependency_actions(
                dependency=dependency,
                trigger_event='task_completed',
                triggered_by=project_owner['user']
            )
            mock_notify.assert_not_called()