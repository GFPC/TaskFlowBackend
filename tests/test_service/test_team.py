import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from peewee import SqliteDatabase
from core.db.models.user import User, UserRole
from core.db.models.team import (
    Team, TeamMember, TeamMemberRole, TeamInvitation
)
from core.services.TeamService import TeamService


# ------------------- FIXTURES -------------------

@pytest.fixture(scope='function')
def test_db():
    """Тестовая БД в памяти"""
    test_db = SqliteDatabase(':memory:')

    test_db.bind([User, UserRole, Team, TeamMember, TeamMemberRole, TeamInvitation],
                 bind_refs=False, bind_backrefs=False)

    test_db.connect()
    test_db.create_tables([User, UserRole, Team, TeamMember, TeamMemberRole, TeamInvitation])

    yield test_db

    test_db.drop_tables([User, UserRole, Team, TeamMember, TeamMemberRole, TeamInvitation])
    test_db.close()


@pytest.fixture
def team_service(test_db):
    """Сервис команд"""
    service = TeamService()
    service.ensure_default_roles()
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
def test_team(test_db, team_service, test_user):
    """Тестовая команда"""
    result = team_service.create_team(
        name='Test Team',
        owner=test_user,
        description='Test Description'
    )
    return result['team']


@pytest.fixture
def owner_role(test_db, team_service):
    """Роль владельца"""
    return team_service.get_role_by_name('owner')


@pytest.fixture
def admin_role(test_db, team_service):
    """Роль администратора"""
    return team_service.get_role_by_name('admin')


@pytest.fixture
def member_role(test_db, team_service):
    """Роль участника"""
    return team_service.get_role_by_name('member')


# ------------------- ТЕСТЫ ВАЛИДАЦИИ -------------------

class TestTeamValidation:
    """Тесты валидации команд"""

    def test_validate_team_name_valid(self, team_service):
        valid, error = team_service._validate_team_name('Valid Team Name 123')
        assert valid is True
        assert error is None

    def test_validate_team_name_too_short(self, team_service):
        valid, error = team_service._validate_team_name('A')
        assert valid is False
        assert 'at least 2 characters' in error

    def test_validate_team_name_too_long(self, team_service):
        valid, error = team_service._validate_team_name('A' * 101)
        assert valid is False
        assert 'at most 100 characters' in error

    def test_validate_team_name_empty(self, team_service):
        valid, error = team_service._validate_team_name('')
        assert valid is False
        assert 'required' in error

    def test_generate_slug(self, team_service):
        slug = team_service._generate_slug('Test Team Name!')
        assert slug == 'test-team-name'

    def test_get_unique_slug(self, team_service, test_db, test_user):
        team_service.create_team(name='Test Team', owner=test_user)

        slug = team_service._get_unique_slug('test-team')
        assert slug == 'test-team-1'


# ------------------- ТЕСТЫ СОЗДАНИЯ КОМАНД -------------------

class TestTeamCreation:
    """Тесты создания команд"""

    def test_create_team_success(self, team_service, test_user):
        result = team_service.create_team(
            name='New Team',
            owner=test_user,
            description='Description'
        )

        assert result['team'] is not None
        assert result['member'] is not None
        assert result['invite_code'] is not None

        team = result['team']
        assert team.name == 'New Team'
        assert team.slug == 'new-team'
        assert team.owner.id == test_user.id
        assert team.members_count == 1

        member = result['member']
        assert member.user.id == test_user.id
        assert member.role.name == 'owner'

    def test_create_team_without_description(self, team_service, test_user):
        result = team_service.create_team(
            name='New Team',
            owner=test_user
        )

        assert result['team'].description is None

    def test_create_team_duplicate_name(self, team_service, test_user):
        team_service.create_team(name='Same Name', owner=test_user)

        result = team_service.create_team(name='Same Name', owner=test_user)
        assert result['team'].slug == 'same-name-1'

    def test_create_team_invalid_name(self, team_service, test_user):
        with pytest.raises(ValueError, match='Invalid team name'):
            team_service.create_team(
                name='A',
                owner=test_user
            )


# ------------------- ТЕСТЫ УПРАВЛЕНИЯ УЧАСТНИКАМИ -------------------

class TestTeamMembers:
    """Тесты управления участниками команд"""

    def test_add_member_success(self, team_service, test_team, second_user, test_user):
        member = team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        assert member.user.id == second_user.id
        assert member.role.name == 'member'
        assert member.created_by.id == test_user.id
        assert member.is_active is True

        test_team = Team.get_by_id(test_team.id)
        assert test_team.members_count == 2

    def test_add_member_already_member(self, team_service, test_team, test_user):
        with pytest.raises(ValueError, match='already a member'):
            team_service.add_member(
                team=test_team,
                user=test_user,
                role_name='member',
                created_by=test_user
            )

    def test_add_member_no_permission(self, team_service, test_team, second_user):
        with pytest.raises(PermissionError, match="You don't have permission to add members"):
            team_service.add_member(
                team=test_team,
                user=second_user,
                role_name='member',
                created_by=second_user
            )

    def test_add_member_invalid_role(self, team_service, test_team, second_user, test_user):
        with pytest.raises(ValueError, match='not found'):
            team_service.add_member(
                team=test_team,
                user=second_user,
                role_name='invalid_role',
                created_by=test_user
            )

    def test_remove_member_success(self, team_service, test_team, second_user, test_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        result = team_service.remove_member(
            team=test_team,
            user=second_user,
            removed_by=test_user
        )

        assert result is True

        member = TeamMember.get(
            (TeamMember.team == test_team) &
            (TeamMember.user == second_user)
        )
        assert member.is_active is False
        assert member.left_at is not None

        test_team = Team.get_by_id(test_team.id)
        assert test_team.members_count == 1

    def test_remove_member_cannot_remove_owner(self, team_service, test_team, test_user):
        with pytest.raises(ValueError, match='Cannot remove team owner'):
            team_service.remove_member(
                team=test_team,
                user=test_user,
                removed_by=test_user
            )

    def test_remove_member_no_permission(self, team_service, test_team, second_user, test_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        with pytest.raises(PermissionError, match="You don't have permission to remove members"):
            team_service.remove_member(
                team=test_team,
                user=second_user,
                removed_by=second_user
            )

    def test_change_member_role_success(self, team_service, test_team, second_user, test_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        member = team_service.change_member_role(
            team=test_team,
            user=second_user,
            new_role_name='admin',
            changed_by=test_user
        )

        assert member.role.name == 'admin'

    def test_change_member_role_no_permission(self, team_service, test_team, second_user, test_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        with pytest.raises(PermissionError, match="You don't have permission to change roles"):
            team_service.change_member_role(
                team=test_team,
                user=second_user,
                new_role_name='admin',
                changed_by=second_user
            )

    def test_transfer_ownership_success(self, team_service, test_team, second_user, test_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        result = team_service.transfer_ownership(
            team=test_team,
            new_owner=second_user,
            current_owner=test_user
        )

        assert result['new_owner'].user.id == second_user.id
        assert result['new_owner'].role.name == 'owner'
        assert result['old_owner'].role.name == 'admin'

        test_team = Team.get_by_id(test_team.id)
        assert test_team.owner.id == second_user.id

    def test_transfer_ownership_not_owner(self, team_service, test_team, second_user, test_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        with pytest.raises(PermissionError, match='Only the owner'):
            team_service.transfer_ownership(
                team=test_team,
                new_owner=test_user,
                current_owner=second_user
            )


# ------------------- ТЕСТЫ КОДОВ ПРИГЛАШЕНИЙ -------------------

class TestInviteCodes:
    """Тесты кодов приглашений"""

    def test_generate_invite_code(self, team_service, test_team, test_user):
        code = team_service.refresh_invite_code(test_team, test_user)

        assert code is not None
        assert len(code) > 0
        assert test_team.invite_code == code
        assert test_team.invite_code_expires > datetime.now()

    def test_get_invite_code_valid(self, team_service, test_team, test_user):
        code = team_service.get_invite_code(test_team, test_user)
        assert code == test_team.invite_code

    def test_get_invite_code_expired(self, team_service, test_team, test_user):
        old_code = test_team.invite_code
        test_team.invite_code_expires = datetime.now() - timedelta(minutes=1)
        test_team.save()

        code = team_service.get_invite_code(test_team, test_user)
        assert code != old_code
        assert code == test_team.invite_code

    def test_join_by_code_success(self, team_service, test_team, second_user):
        code = test_team.invite_code

        result = team_service.join_by_code(code, second_user)

        assert result['team'].id == test_team.id
        assert result['member'].user.id == second_user.id
        assert result['member'].role.name == 'member'

        test_team = Team.get_by_id(test_team.id)
        assert test_team.members_count == 2

    def test_join_by_code_invalid(self, team_service, second_user):
        with pytest.raises(ValueError, match='Invalid invite code'):
            team_service.join_by_code('invalid-code', second_user)

    def test_join_by_code_expired(self, team_service, test_team, second_user):
        test_team.invite_code_expires = datetime.now() - timedelta(minutes=1)
        test_team.save()

        with pytest.raises(ValueError, match='expired'):
            team_service.join_by_code(test_team.invite_code, second_user)

    def test_join_by_code_already_member(self, team_service, test_team, test_user):
        with pytest.raises(ValueError, match='already a member'):
            team_service.join_by_code(test_team.invite_code, test_user)


# ------------------- ТЕСТЫ ПРИГЛАШЕНИЙ -------------------

class TestInvitations:
    """Тесты приглашений в команду"""

    def test_create_invitation_by_username(self, team_service, test_team, test_user):
        invitation = team_service.create_invitation(
            team=test_team,
            invited_by=test_user,
            proposed_role_name='member',
            invitee_username='petrov'
        )

        assert invitation.team.id == test_team.id
        assert invitation.invited_by.id == test_user.id
        assert invitation.proposed_role.name == 'member'
        assert invitation.invitee_username == 'petrov'
        assert invitation.status == 'pending'
        assert invitation.expires_at > datetime.now()

    def test_create_invitation_by_user(self, team_service, test_team, test_user, second_user):
        invitation = team_service.create_invitation(
            team=test_team,
            invited_by=test_user,
            proposed_role_name='member',
            invited_user=second_user
        )

        assert invitation.invited_user.id == second_user.id

    def test_create_invitation_no_identifier(self, team_service, test_team, test_user):
        with pytest.raises(ValueError, match='Must specify'):
            team_service.create_invitation(
                team=test_team,
                invited_by=test_user,
                proposed_role_name='member'
            )

    def test_create_invitation_duplicate(self, team_service, test_team, test_user, second_user):
        team_service.create_invitation(
            team=test_team,
            invited_by=test_user,
            proposed_role_name='member',
            invited_user=second_user
        )

        with pytest.raises(ValueError, match='already exists'):
            team_service.create_invitation(
                team=test_team,
                invited_by=test_user,
                proposed_role_name='admin',
                invited_user=second_user
            )

    def test_accept_invitation(self, team_service, test_team, test_user, second_user):
        invitation = team_service.create_invitation(
            team=test_team,
            invited_by=test_user,
            proposed_role_name='member',
            invited_user=second_user
        )

        result = team_service.accept_invitation(invitation, second_user)

        assert result['team'].id == test_team.id
        assert result['member'].user.id == second_user.id
        assert result['member'].role.name == 'member'

        invitation = TeamInvitation.get_by_id(invitation.id)
        assert invitation.status == 'accepted'
        assert invitation.responded_at is not None

    def test_accept_invitation_wrong_user(self, team_service, test_team, test_user, second_user):
        invitation = team_service.create_invitation(
            team=test_team,
            invited_by=test_user,
            proposed_role_name='member',
            invited_user=second_user
        )

        with pytest.raises(PermissionError, match='another user'):
            team_service.accept_invitation(invitation, test_user)

    def test_decline_invitation(self, team_service, test_team, test_user, second_user):
        invitation = team_service.create_invitation(
            team=test_team,
            invited_by=test_user,
            proposed_role_name='member',
            invited_user=second_user
        )

        result = team_service.decline_invitation(invitation, second_user)
        assert result is True

        invitation = TeamInvitation.get_by_id(invitation.id)
        assert invitation.status == 'declined'

    def test_cancel_invitation(self, team_service, test_team, test_user, second_user):
        invitation = team_service.create_invitation(
            team=test_team,
            invited_by=test_user,
            proposed_role_name='member',
            invited_user=second_user
        )

        result = team_service.cancel_invitation(invitation, test_user)
        assert result is True

        invitation = TeamInvitation.get_by_id(invitation.id)
        assert invitation.status == 'cancelled'


# ------------------- ТЕСТЫ ПОЛУЧЕНИЯ ДАННЫХ -------------------

class TestTeamQueries:
    """Тесты запросов данных команд"""

    def test_get_user_teams(self, team_service, test_team, test_user, second_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        teams = team_service.get_user_teams(second_user)
        assert len(teams) == 1
        assert teams[0].id == test_team.id

    def test_get_team_members(self, team_service, test_team, test_user, second_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        members = team_service.get_team_members(test_team)
        assert len(members) == 2

        roles = [m.role.name for m in members]
        assert 'owner' in roles
        assert 'member' in roles

    def test_get_user_role_in_team(self, team_service, test_team, test_user):
        role = team_service.get_user_role_in_team(test_user, test_team)
        assert role.name == 'owner'

    def test_get_team_by_slug(self, team_service, test_team):
        team = team_service.get_team_by_slug(test_team.slug)
        assert team.id == test_team.id

    def test_get_team_invitations(self, team_service, test_team, test_user, second_user):
        team_service.create_invitation(
            team=test_team,
            invited_by=test_user,
            proposed_role_name='member',
            invited_user=second_user
        )

        invitations = team_service.get_team_invitations(test_team)
        assert len(invitations) == 1
        assert invitations[0].status == 'pending'

    def test_get_user_invitations(self, team_service, test_team, test_user, second_user):
        team_service.create_invitation(
            team=test_team,
            invited_by=test_user,
            proposed_role_name='member',
            invited_user=second_user
        )

        invitations = team_service.get_user_invitations(second_user)
        assert len(invitations) == 1


# ------------------- ТЕСТЫ ПРАВ ДОСТУПА -------------------

class TestTeamPermissions:
    """Тесты проверки прав"""

    def test_is_member(self, team_service, test_team, test_user):
        assert team_service.is_member(test_user, test_team) is True

        non_member = User.create(
            first_name='Non',
            last_name='Member',
            username='nonmember',
            password_hash='hash',
            role_id=1,
            is_active=True
        )
        assert team_service.is_member(non_member, test_team) is False

    def test_can_manage_team(self, team_service, test_team, test_user, second_user):
        assert team_service.can_manage_team(test_user, test_team) is True

        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='admin',
            created_by=test_user
        )
        assert team_service.can_manage_team(second_user, test_team) is False

    def test_can_manage_projects(self, team_service, test_team, test_user, second_user):
        assert team_service.can_manage_projects(test_user, test_team) is True

        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='admin',
            created_by=test_user
        )
        assert team_service.can_manage_projects(second_user, test_team) is True

    def test_can_invite_members(self, team_service, test_team, test_user, second_user):
        assert team_service.can_invite_members(test_user, test_team) is True

        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='admin',
            created_by=test_user
        )
        assert team_service.can_invite_members(second_user, test_team) is True

        third_user = User.create(
            first_name='Third',
            last_name='User',
            username='third',
            password_hash='hash',
            role_id=1
        )
        team_service.add_member(
            team=test_team,
            user=third_user,
            role_name='member',
            created_by=test_user
        )
        assert team_service.can_invite_members(third_user, test_team) is False


# ------------------- ТЕСТЫ ПОИСКА И СТАТИСТИКИ -------------------

class TestTeamSearchAndStats:
    """Тесты поиска и статистики"""

    def test_search_teams(self, team_service, test_team, test_user):
        results = team_service.search_teams(query='Test')
        assert len(results) >= 1
        assert results[0].id == test_team.id

    def test_search_teams_by_user(self, team_service, test_team, test_user, second_user):
        results = team_service.search_teams(user=second_user)
        assert len(results) == 0

        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        results = team_service.search_teams(user=second_user)
        assert len(results) == 1

    def test_get_team_stats(self, team_service, test_team, test_user, second_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        stats = team_service.get_team_stats(test_team)

        assert stats['team_id'] == test_team.id
        assert stats['team_name'] == test_team.name
        assert stats['total_members'] == 2
        assert 'owner' in stats['by_role']
        assert 'member' in stats['by_role']
        assert 'pending_invitations' in stats


# ------------------- ТЕСТЫ ОБНОВЛЕНИЯ КОМАНД -------------------

class TestTeamUpdate:
    """Тесты обновления команд"""

    def test_update_team_success(self, team_service, test_team, test_user):
        updated = team_service.update_team(
            team=test_team,
            updated_by=test_user,
            name='Updated Name',
            description='Updated Description'
        )

        assert updated.name == 'Updated Name'
        assert updated.description == 'Updated Description'
        assert updated.slug == 'updated-name'

    def test_update_team_no_permission(self, team_service, test_team, second_user):
        with pytest.raises(PermissionError, match="You don't have permission to update this team"):
            team_service.update_team(
                team=test_team,
                updated_by=second_user,
                name='New Name'
            )

    def test_update_team_invalid_name(self, team_service, test_team, test_user):
        with pytest.raises(ValueError, match='Invalid team name'):
            team_service.update_team(
                team=test_team,
                updated_by=test_user,
                name='A'
            )


# ------------------- ТЕСТЫ УДАЛЕНИЯ -------------------

class TestTeamDeletion:
    """Тесты удаления команд"""

    def test_delete_team_by_owner(self, team_service, test_team, test_user, second_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        result = team_service.delete_team(test_team, test_user)
        assert result is True

        member = TeamMember.get(
            (TeamMember.team == test_team) &
            (TeamMember.user == second_user)
        )
        assert member.is_active is False
        assert member.left_at is not None

        owner_member = TeamMember.get(
            (TeamMember.team == test_team) &
            (TeamMember.user == test_user)
        )
        assert owner_member.is_active is True

        test_team = Team.get_by_id(test_team.id)
        assert test_team.members_count == 1

    def test_delete_team_not_owner(self, team_service, test_team, second_user):
        with pytest.raises(PermissionError, match='Only the owner'):
            team_service.delete_team(test_team, second_user)


# ------------------- ТЕСТЫ ГРАНИЧНЫХ СЛУЧАЕВ -------------------

class TestTeamEdgeCases:
    """Тесты граничных случаев"""

    def test_team_without_members_except_owner(self, team_service, test_user):
        team = team_service.create_team(
            name='New Team',
            owner=test_user
        )['team']

        assert team.members_count == 1

        members = team_service.get_team_members(team)
        assert len(members) == 1
        assert members[0].role.name == 'owner'

    def test_reactivate_removed_member(self, team_service, test_team, second_user, test_user):
        team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='member',
            created_by=test_user
        )

        team_service.remove_member(
            team=test_team,
            user=second_user,
            removed_by=test_user
        )

        member = team_service.add_member(
            team=test_team,
            user=second_user,
            role_name='admin',
            created_by=test_user
        )

        assert member.is_active is True
        assert member.role.name == 'admin'
        assert member.left_at is None

        test_team = Team.get_by_id(test_team.id)
        assert test_team.members_count == 2

    def test_multiple_teams_same_user(self, team_service, test_user):
        team1 = team_service.create_team(name='Team 1', owner=test_user)['team']
        team2 = team_service.create_team(name='Team 2', owner=test_user)['team']

        teams = team_service.get_user_teams(test_user)
        assert len(teams) == 2
        assert team1.id in [t.id for t in teams]
        assert team2.id in [t.id for t in teams]