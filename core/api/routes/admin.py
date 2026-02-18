# core/api/routes/admin.py - Административные маршруты
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Any, List, Optional
from ...services.UserService import UserService
from ...db.models.user import User
from ..schemas.user import (
    UserProfileResponse, UserRoleChange, UserStatsResponse,
    UserSearchParams
)
from ..deps import get_user_service, get_current_superuser

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=List[UserProfileResponse])
async def search_users(
        *,
        query: Optional[str] = Query(None, description="Search query"),
        role_id: Optional[int] = Query(None, description="Filter by role ID"),
        is_active: Optional[bool] = Query(None, description="Filter by active status"),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        current_user: User = Depends(get_current_superuser),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Поиск пользователей (только для администраторов)
    """
    users = service.search_users(
        query=query,
        role_id=role_id,
        is_active=is_active,
        limit=limit,
        offset=offset
    )

    return [UserProfileResponse.model_validate(u) for u in users]


@router.get("/stats", response_model=UserStatsResponse)
async def get_user_statistics(
        current_user: User = Depends(get_current_superuser),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Статистика по пользователям (только для администраторов)
    """
    return service.get_user_stats()


@router.put("/users/{user_id}/role", response_model=UserProfileResponse)
async def change_user_role(
        user_id: int,
        role_in: UserRoleChange,
        current_user: User = Depends(get_current_superuser),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Изменение роли пользователя (только для администраторов)
    """
    try:
        updated_user = service.change_user_role(
            user_id=user_id,
            role_name=role_in.role_name,
            admin_user=current_user
        )

        return UserProfileResponse.model_validate(updated_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
        user_id: int,
        current_user: User = Depends(get_current_superuser),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Деактивация пользователя (только для администраторов)
    """
    try:
        service.deactivate_user(
            user_id=user_id,
            admin_user=current_user
        )

        return {"message": "User successfully deactivated"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.post("/users/{user_id}/activate")
async def activate_user(
        user_id: int,
        current_user: User = Depends(get_current_superuser),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Активация пользователя (только для администраторов)
    """
    try:
        service.activate_user(
            user_id=user_id,
            admin_user=current_user
        )

        return {"message": "User successfully activated"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )