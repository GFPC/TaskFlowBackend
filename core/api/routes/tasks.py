# core/api/routes/tasks.py - ПОЛНЫЙ ФАЙЛ С ПРАВИЛЬНЫМ ПОРЯДКОМ

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Any, List, Optional, Dict
from datetime import datetime

from ...services.TaskService import TaskService
from ...services.ProjectService import ProjectService
from ...services.TeamService import TeamService
from ...services.UserService import UserService
from ...db.models.user import User
from ...db.models.project import Project
from ..schemas.task import (
    TaskCreate, TaskUpdate, TaskResponse, TaskDetailResponse,
    TaskStatusUpdate, TaskDependencyCreate, TaskDependencyResponse,
    DependencyActionCreate, DependencyActionResponse,
    TaskEventResponse, ProjectGraphResponse,
    TaskStatsResponse, UserTaskStatsResponse
)
from ..deps import get_task_service, get_project_service, get_team_service, get_user_service, get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_slug}/tasks", tags=["tasks"])


# ==================== ХЕЛПЕРЫ ====================

async def get_project_by_slug(
        project_slug: str,
        project_service: ProjectService,
        team_service: TeamService,
        current_user: User
) -> Project:
    """Получение проекта по slug с проверкой доступа"""
    user_teams = team_service.get_user_teams(current_user)

    for team in user_teams:
        project = project_service.get_project_by_slug(project_slug, team)
        if project:
            if not project_service.is_member(current_user, project):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not a member of this project"
                )
            return project

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found"
    )


# ==================== !!! ВАЖНО: СПЕЦИАЛЬНЫЕ ЭНДПОИНТЫ ПЕРВЫМИ !!! ====================
# Эти эндпоинты НЕ должны содержать {task_id} в пути

@router.get("/graph", response_model=ProjectGraphResponse)
async def get_project_graph(
        project_slug: str,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Получение графа проекта для ReactFlow"""
    logger.info(f"Getting project graph for {project_slug}")
    project = await get_project_by_slug(project_slug, project_service, team_service, current_user)
    graph_data = task_service.get_project_graph(project)
    return graph_data


@router.get("/stats", response_model=TaskStatsResponse)
async def get_project_task_stats(
        project_slug: str,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Статистика по задачам проекта"""
    logger.info(f"Getting task stats for project {project_slug}")
    project = await get_project_by_slug(project_slug, project_service, team_service, current_user)
    stats = task_service.get_task_stats(project)
    return stats


@router.get("/stats/user/{username}", response_model=UserTaskStatsResponse)
async def get_user_task_stats(
        project_slug: str,
        username: str,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """Статистика по задачам пользователя в проекте"""
    logger.info(f"Getting task stats for user {username}")
    project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

    user = user_service.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found"
        )

    stats = task_service.get_user_task_stats(user, project)
    return stats


# ==================== ЭНДПОИНТЫ ДЛЯ РАБОТЫ С ЗАВИСИМОСТЯМИ ====================
# Эти эндпоинты используют dependency_id, НЕ task_id

@router.delete("/dependencies/{dependency_id}")
async def delete_dependency(
        project_slug: str,
        dependency_id: int,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Удаление зависимости"""
    logger.info(f"Deleting dependency {dependency_id}")

    try:
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)
        dependency = task_service.dependency_model.get_by_id(dependency_id)

        if dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dependency not found in this project"
            )

        task_service.delete_dependency(dependency, current_user)
        return {"message": "Dependency successfully deleted"}
    except task_service.dependency_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dependency not found"
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.post("/dependencies/{dependency_id}/actions", response_model=DependencyActionResponse)
async def add_dependency_action(
        project_slug: str,
        dependency_id: int,
        action_in: DependencyActionCreate,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """Добавление действия к зависимости"""
    logger.info(f"Adding action to dependency {dependency_id}")

    try:
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)
        dependency = task_service.dependency_model.get_by_id(dependency_id)

        if dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dependency not found in this project"
            )

        target_user = None
        if action_in.target_user_username:
            target_user = user_service.get_user_by_username(action_in.target_user_username)
            if not target_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{action_in.target_user_username}' not found"
                )

        action = task_service.add_dependency_action(
            dependency=dependency,
            action_type_code=action_in.action_type_code,
            created_by=current_user,
            target_user=target_user,
            target_status_name=action_in.target_status,
            message_template=action_in.message_template,
            delay_minutes=action_in.delay_minutes,
            execute_order=action_in.execute_order
        )

        return DependencyActionResponse.model_validate(action)
    except task_service.dependency_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dependency not found"
        )
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


@router.delete("/dependencies/actions/{action_id}")
async def remove_dependency_action(
        project_slug: str,
        action_id: int,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Удаление действия с зависимости"""
    logger.info(f"Removing action {action_id}")

    try:
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)
        action = task_service.action_model.get_by_id(action_id)

        if action.dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Action not found in this project"
            )

        task_service.remove_dependency_action(action, current_user)
        return {"message": "Action successfully removed"}
    except task_service.action_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action not found"
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )

# ==================== ОСНОВНЫЕ ОПЕРАЦИИ С ЗАДАЧАМИ ====================

@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
        project_slug: str,
        task_in: TaskCreate,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Создание новой задачи в проекте

    - Требует прав на создание задач (все кроме observer)
    """
    logger.info(f"Creating task in project {project_slug}")

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

        if not project_service.can_create_tasks(current_user, project):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create tasks in this project"
            )

        # 2. Находим исполнителя, если указан
        assignee = None
        if task_in.assignee_username:
            assignee = user_service.get_user_by_username(task_in.assignee_username)
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with username '{task_in.assignee_username}' not found"
                )

        # 3. Создаем задачу
        result = task_service.create_task(
            project=project,
            name=task_in.name,
            creator=current_user,
            description=task_in.description,
            assignee=assignee,
            deadline=task_in.deadline,
            priority=task_in.priority,
            position_x=task_in.position_x,
            position_y=task_in.position_y,
            metadata=task_in.metadata
        )

        return TaskResponse.model_validate(result['task'])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Error creating task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("", response_model=List[TaskResponse])
async def get_project_tasks(
        project_slug: str,
        status_name: Optional[str] = Query(None, description="Filter by status"),
        assignee_username: Optional[str] = Query(None, description="Filter by assignee"),
        creator_username: Optional[str] = Query(None, description="Filter by creator"),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Получение списка задач проекта с фильтрацией

    - Требует членства в проекте
    """
    logger.info(f"Getting tasks for project {project_slug}")

    # 1. Получаем проект
    project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

    # 2. Преобразуем username в ID для фильтрации
    assignee_id = None
    if assignee_username:
        user = user_service.get_user_by_username(assignee_username)
        assignee_id = user.id if user else None

    creator_id = None
    if creator_username:
        user = user_service.get_user_by_username(creator_username)
        creator_id = user.id if user else None

    # 3. Получаем задачи
    tasks = task_service.get_project_tasks(
        project=project,
        status_name=status_name,
        assignee_id=assignee_id,
        creator_id=creator_id,
        limit=limit,
        offset=offset
    )

    # 4. Добавляем флаг is_ready
    result = []
    for task in tasks:
        task_data = TaskResponse.model_validate(task)
        task_data.is_ready = task_service.check_task_readiness(task)
        result.append(task_data)

    return result


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task_by_id(
        project_slug: str,
        task_id: int,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """Получение детальной информации о задаче"""

    project = await get_project_by_slug(project_slug, project_service, team_service, current_user)
    task = task_service.get_task_by_id(project, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    dependencies = task_service.get_task_dependencies(task)

    task_data = TaskDetailResponse.model_validate(task)
    # ВАЖНО: вычисляем is_ready!
    task_data.is_ready = task_service.check_task_readiness(task)
    task_data.incoming_dependencies = [
        TaskDependencyResponse.model_validate(dep) for dep in dependencies['incoming']
    ]
    task_data.outgoing_dependencies = [
        TaskDependencyResponse.model_validate(dep) for dep in dependencies['outgoing']
    ]

    return task_data


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
        project_slug: str,
        task_id: int,
        task_in: TaskUpdate,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """Обновление информации о задаче"""
    logger.info(f"Updating task {task_id} in project {project_slug}")

    try:
        # Получаем проект и задачу
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)
        task = task_service.get_task_by_id(project, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # ПРОВЕРКА: Developer может менять только статус, не название!
        role = project_service.get_user_role_in_project(current_user, project)
        if role and role.name == 'developer':
            # Developer не может менять название задачи
            if task_in.name is not None and task_in.name != task.name:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Developer cannot change task name"
                )

        # 3. Находим нового исполнителя, если указан
        assignee = None
        if task_in.assignee_username:
            assignee = user_service.get_user_by_username(task_in.assignee_username)
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with username '{task_in.assignee_username}' not found"
                )

        # 4. Обновляем задачу
        updated_task = task_service.update_task(
            task=task,
            updated_by=current_user,
            name=task_in.name,
            description=task_in.description,
            assignee=assignee,
            deadline=task_in.deadline,
            priority=task_in.priority,
            position_x=task_in.position_x,
            position_y=task_in.position_y,
            metadata=task_in.metadata
        )

        return TaskResponse.model_validate(updated_task)

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


@router.delete("/{task_id}")
async def delete_task(
        project_slug: str,
        task_id: int,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Удаление задачи

    - Требует прав на удаление задачи (owner/manager или создатель)
    """
    logger.info(f"Deleting task {task_id} from project {project_slug}")

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

        # 2. Получаем задачу
        task = task_service.get_task_by_id(project, task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )

        # 3. Проверяем права через ProjectService
        if not project_service.can_delete_task(current_user, task):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this task"
            )

        # 4. Удаляем задачу
        task.delete_instance()

        return {"message": "Task successfully deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{task_id}/status")
async def change_task_status(
        project_slug: str,
        task_id: int,
        status_update: TaskStatusUpdate,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Изменение статуса задачи

    - Требует прав на редактирование задачи
    - При завершении задачи выполняются действия на исходящих ребрах
    """
    logger.info(f"Changing task {task_id} status to {status_update.status}")

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

        # 2. Получаем задачу
        task = task_service.get_task_by_id(project, task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )

        # 3. Изменяем статус
        result = task_service.change_task_status(
            task=task,
            new_status_name=status_update.status,
            changed_by=current_user
        )

        return {
            "task": TaskResponse.model_validate(result['task']),
            "status_changed": result['status_changed'],
            "old_status": result['old_status'].name,
            "new_status": result['new_status'].name,
            "actions_executed": result.get('actions_executed', [])
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


# ==================== УПРАВЛЕНИЕ ЗАВИСИМОСТЯМИ ====================

@router.get("/{task_id}/dependencies", response_model=Dict[str, List[TaskDependencyResponse]])
async def get_task_dependencies(
        project_slug: str,
        task_id: int,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение всех зависимостей задачи

    - Входящие: задачи, от которых зависит данная
    - Исходящие: задачи, которые зависят от данной
    """
    logger.info(f"Getting dependencies for task {task_id}")

    # 1. Получаем проект
    project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

    # 2. Получаем задачу
    task = task_service.get_task_by_id(project, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    # 3. Получаем зависимости
    dependencies = task_service.get_task_dependencies(task)

    return {
        'incoming': [TaskDependencyResponse.model_validate(d) for d in dependencies['incoming']],
        'outgoing': [TaskDependencyResponse.model_validate(d) for d in dependencies['outgoing']]
    }


@router.post("/{task_id}/dependencies", response_model=TaskDependencyResponse)
async def create_dependency(
        project_slug: str,
        task_id: int,
        dependency_in: TaskDependencyCreate,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Создание зависимости от текущей задачи к целевой

    - Требует прав на создание зависимостей
    - Проверяет на циклические зависимости
    """
    logger.info(f"Creating dependency from task {task_id} to task {dependency_in.target_task_id}")

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

        # 2. Получаем исходную задачу
        source_task = task_service.get_task_by_id(project, task_id)
        if not source_task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source task not found"
            )

        # 3. Получаем целевую задачу
        target_task = task_service.get_task_by_id(project, dependency_in.target_task_id)
        if not target_task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target task not found"
            )

        # 4. Создаем зависимость
        dependency = task_service.create_dependency(
            source_task=source_task,
            target_task=target_task,
            created_by=current_user,
            dependency_type=dependency_in.dependency_type,
            description=dependency_in.description
        )

        return TaskDependencyResponse.model_validate(dependency)

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


@router.delete("/dependencies/{dependency_id}")
async def delete_dependency(
        project_slug: str,
        dependency_id: int,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Удаление зависимости

    - Требует прав на удаление зависимостей (owner/manager)
    """
    logger.info(f"Deleting dependency {dependency_id}")

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

        # 2. Получаем зависимость
        dependency = task_service.dependency_model.get_by_id(dependency_id)

        # 3. Проверяем, что зависимость из этого проекта
        if dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dependency not found in this project"
            )

        # 4. Удаляем зависимость
        task_service.delete_dependency(dependency, current_user)

        return {"message": "Dependency successfully deleted"}

    except task_service.dependency_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dependency not found"
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


# ==================== ДЕЙСТВИЯ НА ЗАВИСИМОСТЯХ ====================

@router.post("/dependencies/{dependency_id}/actions", response_model=DependencyActionResponse)
async def add_dependency_action(
        project_slug: str,
        dependency_id: int,
        action_in: DependencyActionCreate,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Добавление действия к зависимости

    - Требует прав на редактирование любых задач (owner/manager)
    """
    logger.info(f"Adding action to dependency {dependency_id}")

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

        # 2. Получаем зависимость
        dependency = task_service.dependency_model.get_by_id(dependency_id)

        # 3. Проверяем, что зависимость из этого проекта
        if dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dependency not found in this project"
            )

        # 4. Находим целевого пользователя, если указан
        target_user = None
        if action_in.target_user_username:
            target_user = user_service.get_user_by_username(action_in.target_user_username)
            if not target_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with username '{action_in.target_user_username}' not found"
                )

        # 5. Создаем действие
        action = task_service.add_dependency_action(
            dependency=dependency,
            action_type_code=action_in.action_type_code,
            created_by=current_user,
            target_user=target_user,
            target_status_name=action_in.target_status,
            message_template=action_in.message_template,
            delay_minutes=action_in.delay_minutes,
            execute_order=action_in.execute_order
        )

        return DependencyActionResponse.model_validate(action)

    except task_service.dependency_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dependency not found"
        )
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


@router.delete("/dependencies/actions/{action_id}")
async def remove_dependency_action(
        project_slug: str,
        action_id: int,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Удаление действия с зависимости

    - Требует прав на редактирование любых задач (owner/manager)
    """
    logger.info(f"Removing action {action_id} from dependency")

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

        # 2. Получаем действие
        action = task_service.action_model.get_by_id(action_id)

        # 3. Проверяем, что действие принадлежит зависимости из этого проекта
        if action.dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Action not found in this project"
            )

        # 4. Удаляем действие
        task_service.remove_dependency_action(action, current_user)

        return {"message": "Action successfully removed"}

    except task_service.action_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action not found"
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )



# ==================== СОБЫТИЯ ====================

@router.get("/{task_id}/events", response_model=List[TaskEventResponse])
async def get_task_events(
        project_slug: str,
        task_id: int,
        limit: int = Query(50, ge=1, le=500),
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service)
) -> Any:
    """
    Получение истории событий задачи

    - Требует членства в проекте
    """
    logger.info(f"Getting events for task {task_id}")

    # 1. Получаем проект
    project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

    # 2. Получаем задачу
    task = task_service.get_task_by_id(project, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    # 3. Получаем события
    events = task_service.event_model.select().where(
        task_service.event_model.task == task
    ).order_by(
        task_service.event_model.created_at.desc()
    ).limit(limit)

    return [TaskEventResponse.model_validate(e) for e in events]

@router.get("/stats/user/{username}", response_model=UserTaskStatsResponse)
async def get_user_task_stats(
        project_slug: str,
        username: str,
        current_user: User = Depends(get_current_active_user),
        task_service: TaskService = Depends(get_task_service),
        project_service: ProjectService = Depends(get_project_service),
        team_service: TeamService = Depends(get_team_service),
        user_service: UserService = Depends(get_user_service)
) -> Any:
    """
    Получение статистики по задачам пользователя в проекте

    - Требует членства в проекте
    """
    logger.info(f"Getting task stats for user {username} in project {project_slug}")

    # 1. Получаем проект
    project = await get_project_by_slug(project_slug, project_service, team_service, current_user)

    # 2. Получаем пользователя
    user = user_service.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with username '{username}' not found"
        )

    # 3. Получаем статистику
    stats = task_service.get_user_task_stats(user, project)

    return stats