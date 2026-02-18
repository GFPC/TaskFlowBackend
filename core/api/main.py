# core/api/main.py
from fastapi import APIRouter
from .routes import auth_router, users_router, admin_router, roles_router, telegram_router, teams, projects, tasks

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(admin_router)
api_router.include_router(roles_router)
api_router.include_router(telegram_router)  # Добавляем
api_router.include_router(teams.router)  # Добавляем
api_router.include_router(projects.router)
api_router.include_router(tasks.router)