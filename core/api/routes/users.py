# core/api/routes/users.py - исправленный
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Any, List, Optional
from ...services.UserService import UserService
from ...db.models.user import User
from ..schemas.user import (
    UserProfileResponse, UserUpdate, PasswordChange,
    ThemePreferences, NotificationSettings, SessionResponse
)
from ..deps import get_user_service, get_current_active_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
        current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Получение профиля текущего пользователя
    """
    return UserProfileResponse.model_validate(current_user)


@router.put("/me", response_model=UserProfileResponse)
async def update_current_user_profile(
        user_in: UserUpdate,
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Обновление профиля текущего пользователя
    """
    try:
        updated_user = service.update_profile(
            user_id=current_user.id,
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            email=user_in.email,
            tg_username=user_in.tg_username
        )

        return UserProfileResponse.model_validate(updated_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/me/change-password")
async def change_password(
        password_in: PasswordChange,
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Смена пароля
    """
    try:
        service.change_password(
            user_id=current_user.id,
            current_password=password_in.current_password,
            new_password=password_in.new_password
        )

        return {"message": "Password successfully changed"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/me/theme", response_model=ThemePreferences)
async def update_theme(
        theme: ThemePreferences,
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Обновление настроек темы
    """
    result = service.update_theme_preferences(
        user_id=current_user.id,
        theme_data=theme.model_dump(exclude_unset=True)
    )

    return result


@router.put("/me/notifications", response_model=NotificationSettings)
async def update_notifications(
        settings: NotificationSettings,
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Обновление настроек уведомлений
    """
    result = service.update_notification_settings(
        user_id=current_user.id,
        settings=settings.model_dump(exclude_unset=True)
    )

    return result


@router.get("/me/sessions", response_model=List[SessionResponse])
async def get_my_sessions(
        request: Request,
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Получение всех активных сессий текущего пользователя
    """
    sessions = service.get_user_sessions(current_user.id)
    current_token = request.state.token if hasattr(request.state, 'token') else None

    result = []
    for session in sessions:
        session_data = SessionResponse.model_validate(session)
        session_data.is_current = (session.token == current_token)
        result.append(session_data)

    return result


@router.delete("/me/sessions/{session_id}")
async def revoke_session(
        session_id: int,
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Завершение конкретной сессии
    """
    result = service.revoke_session(session_id, current_user.id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    return {"message": "Session successfully terminated"}


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user_by_id(
        user_id: int,
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Получение пользователя по ID
    """
    user = service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserProfileResponse.model_validate(user)


@router.get("/by-username/{username}", response_model=UserProfileResponse)
async def get_user_by_username(
        username: str,
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Получение пользователя по username
    """
    user = service.get_user_by_username(username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserProfileResponse.model_validate(user)