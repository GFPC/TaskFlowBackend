# core/api/routes/auth.py
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ...config import settings
from ...db.models.user import User
from ...services.UserService import UserService
from ..deps import get_current_user, get_user_service
from ..schemas.user import (
    AuthResponse,
    EmailCodeResponse,
    EmailVerify,
    LoginResponse,
    RecoveryInitiateResponse,
    RecoveryResetResponse,
    RefreshToken,
    UserLogin,
    UserProfileResponse,
    UserRegister,
)

router = APIRouter(prefix='/auth', tags=['authentication'])
_optional_bearer = HTTPBearer(auto_error=False)


@router.post('/register', response_model=EmailCodeResponse)
async def register(
    user_in: UserRegister,
    request: Request,
    service: UserService = Depends(get_user_service),
) -> Any:
    """
    Регистрация: код подтверждения отправляется на email.
    """
    try:
        result = service.register(
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            username=user_in.username,
            password=user_in.password,
            email=str(user_in.email),
        )

        show_code = settings.DEBUG or not result['email_sent']
        return EmailCodeResponse(
            user_id=result['user'].id,
            verification_code=result['verification_code'] if show_code else None,
            email_sent=result['email_sent'],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post('/login', response_model=LoginResponse, response_model_exclude_none=True)
async def login(
    user_in: UserLogin,
    request: Request,
    service: UserService = Depends(get_user_service),
) -> Any:
    """
    Вход: при неподтверждённом email — новый код на почту.
    """
    try:
        result = service.login(
            username=user_in.username,
            password=user_in.password,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent'),
            device_id=request.headers.get('x-device-id'),
        )

        if result['requires_verification']:
            show_code = settings.DEBUG or not result.get('email_sent', True)
            return LoginResponse(
                requires_verification=True,
                user_id=result['user_id'],
                verification_code=result['verification_code'] if show_code else None,
                email_sent=result.get('email_sent'),
            )

        user_data = UserProfileResponse.model_validate(result['user'])

        return LoginResponse(
            requires_verification=False,
            access_token=result['access_token'],
            refresh_token=result['refresh_token'],
            user=user_data,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={'WWW-Authenticate': 'Bearer'},
        )


@router.post('/verify-email', response_model=AuthResponse)
async def verify_email(
    verify_in: EmailVerify,
    request: Request,
    service: UserService = Depends(get_user_service),
) -> Any:
    """Подтверждение email по коду из письма."""
    try:
        result = service.verify_email_code(
            user_id=verify_in.user_id,
            code=verify_in.code,
        )

        user_data = UserProfileResponse.model_validate(result['user'])

        return AuthResponse(
            access_token=result['session'].token,
            refresh_token=result['session'].refresh_token,
            expires_at=result['session'].expires_at,
            user=user_data,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post('/refresh', response_model=AuthResponse)
async def refresh_token(
    refresh_in: RefreshToken, service: UserService = Depends(get_user_service)
) -> Any:
    """Обновление access токена."""
    try:
        result = service.refresh_session(refresh_in.refresh_token)

        user = service.validate_token(result['access_token'])
        user_data = UserProfileResponse.model_validate(user)

        return AuthResponse(
            access_token=result['access_token'],
            refresh_token=result['refresh_token'],
            expires_at=result['expires_at'],
            user=user_data,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={'WWW-Authenticate': 'Bearer'},
        )


@router.post('/logout')
async def logout(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    service: UserService = Depends(get_user_service),
) -> Any:
    """Выход из системы (завершение текущей сессии)."""
    token = None
    if credentials:
        token = credentials.credentials
    elif hasattr(request.state, 'token'):
        token = request.state.token
    if token:
        service.logout(token)

    return {'message': 'Successfully logged out'}


@router.post('/logout-all')
async def logout_all(
    request: Request,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> Any:
    """Завершение всех сессий пользователя, кроме текущей."""
    count = service.logout_all(
        user_id=current_user.id,
        exclude_token=request.state.token if hasattr(request.state, 'token') else None,
    )

    return {'message': f'Successfully terminated {count} sessions'}


@router.post('/recovery/initiate', response_model=RecoveryInitiateResponse)
async def initiate_recovery(
    service: UserService = Depends(get_user_service),
    username: str = Body(..., embed=True),
) -> Any:
    """Инициация восстановления пароля."""
    result = service.initiate_password_recovery(username)

    if result['success']:
        email_sent = result.get('email_sent', False)
        show_code = settings.DEBUG or not email_sent
        msg = (
            'Recovery code sent to your email'
            if email_sent
            else 'Recovery code generated'
        )
        return RecoveryInitiateResponse(
            success=True,
            message=msg,
            user_id=result['user_id'],
            recovery_code=result['recovery_code'] if show_code else None,
            expires_at=result['expires_at'],
            email_sent=email_sent,
        )
    else:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=200, content={'success': False, 'message': result['message']}
        )


@router.post('/recovery/reset', response_model=RecoveryResetResponse)
async def reset_password(
    request: Request,
    recovery_code: str = Body(...),
    new_password: str = Body(...),
    service: UserService = Depends(get_user_service),
) -> Any:
    """Сброс пароля с использованием кода восстановления."""
    try:
        service.reset_password(
            recovery_code=recovery_code,
            new_password=new_password,
            ip=request.client.host if request.client else None,
        )

        return RecoveryResetResponse(
            success=True, message='Password successfully reset'
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post('/test/verify/{user_id}')
async def test_verify_user(
    user_id: int, service: UserService = Depends(get_user_service)
) -> Any:
    """ТЕСТОВЫЙ: пометить email как подтверждённый. Только при DEBUG."""
    if not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Test endpoints are only available in DEBUG mode',
        )

    try:
        user = service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail='User not found'
            )

        user.email_verified = True
        user.save()

        return {
            'message': 'User email marked verified',
            'user_id': user.id,
            'username': user.username,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
