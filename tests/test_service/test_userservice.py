import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json
import bcrypt
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Создаем тестовую БД перед импортом моделей
from peewee import SqliteDatabase

# Импортируем модели и сервис
from core.db.models.user import User, UserRole, AuthSession, RecoveryCode, AuthLog
from core.services.UserService import UserService


# ------------------- Фикстуры для тестов -------------------

@pytest.fixture(scope='function')
def test_db():
    """Создаем тестовую БД в памяти"""
    test_db = SqliteDatabase(':memory:')

    # Привязываем модели к тестовой БД
    test_db.bind([User, UserRole, AuthSession, RecoveryCode, AuthLog], bind_refs=False, bind_backrefs=False)

    test_db.connect()
    test_db.create_tables([User, UserRole, AuthSession, RecoveryCode, AuthLog])

    yield test_db

    test_db.drop_tables([User, UserRole, AuthSession, RecoveryCode, AuthLog])
    test_db.close()


@pytest.fixture
def user_service(test_db):
    """Создаем экземпляр сервиса с тестовой БД"""
    return UserService()


@pytest.fixture
def default_role(test_db):
    """Создаем роль по умолчанию"""
    role, _ = UserRole.get_or_create(
        name='Работник',
        defaults={
            'description': 'Стандартный пользователь',
            'priority': 1,
            'permissions': json.dumps({'view_tasks': True})
        }
    )
    return role


@pytest.fixture
def admin_role(test_db):
    """Создаем роль администратора"""
    role, _ = UserRole.get_or_create(
        name='Хозяин',
        defaults={
            'description': 'Администратор',
            'priority': 100,
            'permissions': json.dumps({'all': True})
        }
    )
    return role


@pytest.fixture
def test_user(test_db, default_role):
    """Создаем тестового пользователя (неверифицированный)"""
    return User.create(
        first_name='Иван',
        last_name='Иванов',
        username='ivanov',
        password_hash=bcrypt.hashpw('Password123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        email='ivanov@test.com',
        tg_username='@ivanov',
        role=default_role,
        is_active=True,
        is_verified=False,
        tg_verified=False
    )


@pytest.fixture
def verified_user(test_db, default_role):
    """Создаем верифицированного пользователя"""
    return User.create(
        first_name='Иван',
        last_name='Иванов',
        username='ivanov_verified',
        password_hash=bcrypt.hashpw('Password123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        email='ivanov_verified@test.com',
        tg_username='@ivanov_verified',
        tg_id=123456789,
        tg_chat_id=-123456789,
        role=default_role,
        is_active=True,
        is_verified=True,
        tg_verified=True
    )


@pytest.fixture
def unverified_user(test_db, default_role):
    """Создаем неподтвержденного пользователя"""
    return User.create(
        first_name='Петр',
        last_name='Петров',
        username='petrov',
        password_hash=bcrypt.hashpw('Password123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        email='petrov@test.com',  # Добавляем email
        role=default_role,
        is_active=True,
        is_verified=False,
        tg_verified=False
    )


@pytest.fixture
def admin_user(test_db, admin_role):
    """Создаем администратора"""
    return User.create(
        first_name='Admin',
        last_name='Adminov',
        username='admin',
        password_hash=bcrypt.hashpw('Admin123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
        role=admin_role,
        is_active=True,
        is_superuser=True,
        is_verified=True,
        tg_verified=True
    )


@pytest.fixture
def auth_session(test_db, verified_user):
    """Создаем тестовую сессию"""
    return AuthSession.create_session(
        user=verified_user,
        session_type='web',
        ip='127.0.0.1',
        user_agent='test-agent'
    )


# ------------------- Тесты валидации -------------------

class TestValidation:
    """Тесты методов валидации"""

    def test_validate_username_valid(self, user_service):
        valid, error = user_service._validate_username('valid_user123')
        assert valid is True
        assert error is None

    def test_validate_username_too_short(self, user_service):
        valid, error = user_service._validate_username('ab')
        assert valid is False
        assert 'at least 3 characters' in error

    def test_validate_username_too_long(self, user_service):
        valid, error = user_service._validate_username('a' * 51)
        assert valid is False
        assert 'at most 50 characters' in error

    def test_validate_username_invalid_chars(self, user_service):
        valid, error = user_service._validate_username('user@name')
        assert valid is False
        assert 'only contain letters, numbers' in error

    def test_validate_password_valid(self, user_service):
        valid, error = user_service._validate_password('Password123!')
        assert valid is True
        assert error is None

    def test_validate_password_too_short(self, user_service):
        valid, error = user_service._validate_password('Pass1')
        assert valid is False
        assert 'at least 8 characters' in error

    def test_validate_password_no_uppercase(self, user_service):
        valid, error = user_service._validate_password('password123')
        assert valid is False
        assert 'uppercase, lowercase and digit' in error

    def test_validate_password_no_digit(self, user_service):
        valid, error = user_service._validate_password('Password!')
        assert valid is False
        assert 'uppercase, lowercase and digit' in error

    def test_validate_email_valid(self, user_service):
        valid, error = user_service._validate_email('test@example.com')
        assert valid is True
        assert error is None

    def test_validate_email_invalid(self, user_service):
        valid, error = user_service._validate_email('invalid-email')
        assert valid is False
        assert 'Invalid email format' in error

    def test_validate_email_empty(self, user_service):
        valid, error = user_service._validate_email('')
        assert valid is True
        assert error is None


# ------------------- Тесты регистрации -------------------

class TestRegistration:
    """Тесты регистрации пользователей"""

    def test_register_success(self, user_service, test_db):
        """Успешная регистрация"""
        result = user_service.register(
            first_name='Сергей',
            last_name='Сергеев',
            username='sergeev',
            password='Password123!',
            email='sergeev@test.com',
            tg_username='@sergeev'
        )

        assert result['user'] is not None
        assert result['tg_code'] is not None
        assert result['requires_verification'] is True
        assert result['user'].username == 'sergeev'
        assert result['user'].is_verified is False

        user = User.get(User.username == 'sergeev')
        assert user.first_name == 'Сергей'
        assert user.last_name == 'Сергеев'
        assert user.email == 'sergeev@test.com'
        assert user.tg_username == '@sergeev'

    def test_register_duplicate_username(self, user_service, test_user):
        """Регистрация с существующим username"""
        with pytest.raises(ValueError, match='Username already taken'):
            user_service.register(
                first_name='Иван',
                last_name='Иванов',
                username='ivanov',
                password='Password123!'
            )

    def test_register_duplicate_email(self, user_service, test_user):
        """Регистрация с существующим email"""
        with pytest.raises(ValueError, match='Email already registered'):
            user_service.register(
                first_name='Петр',
                last_name='Петров',
                username='petrov',
                password='Password123!',
                email='ivanov@test.com'
            )

    def test_register_duplicate_tg_username(self, user_service, test_user):
        """Регистрация с существующим Telegram username"""
        with pytest.raises(ValueError, match='Telegram username already registered'):
            user_service.register(
                first_name='Петр',
                last_name='Петров',
                username='petrov',
                password='Password123!',
                tg_username='@ivanov'
            )

    def test_register_invalid_password(self, user_service):
        """Регистрация с невалидным паролем"""
        with pytest.raises(ValueError, match='Invalid password'):
            user_service.register(
                first_name='Анна',
                last_name='Аннова',
                username='annova',
                password='weak'
            )

    def test_register_invalid_username(self, user_service):
        """Регистрация с невалидным username"""
        with pytest.raises(ValueError, match='Invalid username'):
            user_service.register(
                first_name='Анна',
                last_name='Аннова',
                username='an',
                password='Password123!'
            )


# ------------------- Тесты аутентификации -------------------

class TestAuthentication:
    """Тесты аутентификации"""

    def test_login_success_verified(self, user_service, verified_user):
        """Успешный вход с подтвержденным Telegram"""
        result = user_service.login(
            username='ivanov_verified',
            password='Password123',
            ip='127.0.0.1',
            user_agent='test-agent'
        )

        assert result['requires_verification'] is False
        assert result['user'] is not None
        assert result['session'] is not None
        assert result['access_token'] is not None
        assert result['refresh_token'] is not None

        user = User.get_by_id(verified_user.id)
        assert user.last_login is not None
        assert user.last_ip == '127.0.0.1'

    def test_login_success_unverified(self, user_service, unverified_user):
        """Вход с неподтвержденным Telegram - требует верификации"""
        result = user_service.login(
            username='petrov',
            password='Password123'
        )

        assert result['requires_verification'] is True
        assert result['user_id'] == unverified_user.id
        assert result['tg_code'] is not None
        assert result['session'] is None

        user = User.get_by_id(unverified_user.id)
        assert user.tg_code is not None
        assert user.tg_code_expires is not None

    def test_login_wrong_password(self, user_service, test_user):
        """Неверный пароль"""
        with pytest.raises(ValueError, match='Invalid username or password'):
            user_service.login(
                username='ivanov',
                password='WrongPassword'
            )

    def test_login_user_not_found(self, user_service):
        """Пользователь не найден"""
        with pytest.raises(ValueError, match='Invalid username or password'):
            user_service.login(
                username='nonexistent',
                password='Password123'
            )

    def test_login_inactive_user(self, user_service, test_user):
        """Неактивный пользователь"""
        test_user.is_active = False
        test_user.save()

        with pytest.raises(ValueError, match='Invalid username or password'):
            user_service.login(
                username='ivanov',
                password='Password123'
            )

    def test_verify_telegram_code_success(self, user_service, unverified_user):
        """Успешная верификация Telegram кода"""
        tg_code = unverified_user.generate_tg_code()
        unverified_user.save()

        result = user_service.verify_telegram_code(
            user_id=unverified_user.id,
            code=tg_code,
            tg_id=123456789,
            tg_chat_id=-123456789
        )

        assert result['success'] is True
        assert result['user'] is not None
        assert result['session'] is not None

        user = User.get_by_id(unverified_user.id)
        assert user.tg_verified is True
        assert user.tg_id == 123456789
        assert user.tg_chat_id == -123456789
        assert user.tg_code is None

    def test_verify_telegram_code_invalid(self, user_service, unverified_user):
        """Неверный код верификации"""
        unverified_user.generate_tg_code()
        unverified_user.save()

        with pytest.raises(ValueError, match='Invalid or expired verification code'):
            user_service.verify_telegram_code(
                user_id=unverified_user.id,
                code='000000'
            )

    def test_verify_telegram_code_expired(self, user_service, unverified_user):
        """Просроченный код"""
        unverified_user.tg_code = '123456'
        unverified_user.tg_code_expires = datetime.now() - timedelta(minutes=1)
        unverified_user.save()

        with pytest.raises(ValueError, match='Invalid or expired verification code'):
            user_service.verify_telegram_code(
                user_id=unverified_user.id,
                code='123456'
            )

    def test_verify_telegram_code_max_attempts(self, user_service, unverified_user):
        """Превышение лимита попыток"""
        unverified_user.tg_code = '123456'
        unverified_user.tg_code_expires = datetime.now() + timedelta(minutes=10)
        unverified_user.tg_code_attempts = 5
        unverified_user.save()

        with pytest.raises(ValueError, match='Invalid or expired verification code'):
            user_service.verify_telegram_code(
                user_id=unverified_user.id,
                code='123456'
            )

    def test_verify_telegram_code_user_not_found(self, user_service):
        """Пользователь не найден"""
        with pytest.raises(ValueError, match='User not found'):
            user_service.verify_telegram_code(
                user_id=999,
                code='123456'
            )


# ------------------- Тесты сессий -------------------

class TestSessions:
    """Тесты управления сессиями"""

    def test_refresh_session_success(self, user_service, auth_session):
        """Успешное обновление сессии"""
        result = user_service.refresh_session(auth_session.refresh_token)

        assert result['access_token'] is not None
        assert result['refresh_token'] == auth_session.refresh_token
        assert result['expires_at'] is not None

        session = AuthSession.get_by_id(auth_session.id)
        assert session.token == result['access_token']
        assert session.expires_at > auth_session.expires_at

    def test_refresh_session_invalid_token(self, user_service):
        """Невалидный refresh токен"""
        with pytest.raises(ValueError, match='Invalid refresh token'):
            user_service.refresh_session('invalid-token')

    def test_refresh_session_expired(self, user_service, auth_session):
        """Просроченный refresh токен"""
        auth_session.refresh_expires_at = datetime.now() - timedelta(days=1)
        auth_session.save()

        with pytest.raises(ValueError, match='Refresh token expired'):
            user_service.refresh_session(auth_session.refresh_token)

    def test_logout_success(self, user_service, auth_session):
        """Успешный выход из системы"""
        result = user_service.logout(auth_session.token)
        assert result is True

        session = AuthSession.get_by_id(auth_session.id)
        assert session.is_active is False

    def test_logout_invalid_token(self, user_service):
        """Невалидный токен"""
        result = user_service.logout('invalid-token')
        assert result is False

    def test_logout_all(self, user_service, verified_user):
        """Завершение всех сессий"""
        session1 = AuthSession.create_session(verified_user)
        session2 = AuthSession.create_session(verified_user)
        session3 = AuthSession.create_session(verified_user)

        count = user_service.logout_all(verified_user.id, exclude_token=session1.token)

        assert count == 2

        assert AuthSession.get_by_id(session1.id).is_active is True
        assert AuthSession.get_by_id(session2.id).is_active is False
        assert AuthSession.get_by_id(session3.id).is_active is False

    def test_validate_token_valid(self, user_service, auth_session, verified_user):
        """Валидация корректного токена"""
        user = user_service.validate_token(auth_session.token)

        assert user is not None
        assert user.id == verified_user.id

        session = AuthSession.get_by_id(auth_session.id)
        assert session.last_used_at is not None

    def test_validate_token_expired(self, user_service, auth_session):
        """Просроченный токен"""
        auth_session.expires_at = datetime.now() - timedelta(minutes=1)
        auth_session.save()

        user = user_service.validate_token(auth_session.token)
        assert user is None

        session = AuthSession.get_by_id(auth_session.id)
        assert session.is_active is False

    def test_get_user_sessions(self, user_service, verified_user):
        """Получение сессий пользователя"""
        AuthSession.create_session(verified_user)
        AuthSession.create_session(verified_user)

        sessions = user_service.get_user_sessions(verified_user.id)
        assert len(sessions) >= 2

    def test_revoke_session(self, user_service, verified_user):
        """Отзыв сессии"""
        session = AuthSession.create_session(verified_user)

        result = user_service.revoke_session(session.id, verified_user.id)
        assert result is True

        assert AuthSession.get_by_id(session.id).is_active is False

    def test_revoke_session_wrong_user(self, user_service, verified_user, unverified_user):
        """Отзыв сессии другого пользователя"""
        session = AuthSession.create_session(verified_user)

        result = user_service.revoke_session(session.id, unverified_user.id)
        assert result is False
        assert AuthSession.get_by_id(session.id).is_active is True


# ------------------- Тесты восстановления доступа -------------------

class TestRecovery:
    """Тесты восстановления пароля"""

    def test_initiate_password_recovery_success(self, user_service, test_user):
        """Успешная инициация восстановления"""
        result = user_service.initiate_password_recovery('ivanov')

        assert result['success'] is True
        assert result['user_id'] == test_user.id
        assert result['recovery_code'] is not None
        assert result['expires_at'] is not None

        code = RecoveryCode.get(RecoveryCode.user == test_user)
        assert code.code == result['recovery_code']
        assert code.used_at is None

    def test_initiate_password_recovery_user_not_found(self, user_service):
        """Пользователь не найден - не сообщаем об этом"""
        result = user_service.initiate_password_recovery('nonexistent')

        assert result['success'] is False
        assert 'If user exists' in result['message']

        assert RecoveryCode.select().count() == 0

    def test_reset_password_success(self, user_service, test_user):
        """Успешный сброс пароля"""
        recovery = RecoveryCode.create_for_user(test_user)

        result = user_service.reset_password(
            recovery_code=recovery.code,
            new_password='NewPassword123!',
            ip='127.0.0.1'
        )

        assert result['success'] is True

        user = User.get_by_id(test_user.id)
        assert user_service._verify_password('NewPassword123!', user.password_hash)

        recovery = RecoveryCode.get_by_id(recovery.id)
        assert recovery.used_at is not None
        assert recovery.used_ip == '127.0.0.1'

    def test_reset_password_invalid_code(self, user_service):
        """Невалидный код восстановления"""
        with pytest.raises(ValueError, match='Invalid recovery code'):
            user_service.reset_password(
                recovery_code='invalid-code',
                new_password='NewPassword123!'
            )

    def test_reset_password_expired_code(self, user_service, test_user):
        """Просроченный код восстановления"""
        recovery = RecoveryCode.create_for_user(test_user)
        recovery.expires_at = datetime.now() - timedelta(hours=1)
        recovery.save()

        # Должен выбросить исключение с сообщением "Recovery code expired or already used"
        with pytest.raises(ValueError, match='Recovery code expired or already used'):
            user_service.reset_password(
                recovery_code=recovery.code,
                new_password='NewPassword123!'
            )

    def test_reset_password_used_code(self, user_service, test_user):
        """Уже использованный код"""
        recovery = RecoveryCode.create_for_user(test_user)
        recovery.used_at = datetime.now()
        recovery.save()

        # Должен выбросить исключение с сообщением "Recovery code expired or already used"
        with pytest.raises(ValueError, match='Recovery code expired or already used'):
            user_service.reset_password(
                recovery_code=recovery.code,
                new_password='NewPassword123!'
            )

    def test_reset_password_invalid_new_password(self, user_service, test_user):
        """Невалидный новый пароль"""
        recovery = RecoveryCode.create_for_user(test_user)

        with pytest.raises(ValueError, match='Invalid password'):
            user_service.reset_password(
                recovery_code=recovery.code,
                new_password='weak'
            )


# ------------------- Тесты управления профилем -------------------

class TestProfileManagement:
    """Тесты управления профилем"""

    def test_get_user_by_id(self, user_service, test_user):
        """Получение пользователя по ID"""
        user = user_service.get_user_by_id(test_user.id)
        assert user is not None
        assert user.id == test_user.id

    def test_get_user_by_id_not_found(self, user_service):
        """Пользователь не найден по ID"""
        user = user_service.get_user_by_id(999)
        assert user is None

    def test_get_user_by_username(self, user_service, test_user):
        """Получение пользователя по username"""
        user = user_service.get_user_by_username('ivanov')
        assert user is not None
        assert user.username == 'ivanov'

    def test_get_user_by_username_not_found(self, user_service):
        """Пользователь не найден по username"""
        user = user_service.get_user_by_username('nonexistent')
        assert user is None

    def test_get_user_by_tg_id(self, user_service, verified_user):
        """Получение пользователя по Telegram ID"""
        user = user_service.get_user_by_tg_id(123456789)
        assert user is not None
        assert user.tg_id == 123456789

    def test_update_profile_success(self, user_service, test_user):
        """Успешное обновление профиля"""
        updated_user = user_service.update_profile(
            user_id=test_user.id,
            first_name='Петр',
            last_name='Петров',
            email='petrov@test.com',
            tg_username='@petrov'
        )

        assert updated_user.first_name == 'Петр'
        assert updated_user.last_name == 'Петров'
        assert updated_user.email == 'petrov@test.com'
        assert updated_user.tg_username == '@petrov'
        assert updated_user.tg_verified is False

    def test_update_profile_partial(self, user_service, test_user):
        """Частичное обновление профиля"""
        updated_user = user_service.update_profile(
            user_id=test_user.id,
            first_name='Петр'
        )

        assert updated_user.first_name == 'Петр'
        assert updated_user.last_name == 'Иванов'
        assert updated_user.email == 'ivanov@test.com'

    def test_update_profile_clear_email(self, user_service, test_user):
        """Очистка email"""
        updated_user = user_service.update_profile(
            user_id=test_user.id,
            email=''
        )

        assert updated_user.email is None

    def test_update_profile_clear_tg_username(self, user_service, test_user):
        """Очистка Telegram username"""
        updated_user = user_service.update_profile(
            user_id=test_user.id,
            tg_username=''
        )

        assert updated_user.tg_username is None
        assert updated_user.tg_verified is False

    def test_update_profile_duplicate_email(self, user_service, test_user, unverified_user):
        """Обновление с существующим email"""
        # Убедимся, что у unverified_user есть email
        assert unverified_user.email is not None

        with pytest.raises(ValueError, match='Email already registered'):
            user_service.update_profile(
                user_id=test_user.id,
                email=unverified_user.email
            )

    def test_update_profile_duplicate_tg_username(self, user_service, test_user, verified_user):
        """Обновление с существующим Telegram username"""
        with pytest.raises(ValueError, match='Telegram username already registered'):
            user_service.update_profile(
                user_id=test_user.id,
                tg_username='@ivanov_verified'
            )

    def test_update_profile_invalid_email(self, user_service, test_user):
        """Невалидный email"""
        with pytest.raises(ValueError, match='Invalid email'):
            user_service.update_profile(
                user_id=test_user.id,
                email='invalid-email'
            )

    def test_update_profile_user_not_found(self, user_service):
        """Пользователь не найден"""
        with pytest.raises(ValueError, match='User not found'):
            user_service.update_profile(
                user_id=999,
                first_name='Новое имя'
            )

    def test_change_password_success(self, user_service, test_user):
        """Успешная смена пароля"""
        result = user_service.change_password(
            user_id=test_user.id,
            current_password='Password123',
            new_password='NewPassword123!'
        )

        assert result is True

        user = User.get_by_id(test_user.id)
        assert user_service._verify_password('NewPassword123!', user.password_hash)

    def test_change_password_wrong_current(self, user_service, test_user):
        """Неверный текущий пароль"""
        with pytest.raises(ValueError, match='Current password is incorrect'):
            user_service.change_password(
                user_id=test_user.id,
                current_password='WrongPassword',
                new_password='NewPassword123!'
            )

    def test_change_password_invalid_new(self, user_service, test_user):
        """Невалидный новый пароль"""
        with pytest.raises(ValueError, match='Invalid new password'):
            user_service.change_password(
                user_id=test_user.id,
                current_password='Password123',
                new_password='weak'
            )

    def test_change_password_user_not_found(self, user_service):
        """Пользователь не найден"""
        with pytest.raises(ValueError, match='User not found'):
            user_service.change_password(
                user_id=999,
                current_password='Password123',
                new_password='NewPassword123!'
            )

    def test_update_theme_preferences(self, user_service, test_user):
        """Обновление настроек темы"""
        theme_data = {
            'mode': 'dark',
            'primary_color': '#ff0000'
        }

        result = user_service.update_theme_preferences(
            user_id=test_user.id,
            theme_data=theme_data
        )

        assert result['mode'] == 'dark'
        assert result['primary_color'] == '#ff0000'
        assert result['language'] == 'ru'

        user = User.get_by_id(test_user.id)
        assert json.loads(user.theme_preferences)['mode'] == 'dark'

    def test_update_notification_settings(self, user_service, test_user):
        """Обновление настроек уведомлений"""
        # Сначала устанавливаем начальные настройки со всеми полями
        initial_settings = {
            'telegram': True,
            'email': False,
            'task_assigned': True,
            'task_completed': True,
            'dependency_ready': True
        }
        test_user.notification_settings = json.dumps(initial_settings)
        test_user.save()

        settings = {
            'telegram': False,
            'email': True,
            'task_assigned': False
        }

        result = user_service.update_notification_settings(
            user_id=test_user.id,
            settings=settings
        )

        assert result['telegram'] is False
        assert result['email'] is True
        assert result['task_assigned'] is False
        assert result['task_completed'] is True  # Должно сохраниться
        assert result['dependency_ready'] is True  # Должно сохраниться


# ------------------- Тесты административных функций -------------------

class TestAdminFunctions:
    """Тесты административных функций"""

    def test_change_user_role_by_admin(self, user_service, test_user, admin_user, admin_role):
        """Администратор меняет роль пользователя"""
        updated_user = user_service.change_user_role(
            user_id=test_user.id,
            role_name='Хозяин',
            admin_user=admin_user
        )

        assert updated_user.role_id == admin_role.id

    def test_change_user_role_no_permission(self, user_service, test_user):
        """Обычный пользователь не может менять роли"""
        with pytest.raises(PermissionError, match='Insufficient permissions'):
            user_service.change_user_role(
                user_id=test_user.id,
                role_name='Хозяин',
                admin_user=test_user
            )

    def test_change_user_role_role_not_found(self, user_service, admin_user):
        """Роль не найдена"""
        with pytest.raises(ValueError, match='Role .* not found'):
            user_service.change_user_role(
                user_id=1,
                role_name='NonExistentRole',
                admin_user=admin_user
            )

    def test_deactivate_user_by_admin(self, user_service, test_user, admin_user):
        """Администратор деактивирует пользователя"""
        result = user_service.deactivate_user(
            user_id=test_user.id,
            admin_user=admin_user
        )

        assert result is True

        user = User.get_by_id(test_user.id)
        assert user.is_active is False

    def test_deactivate_user_no_permission(self, user_service, test_user):
        """Обычный пользователь не может деактивировать"""
        with pytest.raises(PermissionError, match='Insufficient permissions'):
            user_service.deactivate_user(
                user_id=test_user.id,
                admin_user=test_user
            )

    def test_deactivate_user_not_found(self, user_service, admin_user):
        """Пользователь для деактивации не найден"""
        with pytest.raises(ValueError, match='User not found'):
            user_service.deactivate_user(
                user_id=999,
                admin_user=admin_user
            )

    def test_activate_user(self, user_service, test_user, admin_user):
        """Активация пользователя"""
        test_user.is_active = False
        test_user.save()

        result = user_service.activate_user(
            user_id=test_user.id,
            admin_user=admin_user
        )

        assert result is True

        user = User.get_by_id(test_user.id)
        assert user.is_active is True

    def test_activate_user_not_found(self, user_service, admin_user):
        """Пользователь для активации не найден"""
        with pytest.raises(ValueError, match='User not found'):
            user_service.activate_user(
                user_id=999,
                admin_user=admin_user
            )


# ------------------- Тесты поиска и статистики -------------------

class TestSearchAndStats:
    """Тесты поиска и статистики"""

    def test_search_users_by_name(self, user_service, test_user, unverified_user):
        """Поиск пользователей по имени"""
        results = user_service.search_users(query='Иван')

        assert len(results) >= 1
        assert any(u.id == test_user.id for u in results)

    def test_search_users_by_username(self, user_service, test_user):
        """Поиск пользователей по username"""
        results = user_service.search_users(query='ivanov')

        assert len(results) >= 1
        assert results[0].username == 'ivanov'

    def test_search_users_by_role(self, user_service, test_user, unverified_user, default_role):
        """Поиск пользователей по роли"""
        results = user_service.search_users(role_id=default_role.id)

        assert len(results) >= 2
        assert all(u.role_id == default_role.id for u in results)

    def test_search_users_by_active_status(self, user_service, test_user, unverified_user):
        """Поиск по статусу активности"""
        test_user.is_active = False
        test_user.save()

        active_users = user_service.search_users(is_active=True)
        inactive_users = user_service.search_users(is_active=False)

        assert len(active_users) >= 1
        assert len(inactive_users) >= 1
        assert all(u.is_active is True for u in active_users)
        assert all(u.is_active is False for u in inactive_users)

    def test_search_users_with_limit_offset(self, user_service):
        """Поиск с пагинацией"""
        for i in range(5):
            User.create(
                first_name=f'User{i}',
                last_name='Test',
                username=f'testuser{i}',
                password_hash='hash',
                role_id=1,
                is_active=True
            )

        results = user_service.search_users(limit=2, offset=0)
        assert len(results) == 2

        results_page2 = user_service.search_users(limit=2, offset=2)
        assert len(results_page2) == 2
        assert results[0].id != results_page2[0].id

    def test_get_user_stats(self, user_service, verified_user, unverified_user, admin_user):
        """Получение статистики пользователей"""
        # Убедимся, что verified_user имеет tg_verified=True
        verified_user.tg_verified = True
        verified_user.save()

        stats = user_service.get_user_stats()

        assert stats['total_users'] >= 3
        assert stats['active_users'] >= 3
        assert stats['inactive_users'] == 0
        assert stats['verified_telegram'] >= 1
        assert 'Работник' in stats['by_role']
        assert 'Хозяин' in stats['by_role']
        assert stats['by_role']['Работник'] >= 2
        assert stats['by_role']['Хозяин'] >= 1

    def test_get_role_by_name(self, user_service, default_role):
        """Получение роли по имени"""
        role = user_service.get_role_by_name('Работник')
        assert role is not None
        assert role.name == 'Работник'

    def test_get_role_by_name_not_found(self, user_service):
        """Роль не найдена"""
        role = user_service.get_role_by_name('NonExistent')
        assert role is None

    def test_get_default_role(self, user_service, test_db):
        """Получение роли по умолчанию"""
        UserRole.delete().execute()

        role = user_service.get_default_role()
        assert role is not None
        assert role.name == 'Работник'
        assert role.priority == 1


# ------------------- Тесты логирования -------------------

class TestLogging:
    """Тесты системы логирования"""

    def test_auth_log_created_on_login(self, user_service, verified_user):
        """Проверка создания лога при входе"""
        initial_count = AuthLog.select().count()

        user_service.login(
            username='ivanov_verified',
            password='Password123',
            ip='127.0.0.1'
        )

        assert AuthLog.select().count() == initial_count + 1

        log = AuthLog.select().order_by(AuthLog.id.desc()).get()
        assert log.action == 'login'
        assert log.status == 'success'
        assert log.user_id == verified_user.id
        assert log.ip_address == '127.0.0.1'

    def test_auth_log_failed_login(self, user_service, test_user):
        """Проверка лога при неудачном входе"""
        initial_count = AuthLog.select().count()

        try:
            user_service.login(
                username='ivanov',
                password='WrongPassword'
            )
        except ValueError:
            pass

        assert AuthLog.select().count() == initial_count + 1

        log = AuthLog.select().order_by(AuthLog.id.desc()).get()
        assert log.action == 'login'
        assert log.status == 'failed'
        assert log.failure_reason == 'Invalid password'
        assert log.username == 'ivanov'

    def test_auth_log_registration(self, user_service):
        """Проверка лога при регистрации"""
        initial_count = AuthLog.select().count()

        user_service.register(
            first_name='Тест',
            last_name='Тестов',
            username='testuser',
            password='Password123!'
        )

        assert AuthLog.select().count() == initial_count + 1

        log = AuthLog.select().order_by(AuthLog.id.desc()).get()
        assert log.action == 'register'
        assert log.status == 'success'

    def test_auth_log_logout(self, user_service, auth_session):
        """Проверка лога при выходе"""
        initial_count = AuthLog.select().count()

        user_service.logout(auth_session.token)

        assert AuthLog.select().count() == initial_count + 1

        log = AuthLog.select().order_by(AuthLog.id.desc()).get()
        assert log.action == 'logout'
        assert log.status == 'success'

    def test_auth_log_refresh(self, user_service, auth_session):
        """Проверка лога при обновлении сессии"""
        initial_count = AuthLog.select().count()

        user_service.refresh_session(auth_session.refresh_token)

        assert AuthLog.select().count() == initial_count + 1

        log = AuthLog.select().order_by(AuthLog.id.desc()).get()
        assert log.action == 'refresh'
        assert log.status == 'success'

    def test_auth_log_verify(self, user_service, unverified_user):
        """Проверка лога при верификации"""
        tg_code = unverified_user.generate_tg_code()
        unverified_user.save()

        initial_count = AuthLog.select().count()

        user_service.verify_telegram_code(
            user_id=unverified_user.id,
            code=tg_code
        )

        assert AuthLog.select().count() == initial_count + 1

        log = AuthLog.select().order_by(AuthLog.id.desc()).get()
        assert log.action == 'verify'
        assert log.status == 'success'


# ------------------- Тесты граничных случаев -------------------

class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_create_session_for_unverified_user(self, user_service, unverified_user):
        """Создание сессии для неподтвержденного пользователя"""
        result = user_service.login(
            username='petrov',
            password='Password123'
        )

        assert result['requires_verification'] is True
        assert result['session'] is None

    def test_multiple_sessions_same_user(self, user_service, verified_user):
        """Множественные сессии одного пользователя"""
        session1 = user_service.login(
            username='ivanov_verified',
            password='Password123',
            device_id='device1'
        )

        session2 = user_service.login(
            username='ivanov_verified',
            password='Password123',
            device_id='device2'
        )

        sessions = user_service.get_user_sessions(verified_user.id)
        assert len(sessions) >= 2

    def test_concurrent_login_different_devices(self, user_service, verified_user):
        """Одновременный вход с разных устройств"""
        web_session = user_service.login(
            username='ivanov_verified',
            password='Password123',
            device_id='web',
            user_agent='chrome'
        )

        mobile_session = user_service.login(
            username='ivanov_verified',
            password='Password123',
            device_id='mobile',
            user_agent='ios'
        )

        assert web_session['session'].id != mobile_session['session'].id
        assert web_session['access_token'] != mobile_session['access_token']

    def test_session_expiry(self, user_service, verified_user):
        """Проверка истечения сессии"""
        session = AuthSession.create_session(verified_user)
        session.expires_at = datetime.now() - timedelta(minutes=1)
        session.save()

        user = user_service.validate_token(session.token)
        assert user is None

        with pytest.raises(ValueError):
            user_service.refresh_session(session.refresh_token)

    def test_verify_already_verified_user(self, user_service, verified_user):
        """Верификация уже подтвержденного пользователя"""
        result = user_service.login(
            username='ivanov_verified',
            password='Password123'
        )

        assert result['requires_verification'] is False
        assert result['session'] is not None

    def test_register_without_optional_fields(self, user_service):
        """Регистрация без опциональных полей"""
        result = user_service.register(
            first_name='Анна',
            last_name='Аннова',
            username='annova',
            password='Password123!'
        )

        assert result['user'] is not None
        assert result['user'].email is None
        assert result['user'].tg_username is None

    def test_update_profile_without_changes(self, user_service, test_user):
        """Обновление профиля без изменений"""
        user = user_service.update_profile(user_id=test_user.id)

        assert user.first_name == test_user.first_name
        assert user.last_name == test_user.last_name
        assert user.email == test_user.email

    def test_get_user_sessions_empty(self, user_service, unverified_user):
        """Получение сессий пользователя без сессий"""
        sessions = user_service.get_user_sessions(unverified_user.id)
        assert len(sessions) == 0

    def test_reset_password_with_same_password(self, user_service, test_user):
        """Сброс пароля на тот же самый"""
        recovery = RecoveryCode.create_for_user(test_user)
        old_hash = test_user.password_hash

        user_service.reset_password(
            recovery_code=recovery.code,
            new_password='Password123'  # Тот же пароль
        )

        user = User.get_by_id(test_user.id)
        assert user.password_hash != old_hash
        assert user_service._verify_password('Password123', user.password_hash)


# ------------------- Тесты производительности -------------------

class TestPerformance:
    """Тесты производительности"""

    def test_password_hashing(self, user_service):
        """Проверка хеширования пароля"""
        password = "TestPassword123!"
        hashed = user_service._hash_password(password)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert len(hashed) > 0
        assert hashed != password
        assert user_service._verify_password(password, hashed) is True

    def test_password_verification_fails(self, user_service):
        """Проверка неудачной верификации пароля"""
        password = "TestPassword123!"
        hashed = user_service._hash_password(password)

        assert user_service._verify_password("WrongPassword", hashed) is False

    def test_session_token_generation(self, user_service, verified_user):
        """Проверка генерации токенов сессии"""
        session = AuthSession.create_session(verified_user)

        assert session.token is not None
        assert len(session.token) > 0
        assert session.refresh_token is not None
        assert len(session.refresh_token) > 0
        assert session.token != session.refresh_token

    def test_unique_tokens(self, user_service, verified_user):
        """Проверка уникальности токенов"""
        session1 = AuthSession.create_session(verified_user)
        session2 = AuthSession.create_session(verified_user)

        assert session1.token != session2.token
        assert session1.refresh_token != session2.refresh_token

    def test_tg_code_generation(self, user_service, unverified_user):
        """Проверка генерации Telegram кода"""
        code = unverified_user.generate_tg_code()

        assert code is not None
        assert len(code) == 6
        assert code.isdigit()
        assert unverified_user.tg_code == code
        assert unverified_user.tg_code_expires is not None

    def test_recovery_code_generation(self, user_service, test_user):
        """Проверка генерации кода восстановления"""
        recovery = RecoveryCode.create_for_user(test_user)

        assert recovery.code is not None
        assert len(recovery.code) > 0
        assert recovery.used_at is None
        assert recovery.expires_at is not None