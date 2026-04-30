from peewee import SqliteDatabase
import pytest

from core.db.models.project import Project, ProjectInvitation, ProjectMember, ProjectRole
from core.db.models.task import (
    DependencyAction,
    DependencyActionType,
    Note,
    ScheduledAction,
    Task,
    TaskDependency,
    TaskEvent,
    TaskStatus,
)
from core.db.models.team import Team, TeamInvitation, TeamMember, TeamMemberRole
from core.db.models.user import User, UserRole
from core.services.NoteService import NoteService
from core.services.ProjectService import ProjectService
from core.services.TaskService import TaskService
from core.services.TeamService import TeamService


@pytest.fixture
def acceptance_db():
    db = SqliteDatabase(':memory:')
    models = [
        User,
        UserRole,
        Team,
        TeamMember,
        TeamMemberRole,
        Project,
        ProjectRole,
        ProjectMember,
        ProjectInvitation,
        TeamInvitation,
        TaskStatus,
        DependencyActionType,
        Task,
        TaskDependency,
        DependencyAction,
        TaskEvent,
        Note,
        ScheduledAction,
    ]
    db.bind(models, bind_refs=False, bind_backrefs=False)
    db.connect()
    db.create_tables(models)
    yield db
    db.drop_tables(models)
    db.close()


@pytest.fixture
def acceptance_context(acceptance_db):
    user_role = UserRole.create(name='Работник', description='Test', priority=1)

    owner = User.create(
        first_name='Олег',
        last_name='Owner',
        username='owner',
        password_hash='hash',
        email='owner@test.local',
        role=user_role,
        is_active=True,
    )
    manager = User.create(
        first_name='Мария',
        last_name='Manager',
        username='manager',
        password_hash='hash',
        email='manager@test.local',
        role=user_role,
        is_active=True,
    )
    developer = User.create(
        first_name='Денис',
        last_name='Developer',
        username='developer',
        password_hash='hash',
        email='developer@test.local',
        role=user_role,
        is_active=True,
    )
    observer = User.create(
        first_name='Ольга',
        last_name='Observer',
        username='observer',
        password_hash='hash',
        email='observer@test.local',
        role=user_role,
        is_active=True,
    )

    team_service = TeamService()
    project_service = ProjectService()
    task_service = TaskService()
    note_service = NoteService()
    team_service.ensure_default_roles()
    project_service.ensure_default_roles()
    task_service.ensure_default_statuses()
    task_service.ensure_default_action_types()

    team = team_service.create_team('Acceptance Team', owner)['team']
    for user in (manager, developer, observer):
        team_service.add_member(team, user, 'member', owner)

    project = project_service.create_project(team, 'Acceptance Project', owner)[
        'project'
    ]
    project_service.add_member(project, manager, 'manager', owner)
    project_service.add_member(project, developer, 'developer', owner)
    project_service.add_member(project, observer, 'observer', owner)

    task = task_service.create_task(project, 'Acceptance Task', owner)['task']
    blocker = task_service.create_task(project, 'Blocker Task', owner)['task']

    return {
        'owner': owner,
        'manager': manager,
        'developer': developer,
        'observer': observer,
        'project': project,
        'task': task,
        'blocker': blocker,
        'project_service': project_service,
        'task_service': task_service,
        'note_service': note_service,
    }


def test_project_role_acceptance_matrix(acceptance_context):
    ctx = acceptance_context
    project = ctx['project']
    task = ctx['task']
    project_service = ctx['project_service']
    task_service = ctx['task_service']

    for user_key in ('owner', 'manager'):
        user = ctx[user_key]
        assert project_service.can_create_tasks(user, project) is True
        assert project_service.can_edit_task(user, task) is True
        assert project_service.can_delete_task(user, task) is True
        assert project_service.can_manage_task_graph(user, project) is True

    for user_key in ('developer', 'observer'):
        user = ctx[user_key]
        assert project_service.can_create_tasks(user, project) is False
        assert project_service.can_edit_task(user, task) is False
        assert project_service.can_delete_task(user, task) is False
        assert project_service.can_manage_task_graph(user, project) is False
        assert project_service.can_change_task_status(user, task) is True

        with pytest.raises(PermissionError):
            task_service.create_task(project, f'{user_key} task', user)
        with pytest.raises(PermissionError):
            task_service.update_task(task, user, description='forbidden')
        with pytest.raises(PermissionError):
            task_service.create_dependency(ctx['blocker'], task, user, 'blocks')
        with pytest.raises(PermissionError):
            project_service.save_graph_data(project, {'nodes': []}, user)

    result = task_service.change_task_status(task, 'review', ctx['developer'])
    assert result['status_changed'] is True


def test_note_acceptance_permissions_and_task_scope(acceptance_context):
    ctx = acceptance_context
    note_service = ctx['note_service']
    project = ctx['project']
    task = ctx['task']
    developer = ctx['developer']
    observer = ctx['observer']
    manager = ctx['manager']

    project_note = note_service.create_project_note(
        project, developer, 'Project note from developer'
    )
    assert project_note.scope_type == 'project'
    assert note_service.list_project_notes(project, observer)[0].id == project_note.id

    task_note = note_service.create_task_note(
        project, task.id, developer, 'Task note from developer'
    )
    assert task_note.scope_type == 'task'
    assert task_note.task_id == task.id
    assert note_service.list_task_notes(project, task.id, manager)[0].id == task_note.id

    updated_by_author = note_service.update_note(
        project, project_note.id, developer, 'Updated by author'
    )
    assert updated_by_author.content == 'Updated by author'

    updated_by_manager = note_service.update_note(
        project, project_note.id, manager, 'Updated by manager'
    )
    assert updated_by_manager.content == 'Updated by manager'

    with pytest.raises(PermissionError):
        note_service.update_note(project, project_note.id, observer, 'Forbidden')

    note_service.delete_note(project, task_note.id, manager)
    with pytest.raises(ValueError):
        note_service.get_note_or_raise(project, task_note.id)
