import pytest
from unittest.mock import Mock, patch, MagicMock
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
    Task, TaskStatus, TaskDependency,
    DependencyAction, DependencyActionType,
    TaskEvent, ScheduledAction
)
from core.services.TeamService import TeamService
from core.services.ProjectService import ProjectService
from core.services.TaskService import TaskService


# ------------------- FIXTURES -------------------

@pytest.fixture(scope='function')
def test_db():
    """Тестовая БД в памяти со всеми таблицами"""
    test_db = SqliteDatabase(':memory:')

    # Все модели, включая все модели Task
    models = [
        User, UserRole,
        Team, TeamMember, TeamMemberRole,
        Project, ProjectRole, ProjectMember, ProjectInvitation,
        TaskStatus, DependencyActionType,  # Сначала справочники
        Task, TaskDependency, DependencyAction, TaskEvent, ScheduledAction  # Потом основные таблицы
    ]

    test_db.bind(models, bind_refs=False, bind_backrefs=False)
    test_db.connect()
    test_db.create_tables(models)

    yield test_db

    test_db.drop_tables(models)
    test_db.close()


@pytest.fixture
def team_service(test_db):
    """Сервис команд"""
    service = TeamService()
    service.ensure_default_roles()
    return service


@pytest.fixture
def project_service(test_db):
    """Сервис проектов"""
    service = ProjectService()
    service.ensure_default_roles()
    return service


@pytest.fixture
def task_service(test_db):
    """Сервис задач"""
    service = TaskService()
    # Сначала создаем таблицы, потом инициализируем данные
    service.ensure_default_statuses()
    service.ensure_default_action_types()
    return service


@pytest.fixture
def user_role(test_db):
    """Роль пользователя в системе"""
    role, _ = UserRole.get_or_create(
        name='Работник',
        defaults={'description': 'Test', 'priority': 1}
    )
    return role


@pytest.fixture
def test_user(test_db, user_role):
    """Тестовый пользователь"""
    return User.create(
        first_name='Иван',
        last_name='Иванов',
        username='ivanov',
        password_hash='hash',
        email='ivanov@test.com',
        role=user_role,
        is_active=True
    )


@pytest.fixture
def second_user(test_db, user_role):
    """Второй тестовый пользователь"""
    return User.create(
        first_name='Петр',
        last_name='Петров',
        username='petrov',
        password_hash='hash',
        email='petrov@test.com',
        role=user_role,
        is_active=True
    )


@pytest.fixture
def team_owner(test_db, team_service, test_user):
    """Владелец команды"""
    return test_user


@pytest.fixture
def test_team(test_db, team_service, team_owner):
    """Тестовая команда"""
    result = team_service.create_team(
        name='Test Team',
        owner=team_owner,
        description='Test Description'
    )
    return result['team']


@pytest.fixture
def team_admin(test_db, team_service, test_team, team_owner, second_user):
    """Администратор команды"""
    team_service.add_member(
        team=test_team,
        user=second_user,
        role_name='admin',
        created_by=team_owner
    )
    return second_user


@pytest.fixture
def team_member(test_db, team_service, test_team, team_owner):
    """Участник команды"""
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
def another_team_member(test_db, team_service, test_team, team_owner):
    """Еще один участник команды"""
    user = User.create(
        first_name='Анна',
        last_name='Аннова',
        username='annova',
        password_hash='hash',
        email='annova@test.com',
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
    """Владелец проекта"""
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
    """Тестовый проект"""
    return project_owner['project']


@pytest.fixture
def project_manager(test_db, project_service, test_project, team_owner, second_user):
    """Менеджер проекта"""
    project_service.add_member(
        project=test_project,
        user=second_user,
        role_name='manager',
        added_by=team_owner
    )
    return second_user


@pytest.fixture
def project_developer(test_db, project_service, test_project, team_owner, team_member):
    """Разработчик в проекте"""
    project_service.add_member(
        project=test_project,
        user=team_member,
        role_name='developer',
        added_by=team_owner
    )
    return team_member


@pytest.fixture
def todo_status(task_service):
    """Статус 'todo'"""
    return task_service.get_status_by_name('todo')


# ------------------- ТЕСТЫ ВАЛИДАЦИИ -------------------

class TestProjectValidation:
    """Тесты валидации проектов"""

    def test_validate_project_name_valid(self, project_service):
        valid, error = project_service._validate_project_name('Valid Project Name 123')
        assert valid is True
        assert error is None

    def test_validate_project_name_too_short(self, project_service):
        valid, error = project_service._validate_project_name('A')
        assert valid is False
        assert 'at least 2 characters' in error

    def test_validate_project_name_too_long(self, project_service):
        valid, error = project_service._validate_project_name('A' * 201)
        assert valid is False
        assert 'at most 200 characters' in error

    def test_generate_slug(self, project_service):
        slug = project_service._generate_slug('Test Project Name!')
        assert slug == 'test-project-name'

    def test_get_unique_slug(self, project_service, test_team, team_owner):
        project_service.create_project(
            team=test_team,
            name='Test Project',
            created_by=team_owner
        )

        slug = project_service._get_unique_slug('test-project', test_team.id)
        assert slug == 'test-project-1'


# ------------------- ТЕСТЫ СОЗДАНИЯ ПРОЕКТОВ -------------------

class TestProjectCreation:
    """Тесты создания проектов"""

    def test_create_project_success(self, project_service, test_team, team_owner):
        result = project_service.create_project(
            team=test_team,
            name='New Project',
            created_by=team_owner,
            description='Description'
        )

        assert result['project'] is not None
        assert result['member'] is not None

        project = result['project']
        assert project.name == 'New Project'
        assert project.slug == 'new-project'
        assert project.team.id == test_team.id
        assert project.created_by.id == team_owner.id
        assert project.members_count == 1
        assert project.tasks_count == 0

        member = result['member']
        assert member.user.id == team_owner.id
        assert member.role.name == 'owner'

    def test_create_project_without_description(self, project_service, test_team, team_owner):
        result = project_service.create_project(
            team=test_team,
            name='New Project',
            created_by=team_owner
        )

        assert result['project'].description is None

    def test_create_project_with_graph_data(self, project_service, test_team, team_owner):
        graph_data = json.dumps({'nodes': [], 'edges': []})

        result = project_service.create_project(
            team=test_team,
            name='New Project',
            created_by=team_owner,
            initial_graph_data=graph_data
        )

        assert result['project'].graph_data == graph_data

    def test_create_project_no_permission(self, project_service, test_team, team_member):
        with pytest.raises(PermissionError, match="You don't have permission to create projects in this team"):
            project_service.create_project(
                team=test_team,
                name='New Project',
                created_by=team_member
            )

    def test_create_project_invalid_name(self, project_service, test_team, team_owner):
        with pytest.raises(ValueError, match='Invalid project name'):
            project_service.create_project(
                team=test_team,
                name='A',
                created_by=team_owner
            )

    def test_create_project_duplicate_name_same_team(self, project_service, test_team, team_owner):
        project_service.create_project(
            team=test_team,
            name='Same Name',
            created_by=team_owner
        )

        result = project_service.create_project(
            team=test_team,
            name='Same Name',
            created_by=team_owner
        )

        assert result['project'].slug == 'same-name-1'


# ------------------- ТЕСТЫ УПРАВЛЕНИЯ УЧАСТНИКАМИ ПРОЕКТА -------------------

class TestProjectMembers:
    """Тесты управления участниками проекта"""

    def test_add_member_success(self, project_service, test_project, team_member, team_owner):
        member = project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='developer',
            added_by=team_owner
        )

        assert member.user.id == team_member.id
        assert member.role.name == 'developer'
        assert member.created_by.id == team_owner.id

        test_project = Project.get_by_id(test_project.id)
        assert test_project.members_count == 2

    def test_add_member_not_team_member(self, project_service, test_project, second_user, team_owner):
        with pytest.raises(ValueError, match='must be a team member'):
            project_service.add_member(
                project=test_project,
                user=second_user,
                role_name='developer',
                added_by=team_owner
            )

    def test_add_member_already_member(self, project_service, test_project, team_owner):
        with pytest.raises(ValueError, match='already a member'):
            project_service.add_member(
                project=test_project,
                user=team_owner,
                role_name='developer',
                added_by=team_owner
            )

    def test_add_member_no_permission(self, project_service, test_project, team_member, another_team_member):
        with pytest.raises(PermissionError, match="You don't have permission to add members to this project"):
            project_service.add_member(
                project=test_project,
                user=another_team_member,
                role_name='developer',
                added_by=team_member
            )

    def test_remove_member_success(self, project_service, test_project, team_member, team_owner):
        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='developer',
            added_by=team_owner
        )

        result = project_service.remove_member(
            project=test_project,
            user=team_member,
            removed_by=team_owner
        )

        assert result is True

        member = ProjectMember.get(
            (ProjectMember.project == test_project) &
            (ProjectMember.user == team_member)
        )
        assert member.is_active is False

        test_project = Project.get_by_id(test_project.id)
        assert test_project.members_count == 1

    def test_remove_member_cannot_remove_owner(self, project_service, test_project, team_owner):
        with pytest.raises(ValueError, match='Cannot remove project owner'):
            project_service.remove_member(
                project=test_project,
                user=team_owner,
                removed_by=team_owner
            )

    def test_change_member_role_success(self, project_service, test_project, team_member, team_owner):
        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='developer',
            added_by=team_owner
        )

        member = project_service.change_member_role(
            project=test_project,
            user=team_member,
            new_role_name='manager',
            changed_by=team_owner
        )

        assert member.role.name == 'manager'

    def test_transfer_ownership_success(self, project_service, test_project, team_member, team_owner):
        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='developer',
            added_by=team_owner
        )

        result = project_service.transfer_ownership(
            project=test_project,
            new_owner=team_member,
            current_owner=team_owner
        )

        assert result['new_owner'].user.id == team_member.id
        assert result['new_owner'].role.name == 'owner'
        assert result['old_owner'].role.name == 'manager'


# ------------------- ТЕСТЫ ПРИГЛАШЕНИЙ В ПРОЕКТ -------------------

class TestProjectInvitations:
    """Тесты приглашений в проект"""

    def test_create_invitation_success(self, project_service, test_project, team_member, team_owner):
        invitation = project_service.create_invitation(
            project=test_project,
            invited_by=team_owner,
            proposed_role_name='developer',
            team_member=TeamMember.get(
                (TeamMember.team == test_project.team) &
                (TeamMember.user == team_member)
            )
        )

        assert invitation.project.id == test_project.id
        assert invitation.invited_by.id == team_owner.id
        assert invitation.proposed_role.name == 'developer'
        assert invitation.invited_user.id == team_member.id
        assert invitation.status == 'pending'

    def test_accept_invitation_success(self, project_service, test_project, team_member, team_owner):
        invitation = project_service.create_invitation(
            project=test_project,
            invited_by=team_owner,
            proposed_role_name='developer',
            team_member=TeamMember.get(
                (TeamMember.team == test_project.team) &
                (TeamMember.user == team_member)
            )
        )

        result = project_service.accept_invitation(invitation, team_member)

        assert result['project'].id == test_project.id
        assert result['member'].user.id == team_member.id
        assert result['member'].role.name == 'developer'

    def test_accept_invitation_wrong_user(self, project_service, test_project, team_member, team_owner, team_admin):
        invitation = project_service.create_invitation(
            project=test_project,
            invited_by=team_owner,
            proposed_role_name='developer',
            team_member=TeamMember.get(
                (TeamMember.team == test_project.team) &
                (TeamMember.user == team_member)
            )
        )

        with pytest.raises(PermissionError, match='another user'):
            project_service.accept_invitation(invitation, team_admin)


# ------------------- ТЕСТЫ ПРАВ ДОСТУПА -------------------

class TestProjectPermissions:
    """Тесты проверки прав в проекте"""

    def test_is_member(self, project_service, test_project, team_owner):
        assert project_service.is_member(team_owner, test_project) is True

        non_member = User.create(
            first_name='Non',
            last_name='Member',
            username='nonmember',
            password_hash='hash',
            role_id=1
        )
        assert project_service.is_member(non_member, test_project) is False

    def test_can_manage_members(self, project_service, test_project, team_owner, team_member):
        assert project_service.can_manage_members(team_owner, test_project) is True

        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='manager',
            added_by=team_owner
        )

        assert project_service.can_manage_members(team_member, test_project) is True

        project_service.change_member_role(
            project=test_project,
            user=team_member,
            new_role_name='developer',
            changed_by=team_owner
        )

        assert project_service.can_manage_members(team_member, test_project) is False

    def test_can_edit_project(self, project_service, test_project, team_owner, team_member):
        assert project_service.can_edit_project(team_owner, test_project) is True

        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='manager',
            added_by=team_owner
        )

        assert project_service.can_edit_project(team_member, test_project) is True

    def test_can_delete_project(self, project_service, test_project, team_owner, team_member):
        assert project_service.can_delete_project(team_owner, test_project) is True

        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='manager',
            added_by=team_owner
        )

        assert project_service.can_delete_project(team_member, test_project) is False

    def test_can_create_tasks(self, project_service, test_project, team_owner, team_member):
        assert project_service.can_create_tasks(team_owner, test_project) is True

        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='developer',
            added_by=team_owner
        )

        assert project_service.can_create_tasks(team_member, test_project) is True

        project_service.change_member_role(
            project=test_project,
            user=team_member,
            new_role_name='observer',
            changed_by=team_owner
        )

        assert project_service.can_create_tasks(team_member, test_project) is False

    def test_can_edit_task_developer(self, project_service, test_project, team_owner, team_member, task_service,
                                     todo_status):
        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='developer',
            added_by=team_owner
        )

        task = Task.create(
            project=test_project,
            name='Test Task',
            status=todo_status,
            creator=team_member,
            assignee=team_member
        )

        assert project_service.can_edit_task(team_member, task) is True

        other_task = Task.create(
            project=test_project,
            name='Other Task',
            status=todo_status,
            creator=team_owner,
            assignee=team_owner
        )

        assert project_service.can_edit_task(team_member, other_task) is False

    def test_can_edit_task_manager(self, project_service, test_project, team_owner, team_member, task_service,
                                   todo_status):
        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='manager',
            added_by=team_owner
        )

        task = Task.create(
            project=test_project,
            name='Test Task',
            status=todo_status,
            creator=team_owner,
            assignee=team_owner
        )

        assert project_service.can_edit_task(team_member, task) is True


# ------------------- ТЕСТЫ УПРАВЛЕНИЯ ПРОЕКТОМ -------------------

class TestProjectManagement:
    """Тесты управления проектом"""

    def test_update_project_success(self, project_service, test_project, team_owner):
        updated = project_service.update_project(
            project=test_project,
            updated_by=team_owner,
            name='Updated Name',
            description='Updated Description',
            settings={'default_task_status': 'in_progress'}
        )

        assert updated.name == 'Updated Name'
        assert updated.description == 'Updated Description'
        assert updated.settings_dict['default_task_status'] == 'in_progress'

    def test_save_graph_data(self, project_service, test_project, team_owner):
        graph_data = {
            'nodes': [{'id': '1', 'data': {'label': 'Task 1'}}],
            'edges': []
        }

        updated = project_service.save_graph_data(
            project=test_project,
            graph_data=graph_data,
            saved_by=team_owner
        )

        saved = json.loads(updated.graph_data)
        assert len(saved['nodes']) == 1
        assert saved['nodes'][0]['id'] == '1'

    def test_archive_project(self, project_service, test_project, team_owner):
        result = project_service.archive_project(test_project, team_owner)
        assert result is True

        test_project = Project.get_by_id(test_project.id)
        assert test_project.status == 'archived'
        assert test_project.archived_at is not None

    def test_delete_project(self, project_service, test_project, team_member, team_owner):
        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='developer',
            added_by=team_owner
        )

        result = project_service.delete_project(test_project, team_owner)
        assert result is True

        test_project = Project.get_by_id(test_project.id)
        assert test_project.status == 'deleted'

        members = project_service.get_project_members(test_project, include_inactive=True)
        for member in members:
            if member.user.id != team_owner.id:
                assert member.is_active is False


# ------------------- ТЕСТЫ ПОЛУЧЕНИЯ ДАННЫХ -------------------

class TestProjectQueries:
    """Тесты запросов данных проектов"""

    def test_get_user_projects(self, project_service, test_project, team_owner, team_member):
        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='developer',
            added_by=team_owner
        )

        projects = project_service.get_user_projects(team_member)
        assert len(projects) == 1
        assert projects[0].id == test_project.id

    def test_get_project_members(self, project_service, test_project, team_owner):
        members = project_service.get_project_members(test_project)
        assert len(members) == 1
        assert members[0].role.name == 'owner'

    def test_get_user_role_in_project(self, project_service, test_project, team_owner):
        role = project_service.get_user_role_in_project(team_owner, test_project)
        assert role.name == 'owner'

    def test_get_project_by_slug(self, project_service, test_project, test_team):
        project = project_service.get_project_by_slug(test_project.slug, test_team)
        assert project.id == test_project.id


# ------------------- ТЕСТЫ СТАТИСТИКИ -------------------

class TestProjectStats:
    """Тесты статистики проектов"""

    def test_get_project_stats(self, project_service, test_project, team_owner, team_member):
        project_service.add_member(
            project=test_project,
            user=team_member,
            role_name='developer',
            added_by=team_owner
        )

        stats = project_service.get_project_stats(test_project)

        assert stats['project_id'] == test_project.id
        assert stats['project_name'] == test_project.name
        assert stats['total_members'] == 2
        assert 'owner' in stats['by_role']
        assert 'developer' in stats['by_role']
        assert 'tasks' in stats
        assert stats['team'] == test_project.team.name