# tests/conftest.py
import os
import sys
import pytest
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

# Устанавливаем режим тестирования
os.environ['TESTING'] = '1'

# Импортируем и настраиваем БД
from peewee import SqliteDatabase
from core.db.models.user import User, UserRole, AuthSession, RecoveryCode


@pytest.fixture(scope="session")
def test_db():
    """Создает тестовую БД на всю сессию"""
    database = SqliteDatabase(':memory:')

    # Создаем таблицы
    database.create_tables([User, UserRole, AuthSession, RecoveryCode])

    # Создаем базовые роли
    UserRole.get_or_create(
        name='Работник',
        defaults={
            'description': 'Стандартный пользователь',
            'priority': 1,
            'permissions': '{"view_tasks": true, "edit_own_tasks": true}'
        }
    )

    UserRole.get_or_create(
        name='Менеджер проекта',
        defaults={
            'description': 'Управляет задачами проекта',
            'priority': 50,
            'permissions': '{"view_tasks": true, "edit_all_tasks": true, "manage_team": true}'
        }
    )

    UserRole.get_or_create(
        name='Хозяин',
        defaults={
            'description': 'Полный доступ к системе',
            'priority': 100,
            'permissions': '{"all": true}'
        }
    )

    yield database

    database.drop_tables([User, UserRole, AuthSession, RecoveryCode])
    database.close()