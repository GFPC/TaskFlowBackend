# core/config.py
import os
from typing import List

from dotenv import load_dotenv
from peewee import *

load_dotenv()

# Определяем окружение
IS_TESTING = os.environ.get('TESTING') == '1'

# Настройки БД
if IS_TESTING:
    database = SqliteDatabase(':memory:')
elif os.environ.get('USE_SQLITE') == '1':
    database = SqliteDatabase('taskflow.db')
else:
    try:
        import pymysql

        pymysql.install_as_MySQLdb()
    except ImportError:
        print('Failed to import pymysql!!!!!!!!!!!!!')
    database = MySQLDatabase(
        'taskflow',
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 3306)),
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
        '*',
    ]

    # Frontend
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

    # Email: Resend (HTTPS API) или SMTP (например Timeweb: smtp.timeweb.ru:2525 + STARTTLS)
    RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
    EMAIL_FROM = os.getenv('EMAIL_FROM', 'onboarding@resend.dev')
    # Пароль ящика: SMTP_PASSWORD или EMAIL_PASSWORD (для совместимости с .env)
    _smtp_pw = os.getenv('SMTP_PASSWORD', '')
    _email_pw = os.getenv('EMAIL_PASSWORD', '')
    SMTP_PASSWORD = _smtp_pw or _email_pw
    # Пустой хост = SMTP не используется (задайте в .env, например smtp.timeweb.ru)
    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '2525'))
    SMTP_USER = os.getenv('SMTP_USER', '')
    _smtp_starttls = (
        os.getenv('SMTP_USE_STARTTLS', os.getenv('SMTP_USE_TLS', 'true')).lower()
        == 'true'
    )
    SMTP_USE_STARTTLS = _smtp_starttls
    SMTP_USE_TLS = _smtp_starttls  # устаревший алиас
    SMTP_USE_SSL = os.getenv('SMTP_USE_SSL', 'false').lower() == 'true'
    EMAIL_CODE_EXPIRY_MINUTES = int(os.getenv('EMAIL_CODE_EXPIRY_MINUTES', '10'))

    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    ALGORITHM = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 7

    DEBUG: bool = os.getenv('DEBUG', 'True').lower() == 'true'


settings = Settings()
