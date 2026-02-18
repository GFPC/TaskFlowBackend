# core/api/routes/roles.py
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, List
from ...services.UserService import UserService
from ...db.models.user import UserRole, User
from ..schemas.role import RoleResponse, RoleCreate, RoleUpdate
from ..deps import get_user_service, get_current_superuser

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("/", response_model=List[RoleResponse])
async def get_all_roles(
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Получение списка всех ролей
    """
    roles = UserRole.select().order_by(UserRole.priority.desc())
    return [RoleResponse.model_validate(role) for role in roles]


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
        role_id: int,
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Получение роли по ID
    """
    try:
        role = UserRole.get_by_id(role_id)
        return RoleResponse.model_validate(role)
    except UserRole.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )


@router.post("/", response_model=RoleResponse)
async def create_role(
        role_in: RoleCreate,
        current_user: User = Depends(get_current_superuser),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Создание новой роли (только для администраторов)
    """
    try:
        role = UserRole.create(
            name=role_in.name,
            description=role_in.description,
            permissions=role_in.permissions,
            priority=role_in.priority
        )
        return RoleResponse.model_validate(role)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
        role_id: int,
        role_in: RoleUpdate,
        current_user: User = Depends(get_current_superuser),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Обновление роли (только для администраторов)
    """
    try:
        role = UserRole.get_by_id(role_id)

        if role_in.name is not None:
            role.name = role_in.name
        if role_in.description is not None:
            role.description = role_in.description
        if role_in.permissions is not None:
            role.permissions = role_in.permissions
        if role_in.priority is not None:
            role.priority = role_in.priority

        role.save()
        return RoleResponse.model_validate(role)
    except UserRole.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{role_id}")
async def delete_role(
        role_id: int,
        current_user: User = Depends(get_current_superuser),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Удаление роли (только для администраторов)
    """
    try:
        role = UserRole.get_by_id(role_id)

        # Проверяем, не используется ли роль
        if User.select().where(User.role_id == role_id).exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete role that is assigned to users"
            )

        role.delete_instance()
        return {"message": "Role successfully deleted"}
    except UserRole.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )