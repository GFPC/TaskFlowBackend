from peewee import *
from datetime import datetime, timedelta
import json
import secrets
from ...db.base import BaseModel


# ------------------- 1. Роли пользователей -------------------

class UserRole(BaseModel):
    """Роли пользователей"""
    id = AutoField()
    name = CharField(max_length=50, unique=True)
    description = TextField(null=True)
    permissions = TextField(null=True)  # JSON
    priority = IntegerField(default=0, index=True)  # Чем выше число, тем выше роль

    class Meta:
        table_name = 'user_roles'

    @property
    def permissions_dict(self):
        if self.permissions:
            return json.loads(self.permissions)
        return {}

    def has_permission(self, permission):
        """Проверка наличия конкретного разрешения"""
        perms = self.permissions_dict
        return permission in perms


# ------------------- 2. Пользователи -------------------

class User(BaseModel):
    """Пользователи системы"""
    id = AutoField()

    # Основная информация
    first_name = CharField(max_length=100)
    last_name = CharField(max_length=100)
    username = CharField(max_length=50, unique=True, index=True)
    password_hash = CharField(max_length=255)
    email = CharField(max_length=255, null=True, unique=True, index=True)

    # Telegram данные
    tg_username = CharField(max_length=100, null=True, index=True)
    tg_id = BigIntegerField(null=True, unique=True, index=True)
    tg_chat_id = BigIntegerField(null=True)  # ID чата для отправки сообщений
    tg_code = CharField(max_length=6, null=True)
    tg_code_expires = DateTimeField(null=True)
    tg_code_attempts = IntegerField(default=0)  # Количество попыток ввода кода
    tg_verified = BooleanField(default=False)  # Подтвержден ли Telegram

    # Роль и статус
    role = ForeignKeyField(UserRole, backref='users', on_delete='RESTRICT')
    is_active = BooleanField(default=True, index=True)
    is_superuser = BooleanField(default=False)  # Полный доступ ко всему

    # Временные метки
    created_at = DateTimeField(default=datetime.now, index=True)
    updated_at = DateTimeField(default=datetime.now)
    last_login = DateTimeField(null=True)
    last_activity = DateTimeField(null=True)  # Последнее действие
    last_ip = CharField(max_length=45, null=True)  # Последний IP

    # Настройки
    theme_preferences = TextField(null=True)  # JSON
    notification_settings = TextField(null=True, default='{"telegram": true, "email": false}')  # JSON

    class Meta:
        table_name = 'users'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.username})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def theme_preferences_dict(self):
        if self.theme_preferences:
            return json.loads(self.theme_preferences)
        return {
            "mode": "light",
            "primary_color": "#1976d2",
            "language": "ru"
        }

    @property
    def notification_settings_dict(self):
        if self.notification_settings:
            return json.loads(self.notification_settings)
        return {
            "telegram": True,
            "email": False,
            "task_assigned": True,
            "task_completed": True,
            "dependency_ready": True
        }

    def generate_tg_code(self):
        """Генерация 6-значного кода для подтверждения Telegram"""
        import random
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        self.tg_code = code
        self.tg_code_expires = datetime.now() + timedelta(minutes=10)
        self.tg_code_attempts = 0
        return code

    def verify_tg_code(self, code):
        """Проверка введенного кода"""
        if not self.tg_code or not self.tg_code_expires:
            return False

        if datetime.now() > self.tg_code_expires:
            return False

        if self.tg_code_attempts >= 5:  # Максимум 5 попыток
            return False

        self.tg_code_attempts += 1

        if self.tg_code == code:
            self.tg_verified = True
            self.tg_code = None
            self.tg_code_expires = None
            self.tg_code_attempts = 0
            return True

        return False

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(User, self).save(*args, **kwargs)


# ------------------- 3. Сессии аутентификации -------------------

class AuthSession(BaseModel):
    """Сессии аутентификации пользователей"""
    id = AutoField()

    # Токен и тип
    token = CharField(max_length=255, unique=True, index=True)
    refresh_token = CharField(max_length=255, unique=True, null=True, index=True)
    type = CharField(max_length=50, default='web')  # 'web', 'mobile', 'api'

    # Связь с пользователем
    user = ForeignKeyField(User, backref='auth_sessions', on_delete='CASCADE', index=True)

    # Информация о клиенте
    ip_address = CharField(max_length=45, null=True)
    user_agent = TextField(null=True)
    device_id = CharField(max_length=255, null=True)  # Для мобильных устройств
    location = CharField(max_length=255, null=True)  # Геолокация по IP

    # Временные метки
    created_at = DateTimeField(default=datetime.now, index=True)
    expires_at = DateTimeField(null=True, index=True)
    refresh_expires_at = DateTimeField(null=True)
    last_used_at = DateTimeField(null=True)

    # Статус
    is_active = BooleanField(default=True, index=True)
    is_blocked = BooleanField(default=False)
    blocked_reason = TextField(null=True)

    class Meta:
        table_name = 'auth_sessions'

    @classmethod
    def create_session(cls, user, session_type='web', ip=None, user_agent=None, device_id=None):
        """Создание новой сессии"""
        token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)

        # Время жизни: 1 час для токена, 7 дней для refresh
        expires_at = datetime.now() + timedelta(hours=1)
        refresh_expires_at = datetime.now() + timedelta(days=7)

        return cls.create(
            token=token,
            refresh_token=refresh_token,
            type=session_type,
            user=user,
            ip_address=ip,
            user_agent=user_agent,
            device_id=device_id,
            expires_at=expires_at,
            refresh_expires_at=refresh_expires_at
        )

    def refresh(self):
        """Обновление токена сессии"""
        self.token = secrets.token_urlsafe(32)
        self.expires_at = datetime.now() + timedelta(hours=1)
        self.last_used_at = datetime.now()
        self.save()
        return self.token

    def is_valid(self):
        """Проверка валидности сессии"""
        if not self.is_active or self.is_blocked:
            return False
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        return True

    def is_refresh_valid(self):
        """Проверка валидности refresh токена"""
        if not self.is_active or self.is_blocked:
            return False
        if self.refresh_expires_at and datetime.now() > self.refresh_expires_at:
            return False
        return True

    def invalidate(self):
        """Деактивация сессии"""
        self.is_active = False
        self.save()


# ------------------- 4. Коды восстановления -------------------

class RecoveryCode(BaseModel):
    """Коды для восстановления доступа"""
    id = AutoField()
    user = ForeignKeyField(User, backref='recovery_codes', on_delete='CASCADE', index=True)
    code = CharField(max_length=255, unique=True, index=True)

    created_at = DateTimeField(default=datetime.now)
    expires_at = DateTimeField(null=True)
    used_at = DateTimeField(null=True)
    used_ip = CharField(max_length=45, null=True)

    class Meta:
        table_name = 'recovery_codes'

    @classmethod
    def create_for_user(cls, user, expires_in_hours=24):
        """Создание кода восстановления"""
        code = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=expires_in_hours)

        return cls.create(
            user=user,
            code=code,
            expires_at=expires_at
        )

    def is_valid(self):
        """Проверка валидности кода"""
        if self.used_at:
            return False
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        return True

    def use(self, ip=None):
        """Использование кода"""
        self.used_at = datetime.now()
        self.used_ip = ip
        self.save()


class AuthLog(BaseModel):
    """Логирование всех попыток аутентификации"""
    id = AutoField()

    user = ForeignKeyField(User, backref='auth_logs', null=True, on_delete='SET NULL', index=True)
    username = CharField(max_length=50, null=True)  # Сохраняем даже если пользователь не найден

    action = CharField(max_length=50, index=True)  # 'login', 'logout', 'refresh', 'verify', 'recovery'
    status = CharField(max_length=20, index=True)  # 'success', 'failed', 'blocked'
    failure_reason = TextField(null=True)  # Причина неудачи

    ip_address = CharField(max_length=45, null=True)
    user_agent = TextField(null=True)

    created_at = DateTimeField(default=datetime.now, index=True)

    class Meta:
        table_name = 'auth_logs'
        indexes = (
            (('user', 'created_at'), False),
            (('ip_address', 'created_at'), False),
        )

    @classmethod
    def log(cls, action, status, user=None, username=None, ip=None, user_agent=None, reason=None):
        """Быстрое логирование события"""
        return cls.create(
            user=user,
            username=username or (user.username if user else None),
            action=action,
            status=status,
            failure_reason=reason,
            ip_address=ip,
            user_agent=user_agent
        )

