# core/api/routes/__init__.py
from .admin import router as admin_router
from .auth import router as auth_router
from .roles import router as roles_router
from .telegram import router as telegram_router  # Добавляем
from .users import router as users_router

__all__ = [
    'auth_router',
    'users_router',
    'admin_router',
    'roles_router',
    'telegram_router',
]
