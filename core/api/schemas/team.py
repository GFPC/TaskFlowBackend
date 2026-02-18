from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ------------------- БАЗОВЫЕ СХЕМЫ -------------------

class TeamBase(BaseModel):
    """Базовая схема команды"""
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None


class TeamCreate(TeamBase):
    """Создание команды"""
    pass


class TeamUpdate(BaseModel):
    """Обновление команды"""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    avatar: Optional[str] = None


class TeamResponse(BaseModel):
    """Ответ с информацией о команде"""
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    avatar: Optional[str] = None
    owner_id: int
    members_count: int
    projects_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamDetailResponse(TeamResponse):
    """Детальная информация о команде"""
    members: List['TeamMemberResponse']
    user_role: Optional[str] = None
    can_manage: bool = False
    can_manage_projects: bool = False
    can_invite_members: bool = False
    can_remove_members: bool = False

    model_config = ConfigDict(from_attributes=True)


# ------------------- УЧАСТНИКИ -------------------

class TeamMemberBase(BaseModel):
    """Базовая схема участника команды"""
    role: str = Field(..., pattern='^(owner|admin|member)$')


class TeamMemberAdd(TeamMemberBase):
    """Добавление участника"""
    username: str = Field(..., min_length=3, max_length=50)


class TeamMemberUpdate(TeamMemberBase):
    """Обновление роли участника"""
    pass


class TeamMemberResponse(BaseModel):
    """Ответ с информацией об участнике команды"""
    id: int
    team_id: int
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    role_priority: int = 0
    is_active: bool
    joined_at: datetime
    left_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_member(cls, data):
        """Преобразует объект TeamMember в словарь"""
        # Если это уже словарь, возвращаем как есть
        if isinstance(data, dict):
            return data

        # Если это объект TeamMember
        if hasattr(data, '__dict__'):
            return {
                'id': data.id,
                'team_id': data.team_id,
                'user_id': data.user_id,
                'username': data.user.username if data.user else None,
                'first_name': data.user.first_name if data.user else None,
                'last_name': data.user.last_name if data.user else None,
                'role': data.role.name if data.role else None,
                'role_priority': data.role.priority if data.role else 0,
                'is_active': data.is_active,
                'joined_at': data.joined_at,
                'left_at': data.left_at,
            }

        # Если ничего не подошло, возвращаем как есть
        return data


# ------------------- КОДЫ ПРИГЛАШЕНИЙ -------------------

class InviteCodeResponse(BaseModel):
    """Ответ с кодом приглашения"""
    invite_code: str
    expires_at: datetime


class TeamJoinByCode(BaseModel):
    """Вступление по коду"""
    invite_code: str = Field(..., min_length=1)


# ------------------- ПРИГЛАШЕНИЯ -------------------

class TeamInvitationCreate(BaseModel):
    """Создание приглашения"""
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[str] = None
    role: str = Field(..., pattern='^(admin|member)$')
    message: Optional[str] = None


class TeamInvitationResponse(BaseModel):
    """Ответ с информацией о приглашении"""
    id: int
    team_id: int
    team_name: str
    invited_by_username: str
    invited_user_id: Optional[int]
    invited_user_username: Optional[str]
    invitee_username: Optional[str]
    invitee_email: Optional[str]
    proposed_role: str
    status: str
    message: Optional[str]
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamInvitationAccept(BaseModel):
    """Принятие приглашения"""
    invitation_id: int


# ------------------- ПЕРЕДАЧА ВЛАДЕНИЯ -------------------

class TeamTransferOwnership(BaseModel):
    """Передача прав владельца"""
    new_owner_username: str = Field(..., min_length=3, max_length=50)


# ------------------- СТАТИСТИКА -------------------

class TeamStatsResponse(BaseModel):
    """Статистика команды"""
    team_id: int
    team_name: str
    total_members: int
    by_role: Dict[str, int]
    projects_count: int
    pending_invitations: int
    created_at: datetime
    owner: str
