# core/api/routes/tasks.py - ПОЛНЫЙ ФАЙЛ С ПРАВИЛЬНЫМ ПОРЯДКОМ

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...db.models.project import Project
from ...db.models.task import Task
from ...db.models.user import User
from ...services.NoteService import NoteService
from ...services.ProjectService import ProjectService
from ...services.TaskService import TaskService
from ...services.TeamService import TeamService
from ...services.UserService import UserService
from ..deps import (
    get_current_active_user,
    get_note_service,
    get_project_service,
    get_task_service,
    get_team_service,
    get_user_service,
)
from ..schemas.note import NoteCreate, NoteResponse
from ..schemas.project import ProjectGraphData
from ..schemas.task import (
    DependencyActionCreate,
    DependencyActionResponse,
    ProjectGraphResponse,
    TaskCreate,
    TaskDependencyCreate,
    TaskDependencyResponse,
    TaskDependencyUpdate,
    TaskDetailResponse,
    TaskEventResponse,
    TaskResponse,
    TaskStatsResponse,
    TaskStatusUpdate,
    TaskUpdate,
    UserTaskStatsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/projects/{project_slug}/tasks', tags=['tasks'])


# ==================== ХЕЛПЕРЫ ====================


def task_response_with_readiness(task: Task, task_service: TaskService) -> TaskResponse:
    """Сериализация задачи с производными полями готовности."""
    task_data = TaskResponse.model_validate(task)
    readiness = task_service.get_readiness_info(task)
    task_data.is_ready = readiness['is_ready']
    task_data.blocking_task_ids = readiness['blocking_task_ids']
    task_data.blocked_reason = readiness['blocked_reason']
    return task_data


def dependency_error_response(error: ValueError) -> HTTPException:
    """Стабильные error_code для конфликтов зависимостей."""
    message = str(error)
    if 'cycle' in message.lower():
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'error_code': 'DEPENDENCY_CYCLE',
                'message': message,
            },
        )
    if message.startswith('TASK_NOT_READY'):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'error_code': 'TASK_NOT_READY',
                'message': message,
            },
        )
    if message.startswith('UNKNOWN_ACTION_TYPE'):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'error_code': 'UNKNOWN_ACTION_TYPE',
                'message': message,
            },
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def forbidden_response(error_code: str, message: str) -> HTTPException:
    """Стабильный формат 403 для фронта."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={'error_code': error_code, 'message': message},
    )


def permission_error_response(error: PermissionError) -> HTTPException:
    """Маппинг PermissionError сервисов в стабильные коды."""
    message = str(error)
    lowered = message.lower()
    if 'task graph' in lowered or 'dependencies' in lowered:
        return forbidden_response('task_graph_forbidden', message)
    if 'status' in lowered:
        return forbidden_response('task_status_forbidden', message)
    if 'delete' in lowered:
        return forbidden_response('task_delete_forbidden', message)
    if 'create' in lowered:
        return forbidden_response('task_create_forbidden', message)
    return forbidden_response('task_field_edit_forbidden', message)


def note_forbidden_response(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={'error_code': 'note_forbidden', 'message': message},
    )


def note_not_found_response(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={'error_code': 'note_not_found', 'message': message},
    )


async def get_project_by_slug(
    project_slug: str,
    project_service: ProjectService,
    team_service: TeamService,
    current_user: User,
) -> Project:
    """Получение проекта по slug с проверкой доступа"""
    user_teams = team_service.get_user_teams(current_user)

    for team in user_teams:
        project = project_service.get_project_by_slug(project_slug, team)
        if project:
            if not project_service.is_member(current_user, project):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail='You are not a member of this project',
                )
            return project

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail='Project not found'
    )


# ==================== !!! ВАЖНО: СПЕЦИАЛЬНЫЕ ЭНДПОИНТЫ ПЕРВЫМИ !!! ====================
# Эти эндпоинты НЕ должны содержать {task_id} в пути


@router.get('/graph', response_model=ProjectGraphResponse)
async def get_project_graph(
    project_slug: str,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """Получение графа проекта для ReactFlow"""
    logger.info(f'Getting project graph for {project_slug}')
    project = await get_project_by_slug(
        project_slug, project_service, team_service, current_user
    )
    graph_data = task_service.get_project_graph(project)
    return graph_data


@router.put('/graph')
async def save_project_graph(
    project_slug: str,
    graph_data: ProjectGraphData,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """Сохранение графа (автосохранение React Flow): узлы, рёбра, viewport."""
    try:
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )
        if not project_service.can_manage_task_graph(current_user, project):
            raise forbidden_response(
                'task_graph_forbidden',
                "You don't have permission to save this task graph",
            )
        graph_dict = graph_data.model_dump(exclude_none=True)
        nodes = graph_dict.get('nodes', [])
        for node in nodes:
            task_id = node.get('id')
            position = node.get('position', {})
            if task_id and isinstance(task_id, (int, str)):
                try:
                    task = Task.get_by_id(int(task_id))
                    if task.project_id == project.id:
                        task.position_x = position.get('x', task.position_x)
                        task.position_y = position.get('y', task.position_y)
                        task.save()
                except (Task.DoesNotExist, ValueError):
                    logger.warning('Task %s not found or invalid', task_id)
        project_service.save_graph_data(project, graph_dict, current_user)
        return {'message': 'Graph saved successfully'}
    except HTTPException:
        raise
    except PermissionError as e:
        raise permission_error_response(e)
    except Exception as e:
        logger.error('Error saving project graph: %s', e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get('/stats', response_model=TaskStatsResponse)
async def get_project_task_stats(
    project_slug: str,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """Статистика по задачам проекта"""
    logger.info(f'Getting task stats for project {project_slug}')
    project = await get_project_by_slug(
        project_slug, project_service, team_service, current_user
    )
    stats = task_service.get_task_stats(project)
    return stats


@router.get('/stats/user/{username}', response_model=UserTaskStatsResponse)
async def get_user_task_stats(
    project_slug: str,
    username: str,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
    user_service: UserService = Depends(get_user_service),
) -> Any:
    """Статистика по задачам пользователя в проекте"""
    logger.info(f'Getting task stats for user {username}')
    project = await get_project_by_slug(
        project_slug, project_service, team_service, current_user
    )

    user = user_service.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{username}' not found"
        )

    stats = task_service.get_user_task_stats(user, project)
    return stats


# ==================== ЭНДПОИНТЫ ДЛЯ РАБОТЫ С ЗАВИСИМОСТЯМИ ====================
# Эти эндпоинты используют dependency_id, НЕ task_id


@router.delete('/dependencies/{dependency_id}')
async def delete_dependency(
    project_slug: str,
    dependency_id: int,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """Удаление зависимости"""
    logger.info(f'Deleting dependency {dependency_id}')

    try:
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )
        dependency = task_service.dependency_model.get_by_id(dependency_id)

        if dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Dependency not found in this project',
            )

        task_service.delete_dependency(dependency, current_user)
        return {'message': 'Dependency successfully deleted'}
    except task_service.dependency_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Dependency not found'
        )
    except PermissionError as e:
        raise permission_error_response(e)


@router.patch('/dependencies/{dependency_id}', response_model=TaskDependencyResponse)
async def update_dependency(
    project_slug: str,
    dependency_id: int,
    dependency_in: TaskDependencyUpdate,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """Обновление типа или описания зависимости без пересоздания ребра."""
    try:
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )
        dependency = task_service.dependency_model.get_by_id(dependency_id)

        if dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Dependency not found in this project',
            )

        updated = task_service.update_dependency(
            dependency=dependency,
            updated_by=current_user,
            dependency_type=dependency_in.dependency_type,
            description=dependency_in.description,
        )
        return TaskDependencyResponse.model_validate(updated)
    except task_service.dependency_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Dependency not found'
        )
    except PermissionError as e:
        raise permission_error_response(e)
    except ValueError as e:
        raise dependency_error_response(e)


@router.post(
    '/dependencies/{dependency_id}/actions', response_model=DependencyActionResponse
)
async def add_dependency_action(
    project_slug: str,
    dependency_id: int,
    action_in: DependencyActionCreate,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
    user_service: UserService = Depends(get_user_service),
) -> Any:
    """Добавление действия на зависимость."""
    try:
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )
        dependency = task_service.dependency_model.get_by_id(dependency_id)
        if dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Dependency not found in this project',
            )

        target_user = None
        if action_in.target_user_username:
            target_user = user_service.get_user_by_username(
                action_in.target_user_username
            )
            if not target_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User '{action_in.target_user_username}' not found",
                )

        action = task_service.add_dependency_action(
            dependency=dependency,
            action_type_code=action_in.action_type_code,
            created_by=current_user,
            target_user=target_user,
            target_status_name=action_in.target_status,
            message_template=action_in.message_template,
            delay_minutes=action_in.delay_minutes,
            execute_order=action_in.execute_order,
        )
        return DependencyActionResponse.model_validate(action)
    except task_service.dependency_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Dependency not found'
        )
    except PermissionError as e:
        raise permission_error_response(e)
    except ValueError as e:
        raise dependency_error_response(e)


@router.delete('/dependencies/actions/{action_id}')
async def remove_dependency_action(
    project_slug: str,
    action_id: int,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """Мягкое удаление действия с зависимости."""
    try:
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )
        action = task_service.action_model.get_by_id(action_id)
        if action.dependency.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Action not found in this project',
            )

        task_service.remove_dependency_action(action, current_user)
        return {'message': 'Action successfully removed'}
    except task_service.action_model.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Action not found'
        )
    except PermissionError as e:
        raise permission_error_response(e)


# ==================== ОСНОВНЫЕ ОПЕРАЦИИ С ЗАДАЧАМИ ====================


@router.post('', response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    project_slug: str,
    task_in: TaskCreate,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
    user_service: UserService = Depends(get_user_service),
) -> Any:
    """
    Создание новой задачи в проекте

    - Требует прав owner/manager
    """
    logger.info(f'Creating task in project {project_slug}')

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )

        if not project_service.can_create_tasks(current_user, project):
            raise forbidden_response(
                'task_create_forbidden',
                "You don't have permission to create tasks in this project",
            )

        # 2. Находим исполнителя, если указан
        assignee = None
        if task_in.assignee_username:
            assignee = user_service.get_user_by_username(task_in.assignee_username)
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with username '{task_in.assignee_username}' not found",
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
            metadata=task_in.metadata,
        )

        return task_response_with_readiness(result['task'], task_service)
    except HTTPException:
        raise
    except PermissionError as e:
        raise permission_error_response(e)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        logger.error(f'Error creating task: {e}', exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get('', response_model=List[TaskResponse])
async def get_project_tasks(
    project_slug: str,
    status_name: Optional[str] = Query(None, description='Filter by status'),
    assignee_username: Optional[str] = Query(None, description='Filter by assignee'),
    creator_username: Optional[str] = Query(None, description='Filter by creator'),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
    user_service: UserService = Depends(get_user_service),
) -> Any:
    """
    Получение списка задач проекта с фильтрацией

    - Требует членства в проекте
    """
    logger.info(f'Getting tasks for project {project_slug}')

    # 1. Получаем проект
    project = await get_project_by_slug(
        project_slug, project_service, team_service, current_user
    )

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
        offset=offset,
    )

    # 4. Добавляем флаг is_ready
    result = []
    for task in tasks:
        result.append(task_response_with_readiness(task, task_service))

    return result


@router.get('/{task_id}/notes', response_model=List[NoteResponse])
async def get_task_notes(
    project_slug: str,
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    note_service: NoteService = Depends(get_note_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """Получение заметок задачи."""
    try:
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )
        notes = note_service.list_task_notes(project, task_id, current_user)
        return [NoteResponse.model_validate(note) for note in notes]
    except PermissionError as e:
        raise note_forbidden_response(str(e))
    except ValueError as e:
        raise note_not_found_response(str(e))


@router.post('/{task_id}/notes', response_model=NoteResponse)
async def create_task_note(
    project_slug: str,
    task_id: int,
    note_in: NoteCreate,
    current_user: User = Depends(get_current_active_user),
    note_service: NoteService = Depends(get_note_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """Создание заметки задачи."""
    try:
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )
        note = note_service.create_task_note(
            project=project,
            task_id=task_id,
            author=current_user,
            content=note_in.content,
        )
        return NoteResponse.model_validate(note)
    except PermissionError as e:
        raise note_forbidden_response(str(e))
    except ValueError as e:
        raise note_not_found_response(str(e))


@router.get('/{task_id}', response_model=TaskDetailResponse)
async def get_task_by_id(
    project_slug: str,
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """Получение детальной информации о задаче"""

    project = await get_project_by_slug(
        project_slug, project_service, team_service, current_user
    )
    task = task_service.get_task_by_id(project, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    dependencies = task_service.get_task_dependencies(task)

    task_data = TaskDetailResponse.model_validate(task)
    readiness = task_service.get_readiness_info(task)
    task_data.is_ready = readiness['is_ready']
    task_data.blocking_task_ids = readiness['blocking_task_ids']
    task_data.blocked_reason = readiness['blocked_reason']
    task_data.incoming_dependencies = [
        TaskDependencyResponse.model_validate(dep) for dep in dependencies['incoming']
    ]
    task_data.outgoing_dependencies = [
        TaskDependencyResponse.model_validate(dep) for dep in dependencies['outgoing']
    ]
    task_data.events = [
        TaskEventResponse.model_validate(event)
        for event in task.events.order_by(
            task_service.event_model.created_at.desc()
        ).limit(50)
    ]

    return task_data


@router.put('/{task_id}', response_model=TaskResponse)
async def update_task(
    project_slug: str,
    task_id: int,
    task_in: TaskUpdate,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
    user_service: UserService = Depends(get_user_service),
) -> Any:
    """Обновление информации о задаче"""
    logger.info(f'Updating task {task_id} in project {project_slug}')

    try:
        # Получаем проект и задачу
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )
        task = task_service.get_task_by_id(project, task_id)
        if not task:
            raise HTTPException(status_code=404, detail='Task not found')

        if not project_service.can_edit_task(current_user, task):
            raise forbidden_response(
                'task_field_edit_forbidden',
                "You don't have permission to edit task fields",
            )

        # 3. Находим нового исполнителя, если указан
        assignee = None
        if task_in.assignee_username:
            assignee = user_service.get_user_by_username(task_in.assignee_username)
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with username '{task_in.assignee_username}' not found",
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
            metadata=task_in.metadata,
        )

        return task_response_with_readiness(updated_task, task_service)

    except PermissionError as e:
        raise permission_error_response(e)
    except ValueError as e:
        raise dependency_error_response(e)


@router.delete('/{task_id}')
async def delete_task(
    project_slug: str,
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """
    Удаление задачи

    - Требует прав owner/manager
    """
    logger.info(f'Deleting task {task_id} from project {project_slug}')

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )

        # 2. Получаем задачу
        task = task_service.get_task_by_id(project, task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail='Task not found'
            )

        # 3. Проверяем права через ProjectService
        if not project_service.can_delete_task(current_user, task):
            raise forbidden_response(
                'task_delete_forbidden',
                "You don't have permission to delete this task",
            )

        # 4. Удаляем задачу
        task.delete_instance()

        return {'message': 'Task successfully deleted'}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error deleting task: {e}', exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post('/{task_id}/status')
async def change_task_status(
    project_slug: str,
    task_id: int,
    status_update: TaskStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """
    Изменение статуса задачи

    - Требует членства в проекте
    - При завершении задачи выполняются действия на исходящих ребрах
    """
    logger.info(f'Changing task {task_id} status to {status_update.status}')

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )

        # 2. Получаем задачу
        task = task_service.get_task_by_id(project, task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail='Task not found'
            )

        # 3. Изменяем статус
        result = task_service.change_task_status(
            task=task, new_status_name=status_update.status, changed_by=current_user
        )

        return {
            'task': task_response_with_readiness(result['task'], task_service),
            'status_changed': result['status_changed'],
            'old_status': result['old_status'].name,
            'new_status': result['new_status'].name,
            'actions_executed': result.get('actions_executed', []),
        }

    except PermissionError as e:
        raise permission_error_response(e)
    except ValueError as e:
        raise dependency_error_response(e)


# ==================== УПРАВЛЕНИЕ ЗАВИСИМОСТЯМИ ====================


@router.get(
    '/{task_id}/dependencies', response_model=Dict[str, List[TaskDependencyResponse]]
)
async def get_task_dependencies(
    project_slug: str,
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """
    Получение всех зависимостей задачи

    - Входящие: задачи, от которых зависит данная
    - Исходящие: задачи, которые зависят от данной
    """
    logger.info(f'Getting dependencies for task {task_id}')

    # 1. Получаем проект
    project = await get_project_by_slug(
        project_slug, project_service, team_service, current_user
    )

    # 2. Получаем задачу
    task = task_service.get_task_by_id(project, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Task not found'
        )

    # 3. Получаем зависимости
    dependencies = task_service.get_task_dependencies(task)

    return {
        'incoming': [
            TaskDependencyResponse.model_validate(d) for d in dependencies['incoming']
        ],
        'outgoing': [
            TaskDependencyResponse.model_validate(d) for d in dependencies['outgoing']
        ],
    }


@router.post('/{task_id}/dependencies', response_model=TaskDependencyResponse)
async def create_dependency(
    project_slug: str,
    task_id: int,
    dependency_in: TaskDependencyCreate,
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """
    Создание зависимости от текущей задачи к целевой

    - Требует прав на создание зависимостей
    - Требует прав owner/manager
    - Проверяет на циклические зависимости
    """
    logger.info(
        f'Creating dependency from task {task_id} to task {dependency_in.target_task_id}'
    )

    try:
        # 1. Получаем проект
        project = await get_project_by_slug(
            project_slug, project_service, team_service, current_user
        )

        # 2. Получаем исходную задачу
        source_task = task_service.get_task_by_id(project, task_id)
        if not source_task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail='Source task not found'
            )

        # 3. Получаем целевую задачу
        target_task = task_service.get_task_by_id(project, dependency_in.target_task_id)
        if not target_task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail='Target task not found'
            )

        # 4. Создаем зависимость
        dependency = task_service.create_dependency(
            source_task=source_task,
            target_task=target_task,
            created_by=current_user,
            dependency_type=dependency_in.dependency_type,
            description=dependency_in.description,
        )

        return TaskDependencyResponse.model_validate(dependency)

    except PermissionError as e:
        raise permission_error_response(e)
    except ValueError as e:
        raise dependency_error_response(e)


# ==================== СОБЫТИЯ ====================


@router.get('/{task_id}/events', response_model=List[TaskEventResponse])
async def get_task_events(
    project_slug: str,
    task_id: int,
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    team_service: TeamService = Depends(get_team_service),
) -> Any:
    """
    Получение истории событий задачи

    - Требует членства в проекте
    """
    logger.info(f'Getting events for task {task_id}')

    # 1. Получаем проект
    project = await get_project_by_slug(
        project_slug, project_service, team_service, current_user
    )

    # 2. Получаем задачу
    task = task_service.get_task_by_id(project, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail='Task not found'
        )

    # 3. Получаем события
    events = (
        task_service.event_model.select()
        .where(task_service.event_model.task == task)
        .order_by(task_service.event_model.created_at.desc())
        .limit(limit)
    )

    return [TaskEventResponse.model_validate(e) for e in events]
