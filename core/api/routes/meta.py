from typing import Any

from fastapi import APIRouter, Depends

from ...services.TaskService import TaskService
from ..deps import get_task_service

router = APIRouter(prefix='/meta', tags=['meta'])


@router.get('/task-graph')
async def get_task_graph_meta(
    task_service: TaskService = Depends(get_task_service),
) -> Any:
    """Справочники и стабильные коды ошибок для графа задач."""
    return task_service.get_graph_meta()
