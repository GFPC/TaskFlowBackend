# core/bot/deps.py
from typing import Optional
from .bot import TaskFlowBot

_bot_instance: Optional[TaskFlowBot] = None

async def get_bot() -> TaskFlowBot:
    """Получение экземпляра бота"""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = TaskFlowBot()
    return _bot_instance

def set_bot_user_service(user_service):
    """Установка сервиса пользователей в бота"""
    global _bot_instance
    if _bot_instance:
        _bot_instance.set_user_service(user_service)

async def start_bot():
    """Запуск бота"""
    bot = await get_bot()
    import asyncio
    asyncio.create_task(bot.start_polling())

async def stop_bot():
    """Остановка бота"""
    global _bot_instance
    if _bot_instance:
        await _bot_instance.stop_polling()
        _bot_instance = None