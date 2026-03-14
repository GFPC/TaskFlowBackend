# core/bot/bot.py
import asyncio
import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import settings

logger = logging.getLogger(__name__)


class TaskFlowBot:
    """Telegram бот на aiogram"""

    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.bot = Bot(token=self.token)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.user_service = None  # Будет установлен позже

        # Регистрируем обработчики
        self.register_handlers()

    def set_user_service(self, user_service):
        """Установка сервиса пользователей (для избежания циклического импорта)"""
        self.user_service = user_service

    def register_handlers(self):
        """Регистрация всех обработчиков"""

        @self.dp.message(Command('start'))
        async def cmd_start(message: Message):
            """Обработка команды /start"""
            chat_id = message.chat.id
            user_data = message.from_user
            username = user_data.username
            first_name = user_data.first_name or ''

            # Сохраняем chat_id если пользователь уже есть в БД
            if username and self.user_service:
                user = self.user_service.get_user_by_tg_username(f'@{username}')
                if user:
                    user.tg_chat_id = chat_id
                    user.save()
                    await message.answer(
                        f'👋 С возвращением, {first_name}!\n\n'
                        f'Твой аккаунт @{username} уже привязан к TaskFlow.\n'
                        f'Теперь ты будешь получать уведомления здесь!'
                    )
                    return

            # Новый пользователь
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text='🌐 Открыть TaskFlow', url=settings.FRONTEND_URL)
            keyboard.button(text='❓ Как привязать?', callback_data='how_to_link')
            keyboard.adjust(1)

            await message.answer(
                f'👋 Привет, {first_name}!\n\n'
                f'Я бот <b>TaskFlow</b> — системы управления задачами и проектами.\n\n'
                f'📌 <b>Чтобы привязать Telegram к аккаунту:</b>\n'
                f'1. Зарегистрируйся на сайте\n'
                f'2. В профиле нажми «Привязать Telegram»\n'
                f'3. Получи 6-значный код\n'
                f'4. Отправь его сюда\n\n'
                f'✅ <b>Уже есть код?</b> Просто отправь его мне!',
                reply_markup=keyboard.as_markup(),
                parse_mode='HTML',
            )

        @self.dp.message(Command('code'))
        async def cmd_code(message: Message):
            """Обработка команды /code <код>"""
            args = message.text.split()
            if len(args) != 2:
                await message.answer(
                    '❌ Используй: /code <6-значный код>\nПример: /code 483291'
                )
                return

            code = args[1]
            await self.process_verification_code(message, code)

        @self.dp.message(F.text.len() == 6)
        @self.dp.message(F.text.isdigit())
        async def handle_code_message(message: Message):
            """Обработка 6-значного кода из сообщения"""
            await self.process_verification_code(message, message.text)

        @self.dp.callback_query(F.data == 'how_to_link')
        async def callback_how_to_link(callback: CallbackQuery):
            """Обработка кнопки 'Как привязать?'"""
            await callback.message.edit_text(
                '📌 <b>Пошаговая инструкция:</b>\n\n'
                '1️⃣ <b>Зарегистрируйся</b> на сайте TaskFlow\n'
                '2️⃣ Перейди в <b>Настройки профиля</b>\n'
                '3️⃣ Нажми <b>«Привязать Telegram»</b>\n'
                '4️⃣ Скопируй <b>6-значный код</b>\n'
                '5️⃣ Отправь его сюда\n\n'
                '🔗 <b>Ссылка на сайт:</b>\n'
                f'{settings.FRONTEND_URL}\n\n'
                'Готово! Теперь ты будешь получать уведомления в Telegram 🎉',
                parse_mode='HTML',
            )
            await callback.answer()

        @self.dp.callback_query(F.data.startswith('verify:'))
        async def callback_verify(callback: CallbackQuery):
            """Обработка inline кнопки с кодом"""
            code = callback.data.split(':')[1]
            await self.process_verification_code(
                callback.message, code, is_callback=True
            )
            await callback.answer('✅ Код принят!')

        @self.dp.message()
        async def handle_unknown(message: Message):
            """Обработка неизвестных команд"""
            await message.answer(
                '❓ Я понимаю только:\n'
                '• /start - приветствие\n'
                '• /code <код> - привязка аккаунта\n'
                '• Или просто отправь 6-значный код'
            )

    async def process_verification_code(
        self, message: Message, code: str, is_callback: bool = False
    ):
        """Общая логика обработки кода верификации"""
        if not self.user_service:
            logger.error('UserService not set in bot')
            await message.answer(
                '❌ <b>Ошибка конфигурации</b>\n\n'
                'Попробуй позже или обратись к администратору.',
                parse_mode='HTML',
            )
            return

        chat_id = message.chat.id
        user_data = message.from_user

        try:
            # Используем UserService для поиска пользователя
            user = self.user_service.get_user_by_tg_code(code)

            if not user:
                await message.answer(
                    '❌ <b>Неверный код</b>\n\n'
                    'Проверь код в личном кабинете или запроси новый.',
                    parse_mode='HTML',
                )
                return

            # Проверяем срок действия кода
            if user.tg_code_expires and datetime.now() > user.tg_code_expires:
                await message.answer(
                    '❌ <b>Код истек</b>\n\nЗапроси новый код в веб-приложении.',
                    parse_mode='HTML',
                )
                return

            # Привязываем Telegram
            user.tg_id = user_data.id
            user.tg_chat_id = chat_id
            user.tg_verified = True
            user.tg_code = None
            user.tg_code_expires = None
            user.save()

            # Успешное сообщение
            keyboard = InlineKeyboardBuilder()
            keyboard.button(
                text='🚀 Перейти к задачам', url=f'{settings.FRONTEND_URL}/dashboard'
            )

            await message.answer(
                '✅ <b>Telegram успешно привязан!</b>\n\n'
                '🎉 Теперь ты будешь получать уведомления:\n'
                '• 📋 О новых задачах\n'
                '• ✅ О выполнении задач\n'
                '• 🔄 О готовности зависимостей\n'
                '• 👤 О назначениях\n\n'
                'Удачной работы! 🚀',
                reply_markup=keyboard.as_markup(),
                parse_mode='HTML',
            )

            logger.info(f'User {user.username} linked Telegram (chat_id: {chat_id})')

        except Exception as e:
            logger.error(f'Error processing verification code: {e}')
            await message.answer(
                '❌ <b>Произошла ошибка</b>\n\n'
                'Попробуй позже или обратись к администратору.',
                parse_mode='HTML',
            )

    async def send_notification(
        self, chat_id: int, notification_type: str, data: dict
    ) -> bool:
        """Отправка уведомления пользователю"""
        templates = {
            'task_assigned': (
                '📋 <b>Новая задача</b>\n\n'
                f'<b>{data.get("task_title", "Без названия")}</b>\n'
                f'📁 Проект: {data.get("project_name", "Без проекта")}\n'
                f'👤 Создал: {data.get("creator", "Система")}\n'
                f'⏳ Дедлайн: {data.get("deadline", "Не указан")}\n\n'
                f"🔗 <a href='{data.get('task_url', '#')}'>Открыть задачу</a>"
            ),
            'task_completed': (
                '✅ <b>Задача выполнена</b>\n\n'
                f'<b>{data.get("task_title", "Без названия")}</b>\n'
                f'📁 Проект: {data.get("project_name", "Без проекта")}\n'
                f'👤 Исполнитель: {data.get("assignee", "Не указан")}\n\n'
                f"🔗 <a href='{data.get('task_url', '#')}'>Открыть задачу</a>"
            ),
            'dependency_ready': (
                '🔄 <b>Задача готова к работе</b>\n\n'
                f'<b>{data.get("task_title", "Без названия")}</b>\n'
                f'📁 Проект: {data.get("project_name", "Без проекта")}\n\n'
                'Предыдущая зависимость выполнена!\n'
                'Можно приступать к работе.\n\n'
                f"🔗 <a href='{data.get('task_url', '#')}'>Открыть задачу</a>"
            ),
            'comment_added': (
                '💬 <b>Новый комментарий</b>\n\n'
                f'К задаче: <b>{data.get("task_title", "Без названия")}</b>\n'
                f'👤 {data.get("author", "Пользователь")}: {data.get("comment", "")}\n\n'
                f"🔗 <a href='{data.get('task_url', '#')}'>Перейти к задаче</a>"
            ),
        }

        text = templates.get(notification_type)
        if not text:
            logger.warning(f'Unknown notification type: {notification_type}')
            return False

        try:
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text='🔗 Открыть задачу', url=data.get('task_url', '#'))
            keyboard.adjust(1)

            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML',
                reply_markup=keyboard.as_markup(),
                disable_web_page_preview=True,
            )
            return True
        except Exception as e:
            logger.error(f'Failed to send notification to {chat_id}: {e}')
            return False

    async def start_polling(self):
        """Запуск polling"""
        logger.info('🤖 Starting Telegram bot polling...')
        await self.dp.start_polling(self.bot)

    async def stop_polling(self):
        """Остановка polling"""
        logger.info('🤖 Stopping Telegram bot...')
        await self.dp.stop_polling()
        await self.bot.session.close()
