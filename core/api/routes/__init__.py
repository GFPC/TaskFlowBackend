# core/api/routes/__init__.py
from .auth import router as auth_router
from .users import router as users_router
from .admin import router as admin_router
from .roles import router as roles_router
from .telegram import router as telegram_router  # Добавляем

__all__ = ['auth_router', 'users_router', 'admin_router', 'roles_router', 'telegram_router']