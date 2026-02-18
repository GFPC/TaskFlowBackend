# tests/test_api/test_auth.py
import pytest
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import bcrypt
import json

# Добавляем корневую директорию в PYTHONPATH
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

# Устанавливаем режим тестирования ДО любого импорта
os.environ['TESTING'] = '1'

# ПОЛНОСТЬЮ ПЕРЕОПРЕДЕЛЯЕМ МОДУЛЬ core.config ДО ИМПОРТА ОСТАЛЬНОГО
import sys
from unittest.mock import MagicMock, patch
from peewee import SqliteDatabase

# Создаем тестовую БД
test_db = SqliteDatabase(':memory:')

# Создаем мок для модуля core.config
mock_config = MagicMock()
mock_config.database = test_db
mock_config.IS_TESTING = True

# Подменяем модуль core.config
sys.modules['core.config'] = mock_config

# Теперь импортируем все остальное - они будут использовать наш мок
from fastapi.testclient import TestClient
from main import app
from core.db.models.user import User, UserRole, AuthSession, RecoveryCode

# Создаем таблицы в тестовой БД
test_db.create_tables([User, UserRole, AuthSession, RecoveryCode])

# Создаем базовые роли
UserRole.get_or_create(
    name='Работник',
    defaults={
        'description': 'Стандартный пользователь',
        'priority': 1,
        'permissions': json.dumps({'view_tasks': True, 'edit_own_tasks': True})
    }
)

UserRole.get_or_create(
    name='Менеджер проекта',
    defaults={
        'description': 'Управляет задачами проекта',
        'priority': 50,
        'permissions': json.dumps({'view_tasks': True, 'edit_all_tasks': True, 'manage_team': True})
    }
)

UserRole.get_or_create(
    name='Хозяин',
    defaults={
        'description': 'Полный доступ к системе',
        'priority': 100,
        'permissions': json.dumps({'all': True})
    }
)

client = TestClient(app)


# ---------- Фикстуры ----------
@pytest.fixture(autouse=True)
def cleanup_db():
    """Очищаем данные между тестами, но сохраняем структуру"""
    User.delete().execute()
    AuthSession.delete().execute()
    RecoveryCode.delete().execute()
    yield


@pytest.fixture
def worker_role():
    """Роль работника"""
    return UserRole.get(name='Работник')


@pytest.fixture
def test_user(worker_role):
    """Создает тестового пользователя"""
    user = User.create(
        first_name='Тест',
        last_name='Тестов',
        username='test_user',
        password_hash=bcrypt.hashpw('Password123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        email='test@test.com',
        role=worker_role,
        is_active=True
    )
    return user


@pytest.fixture
def verified_user(worker_role):
    """Создает верифицированного пользователя"""
    user = User.create(
        first_name='Иван',
        last_name='Иванов',
        username='ivan_verified',
        password_hash=bcrypt.hashpw('Password123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        email='ivan@test.com',
        tg_username='@ivan',
        tg_id=123456789,
        tg_chat_id=-123456789,
        role=worker_role,
        is_active=True,
        is_verified=True,
        tg_verified=True
    )
    return user


@pytest.fixture
def unverified_user(worker_role):
    """Создает неподтвержденного пользователя"""
    user = User.create(
        first_name='Петр',
        last_name='Петров',
        username='petr_unverified',
        password_hash=bcrypt.hashpw('Password123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        email='petr@test.com',
        role=worker_role,
        is_active=True,
        is_verified=False,
        tg_verified=False
    )
    return user


@pytest.fixture
def auth_token(verified_user):
    """Создает токен авторизации"""
    session = AuthSession.create_session(
        user=verified_user,
        session_type='web',
        ip='127.0.0.1',
        user_agent='test-agent'
    )
    return session.token


# ---------- Тесты ----------
class TestAuthRegister:
    """Тесты регистрации"""

    def test_register_success(self, worker_role):
        """Успешная регистрация"""
        response = client.post("/api/v1/auth/register", json={
            "first_name": "Сергей",
            "last_name": "Сергеев",
            "username": "sergey",
            "password": "Password123!",
            "email": "sergey@test.com",
            "tg_username": "@sergey"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["requires_verification"] is True
        assert "user_id" in data
        assert "tg_code" in data
        assert len(data["tg_code"]) == 6

        user = User.get_or_none(User.username == "sergey")
        assert user is not None
        assert user.first_name == "Сергей"
        assert user.email == "sergey@test.com"
        assert user.role_id == worker_role.id

    def test_register_duplicate_username(self, verified_user):
        """Регистрация с существующим username"""
        response = client.post("/api/v1/auth/register", json={
            "first_name": "Иван",
            "last_name": "Иванов",
            "username": "ivan_verified",
            "password": "Password123!"
        })

        assert response.status_code == 400
        assert "Username already taken" in response.text

    def test_register_duplicate_email(self, verified_user):
        """Регистрация с существующим email"""
        response = client.post("/api/v1/auth/register", json={
            "first_name": "Петр",
            "last_name": "Петров",
            "username": "petr_new",
            "password": "Password123!",
            "email": "ivan@test.com"
        })

        assert response.status_code == 400
        assert "Email already registered" in response.text

    def test_register_invalid_password(self):
        """Регистрация с невалидным паролем"""
        response = client.post("/api/v1/auth/register", json={
            "first_name": "Анна",
            "last_name": "Аннова",
            "username": "anna",
            "password": "weak"
        })

        assert response.status_code == 422


class TestAuthLogin:
    """Тесты входа в систему"""

    def test_login_verified_user_success(self, verified_user):
        """Успешный вход верифицированного пользователя"""
        response = client.post("/api/v1/auth/login", json={
            "username": "ivan_verified",
            "password": "Password123"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["requires_verification"] is False
        assert "access_token" in data
        assert "refresh_token" in data
        assert "user" in data
        assert data["user"]["username"] == "ivan_verified"

    def test_login_unverified_user_success(self, unverified_user):
        """Вход неподтвержденного пользователя - требует верификации"""
        response = client.post("/api/v1/auth/login", json={
            "username": "petr_unverified",
            "password": "Password123"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["requires_verification"] is True
        assert "user_id" in data
        assert "tg_code" in data
        assert "access_token" not in data

    def test_login_wrong_password(self, verified_user):
        """Неверный пароль"""
        response = client.post("/api/v1/auth/login", json={
            "username": "ivan_verified",
            "password": "WrongPassword"
        })

        assert response.status_code == 401
        assert "Invalid username or password" in response.text

    def test_login_user_not_found(self):
        """Пользователь не найден"""
        response = client.post("/api/v1/auth/login", json={
            "username": "nonexistent",
            "password": "Password123"
        })

        assert response.status_code == 401
        assert "Invalid username or password" in response.text


class TestTelegramVerification:
    """Тесты верификации Telegram"""

    def test_verify_telegram_success(self, unverified_user):
        """Успешная верификация Telegram"""
        tg_code = unverified_user.generate_tg_code()
        unverified_user.save()

        response = client.post("/api/v1/auth/verify-telegram", json={
            "user_id": unverified_user.id,
            "code": tg_code,
            "tg_id": 987654321,
            "tg_chat_id": -987654321
        })

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert "user" in data

        user = User.get_by_id(unverified_user.id)
        assert user.tg_verified is True
        assert user.tg_id == 987654321

    def test_verify_telegram_invalid_code(self, unverified_user):
        """Неверный код"""
        unverified_user.generate_tg_code()
        unverified_user.save()

        response = client.post("/api/v1/auth/verify-telegram", json={
            "user_id": unverified_user.id,
            "code": "000000"
        })

        assert response.status_code == 400
        assert "Invalid or expired verification code" in response.text

    def test_verify_telegram_expired_code(self, unverified_user):
        """Просроченный код"""
        unverified_user.tg_code = '123456'
        unverified_user.tg_code_expires = datetime.now() - timedelta(minutes=1)
        unverified_user.save()

        response = client.post("/api/v1/auth/verify-telegram", json={
            "user_id": unverified_user.id,
            "code": "123456"
        })

        assert response.status_code == 400
        assert "Invalid or expired verification code" in response.text


class TestSessions:
    """Тесты управления сессиями"""

    def test_refresh_token_success(self, verified_user, auth_token):
        """Успешное обновление токена"""
        session = AuthSession.get(token=auth_token)

        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": session.refresh_token
        })

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["access_token"] != auth_token
        assert data["refresh_token"] == session.refresh_token

    def test_refresh_token_invalid(self):
        """Невалидный refresh токен"""
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": "invalid-token"
        })

        assert response.status_code == 401
        assert "Invalid refresh token" in response.text

    def test_logout_success(self, verified_user, auth_token):
        """Успешный выход"""
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {auth_token}"}
        )

        assert response.status_code == 200
        assert "Successfully logged out" in response.text

        session = AuthSession.get_or_none(token=auth_token)
        assert session.is_active is False


class TestPasswordRecovery:
    """Тесты восстановления пароля"""

    def test_initiate_recovery_success(self, test_user):
        """Успешная инициация восстановления"""
        response = client.post(
            "/api/v1/auth/recovery/initiate",
            json={"username": "test_user"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "recovery_code" in data
        assert data["user_id"] == test_user.id

        code = RecoveryCode.get_or_none(RecoveryCode.user == test_user)
        assert code is not None

    def test_initiate_recovery_user_not_found(self):
        """Пользователь не найден - не сообщаем об ошибке"""
        response = client.post(
            "/api/v1/auth/recovery/initiate",
            json={"username": "nonexistent"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "If user exists" in data["message"]

    def test_reset_password_success(self, test_user):
        """Успешный сброс пароля"""
        recovery = RecoveryCode.create_for_user(test_user)

        response = client.post(
            "/api/v1/auth/recovery/reset",
            json={
                "recovery_code": recovery.code,
                "new_password": "NewPassword123!"
            }
        )

        assert response.status_code == 200
        assert "Password successfully reset" in response.text

        user = User.get_by_id(test_user.id)
        assert bcrypt.checkpw("NewPassword123!".encode('utf-8'),
                              user.password_hash.encode('utf-8'))

        recovery = RecoveryCode.get_by_id(recovery.id)
        assert recovery.used_at is not None

    def test_reset_password_invalid_code(self):
        """Невалидный код восстановления"""
        response = client.post(
            "/api/v1/auth/recovery/reset",
            json={
                "recovery_code": "invalid-code",
                "new_password": "NewPassword123!"
            }
        )

        assert response.status_code == 400
        assert "Invalid recovery code" in response.text

    def test_reset_password_expired_code(self, test_user):
        """Просроченный код"""
        recovery = RecoveryCode.create_for_user(test_user)
        recovery.expires_at = datetime.now() - timedelta(hours=1)
        recovery.save()

        response = client.post(
            "/api/v1/auth/recovery/reset",
            json={
                "recovery_code": recovery.code,
                "new_password": "NewPassword123!"
            }
        )

        assert response.status_code == 400
        assert "Recovery code expired or already used" in response.text

    def test_reset_password_used_code(self, test_user):
        """Уже использованный код"""
        recovery = RecoveryCode.create_for_user(test_user)
        recovery.used_at = datetime.now()
        recovery.save()

        response = client.post(
            "/api/v1/auth/recovery/reset",
            json={
                "recovery_code": recovery.code,
                "new_password": "NewPassword123!"
            }
        )

        assert response.status_code == 400
        assert "Recovery code expired or already used" in response.text