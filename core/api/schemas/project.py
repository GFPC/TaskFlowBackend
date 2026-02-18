from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from .team import TeamResponse


# ------------------- БАЗОВЫЕ СХЕМЫ -------------------

class ProjectBase(BaseModel):
    """Базовая схема проекта"""
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    """Создание проекта"""
    team_slug: str = Field(..., min_length=1)
    initial_graph_data: Optional[str] = None


class ProjectUpdate(BaseModel):
    """Обновление проекта"""
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class ProjectResponse(BaseModel):
    """Ответ с информацией о проекте"""
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    team_id: int
    team_name: Optional[str] = None
    team_slug: Optional[str] = None
    created_by_id: int
    created_by_username: Optional[str] = None
    tasks_count: int
    members_count: int
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_project(cls, data):
        """Преобразует объект Project в словарь"""
        if hasattr(data, '__dict__'):
            return {
                'id': data.id,
                'name': data.name,
                'slug': data.slug,
                'description': data.description,
                'team_id': data.team_id,
                'team_name': data.team.name if data.team else None,
                'team_slug': data.team.slug if data.team else None,
                'created_by_id': data.created_by_id,
                'created_by_username': data.created_by.username if data.created_by else None,
                'tasks_count': data.tasks_count,
                'members_count': data.members_count,
                'status': data.status,
                'created_at': data.created_at,
                'updated_at': data.updated_at,
                'archived_at': data.archived_at,
            }
        return data


class ProjectDetailResponse(ProjectResponse):
    """Детальная информация о проекте"""
    members: List['ProjectMemberResponse']
    user_role: Optional[str] = None
    can_manage_members: bool = False
    can_edit_project: bool = False
    can_delete_project: bool = False
    can_create_tasks: bool = False
    settings: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


# ------------------- УЧАСТНИКИ -------------------

class ProjectMemberBase(BaseModel):
    """Базовая схема участника проекта"""
    role: str = Field(..., pattern='^(owner|manager|developer|observer)$')


class ProjectMemberAdd(ProjectMemberBase):
    """Добавление участника"""
    username: str = Field(..., min_length=3, max_length=50)


class ProjectMemberUpdate(ProjectMemberBase):
    """Обновление роли участника"""
    pass


class ProjectMemberResponse(BaseModel):
    """Ответ с информацией об участнике проекта"""
    id: int
    project_id: int
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    role_priority: int = 0
    is_active: bool
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_member(cls, data):
        """Преобразует объект ProjectMember в словарь"""
        if hasattr(data, '__dict__'):
            return {
                'id': data.id,
                'project_id': data.project_id,
                'user_id': data.user_id,
                'username': data.user.username if data.user else None,
                'first_name': data.user.first_name if data.user else None,
                'last_name': data.user.last_name if data.user else None,
                'role': data.role.name if data.role else None,
                'role_priority': data.role.priority if data.role else 0,
                'is_active': data.is_active,
                'joined_at': data.joined_at,
            }
        return data


# ------------------- ПРИГЛАШЕНИЯ -------------------

class ProjectInvitationCreate(BaseModel):
    """Создание приглашения в проект"""
    username: str = Field(..., min_length=3, max_length=50)
    role: str = Field(..., pattern='^(manager|developer|observer)$')


class ProjectInvitationResponse(BaseModel):
    """Ответ с информацией о приглашении"""
    id: int
    project_id: int
    project_name: str
    project_slug: str
    team_name: str
    invited_by_username: str
    invited_user_id: int
    invited_user_username: str
    proposed_role: str
    status: str
    created_at: datetime
    expires_at: datetime
    responded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_invitation(cls, data):
        """Преобразует объект ProjectInvitation в словарь"""
        if hasattr(data, '__dict__'):
            return {
                'id': data.id,
                'project_id': data.project_id,
                'project_name': data.project.name if data.project else None,
                'project_slug': data.project.slug if data.project else None,
                'team_name': data.project.team.name if data.project and data.project.team else None,
                'invited_by_username': data.invited_by.username if data.invited_by else None,
                'invited_user_id': data.invited_user.id if data.invited_user else None,
                'invited_user_username': data.invited_user.username if data.invited_user else None,
                'proposed_role': data.proposed_role.name if data.proposed_role else None,
                'status': data.status,
                'created_at': data.created_at,
                'expires_at': data.expires_at,
                'responded_at': data.responded_at,
            }
        return data


# ------------------- ПЕРЕДАЧА ВЛАДЕНИЯ -------------------

class ProjectTransferOwnership(BaseModel):
    """Передача прав владельца проекта"""
    new_owner_username: str = Field(..., min_length=3, max_length=50)


# ------------------- ГРАФ -------------------

class ProjectGraphData(BaseModel):
    """Данные графа для ReactFlow"""
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    viewport: Optional[Dict[str, Any]] = None


# ------------------- СТАТИСТИКА -------------------

class ProjectStatsResponse(BaseModel):
    """Статистика проекта"""
    project_id: int
    project_name: str
    total_members: int
    by_role: Dict[str, int]
    tasks: Dict[str, Any]
    created_at: datetime
    created_by: str
    team: str