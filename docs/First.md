# 📚 TaskFlow - Полная документация проекта

## 📋 Саммари для будущих чатов

### 🎯 **Проект**: TaskFlow — веб-приложение для мониторинга задач с графом зависимостей
**Стек**: Python FastAPI + MySQL + Peewee ORM, React + ReactFlow. Подтверждение аккаунта и сброс пароля — **по email** (SMTP или Resend API).

### ✅ **Что уже реализовано:**

#### 1. **Модели БД** (`core/db/models/user.py`)
- `User` — пользователи с полями `email`, `email_verified`, коды OTP (`email_code`, срок, попытки)
- `UserRole` — глобальные роли (Работник, Менеджер, Хозяин)
- `AuthSession` — access/refresh токены
- `RecoveryCode` — одноразовые коды восстановления пароля
- `AuthLog` — аудит входов и действий

#### 2. **Бизнес-логика** (`core/services/UserService.py`)
- Регистрация с обязательным email и отправкой 6-значного кода
- Вход: при неподтверждённом email — новый код на почту
- `verify_email_code` — подтверждение и выдача сессии
- JWT (access + refresh), logout / logout-all
- Восстановление пароля: код на email, затем `reset_password`
- Профиль, тема, уведомления, админ-операции

#### 3. **Почта** (`core/services/email_service.py`, `core/config.py`)
- Приоритет: **Resend** (`RESEND_API_KEY`), иначе **SMTP** (например Timeweb: `SMTP_HOST`, порт 2525, STARTTLS)
- Учётные данные ящика: `EMAIL_FROM`, `EMAIL_PASSWORD` или `SMTP_PASSWORD`, опционально `SMTP_USER`

#### 4. **REST API** (`core/api/routes/`)
- `auth.py` — register, login, verify-email, refresh, logout, logout-all, recovery/initiate, recovery/reset
- `users.py`, `teams.py`, `projects.py`, `tasks.py`, `admin.py`, `roles.py`

#### 5. **Граф задач**
- `GET` / `PUT` `/api/v1/projects/{project_slug}/tasks/graph` — загрузка и сохранение графа (ReactFlow: nodes, edges, viewport)
- Зависимости: `POST` `.../tasks/{task_id}/dependencies`, `DELETE` `.../tasks/dependencies/{dependency_id}`

#### 6. **Тестирование**
- Unit и API-тесты (pytest, TestClient / SQLite в тестах)

---

## 🔄 **Ключевые flow для фронтенда (email + граф)**

Подробные сценарии запросов и полей ответов см. в [Front.md](./Front.md) (разделы «Аутентификация» и «Интеграция: email и граф»).

### 1. Регистрация

- `POST /api/v1/auth/register` с обязательным `email`, полями профиля и паролем.
- Ответ: `user_id`, `email_sent`, опционально `verification_code` (только в отладке или если письмо не отправилось).
- Далее экран ввода 6-значного кода и `POST /api/v1/auth/verify-email` с `{ user_id, code }` → токены и профиль.

### 2. Вход

- `POST /api/v1/auth/login`. Если `email_verified === false`: ответ с `requires_verification: true`, `user_id`, опционально `verification_code`, поле `email_sent`.
- Подтверждение — тот же `POST /api/v1/auth/verify-email`.

### 3. Восстановление пароля

- `POST /api/v1/auth/recovery/initiate` с `{ "username": "..." }` (в теле JSON).
- При успехе на email уходит код; в JSON могут быть `email_sent`, `recovery_code` (код в ответе только при `DEBUG` или сбое отправки письма — ориентируйтесь на `email_sent` и продакшен без утечки кода).
- `POST /api/v1/auth/recovery/reset` с `recovery_code` и `new_password`.

### 4. Граф (React Flow)

- Чтение: `GET /api/v1/projects/{project_slug}/tasks/graph`.
- Сохранение позиций и viewport: `PUT` на тот же путь, тело — `{ nodes, edges, viewport }` (см. схемы в API и [Front.md](./Front.md)).
- Зависимости между задачами: `POST .../tasks/{task_id}/dependencies`, удаление ребра: `DELETE .../tasks/dependencies/{dependency_id}`.

---

## 📦 **Важные константы и правила**

### 🔐 **Валидация**
```typescript
// Username
const USERNAME_REGEX = /^[a-zA-Z0-9_.-]+$/;
const USERNAME_MIN = 3;
const USERNAME_MAX = 50;

// Password
const PASSWORD_MIN = 8;
const PASSWORD_REQUIREMENTS = [
  { regex: /[A-Z]/, message: 'заглавная буква' },
  { regex: /[a-z]/, message: 'строчная буква' },
  { regex: /[0-9]/, message: 'цифра' }
];

// Email OTP (подтверждение регистрации / входа)
const EMAIL_CODE_LENGTH = 6;
const EMAIL_CODE_EXPIRY_MINUTES = 10; // как на бэкенде (EMAIL_CODE_EXPIRY_MINUTES)
```

### 🚦 **HTTP Status Codes**
- `200` - Успех
- `400` - Ошибка валидации (неверный код, дубликат и т.д.)
- `401` - Не авторизован / Неверные credentials
- `403` - Недостаточно прав
- `404` - Ресурс не найден
- `422` - Pydantic валидация (неправильный формат)
- `500` - Ошибка сервера

### 📁 **Структура проекта для фронтенда (пример)**
```
src/
├── api/
│   ├── auth.ts      # register, login, verify-email, refresh, recovery
│   ├── users.ts     # profile, update, password
│   ├── teams.ts
│   ├── projects.ts
│   ├── tasks.ts     # в т.ч. graph GET/PUT
│   └── admin.ts
├── components/
│   ├── auth/
│   │   ├── RegisterForm.tsx
│   │   ├── LoginForm.tsx
│   │   └── EmailCodeVerification.tsx
│   └── project/
│       └── TaskGraphBoard.tsx
├── hooks/
│   ├── useAuth.ts
│   └── useProjectGraph.ts
└── types/
    └── index.ts
```

---

## 🎯 **Ключевые моменты для фронтенда**

1. **Токены хранятся в localStorage**
   - `access_token` - живет 1 час
   - `refresh_token` - живет 7 дней

2. **Interceptor для обновления токенов**
   ```typescript
   api.interceptors.response.use(
     (response) => response,
     async (error) => {
       if (error.response?.status === 401) {
         const refresh = localStorage.getItem('refresh_token');
         const response = await api.post('/auth/refresh', { refresh_token: refresh });
         localStorage.setItem('access_token', response.access_token);
         // Повторяем исходный запрос
       }
     }
   );
   ```

3. **Код из письма**
   - Пользователь вводит 6 цифр на экране; отдельный polling статуса не нужен (в отличие от бота).
   - Подсказка в UI: «Проверьте почту (и папку «Спам»)».

4. **Отображение кода (только dev / если `email_sent === false`)**
   - Если бэкенд вернул `verification_code` (отладка или ошибка SMTP), можно показать код крупно и кнопку «Копировать».
   - В продакшене при успешной отправке поле кода в ответе обычно отсутствует.

---

## 🚀 **Быстрый старт для фронтенда**

```bash
# Переменные окружения фронтенда
REACT_APP_API_URL=http://localhost:8000

# Установка зависимостей
npm install @mui/material @emotion/react @emotion/styled
npm install axios react-router-dom

# Запуск
npm start
```

---

## 📞 **Полезные команды для тестирования**

```bash
# Запуск бэкенда
python main.py

# Запуск тестов API
python -m pytest tests/test_api/test_auth.py -v
```

---

Актуальные контракты API и сценарии интеграции см. в [Front.md](./Front.md). При расхождении с кодом приоритет у репозитория.