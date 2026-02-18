# core/api/deps.py - Зависимости
from typing import Optional, Generator
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..services.UserService import UserService
from ..services.TeamService import TeamService  # Добавлено
from ..services.ProjectService import ProjectService  # Добавлено
from ..services.TaskService import TaskService  # Добавлено
from ..db.models.user import User

# Схема безопасности
security = HTTPBearer()


# ------------------- СЕРВИСЫ -------------------

def get_user_service() -> Generator:
    """Dependency для UserService"""
    service = UserService()
    yield service


def get_team_service() -> Generator:
    """Dependency для TeamService"""
    service = TeamService()
    yield service


def get_project_service() -> Generator:
    """Dependency для ProjectService"""
    service = ProjectService()
    yield service


def get_task_service() -> Generator:
    """Dependency для TaskService"""
    service = TaskService()
    yield service


# ------------------- АУТЕНТИФИКАЦИЯ -------------------

async def get_current_user(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        service: UserService = Depends(get_user_service)
) -> User:
    """Получение текущего пользователя по токену"""
    token = credentials.credentials
    user = service.validate_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Сохраняем токен и пользователя в request.state для использования в других местах
    request.state.token = token
    request.state.user = user

    return user


async def get_current_active_user(
        current_user: User = Depends(get_current_user)
) -> User:
    """Получение текущего активного пользователя"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


async def get_current_superuser(
        current_user: User = Depends(get_current_active_user)
) -> User:
    """Проверка прав суперпользователя"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


def check_role(required_role: str):
    """Проверка конкретной роли"""

    async def role_checker(
            current_user: User = Depends(get_current_active_user)
    ) -> User:
        if current_user.role.name != required_role and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required"
            )
        return current_user

    return role_checker