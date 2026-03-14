# main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.api import api_router
from core.bot.deps import set_bot_user_service, start_bot, stop_bot
from core.config import settings
from core.services.UserService import UserService

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения
    Запускает Telegram бота при старте и останавливает при завершении
    """
    # Startup
    logging.info('🚀 Starting TaskFlow API...')

    # Создаем экземпляр UserService
    user_service = UserService()

    # Запускаем Telegram бота
    if settings.TELEGRAM_BOT_TOKEN:
        await start_bot()
        # Устанавливаем UserService в бота
        set_bot_user_service(user_service)
        logging.info('🤖 Telegram bot started')
    else:
        logging.warning('⚠️ TELEGRAM_BOT_TOKEN not set, bot disabled')

    yield

    # Shutdown
    logging.info('🛑 Shutting down TaskFlow API...')
    await stop_bot()
    logging.info('👋 Goodbye!')


app = FastAPI(
    title='TaskFlow API',
    description='TaskFlow - система мониторинга задач и управления ими',
    version='1.0.0',
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Подключаем роутеры
app.include_router(api_router)


@app.get('/')
async def root():
    return {
        'message': 'TaskFlow API',
        'docs': '/docs',
        'redoc': '/redoc',
        'telegram_bot': f'https://t.me/{settings.TELEGRAM_BOT_USERNAME.replace("@", "")}',
    }


@app.get('/health')
async def health_check():
    return {'status': 'healthy'}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host=settings.API_HOST, port=settings.API_PORT, reload=True)
