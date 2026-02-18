import json

from peewee import *
from datetime import datetime, timedelta
import bcrypt
import secrets
import re
from typing import Optional, Dict, Any, Tuple, List

from peewee import logger

from ..db.models.user import User, UserRole, AuthSession, RecoveryCode, AuthLog
from fastapi import HTTPException, status


class UserService:
    """Сервис для работы с пользователями и аутентификацией"""

    # Константы
    USERNAME_MIN_LENGTH = 3
    USERNAME_MAX_LENGTH = 50
    PASSWORD_MIN_LENGTH = 8
    TG_CODE_EXPIRY_MINUTES = 10
    SESSION_EXPIRY_HOURS = 1
    REFRESH_EXPIRY_DAYS = 7
    RECOVERY_EXPIRY_HOURS = 24

    def __init__(self):
        self.user_model = User
        self.role_model = UserRole
        self.session_model = AuthSession
        self.recovery_model = RecoveryCode
        self.log_model = AuthLog

    # ------------------- Валидация -------------------

    def _validate_username(self, username: str) -> Tuple[bool, Optional[str]]:
        """Валидация имени пользователя"""
        if not username:
            return False, "Username is required"

        if len(username) < self.USERNAME_MIN_LENGTH:
            return False, f"Username must be at least {self.USERNAME_MIN_LENGTH} characters"

        if len(username) > self.USERNAME_MAX_LENGTH:
            return False, f"Username must be at most {self.USERNAME_MAX_LENGTH} characters"

        if not re.match("^[a-zA-Z0-9_.-]+$", username):
            return False, "Username can only contain letters, numbers, underscores, dots and hyphens"

        return True, None

    def _validate_password(self, password: str) -> Tuple[bool, Optional[str]]:
        """Валидация пароля"""
        if not password:
            return False, "Password is required"

        if len(password) < self.PASSWORD_MIN_LENGTH:
            return False, f"Password must be at least {self.PASSWORD_MIN_LENGTH} characters"

        # Проверка на сложность
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(not c.isalnum() for c in password)

        if not (has_upper and has_lower and has_digit):
            return False, "Password must contain uppercase, lowercase and digit characters"

        return True, None

    def _validate_email(self, email: str) -> Tuple[bool, Optional[str]]:
        """Валидация email"""
        if not email:
            return True, None  # Email не обязателен

        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False, "Invalid email format"

        return True, None

    def _hash_password(self, password: str) -> str:
        """Хеширование пароля"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Проверка пароля"""
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

    # ------------------- Роли -------------------

    def get_default_role(self) -> Optional[UserRole]:
        """Получение роли по умолчанию (Работник)"""
        try:
            role, created = self.role_model.get_or_create(
                name='Работник',
                defaults={
                    'description': 'Стандартный пользователь системы',
                    'priority': 1,
                    'permissions': json.dumps({
                        'view_tasks': True,
                        'view_own_tasks': True,
                        'update_own_tasks': True,
                        'add_comments': True
                    })
                }
            )
            return role
        except Exception as e:
            # Если роль уже существует
            return self.role_model.get(name='Работник')

    def get_role_by_name(self, name: str) -> Optional[UserRole]:
        """Получение роли по имени"""
        try:
            return self.role_model.get(self.role_model.name == name)
        except self.role_model.DoesNotExist:
            return None

    # ------------------- Регистрация -------------------

    def register(self,
                 first_name: str,
                 last_name: str,
                 username: str,
                 password: str,
                 email: Optional[str] = None,
                 tg_username: Optional[str] = None) -> Dict[str, Any]:
        """
        Регистрация нового пользователя
        Возвращает данные пользователя и TG код для верификации
        """
        # Валидация
        valid, error = self._validate_username(username)
        if not valid:
            raise ValueError(f"Invalid username: {error}")

        valid, error = self._validate_password(password)
        if not valid:
            raise ValueError(f"Invalid password: {error}")

        valid, error = self._validate_email(email)
        if not valid:
            raise ValueError(f"Invalid email: {error}")

        # Проверка уникальности
        if self.user_model.select().where(self.user_model.username == username).exists():
            raise ValueError("Username already taken")

        if email and self.user_model.select().where(self.user_model.email == email).exists():
            raise ValueError("Email already registered")

        if tg_username and self.user_model.select().where(self.user_model.tg_username == tg_username).exists():
            raise ValueError("Telegram username already registered")

        # Получаем роль по умолчанию
        default_role = self.get_default_role()

        # Хешируем пароль
        password_hash = self._hash_password(password)

        # Создаем пользователя
        user = self.user_model.create(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            username=username.lower().strip(),
            password_hash=password_hash,
            email=email.strip() if email else None,
            tg_username=tg_username.strip() if tg_username else None,
            role=default_role,
            is_active=True,
            is_verified=False,
            theme_preferences=json.dumps({
                "mode": "light",
                "primary_color": "#1976d2",
                "language": "ru"
            })
        )

        # Генерируем код для Telegram
        tg_code = user.generate_tg_code()
        user.save()

        # Логируем регистрацию
        self.log_model.log(
            action='register',
            status='success',
            user=user
        )

        return {
            'user': user,
            'tg_code': tg_code,
            'requires_verification': True
        }

    # ------------------- Аутентификация -------------------

    def login(self,
              username: str,
              password: str,
              ip: Optional[str] = None,
              user_agent: Optional[str] = None,
              device_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Аутентификация пользователя
        Возвращает сессию и флаг необходимости TG кода
        """
        try:
            # Ищем пользователя
            user = self.user_model.get(
                (self.user_model.username == username.lower().strip()) &
                (self.user_model.is_active == True)
            )

            # Проверяем пароль
            if not self._verify_password(password, user.password_hash):
                # Логируем неудачную попытку
                self.log_model.log(
                    action='login',
                    status='failed',
                    username=username,
                    ip=ip,
                    user_agent=user_agent,
                    reason='Invalid password'
                )
                raise ValueError("Invalid username or password")

            # ТЕСТОВЫЙ РЕЖИМ - пропускаем верификацию
            from ..config import settings
            if settings.DEBUG:
                # В режиме отладки автоматически верифицируем
                if not user.tg_verified:
                    user.tg_verified = True
                    # Используем ID пользователя как основу для уникальности
                    user.tg_id = 1000000 + user.id  # Уникальный ID для каждого пользователя
                    user.tg_chat_id = -(1000000 + user.id)  # Уникальный chat_id
                    user.save()

            # Проверяем верификацию Telegram
            if not user.tg_verified:
                # Генерируем новый код
                tg_code = user.generate_tg_code()
                user.save()

                return {
                    'requires_verification': True,
                    'user_id': user.id,
                    'tg_code': tg_code,
                    'session': None
                }

            # Создаем сессию
            session = self.session_model.create_session(
                user=user,
                session_type='web',
                ip=ip,
                user_agent=user_agent,
                device_id=device_id
            )

            # Обновляем информацию о пользователе
            user.last_login = datetime.now()
            user.last_ip = ip
            user.save()

            # Логируем успешный вход
            self.log_model.log(
                action='login',
                status='success',
                user=user,
                ip=ip,
                user_agent=user_agent
            )

            return {
                'requires_verification': False,
                'user': user,
                'session': session,
                'access_token': session.token,
                'refresh_token': session.refresh_token,
                'token_type': 'bearer',
                'expires_at': session.expires_at
            }

        except self.user_model.DoesNotExist:
            # Логируем неудачную попытку
            self.log_model.log(
                action='login',
                status='failed',
                username=username,
                ip=ip,
                user_agent=user_agent,
                reason='User not found'
            )
            raise ValueError("Invalid username or password")

    def verify_telegram_code(self,
                             user_id: int,
                             code: str,
                             tg_id: Optional[int] = None,
                             tg_chat_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Верификация Telegram кода
        """
        try:
            user = self.user_model.get(
                (self.user_model.id == user_id) &
                (self.user_model.is_active == True)
            )

            # Проверяем код
            if user.verify_tg_code(code):
                # Сохраняем Telegram ID
                if tg_id:
                    user.tg_id = tg_id
                if tg_chat_id:
                    user.tg_chat_id = tg_chat_id
                user.save()

                # Создаем сессию
                session = self.session_model.create_session(user)

                # Логируем верификацию
                self.log_model.log(
                    action='verify',
                    status='success',
                    user=user
                )

                return {
                    'success': True,
                    'user': user,
                    'session': session,
                    'access_token': session.token,
                    'refresh_token': session.refresh_token
                }
            else:
                # Логируем неудачную верификацию
                self.log_model.log(
                    action='verify',
                    status='failed',
                    user=user,
                    reason='Invalid or expired code'
                )
                raise ValueError("Invalid or expired verification code")

        except self.user_model.DoesNotExist:
            raise ValueError("User not found")

    def refresh_session(self, refresh_token: str) -> Dict[str, Any]:
        """
        Обновление сессии по refresh token
        """
        try:
            session = self.session_model.get(
                (self.session_model.refresh_token == refresh_token) &
                (self.session_model.is_active == True) &
                (self.session_model.is_blocked == False)
            )

            # Проверяем валидность refresh токена
            if not session.is_refresh_valid():
                session.invalidate()
                raise ValueError("Refresh token expired")

            # Обновляем токен
            new_token = session.refresh()

            # Логируем обновление
            self.log_model.log(
                action='refresh',
                status='success',
                user=session.user
            )

            return {
                'access_token': new_token,
                'refresh_token': session.refresh_token,
                'expires_at': session.expires_at
            }

        except self.session_model.DoesNotExist:
            raise ValueError("Invalid refresh token")

    def logout(self, token: str) -> bool:
        """
        Завершение сессии
        """
        try:
            session = self.session_model.get(
                (self.session_model.token == token) &
                (self.session_model.is_active == True)
            )

            user = session.user
            session.invalidate()

            # Логируем выход
            self.log_model.log(
                action='logout',
                status='success',
                user=user
            )

            return True

        except self.session_model.DoesNotExist:
            return False

    def logout_all(self, user_id: int, exclude_token: Optional[str] = None) -> int:
        """
        Завершение всех сессий пользователя
        Возвращает количество завершенных сессий
        """
        query = self.session_model.select().where(
            (self.session_model.user_id == user_id) &
            (self.session_model.is_active == True)
        )

        if exclude_token:
            query = query.where(self.session_model.token != exclude_token)

        count = 0
        for session in query:
            session.invalidate()
            count += 1

        if count > 0:
            # Логируем завершение всех сессий
            user = self.user_model.get_by_id(user_id)
            self.log_model.log(
                action='logout_all',
                status='success',
                user=user
            )

        return count

    # ------------------- Восстановление доступа -------------------

    def initiate_password_recovery(self, username: str) -> Dict[str, Any]:
        """
        Инициация восстановления пароля
        """
        try:
            user = self.user_model.get(
                (self.user_model.username == username.lower().strip()) &
                (self.user_model.is_active == True)
            )

            # Создаем код восстановления
            recovery = self.recovery_model.create_for_user(
                user=user,
                expires_in_hours=self.RECOVERY_EXPIRY_HOURS
            )

            # Логируем запрос
            self.log_model.log(
                action='recovery',
                status='success',
                user=user
            )

            return {
                'success': True,
                'user_id': user.id,
                'recovery_code': recovery.code,
                'expires_at': recovery.expires_at
            }

        except self.user_model.DoesNotExist:
            # Не сообщаем, что пользователь не найден
            return {
                'success': False,
                'message': 'If user exists, recovery code will be sent'
            }

    def reset_password(self,
                       recovery_code: str,
                       new_password: str,
                       ip: Optional[str] = None) -> Dict[str, Any]:
        """
        Сброс пароля с использованием кода восстановления
        """
        try:
            # Валидация нового пароля
            valid, error = self._validate_password(new_password)
            if not valid:
                raise ValueError(f"Invalid password: {error}")

            # Сначала находим код по строке (даже если использован)
            try:
                recovery = self.recovery_model.get(
                    self.recovery_model.code == recovery_code
                )
            except self.recovery_model.DoesNotExist:
                raise ValueError("Invalid recovery code")

            # Проверяем валидность
            if not recovery.is_valid():
                raise ValueError("Recovery code expired or already used")

            user = recovery.user

            # Меняем пароль
            user.password_hash = self._hash_password(new_password)
            user.save()

            # Используем код
            recovery.use(ip)

            # Завершаем все сессии пользователя
            self.logout_all(user.id)

            # Логируем сброс пароля
            self.log_model.log(
                action='reset_password',
                status='success',
                user=user,
                ip=ip
            )

            return {
                'success': True,
                'message': 'Password successfully reset'
            }

        except self.recovery_model.DoesNotExist:
            raise ValueError("Invalid recovery code")

    # ------------------- Управление профилем -------------------

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Получение пользователя по ID
        """
        try:
            return self.user_model.get(
                (self.user_model.id == user_id) &
                (self.user_model.is_active == True)
            )
        except self.user_model.DoesNotExist:
            return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Получение пользователя по username
        """
        try:
            return self.user_model.get(
                (self.user_model.username == username.lower().strip()) &
                (self.user_model.is_active == True)
            )
        except self.user_model.DoesNotExist:
            return None

    def get_user_by_tg_id(self, tg_id: int) -> Optional[User]:
        """
        Получение пользователя по Telegram ID
        """
        try:
            return self.user_model.get(
                (self.user_model.tg_id == tg_id) &
                (self.user_model.is_active == True)
            )
        except self.user_model.DoesNotExist:
            return None

    def update_profile(self,
                       user_id: int,
                       first_name: Optional[str] = None,
                       last_name: Optional[str] = None,
                       email: Optional[str] = None,
                       tg_username: Optional[str] = None) -> User:
        """
        Обновление профиля пользователя
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        # Обновляем поля
        if first_name is not None:
            user.first_name = first_name.strip()

        if last_name is not None:
            user.last_name = last_name.strip()

        if email is not None:
            valid, error = self._validate_email(email)
            if not valid:
                raise ValueError(f"Invalid email: {error}")

            # Проверяем уникальность
            if email != user.email:
                exists = self.user_model.select().where(
                    (self.user_model.email == email) &
                    (self.user_model.id != user_id)
                ).exists()
                if exists:
                    raise ValueError("Email already registered")
                user.email = email.strip() if email else None

        if tg_username is not None:
            # Проверяем уникальность
            if tg_username != user.tg_username:
                exists = self.user_model.select().where(
                    (self.user_model.tg_username == tg_username) &
                    (self.user_model.id != user_id)
                ).exists()
                if exists:
                    raise ValueError("Telegram username already registered")
                user.tg_username = tg_username.strip() if tg_username else None
                # Сбрасываем верификацию при смене Telegram
                if tg_username:
                    user.tg_verified = False
                    user.tg_id = None
                    user.tg_chat_id = None

        user.save()

        # Логируем обновление
        self.log_model.log(
            action='update_profile',
            status='success',
            user=user
        )

        return user

    def change_password(self,
                        user_id: int,
                        current_password: str,
                        new_password: str) -> bool:
        """
        Смена пароля
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        # Проверяем текущий пароль
        if not self._verify_password(current_password, user.password_hash):
            raise ValueError("Current password is incorrect")

        # Валидация нового пароля
        valid, error = self._validate_password(new_password)
        if not valid:
            raise ValueError(f"Invalid new password: {error}")

        # Меняем пароль
        user.password_hash = self._hash_password(new_password)
        user.save()

        # Завершаем все сессии, кроме текущей
        # (текущая сессия будет передана отдельно)

        # Логируем смену пароля
        self.log_model.log(
            action='change_password',
            status='success',
            user=user
        )

        return True

    def update_theme_preferences(self,
                                 user_id: int,
                                 theme_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновление настроек темы
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        current_theme = user.theme_preferences_dict
        current_theme.update(theme_data)

        user.theme_preferences = json.dumps(current_theme)
        user.save()

        return current_theme

    def update_notification_settings(self,
                                     user_id: int,
                                     settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновление настроек уведомлений
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        current_settings = user.notification_settings_dict
        current_settings.update(settings)

        user.notification_settings = json.dumps(current_settings)
        user.save()

        return current_settings

    # ------------------- Валидация сессий -------------------

    def validate_token(self, token: str) -> Optional[User]:
        """
        Проверка токена и получение пользователя
        """
        try:
            session = self.session_model.get(
                (self.session_model.token == token) &
                (self.session_model.is_active == True) &
                (self.session_model.is_blocked == False)
            )

            if not session.is_valid():
                session.invalidate()
                return None

            # Обновляем время последнего использования
            session.last_used_at = datetime.now()
            session.save()

            # Обновляем активность пользователя
            user = session.user
            user.last_activity = datetime.now()
            user.save()

            return user

        except self.session_model.DoesNotExist:
            return None

    def get_user_sessions(self, user_id: int, active_only: bool = True) -> List[AuthSession]:
        """
        Получение всех сессий пользователя
        """
        query = self.session_model.select().where(
            self.session_model.user_id == user_id
        )

        if active_only:
            query = query.where(
                (self.session_model.is_active == True) &
                (self.session_model.is_blocked == False)
            )

        return list(query.order_by(self.session_model.created_at.desc()))

    def revoke_session(self, session_id: int, user_id: int) -> bool:
        """
        Отзыв конкретной сессии
        """
        try:
            session = self.session_model.get(
                (self.session_model.id == session_id) &
                (self.session_model.user_id == user_id)
            )

            session.invalidate()
            return True

        except self.session_model.DoesNotExist:
            return False

    # ------------------- Административные функции -------------------

    def change_user_role(self, user_id: int, role_name: str, admin_user: User) -> User:
        """
        Изменение роли пользователя (только для админов)
        """
        # Проверяем права администратора
        if not admin_user.is_superuser:
            # Проверяем роль
            admin_role = admin_user.role
            if admin_role.name not in ['Хозяин', 'Менеджер проекта']:
                raise PermissionError("Insufficient permissions to change user roles")

        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        role = self.get_role_by_name(role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' not found")

        # Меняем роль
        user.role = role
        user.save()

        # Логируем изменение
        self.log_model.log(
            action='change_role',
            status='success',
            user=user,
            reason=f"Role changed to {role_name} by {admin_user.username}"
        )

        return user

    def deactivate_user(self, user_id: int, admin_user: User) -> bool:
        """
        Деактивация пользователя (только для админов)
        """
        if not admin_user.is_superuser:
            raise PermissionError("Insufficient permissions to deactivate users")

        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        user.is_active = False
        user.save()

        # Завершаем все сессии
        self.logout_all(user.id)

        # Логируем деактивацию
        self.log_model.log(
            action='deactivate',
            status='success',
            user=user,
            reason=f"User deactivated by {admin_user.username}"
        )

        return True

    def activate_user(self, user_id: int, admin_user: User) -> bool:
        """
        Активация пользователя (только для админов)
        """
        if not admin_user.is_superuser:
            raise PermissionError("Insufficient permissions to activate users")

        try:
            user = self.user_model.get(self.user_model.id == user_id)
            user.is_active = True
            user.save()

            # Логируем активацию
            self.log_model.log(
                action='activate',
                status='success',
                user=user,
                reason=f"User activated by {admin_user.username}"
            )

            return True

        except self.user_model.DoesNotExist:
            raise ValueError("User not found")

    # ------------------- Поиск и фильтрация -------------------

    def search_users(self,
                     query: Optional[str] = None,
                     role_id: Optional[int] = None,
                     is_active: Optional[bool] = None,
                     limit: int = 20,
                     offset: int = 0) -> List[User]:
        """
        Поиск пользователей с фильтрацией
        """
        conditions = []

        if query:
            search = f"%{query}%"
            conditions.append(
                (self.user_model.first_name ** search) |
                (self.user_model.last_name ** search) |
                (self.user_model.username ** search) |
                (self.user_model.email ** search) |
                (self.user_model.tg_username ** search)
            )

        if role_id:
            conditions.append(self.user_model.role_id == role_id)

        if is_active is not None:
            conditions.append(self.user_model.is_active == is_active)

        query = self.user_model.select()
        if conditions:
            from peewee import SQL
            query = query.where(*conditions)

        return list(
            query.order_by(self.user_model.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

    def get_user_stats(self) -> Dict[str, Any]:
        """
        Статистика по пользователям
        """
        total = self.user_model.select().count()
        active = self.user_model.select().where(self.user_model.is_active == True).count()
        verified = self.user_model.select().where(self.user_model.tg_verified == True).count()

        # Статистика по ролям
        role_stats = {}
        for role in self.role_model.select():
            count = self.user_model.select().where(
                self.user_model.role_id == role.id
            ).count()
            role_stats[role.name] = count

        return {
            'total_users': total,
            'active_users': active,
            'inactive_users': total - active,
            'verified_telegram': verified,
            'by_role': role_stats
        }

    async def send_telegram_code(self, user_id: int) -> Optional[str]:
        """Отправка кода верификации в Telegram"""
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        if not user.tg_chat_id:
            # Если нет chat_id, возвращаем код для ручного ввода
            return user.tg_code

        # Отправляем код через бота
        from core.bot.client import get_bot
        bot = get_bot()

        success = await bot.send_verification_code(
            chat_id=user.tg_chat_id,
            code=user.tg_code
        )

        return user.tg_code if success else None

    async def send_task_notification(self, user_id: int,
                                     notification_type: str,
                                     task_data: dict) -> bool:
        """Отправка уведомления о задаче"""
        user = self.get_user_by_id(user_id)
        if not user or not user.tg_chat_id:
            return False

        from core.bot.client import send_telegram_notification
        return await send_telegram_notification(
            chat_id=user.tg_chat_id,
            notification_type=notification_type,
            data=task_data
        )

    async def send_telegram_notification(self, user_id: int,
                                         notification_type: str,
                                         data: dict) -> bool:
        """Отправка уведомления пользователю через Telegram"""
        user = self.get_user_by_id(user_id)
        if not user or not user.tg_chat_id or not user.tg_verified:
            return False

        try:
            # Импортируем здесь, чтобы избежать циклического импорта
            from ..bot.deps import get_bot
            bot = await get_bot()
            return await bot.send_notification(
                chat_id=user.tg_chat_id,
                notification_type=notification_type,
                data=data
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False

    def get_user_by_tg_code(self, tg_code: str) -> Optional[User]:
        """Получение пользователя по Telegram коду"""
        try:
            return self.user_model.get(
                (self.user_model.tg_code == tg_code) &
                (self.user_model.is_active == True)
            )
        except self.user_model.DoesNotExist:
            return None

    def get_user_by_tg_username(self, tg_username: str) -> Optional[User]:
        """Получение пользователя по Telegram username"""
        try:
            return self.user_model.get(
                (self.user_model.tg_username == tg_username) &
                (self.user_model.is_active == True)
            )
        except self.user_model.DoesNotExist:
            return None