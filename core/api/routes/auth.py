# core/api/routes/auth.py - исправленный
from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from typing import Any
from ...services.UserService import UserService
from ...db.models.user import User
from ..schemas.user import (
    UserRegister, UserLogin, TelegramVerify, RefreshToken,
    AuthResponse, TelegramCodeResponse, LoginResponse, RecoveryInitiateResponse,
    RecoveryResetResponse, UserProfileResponse
)
from ..deps import get_user_service, get_current_user, get_current_active_user

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TelegramCodeResponse)
async def register(
        user_in: UserRegister,
        request: Request,
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Регистрация нового пользователя
    Возвращает код для подтверждения Telegram
    """
    try:
        result = service.register(
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            username=user_in.username,
            password=user_in.password,
            email=user_in.email,
            tg_username=user_in.tg_username
        )

        return TelegramCodeResponse(
            user_id=result['user'].id,
            tg_code=result['tg_code']
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=LoginResponse)
async def login(
        user_in: UserLogin,
        request: Request,
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Вход в систему
    Если Telegram подтвержден - возвращает токен
    Если нет - возвращает код для верификации
    """
    try:
        result = service.login(
            username=user_in.username,
            password=user_in.password,
            ip=request.client.host,
            user_agent=request.headers.get("user-agent"),
            device_id=request.headers.get("x-device-id")
        )

        if result['requires_verification']:
            return LoginResponse(
                requires_verification=True,
                user_id=result['user_id'],
                tg_code=result['tg_code']
            )

        user_data = UserProfileResponse.model_validate(result['user'])

        return LoginResponse(
            requires_verification=False,
            access_token=result['access_token'],
            refresh_token=result['refresh_token'],
            user=user_data
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/verify-telegram", response_model=AuthResponse)
async def verify_telegram(
        verify_in: TelegramVerify,
        request: Request,
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Подтверждение Telegram кода
    """
    try:
        result = service.verify_telegram_code(
            user_id=verify_in.user_id,
            code=verify_in.code,
            tg_id=verify_in.tg_id,
            tg_chat_id=verify_in.tg_chat_id
        )

        user_data = UserProfileResponse.model_validate(result['user'])

        return AuthResponse(
            access_token=result['session'].token,
            refresh_token=result['session'].refresh_token,
            expires_at=result['session'].expires_at,
            user=user_data
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
        refresh_in: RefreshToken,
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Обновление access токена
    """
    try:
        result = service.refresh_session(refresh_in.refresh_token)

        # Получаем пользователя
        user = service.validate_token(result['access_token'])
        user_data = UserProfileResponse.model_validate(user)

        return AuthResponse(
            access_token=result['access_token'],
            refresh_token=result['refresh_token'],
            expires_at=result['expires_at'],
            user=user_data
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/logout")
async def logout(
        request: Request,
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Выход из системы (завершение текущей сессии)
    """
    token = request.state.token if hasattr(request.state, 'token') else None
    if token:
        service.logout(token)

    return {"message": "Successfully logged out"}


@router.post("/logout-all")
async def logout_all(
        request: Request,
        current_user: User = Depends(get_current_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Завершение всех сессий пользователя, кроме текущей
    """
    count = service.logout_all(
        user_id=current_user.id,
        exclude_token=request.state.token if hasattr(request.state, 'token') else None
    )

    return {"message": f"Successfully terminated {count} sessions"}


@router.post("/recovery/initiate", response_model=RecoveryInitiateResponse)
async def initiate_recovery(
        service: UserService = Depends(get_user_service),
        username: str = Body(..., embed=True)
) -> Any:
    """
    Инициация восстановления пароля
    """
    result = service.initiate_password_recovery(username)

    if result['success']:
        return RecoveryInitiateResponse(
            success=True,
            message="Recovery code generated",
            user_id=result['user_id'],
            recovery_code=result['recovery_code'],
            expires_at=result['expires_at']
        )
    else:
        # Для неуспешного случая возвращаем ответ без обязательных полей
        # Используем response_model=None или другой подход
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "message": result['message']
            }
        )


@router.post("/recovery/reset", response_model=RecoveryResetResponse)
async def reset_password(
        request: Request,
        recovery_code: str = Body(...),
        new_password: str = Body(...),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Сброс пароля с использованием кода восстановления
    """
    try:
        result = service.reset_password(
            recovery_code=recovery_code,
            new_password=new_password,
            ip=request.client.host
        )

        return RecoveryResetResponse(
            success=True,
            message="Password successfully reset"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/send-code-to-telegram")
async def send_code_to_telegram(
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
):
    """Отправка кода верификации в Telegram"""
    if not current_user.tg_chat_id:
        raise HTTPException(
            status_code=400,
            detail="Telegram chat not found. Send /start to bot first."
        )

    code = await service.send_telegram_code(current_user.id)

    return {
        "success": True,
        "message": "Code sent to Telegram",
        "chat_id": current_user.tg_chat_id
    }


@router.post("/test/verify/{user_id}")
async def test_verify_user(
        user_id: int,
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    ТЕСТОВЫЙ ЭНДПОИНТ: Верифицировать пользователя без Telegram

    Только для разработки и тестирования!
    """
    from core.config import settings

    # Проверяем, что мы в режиме разработки
    if not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test endpoints are only available in DEBUG mode"
        )

    try:
        user = service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Принудительно верифицируем пользователя
        user.tg_verified = True
        user.tg_id = 123456789  # Тестовый Telegram ID
        user.tg_chat_id = -123456789  # Тестовый chat ID
        user.save()

        return {
            "message": "User verified successfully",
            "user_id": user.id,
            "username": user.username
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )