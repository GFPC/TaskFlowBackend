# tests/conftest.py
import os
import sys
import tempfile
import types
from pathlib import Path

import pytest
from peewee import SqliteDatabase

# Добавляем корневую директорию в PYTHONPATH
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

os.environ['TESTING'] = '1'

# Сброс ранних импортов core.* (иначе BaseModel привязывается к «боевой» БД из core.config)
for _mod in list(sys.modules.keys()):
    if _mod == 'core' or _mod.startswith('core.'):
        del sys.modules[_mod]

# Мок core.config ДО любого импорта моделей Peewee
# Файл на диске: :memory: в отдельном потоке TestClient не видит таблицы
_test_db_path = tempfile.NamedTemporaryFile(delete=False, suffix='.db').name
test_db = SqliteDatabase(_test_db_path)
mock_config = types.ModuleType('core.config')
mock_config.database = test_db
mock_config.IS_TESTING = True
mock_config.DEBUG = False
mock_config.EMAIL_CODE_EXPIRY_MINUTES = 10
mock_config.EMAIL_FROM = 'test@localhost'
mock_config.RESEND_API_KEY = ''
mock_config.SMTP_HOST = ''
mock_config.SMTP_PORT = 2525
mock_config.SMTP_USER = ''
mock_config.SMTP_PASSWORD = ''
mock_config.EMAIL_PASSWORD = ''
mock_config.SMTP_USE_TLS = True
mock_config.SMTP_USE_STARTTLS = True
mock_config.SMTP_USE_SSL = False
mock_config.ALLOWED_ORIGINS = ['*']
mock_config.API_HOST = 'localhost'
mock_config.API_PORT = 8000
# `from core.config import settings` — объект с теми же полями, что Settings
mock_config.settings = mock_config
sys.modules['core.config'] = mock_config

from core.db.models.user import AuthLog, AuthSession, RecoveryCode, User, UserRole

test_db.connect(reuse_if_open=True)
test_db.create_tables([UserRole, User, AuthSession, RecoveryCode, AuthLog])

UserRole.get_or_create(
    name='Работник',
    defaults={
        'description': 'Стандартный пользователь',
        'priority': 1,
        'permissions': '{"view_tasks": true, "edit_own_tasks": true}',
    },
)

UserRole.get_or_create(
    name='Менеджер проекта',
    defaults={
        'description': 'Управляет задачами проекта',
        'priority': 50,
        'permissions': '{"view_tasks": true, "edit_all_tasks": true, "manage_team": true}',
    },
)

UserRole.get_or_create(
    name='Хозяин',
    defaults={
        'description': 'Полный доступ к системе',
        'priority': 100,
        'permissions': '{"all": true}',
    },
)


@pytest.fixture(scope='session')
def test_db_session():
    """Сессионная БД (тот же in-memory экземпляр)."""
    yield test_db


@pytest.fixture(autouse=True)
def cleanup_db():
    """Очищаем данные между тестами."""
    User.delete().execute()
    AuthSession.delete().execute()
    RecoveryCode.delete().execute()
    AuthLog.delete().execute()
    yield
