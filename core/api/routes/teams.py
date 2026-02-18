# core/api/routes/teams.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Any, List, Optional
from ...services.TeamService import TeamService
from ...services.UserService import UserService
from ...db.models.user import User
from ...db.models.team import Team, TeamMember, TeamInvitation
from ..schemas.team import (
    TeamCreate, TeamUpdate, TeamResponse, TeamDetailResponse,
    TeamMemberResponse, TeamMemberUpdate, TeamMemberAdd,
    TeamInvitationCreate, TeamInvitationResponse, TeamInvitationAccept,
    TeamJoinByCode, TeamTransferOwnership, TeamStatsResponse,
    InviteCodeResponse
)
from ..schemas.user import UserProfileResponse
from ..deps import get_team_service, get_user_service, get_current_active_user

# ⚠️ ОДНО ОПРЕДЕЛЕНИЕ РОУТЕРА - В САМОМ НАЧАЛЕ!
router = APIRouter(prefix="/teams", tags=["teams"])
logger = logging.getLogger(__name__)


# ------------------- ОСНОВНЫЕ ОПЕРАЦИИ С КОМАНДАМИ -------------------

@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
        team_in: TeamCreate,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Создание новой команды

    - Требует аутентификации
    - Создатель становится владельцем команды
    - Генерируется код приглашения
    """
    try:
        result = service.create_team(
            name=team_in.name,
            owner=current_user,
            description=team_in.description
        )

        return TeamResponse.model_validate(result['team'])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[TeamResponse])
async def get_my_teams(
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение всех команд текущего пользователя
    """
    teams = service.get_user_teams(current_user)
    return [TeamResponse.model_validate(team) for team in teams]


@router.get("/{team_slug}", response_model=TeamDetailResponse)
async def get_team_by_slug(
        team_slug: str,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение детальной информации о команде по slug

    - Требует членства в команде
    - Возвращает полную информацию о команде и участниках
    """
    try:
        logger.info(f"Getting team by slug: {team_slug} for user {current_user.username}")

        team = service.get_team_by_slug(team_slug)

        if not team:
            logger.warning(f"Team not found: {team_slug}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )

        logger.info(f"Team found: {team.id} - {team.name}")

        # Проверяем, что пользователь - член команды
        is_member = service.is_member(current_user, team)
        logger.info(f"User is member: {is_member}")

        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this team"
            )

        # Получаем участников
        members = service.get_team_members(team)
        logger.info(f"Found {len(members)} members")

        # Безопасно сериализуем каждого участника
        member_responses = []
        for member in members:
            try:
                logger.debug(f"Serializing member {member.id}, user_id: {member.user_id}")
                member_responses.append(TeamMemberResponse.model_validate(member))
            except Exception as e:
                logger.error(f"Error serializing member {member.id}: {e}")
                # Создаем словарь вручную
                member_data = {
                    'id': member.id,
                    'team_id': member.team_id,
                    'user_id': member.user_id,
                    'username': member.user.username if member.user else None,
                    'first_name': member.user.first_name if member.user else None,
                    'last_name': member.user.last_name if member.user else None,
                    'role': member.role.name if member.role else None,
                    'role_priority': member.role.priority if member.role else 0,
                    'is_active': member.is_active,
                    'joined_at': member.joined_at,
                }
                member_responses.append(TeamMemberResponse(**member_data))

        user_role = service.get_user_role_in_team(current_user, team)
        logger.info(f"User role: {user_role.name if user_role else None}")

        # Создаем словарь с данными команды
        team_data = {
            'id': team.id,
            'name': team.name,
            'slug': team.slug,
            'description': team.description,
            'avatar': team.avatar,
            'owner_id': team.owner_id,
            'members_count': team.members_count,
            'projects_count': team.projects_count,
            'created_at': team.created_at,
            'updated_at': team.updated_at,
            'members': member_responses,
            'user_role': user_role.name if user_role else None,
            'can_manage': service.can_manage_team(current_user, team),
            'can_manage_projects': service.can_manage_projects(current_user, team),
            'can_invite_members': service.can_invite_members(current_user, team),
            'can_remove_members': service.can_remove_members(current_user, team),
        }

        logger.info("Successfully prepared team data")
        return TeamDetailResponse(**team_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_team_by_slug: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )



@router.put("/{team_slug}", response_model=TeamResponse)
async def update_team(
        team_slug: str,
        team_in: TeamUpdate,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Обновление информации о команде

    - Требует прав управления командой (owner/admin)
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    try:
        updated_team = service.update_team(
            team=team,
            updated_by=current_user,
            name=team_in.name,
            description=team_in.description,
            avatar=team_in.avatar
        )

        return TeamResponse.model_validate(updated_team)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{team_slug}")
async def delete_team(
        team_slug: str,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Удаление команды (мягкое удаление)

    - Только владелец команды может удалить
    - Участники деактивируются
    - Приглашения отменяются
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    try:
        service.delete_team(team, current_user)
        return {"message": "Team successfully deleted"}
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


# ------------------- УПРАВЛЕНИЕ УЧАСТНИКАМИ -------------------

@router.get("/{team_slug}/members", response_model=List[TeamMemberResponse])
async def get_team_members(
        team_slug: str,
        include_inactive: bool = Query(False, description="Include inactive members"),
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение списка участников команды

    - Требует членства в команде
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    if not service.is_member(current_user, team):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team"
        )

    members = service.get_team_members(team, include_inactive)
    return [TeamMemberResponse.model_validate(m) for m in members]


@router.post("/{team_slug}/members", response_model=TeamMemberResponse)
async def add_team_member(
        team_slug: str,
        member_in: TeamMemberAdd,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Прямое добавление участника в команду

    - Требует прав управления командой (owner/admin)
    - Пользователь должен существовать в системе
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    # Ищем пользователя по username
    user = user_service.get_user_by_username(member_in.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with username '{member_in.username}' not found"
        )

    try:
        member = service.add_member(
            team=team,
            user=user,
            role_name=member_in.role,
            created_by=current_user
        )

        return TeamMemberResponse.model_validate(member)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{team_slug}/members/{username}", response_model=TeamMemberResponse)
async def update_member_role(
        team_slug: str,
        username: str,
        member_in: TeamMemberUpdate,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Изменение роли участника команды

    - Требует прав управления командой (owner/admin)
    - Нельзя изменить роль владельца (кроме передачи владения)
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    user = user_service.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with username '{username}' not found"
        )

    try:
        member = service.change_member_role(
            team=team,
            user=user,
            new_role_name=member_in.role,
            changed_by=current_user
        )

        return TeamMemberResponse.model_validate(member)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{team_slug}/members/{username}")
async def remove_team_member(
        team_slug: str,
        username: str,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Удаление участника из команды

    - Требует прав управления командой (owner/admin)
    - Нельзя удалить владельца команды
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    user = user_service.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with username '{username}' not found"
        )

    try:
        service.remove_member(team, user, current_user)
        return {"message": f"User {username} successfully removed from team"}
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{team_slug}/transfer-ownership")
async def transfer_ownership(
        team_slug: str,
        transfer_in: TeamTransferOwnership,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Передача прав владельца команды

    - Только текущий владелец может передать права
    - Новый владелец должен быть участником команды
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    new_owner = user_service.get_user_by_username(transfer_in.new_owner_username)
    if not new_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with username '{transfer_in.new_owner_username}' not found"
        )

    try:
        result = service.transfer_ownership(
            team=team,
            new_owner=new_owner,
            current_owner=current_user
        )

        return {
            "message": "Ownership transferred successfully",
            "new_owner": result['new_owner'].user.username,
            "old_owner": result['old_owner'].user.username
        }
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except service.member_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New owner is not a member of this team"
        )


# ------------------- КОДЫ ПРИГЛАШЕНИЙ -------------------

@router.get("/{team_slug}/invite-code", response_model=InviteCodeResponse)
async def get_invite_code(
        team_slug: str,
        refresh: bool = Query(False, description="Force refresh invite code"),
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение кода приглашения в команду

    - Требует членства в команде
    - Код автоматически обновляется при истечении
    - С refresh=true принудительно генерирует новый код
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    if not service.is_member(current_user, team):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team"
        )

    try:
        if refresh:
            code = service.refresh_invite_code(team, current_user)
        else:
            code = service.get_invite_code(team, current_user)

        return InviteCodeResponse(
            invite_code=code,
            expires_at=team.invite_code_expires
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.post("/join-by-code")
async def join_team_by_code(
        join_in: TeamJoinByCode,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Вступление в команду по коду приглашения

    - Публичный эндпоинт (требуется только аутентификация)
    - Код действует 1 час
    """
    try:
        result = service.join_by_code(join_in.invite_code, current_user)

        return {
            "message": "Successfully joined the team",
            "team": TeamResponse.model_validate(result['team']),
            "member": TeamMemberResponse.model_validate(result['member'])
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ------------------- ПРИГЛАШЕНИЯ -------------------

@router.post("/{team_slug}/invitations", response_model=TeamInvitationResponse)
async def create_invitation(
        team_slug: str,
        invitation_in: TeamInvitationCreate,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Создание персонального приглашения в команду

    - Требует прав на приглашение участников (owner/admin)
    - Можно пригласить по username или email
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    invited_user = None
    if invitation_in.username:
        invited_user = user_service.get_user_by_username(invitation_in.username)
        if not invited_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username '{invitation_in.username}' not found"
            )

    try:
        invitation = service.create_invitation(
            team=team,
            invited_by=current_user,
            proposed_role_name=invitation_in.role,
            invitee_username=invitation_in.username,
            invitee_email=invitation_in.email,
            invited_user=invited_user,
            message=invitation_in.message
        )

        return TeamInvitationResponse.model_validate(invitation)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/invitations", response_model=List[TeamInvitationResponse])
async def get_my_invitations(
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение всех активных приглашений текущего пользователя
    """
    invitations = service.get_user_invitations(current_user)
    return [TeamInvitationResponse.model_validate(inv) for inv in invitations]


@router.get("/{team_slug}/invitations", response_model=List[TeamInvitationResponse])
async def get_team_invitations(
        team_slug: str,
        status: Optional[str] = Query('pending', description="Filter by status"),
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение списка приглашений команды

    - Требует прав на управление командой
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    if not service.can_manage_team(current_user, team):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view team invitations"
        )

    invitations = service.get_team_invitations(team, status)
    return [TeamInvitationResponse.model_validate(inv) for inv in invitations]


@router.post("/invitations/{invitation_id}/accept")
async def accept_invitation(
        invitation_id: int,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Принятие приглашения в команду
    """
    try:
        invitation = service.invitation_model.get_by_id(invitation_id)
    except service.invitation_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    try:
        result = service.accept_invitation(invitation, current_user)

        return {
            "message": "Invitation accepted successfully",
            "team": TeamResponse.model_validate(result['team']),
            "member": TeamMemberResponse.model_validate(result['member'])
        }
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/invitations/{invitation_id}/decline")
async def decline_invitation(
        invitation_id: int,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Отклонение приглашения в команду
    """
    try:
        invitation = service.invitation_model.get_by_id(invitation_id)
    except service.invitation_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    try:
        service.decline_invitation(invitation, current_user)
        return {"message": "Invitation declined successfully"}
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.delete("/invitations/{invitation_id}")
async def cancel_invitation(
        invitation_id: int,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Отмена приглашения (только создатель)
    """
    try:
        invitation = service.invitation_model.get_by_id(invitation_id)
    except service.invitation_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    try:
        service.cancel_invitation(invitation, current_user)
        return {"message": "Invitation cancelled successfully"}
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


# ------------------- СТАТИСТИКА -------------------

@router.get("/{team_slug}/stats", response_model=TeamStatsResponse)
async def get_team_stats(
        team_slug: str,
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение статистики по команде

    - Требует членства в команде
    """
    team = service.get_team_by_slug(team_slug)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )

    if not service.is_member(current_user, team):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team"
        )

    stats = service.get_team_stats(team)
    return TeamStatsResponse(**stats)


# ------------------- ПОИСК -------------------

@router.get("/search", response_model=List[TeamResponse])
async def search_teams(
        query: Optional[str] = Query(None, description="Search query"),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        current_user: User = Depends(get_current_active_user),
        service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Поиск команд по названию, slug или описанию
    """
    teams = service.search_teams(
        query=query,
        user=current_user,
        limit=limit,
        offset=offset
    )

    return [TeamResponse.model_validate(team) for team in teams]