# core/api/routes/__init__.py
from .admin import router as admin_router
from .auth import router as auth_router
from .projects import router as projects_router  # добавлено
from .roles import router as roles_router
from .tasks import router as tasks_router
from .teams import router as teams_router
from .users import router as users_router

__all__ = [
    'auth_router',
    'users_router',
    'admin_router',
    'roles_router',
    'teams_router',
    'projects_router',
    'tasks_router',
]
