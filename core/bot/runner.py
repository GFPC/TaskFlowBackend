# core/bot/runner.py
import asyncio
import os
import sys
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging

from core.bot.bot import TaskFlowBot
from core.config import settings

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def main():
    """Запуск бота"""
    bot = TaskFlowBot()
    try:
        await bot.run_polling()
    except KeyboardInterrupt:
        bot.stop()
        print('\n👋 Бот остановлен')


if __name__ == '__main__':
    asyncio.run(main())
