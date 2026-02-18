# core/config.py
from peewee import *
import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

# Определяем окружение
IS_TESTING = os.environ.get('TESTING') == '1'

# Настройки БД
if IS_TESTING:
    database = SqliteDatabase(':memory:')
else:
    try:
        import pymysql

        pymysql.install_as_MySQLdb()
    except ImportError:
        pass

    database = MySQLDatabase(
        'taskflow',
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 3306))
    )


# Настройки приложения
class Settings:
    # Database
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_NAME = os.getenv('DB_NAME', 'taskflow')

    # API
    API_HOST = os.getenv('API_HOST', 'localhost')
    API_PORT = int(os.getenv('API_PORT', 8000))
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # Frontend
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', 'taskflow_bot')

    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 7

    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"


settings = Settings()