# core/api/schemas/task.py
import json

from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ------------------- СТАТУСЫ ЗАДАЧ -------------------

class TaskStatusResponse(BaseModel):
    """Схема статуса задачи"""
    id: int
    name: str
    display_name: str
    color: str
    order: int
    is_final: bool
    is_blocking: bool

    model_config = ConfigDict(from_attributes=True)


# ------------------- ТИПЫ ДЕЙСТВИЙ -------------------

class DependencyActionTypeResponse(BaseModel):
    """Схема типа действия на зависимости"""
    id: int
    name: str
    code: str
    description: Optional[str] = None
    requires_target_user: bool
    requires_template: bool
    supports_delay: bool

    model_config = ConfigDict(from_attributes=True)


# ------------------- ЗАДАЧИ -------------------

class TaskBase(BaseModel):
    """Базовая схема задачи"""
    name: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    assignee_username: Optional[str] = None
    deadline: Optional[datetime] = None
    priority: int = Field(0, ge=0, le=2)
    position_x: float = 0
    position_y: float = 0
    metadata: Optional[Dict[str, Any]] = None


class TaskCreate(TaskBase):
    """Создание задачи"""
    project_slug: str


class TaskUpdate(BaseModel):
    """Обновление задачи"""
    name: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    assignee_username: Optional[str] = None
    deadline: Optional[datetime] = None
    priority: Optional[int] = Field(None, ge=0, le=2)
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    """Ответ с информацией о задаче"""
    id: int
    project_id: int
    project_slug: str
    name: str
    description: Optional[str] = None
    status: str
    status_color: str
    assignee_id: Optional[int] = None
    assignee_username: Optional[str] = None
    creator_id: int
    creator_username: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    priority: int
    position_x: float
    position_y: float
    is_ready: bool = False
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_task(cls, data):
        """Преобразует объект Task в словарь"""
        if hasattr(data, '__dict__'):
            return {
                'id': data.id,
                'project_id': data.project_id,
                'project_slug': data.project.slug if data.project else None,
                'name': data.name,
                'description': data.description,
                'status': data.status.name if data.status else None,
                'status_color': data.status.color if data.status else None,
                'assignee_id': data.assignee.id if data.assignee else None,
                'assignee_username': data.assignee.username if data.assignee else None,
                'creator_id': data.creator.id if data.creator else None,
                'creator_username': data.creator.username if data.creator else None,
                'created_at': data.created_at,
                'updated_at': data.updated_at,
                'started_at': data.started_at,
                'completed_at': data.completed_at,
                'deadline': data.deadline,
                'priority': data.priority,
                'position_x': data.position_x,
                'position_y': data.position_y,
                'is_ready': False,  # Будет обновлено отдельно
                'metadata': data.metadata_dict,
            }
        return data


class TaskDetailResponse(TaskResponse):
    """Детальная информация о задаче"""
    incoming_dependencies: List['TaskDependencyResponse'] = []
    outgoing_dependencies: List['TaskDependencyResponse'] = []
    events: List['TaskEventResponse'] = []

    model_config = ConfigDict(from_attributes=True)


class TaskStatusUpdate(BaseModel):
    """Изменение статуса задачи"""
    status: str


# ------------------- ЗАВИСИМОСТИ -------------------

class TaskDependencyBase(BaseModel):
    """Базовая схема зависимости"""
    source_task_id: int
    target_task_id: int
    dependency_type: str = 'simple'
    description: Optional[str] = None


class TaskDependencyCreate(TaskDependencyBase):
    """Создание зависимости"""
    pass


class TaskDependencyResponse(BaseModel):
    """Ответ с информацией о зависимости"""
    id: int
    project_id: int
    source_task_id: int
    source_task_name: str
    target_task_id: int
    target_task_name: str
    dependency_type: str
    description: Optional[str] = None
    created_at: datetime
    created_by_username: str
    actions: List['DependencyActionResponse'] = []

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_dependency(cls, data):
        """Преобразует объект TaskDependency в словарь"""
        if hasattr(data, '__dict__'):
            return {
                'id': data.id,
                'project_id': data.project_id,
                'source_task_id': data.source_task_id,
                'source_task_name': data.source_task.name if data.source_task else None,
                'target_task_id': data.target_task_id,
                'target_task_name': data.target_task.name if data.target_task else None,
                'dependency_type': data.dependency_type,
                'description': data.description,
                'created_at': data.created_at,
                'created_by_username': data.created_by.username if data.created_by else None,
                'actions': [],
            }
        return data


# ------------------- ДЕЙСТВИЯ НА ЗАВИСИМОСТЯХ -------------------

class DependencyActionCreate(BaseModel):
    """Создание действия на зависимости"""
    action_type_code: str
    target_user_username: Optional[str] = None
    target_status: Optional[str] = None
    message_template: Optional[str] = None
    delay_minutes: int = 0
    execute_order: int = 0


class DependencyActionResponse(BaseModel):
    """Ответ с информацией о действии"""
    id: int
    dependency_id: int
    action_type_code: str
    action_type_name: str
    target_user_id: Optional[int] = None
    target_user_username: Optional[str] = None
    target_status: Optional[str] = None
    message_template: Optional[str] = None
    delay_minutes: int
    execute_order: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_action(cls, data):
        """Преобразует объект DependencyAction в словарь"""
        if hasattr(data, '__dict__'):
            return {
                'id': data.id,
                'dependency_id': data.dependency_id,
                'action_type_code': data.action_type.code if data.action_type else None,
                'action_type_name': data.action_type.name if data.action_type else None,
                'target_user_id': data.target_user.id if data.target_user else None,
                'target_user_username': data.target_user.username if data.target_user else None,
                'target_status': data.target_status.name if data.target_status else None,
                'message_template': data.message_template,
                'delay_minutes': data.delay_minutes,
                'execute_order': data.execute_order,
                'is_active': data.is_active,
            }
        return data


# ------------------- СОБЫТИЯ -------------------

class TaskEventResponse(BaseModel):
    """Ответ с информацией о событии задачи"""
    id: int
    task_id: int
    user_id: int
    user_username: str
    event_type: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_event(cls, data):
        """Преобразует объект TaskEvent в словарь"""
        if hasattr(data, '__dict__'):
            return {
                'id': data.id,
                'task_id': data.task_id,
                'user_id': data.user_id,
                'user_username': data.user.username if data.user else None,
                'event_type': data.event_type,
                'old_value': data.old_value,
                'new_value': data.new_value,
                'metadata': json.loads(data.metadata) if data.metadata else None,
                'created_at': data.created_at,
            }
        return data


# ------------------- ГРАФ -------------------

class GraphNodeData(BaseModel):
    """Данные узла графа"""
    id: str
    type: str = 'taskNode'
    data: Dict[str, Any]
    position: Dict[str, float]


class GraphEdgeData(BaseModel):
    """Данные ребра графа"""
    id: str
    source: str
    target: str
    type: str = 'default'
    data: Optional[Dict[str, Any]] = None
    animated: bool = False
    label: Optional[str] = None


class ProjectGraphResponse(BaseModel):
    """Ответ с данными графа проекта для ReactFlow"""
    nodes: List[GraphNodeData]
    edges: List[GraphEdgeData]
    viewport: Dict[str, Any] = {'x': 0, 'y': 0, 'zoom': 1}


# ------------------- СТАТИСТИКА -------------------

class TaskStatsResponse(BaseModel):
    """Статистика по задачам проекта"""
    total: int
    by_status: Dict[str, Dict[str, Any]]
    by_assignee: Dict[str, int]
    overdue: int


class UserTaskStatsResponse(BaseModel):
    """Статистика по задачам пользователя"""
    assigned: int
    created: int
    completed: int
    in_progress: int
    overdue: int
    completion_rate: float


# ------------------- ОТЛОЖЕННЫЕ ДЕЙСТВИЯ -------------------

class ScheduledActionResponse(BaseModel):
    """Ответ с информацией о запланированном действии"""
    id: int
    task_id: int
    task_name: str
    action_type: str
    scheduled_for: datetime
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)