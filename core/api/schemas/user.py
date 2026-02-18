# core/api/schemas/user.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
from pydantic import BaseModel, Field, EmailStr, validator, ConfigDict, model_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import re
import json

# ---------- Базовые схемы ----------
class UserBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    tg_username: Optional[str] = None

    @validator('username')
    def validate_username(cls, v):
        if not re.match("^[a-zA-Z0-9_.-]+$", v):
            raise ValueError('Username can only contain letters, numbers, underscores, dots and hyphens')
        return v.lower()

# ---------- Регистрация и авторизация ----------
class UserRegister(UserBase):
    password: str = Field(..., min_length=8)

    @validator('password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain digit')
        return v

class UserLogin(BaseModel):
    username: str
    password: str

class TelegramVerify(BaseModel):
    user_id: int
    code: str = Field(..., min_length=6, max_length=6)
    tg_id: Optional[int] = None
    tg_chat_id: Optional[int] = None

class RefreshToken(BaseModel):
    refresh_token: str

# ---------- Ответы ----------
class UserResponse(UserBase):
    id: int
    role_id: int
    role_name: str
    is_active: bool
    is_verified: bool
    tg_verified: bool
    created_at: datetime
    last_login: Optional[datetime]
    theme_preferences: Dict[str, Any]
    notification_settings: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)

class UserProfileResponse(BaseModel):
    """Схема для ответа с профилем пользователя"""
    id: int
    first_name: str
    last_name: str
    username: str
    email: Optional[str] = None
    tg_username: Optional[str] = None
    tg_verified: bool
    role: str
    is_active: bool
    is_superuser: bool = False
    created_at: datetime
    last_login: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    theme_preferences: Dict[str, Any]
    notification_settings: Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_user(cls, data):
        """Преобразует объект User или словарь в нужный формат"""
        if hasattr(data, '__dict__'):  # Это объект User
            return {
                'id': data.id,
                'first_name': data.first_name,
                'last_name': data.last_name,
                'username': data.username,
                'email': data.email,
                'tg_username': data.tg_username,
                'tg_verified': data.tg_verified,
                'role': data.role.name if data.role else None,
                'is_active': data.is_active,
                'is_superuser': data.is_superuser,
                'created_at': data.created_at,
                'last_login': data.last_login,
                'last_activity': data.last_activity,
                'theme_preferences': data.theme_preferences_dict if hasattr(data, 'theme_preferences_dict') else {},
                'notification_settings': data.notification_settings_dict if hasattr(data, 'notification_settings_dict') else {},
            }
        return data

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_at: Optional[datetime] = None
    user: UserProfileResponse

    model_config = ConfigDict(from_attributes=True)

class TelegramCodeResponse(BaseModel):
    requires_verification: bool = True
    user_id: int
    tg_code: str
    message: str = "Verification code sent to Telegram"

    model_config = ConfigDict(from_attributes=True)

class LoginResponse(BaseModel):
    requires_verification: bool
    user_id: Optional[int] = None
    tg_code: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user: Optional[UserProfileResponse] = None
    token_type: str = "bearer"
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class SessionResponse(BaseModel):
    id: int
    token: str
    type: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_id: Optional[str] = None
    is_current: bool = False

    model_config = ConfigDict(from_attributes=True)

class RecoveryInitiateResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[int] = None
    recovery_code: Optional[str] = None
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class RecoveryResetResponse(BaseModel):
    success: bool
    message: str

    model_config = ConfigDict(from_attributes=True)

# ---------- Обновление профиля ----------
class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    tg_username: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

    @validator('new_password')
    def validate_new_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain digit')
        return v

    model_config = ConfigDict(from_attributes=True)

class ThemePreferences(BaseModel):
    mode: Optional[str] = "light"
    primary_color: Optional[str] = "#1976d2"
    language: Optional[str] = "ru"

    model_config = ConfigDict(from_attributes=True)

class NotificationSettings(BaseModel):
    telegram: Optional[bool] = True
    email: Optional[bool] = False
    task_assigned: Optional[bool] = True
    task_completed: Optional[bool] = True
    dependency_ready: Optional[bool] = True

    model_config = ConfigDict(from_attributes=True)

# ---------- Админ ----------
class UserRoleChange(BaseModel):
    role_name: str

    model_config = ConfigDict(from_attributes=True)

class UserStatsResponse(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    verified_telegram: int
    by_role: Dict[str, int]

    model_config = ConfigDict(from_attributes=True)

class UserSearchParams(BaseModel):
    query: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None
    limit: int = 20
    offset: int = 0

    model_config = ConfigDict(from_attributes=True)