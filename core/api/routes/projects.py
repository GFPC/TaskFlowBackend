# core/api/routes/projects.py - ПОЛНАЯ ВЕРСИЯ С ВСЕМИ ЭНДПОИНТАМИ

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Any, List, Optional
from datetime import datetime

from ...services.ProjectService import ProjectService
from ...services.TeamService import TeamService
from ...services.UserService import UserService
from ...db.models.user import User
from ...db.models.project import Project, ProjectMember, ProjectInvitation
from ..schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectResponse, ProjectDetailResponse,
    ProjectMemberResponse, ProjectMemberUpdate, ProjectMemberAdd,
    ProjectInvitationCreate, ProjectInvitationResponse,
    ProjectTransferOwnership, ProjectStatsResponse, ProjectGraphData
)
from ..schemas.team import TeamResponse
from ..deps import get_project_service, get_team_service, get_user_service, get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


# ==================== ХЕЛПЕРЫ ====================

async def find_project_by_slug(
        project_slug: str,
        project_service: ProjectService,
        team_service: TeamService,
        current_user: User,
        include_archived: bool = False
) -> Project:
    """Поиск проекта по slug среди команд пользователя"""
    logger.info(f"🔍 FIND_PROJECT: Looking for project '{project_slug}'")
    logger.info(f"🔍 FIND_PROJECT: User: {current_user.username} (ID: {current_user.id})")
    logger.info(f"🔍 FIND_PROJECT: Include archived: {include_archived}")

    # Получаем все команды пользователя
    user_teams = team_service.get_user_teams(current_user)
    logger.info(f"🔍 FIND_PROJECT: User has {len(user_teams)} teams")

    for i, team in enumerate(user_teams):
        logger.info(f"🔍 FIND_PROJECT: Checking team {i + 1}/{len(user_teams)}: {team.slug} (ID: {team.id})")

        project = project_service.get_project_by_slug(project_slug, team)

        if project:
            logger.info(f"✅ FIND_PROJECT: Found project in team {team.slug}")
            logger.info(f"   Project ID: {project.id}")
            logger.info(f"   Project name: {project.name}")
            logger.info(f"   Project status: {project.status}")
            logger.info(f"   Project archived_at: {project.archived_at}")

            if include_archived:
                logger.info(f"🔍 FIND_PROJECT: Returning project (include_archived=True)")
                return project

            if project.status == 'active':
                logger.info(f"🔍 FIND_PROJECT: Returning active project")
                return project
            else:
                logger.info(f"🔍 FIND_PROJECT: Project is {project.status}, but include_archived=False")
        else:
            logger.info(f"❌ FIND_PROJECT: No project '{project_slug}' in team {team.slug}")

    logger.error(f"❌ FIND_PROJECT: Project '{project_slug}' not found in any team")
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found"
    )


# ==================== АРХИВАЦИЯ ====================

@router.post("/{project_slug}/archive", response_model=ProjectResponse)
async def archive_project(
        project_slug: str,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Архивация проекта

    - Требует прав на удаление проекта (owner)
    - Проект становится доступным только для чтения
    """
    logger.info(f"Archiving project: {project_slug}")

    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user,
            include_archived=True
        )

        if not project_service.can_delete_project(current_user, project):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only project owner can archive the project"
            )

        if project.status == 'archived':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project is already archived"
            )

        project_service.archive_project(project, current_user)

        # Получаем обновленный проект
        updated_project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user,
            include_archived=True
        )

        return ProjectResponse.model_validate(updated_project)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error archiving project: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{project_slug}/restore", response_model=ProjectResponse)
async def restore_project(
        project_slug: str,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Восстановление проекта из архива

    - Только владелец проекта может восстановить
    """
    logger.info(f"Restoring project: {project_slug}")

    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user,
            include_archived=True
        )

        if not project_service.can_delete_project(current_user, project):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only project owner can restore the project"
            )

        if project.status != 'archived':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project is not archived"
            )

        project.status = 'active'
        project.archived_at = None
        project.save()

        return ProjectResponse.model_validate(project)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring project: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== УПРАВЛЕНИЕ УЧАСТНИКАМИ ====================

@router.get("/{project_slug}/members", response_model=List[ProjectMemberResponse])
async def get_project_members(
        project_slug: str,
        include_inactive: bool = Query(False, description="Include inactive members"),
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Получение списка участников проекта"""
    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user
        )

        if not project_service.is_member(current_user, project):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this project"
            )

        members = project_service.get_project_members(project, include_inactive)
        return [ProjectMemberResponse.model_validate(m) for m in members]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project members: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{project_slug}/members", response_model=ProjectMemberResponse)
async def add_project_member(
        project_slug: str,
        member_in: ProjectMemberAdd,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Добавление участника в проект

    - Требует прав на управление участниками (owner/manager)
    - Пользователь должен быть членом команды-владельца проекта
    """
    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user
        )

        # Ищем пользователя по username
        user = user_service.get_user_by_username(member_in.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username '{member_in.username}' not found"
            )

        member = project_service.add_member(
            project=project,
            user=user,
            role_name=member_in.role,
            added_by=current_user
        )

        return ProjectMemberResponse.model_validate(member)
    except HTTPException:
        raise
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


@router.put("/{project_slug}/members/{username}", response_model=ProjectMemberResponse)
async def update_member_role(
        project_slug: str,
        username: str,
        member_in: ProjectMemberUpdate,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Изменение роли участника проекта

    - Требует прав на управление участниками (owner/manager)
    - Нельзя изменить роль владельца (кроме передачи владения)
    """
    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user
        )

        user = user_service.get_user_by_username(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username '{username}' not found"
            )

        member = project_service.change_member_role(
            project=project,
            user=user,
            new_role_name=member_in.role,
            changed_by=current_user
        )

        return ProjectMemberResponse.model_validate(member)
    except HTTPException:
        raise
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


@router.delete("/{project_slug}/members/{username}")
async def remove_project_member(
        project_slug: str,
        username: str,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Удаление участника из проекта

    - Требует прав на управление участниками (owner/manager)
    - Нельзя удалить владельца проекта
    """
    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user
        )

        user = user_service.get_user_by_username(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username '{username}' not found"
            )

        project_service.remove_member(project, user, current_user)
        return {"message": f"User {username} successfully removed from project"}
    except HTTPException:
        raise
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


@router.post("/{project_slug}/transfer-ownership")
async def transfer_ownership(
        project_slug: str,
        transfer_in: ProjectTransferOwnership,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Передача прав владельца проекта

    - Только текущий владелец может передать права
    - Новый владелец должен быть участником проекта
    """
    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user
        )

        new_owner = user_service.get_user_by_username(transfer_in.new_owner_username)
        if not new_owner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username '{transfer_in.new_owner_username}' not found"
            )

        result = project_service.transfer_ownership(
            project=project,
            new_owner=new_owner,
            current_owner=current_user
        )

        return {
            "message": "Ownership transferred successfully",
            "new_owner": result['new_owner'].user.username,
            "old_owner": result['old_owner'].user.username
        }
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except project_service.member_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New owner is not a member of this project"
        )


@router.post("/{project_slug}/invitations/{invitation_id}/accept")
async def accept_project_invitation(
        project_slug: str,  # Добавляем project_slug
        invitation_id: int,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Принятие приглашения в проект
    """
    logger.info(f"=" * 60)
    logger.info(f"ACCEPT PROJECT INVITATION")
    logger.info(f"=" * 60)
    logger.info(f"Project slug: {project_slug}")
    logger.info(f"Invitation ID: {invitation_id}")
    logger.info(f"User: {current_user.username}")

    try:
        # 1. Находим проект для проверки доступа
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user,
            include_archived=True
        )

        # 2. Находим приглашение
        invitation = project_service.invitation_model.get_by_id(invitation_id)

        # 3. Проверяем, что приглашение принадлежит этому проекту
        if invitation.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found for this project"
            )

        # 4. Проверяем, что приглашение адресовано этому пользователю
        if invitation.invited_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This invitation was sent to another user"
            )

        # 5. Принимаем приглашение
        result = project_service.accept_invitation(invitation, current_user)

        return {
            "message": "Invitation accepted successfully",
            "project": ProjectResponse.model_validate(result['project']),
            "member": ProjectMemberResponse.model_validate(result['member'])
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting invitation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{project_slug}/invitations/{invitation_id}/decline")
async def decline_project_invitation(
        project_slug: str,  # Добавляем project_slug
        invitation_id: int,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Отклонение приглашения в проект
    """
    logger.info(f"=" * 60)
    logger.info(f"DECLINE PROJECT INVITATION")
    logger.info(f"=" * 60)
    logger.info(f"Project slug: {project_slug}")
    logger.info(f"Invitation ID: {invitation_id}")
    logger.info(f"User: {current_user.username}")

    try:
        # 1. Находим проект
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user,
            include_archived=True
        )

        # 2. Находим приглашение
        invitation = project_service.invitation_model.get_by_id(invitation_id)

        # 3. Проверяем, что приглашение принадлежит этому проекту
        if invitation.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found for this project"
            )

        # 4. Проверяем, что приглашение адресовано этому пользователю
        if invitation.invited_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot decline this invitation"
            )

        # 5. Отклоняем приглашение
        invitation.status = 'declined'
        invitation.responded_at = datetime.now()
        invitation.save()

        return {"message": "Invitation declined successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error declining invitation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{project_slug}/invitations", response_model=ProjectInvitationResponse)
async def create_invitation(
        project_slug: str,
        invitation_in: ProjectInvitationCreate,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Создание приглашения в проект

    - Требует прав на управление участниками (owner/manager)
    - Приглашать можно только участников команды
    """
    logger.info(f"=" * 60)
    logger.info(f"CREATE PROJECT INVITATION")
    logger.info(f"=" * 60)
    logger.info(f"Project slug: {project_slug}")
    logger.info(f"Username: {invitation_in.username}")
    logger.info(f"Role: {invitation_in.role}")
    logger.info(f"Invited by: {current_user.username}")

    try:
        # 1. Находим проект
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user
        )
        logger.info(f"Found project: {project.id} - {project.name}")

        # 2. Проверяем права на управление участниками
        if not project_service.can_manage_members(current_user, project):
            logger.error(f"User {current_user.username} cannot manage members")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to invite members to this project"
            )

        # 3. Находим пользователя по username
        user = user_service.get_user_by_username(invitation_in.username)
        if not user:
            logger.error(f"User not found: {invitation_in.username}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username '{invitation_in.username}' not found"
            )
        logger.info(f"Found user: {user.username} (ID: {user.id})")

        # 4. Находим участника команды - ИСПРАВЛЕНО!
        team_member = team_service.member_model.select().where(
            (team_service.member_model.team == project.team) &
            (team_service.member_model.user == user)  # Вместо .user.has()
        ).first()

        if not team_member:
            logger.error(f"User {user.username} is not a member of team {project.team.slug}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with username '{invitation_in.username}' is not a member of the team"
            )
        logger.info(f"Found team member: {team_member.id}")

        # 5. Проверяем, не участник ли уже проекта
        existing_member = project_service.member_model.select().where(
            (project_service.member_model.project == project) &
            (project_service.member_model.user == user) &
            (project_service.member_model.is_active == True)
        ).first()

        if existing_member:
            logger.error(f"User {user.username} is already a member of project")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this project"
            )

        # 6. Проверяем, нет ли уже активного приглашения
        existing_invitation = project_service.invitation_model.select().where(
            (project_service.invitation_model.project == project) &
            (project_service.invitation_model.invited_user == user) &
            (project_service.invitation_model.status == 'pending')
        ).first()

        if existing_invitation:
            logger.error(f"Active invitation already exists for user {user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Active invitation already exists for this user"
            )

        # 7. Создаем приглашение
        invitation = project_service.create_invitation(
            project=project,
            invited_by=current_user,
            proposed_role_name=invitation_in.role,
            team_member=team_member
        )
        logger.info(f"✅ Invitation created: {invitation.id}")

        return ProjectInvitationResponse.model_validate(invitation)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating invitation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{project_slug}/stats", response_model=ProjectStatsResponse)
async def get_project_stats(
        project_slug: str,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение статистики по проекту

    - Требует членства в проекте
    """
    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user
        )

        if not project_service.is_member(current_user, project):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this project"
            )

        stats = project_service.get_project_stats(project)
        return ProjectStatsResponse(**stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== ОСНОВНЫЕ ОПЕРАЦИИ ====================

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
        project_in: ProjectCreate,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Создание нового проекта в команде"""
    try:
        team = team_service.get_team_by_slug(project_in.team_slug)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Team with slug '{project_in.team_slug}' not found"
            )

        if not team_service.is_member(current_user, team):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this team"
            )

        result = project_service.create_project(
            team=team,
            name=project_in.name,
            created_by=current_user,
            description=project_in.description,
            initial_graph_data=project_in.initial_graph_data
        )

        return ProjectResponse.model_validate(result['project'])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[ProjectResponse])
async def get_my_projects(
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service)
) -> Any:
    """Получение всех проектов текущего пользователя"""
    projects = project_service.get_user_projects(current_user)
    return [ProjectResponse.model_validate(p) for p in projects if p.status == 'active']


@router.get("/team/{team_slug}", response_model=List[ProjectResponse])
async def get_team_projects(
        team_slug: str,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Получение всех проектов команды"""
    team = team_service.get_team_by_slug(team_slug)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team with slug '{team_slug}' not found"
        )

    if not team_service.is_member(current_user, team):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this team"
        )

    projects = [p for p in team.projects if p.status == 'active']
    return [ProjectResponse.model_validate(p) for p in projects]


@router.get("/{project_slug}", response_model=ProjectDetailResponse)
async def get_project_by_slug(
        project_slug: str,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Получение детальной информации о проекте по slug"""
    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user,
            include_archived=True
        )

        if not project_service.is_member(current_user, project):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this project"
            )

        members = project_service.get_project_members(project)
        user_role = project_service.get_user_role_in_project(current_user, project)
        team = team_service.get_team_by_id(project.team_id)

        project_data = {
            'id': project.id,
            'name': project.name,
            'slug': project.slug,
            'description': project.description,
            'team_id': project.team_id,
            'team_name': team.name if team else None,
            'team_slug': team.slug if team else None,
            'created_by_id': project.created_by_id,
            'created_by_username': project.created_by.username if project.created_by else None,
            'tasks_count': project.tasks_count,
            'members_count': project.members_count,
            'status': project.status,
            'created_at': project.created_at,
            'updated_at': project.updated_at,
            'archived_at': project.archived_at,
            'members': [ProjectMemberResponse.model_validate(m) for m in members],
            'user_role': user_role.name if user_role else None,
            'can_manage_members': project_service.can_manage_members(current_user, project),
            'can_edit_project': project_service.can_edit_project(current_user, project),
            'can_delete_project': project_service.can_delete_project(current_user, project),
            'can_create_tasks': project_service.can_create_tasks(current_user, project),
            'settings': project.settings_dict,
        }

        return ProjectDetailResponse(**project_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_project_by_slug: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/{project_slug}", response_model=ProjectResponse)
async def update_project(
        project_slug: str,
        project_in: ProjectUpdate,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Обновление информации о проекте"""
    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user
        )

        updated_project = project_service.update_project(
            project=project,
            updated_by=current_user,
            name=project_in.name,
            description=project_in.description,
            settings=project_in.settings
        )

        return ProjectResponse.model_validate(updated_project)
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


@router.delete("/{project_slug}")
async def delete_project(
        project_slug: str,
        current_user: User = Depends(get_current_active_user),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Удаление проекта (мягкое удаление)"""
    try:
        project = await find_project_by_slug(
            project_slug,
            project_service,
            team_service,
            current_user
        )

        project_service.delete_project(project, current_user)
        return {"message": "Project successfully deleted"}
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
