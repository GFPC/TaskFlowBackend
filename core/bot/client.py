# core/bot/client.py
from typing import Optional
from .bot import TaskFlowBot

_bot_instance: Optional[TaskFlowBot] = None

def get_bot() -> TaskFlowBot:
    """Получение экземпляра бота (синглтон)"""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = TaskFlowBot()
    return _bot_instance

async def send_telegram_notification(chat_id: int,
                                   notification_type: str,
                                   data: dict) -> bool:
    """Отправка уведомления через бота"""
    bot = get_bot()
    return await bot.send_notification(chat_id, notification_type, data)