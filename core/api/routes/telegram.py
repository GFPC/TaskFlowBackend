# core/api/routes/telegram.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Any
from ...services.UserService import UserService
from ...db.models.user import User
from ..deps import get_current_active_user, get_user_service
from ...bot.deps import get_bot
from ...config import settings

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/link")
async def generate_telegram_code(
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Генерация кода для привязки Telegram
    """
    # Генерируем код
    code = current_user.generate_tg_code()
    current_user.save()

    # Если у пользователя уже есть chat_id, отправляем код сразу
    if current_user.tg_chat_id:
        bot = await get_bot()
        await bot.send_verification_code(current_user.tg_chat_id, code)
        return {
            "code": code,
            "sent_to_telegram": True,
            "expires_in": 10,
            "chat_id": current_user.tg_chat_id
        }

    # Иначе возвращаем код для ручного ввода
    return {
        "code": code,
        "sent_to_telegram": False,
        "expires_in": 10,
        "bot_username": settings.TELEGRAM_BOT_USERNAME
    }


@router.get("/status")
async def get_telegram_status(
        current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Получение статуса привязки Telegram
    """
    return {
        "is_linked": current_user.tg_verified,
        "tg_username": current_user.tg_username,
        "tg_id": current_user.tg_id,
        "tg_chat_id": current_user.tg_chat_id,
        "bot_username": settings.TELEGRAM_BOT_USERNAME
    }


@router.delete("/unlink")
async def unlink_telegram(
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Отвязка Telegram от аккаунта
    """
    current_user.tg_id = None
    current_user.tg_chat_id = None
    current_user.tg_verified = False
    current_user.tg_username = None
    current_user.save()

    return {"success": True, "message": "Telegram unlinked successfully"}


@router.post("/test")
async def send_test_notification(
        current_user: User = Depends(get_current_active_user),
        service: UserService = Depends(get_user_service)
) -> Any:
    """
    Отправка тестового уведомления
    """
    if not current_user.tg_verified:
        raise HTTPException(
            status_code=400,
            detail="Telegram not linked"
        )

    test_data = {
        "task_title": "Тестовое уведомление",
        "project_name": "TaskFlow",
        "creator": current_user.full_name,
        "task_url": f"{settings.FRONTEND_URL}/profile"
    }

    success = await service.send_telegram_notification(
        user_id=current_user.id,
        notification_type="task_assigned",
        data=test_data
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to send test notification"
        )

    return {"success": True, "message": "Test notification sent"}