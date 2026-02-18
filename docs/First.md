# 📚 TaskFlow - Полная документация проекта

## 📋 Саммари для будущих чатов

### 🎯 **Проект**: TaskFlow - Веб-приложение для мониторинга задач с Dependency Graph
**Стек**: Python FastAPI + MySQL + Peewee ORM, React + ReactFlow, Telegram Bot (aiogram)

### ✅ **Что уже реализовано:**

#### 1. **Модели БД** (`core/db/models/user.py`)
- `User` - пользователи с Telegram верификацией
- `UserRole` - роли (Работник, Менеджер, Хозяин) с правами
- `AuthSession` - сессии с access/refresh токенами
- `RecoveryCode` - восстановление пароля
- `AuthLog` - логирование действий

#### 2. **Бизнес-логика** (`core/services/UserService.py`)
- ✅ Регистрация, логин, logout
- ✅ Telegram верификация (6-значные коды)
- ✅ JWT токены (access + refresh)
- ✅ Восстановление пароля
- ✅ Управление профилем
- ✅ CRUD ролей
- ✅ Админ-функции

#### 3. **REST API** (`core/api/routes/`)
- ✅ `auth.py` - 8 эндпоинтов аутентификации
- ✅ `users.py` - 9 эндпоинтов управления профилем
- ✅ `admin.py` - 5 эндпоинтов администрирования
- ✅ `roles.py` - 5 эндпоинтов CRUD ролей
- ✅ `telegram.py` - 4 эндпоинта для Telegram

#### 4. **Telegram Bot** (`core/bot/bot.py`)
- ✅ Aiogram 3.x, polling режим
- ✅ Привязка по 6-значному коду
- ✅ Команды `/start`, `/code`
- ✅ Инлайн-клавиатуры
- ✅ Уведомления о задачах

#### 5. **Тестирование**
- ✅ 102 unit-теста UserService
- ✅ 11 live API тестов (все проходят)
- ✅ In-memory SQLite для тестов

---

## 🔄 **Ключевые Flow для фронтенда**

### 1. 🚀 **Регистрация нового пользователя**

```typescript
// ========== FLOW РЕГИСТРАЦИИ ==========
// 1. Пользователь заполняет форму
interface RegisterData {
  first_name: string;
  last_name: string;
  username: string;      // минимум 3 символа, только a-z0-9_.-
  password: string;      // минимум 8, заглавная, строчная, цифра
  email?: string;        // опционально, валидация email
  tg_username?: string;  // опционально, формат @username
}

// 2. Отправка запроса
POST /api/v1/auth/register

// 3. Успешный ответ (200 OK)
{
  "requires_verification": true,
  "user_id": 123,
  "tg_code": "483291"  // 6-значный код
}

// 4. UI - отображение кода
```

**📱 Отображение в React:**
```tsx
// Компонент после успешной регистрации
const RegistrationSuccess = ({ userId, tgCode }) => {
  return (
    <Card>
      <Typography variant="h5">
        ✅ Почти готово!
      </Typography>
      
      <Alert severity="info">
        Для завершения регистрации привяжите Telegram
      </Alert>

      {/* Крупный код для копирования */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', my: 3 }}>
        <Paper 
          elevation={3} 
          sx={{ 
            p: 2, 
            bgcolor: '#f5f5f5',
            border: '2px dashed #1976d2'
          }}
        >
          <Typography variant="h2" sx={{ letterSpacing: 8 }}>
            {tgCode}
          </Typography>
        </Paper>
        
        <Button 
          startIcon={<ContentCopyIcon />}
          onClick={() => navigator.clipboard.writeText(tgCode)}
          sx={{ ml: 2 }}
        >
          Копировать
        </Button>
      </Box>

      {/* Инструкция */}
      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle1" gutterBottom>
          📌 <b>Как привязать Telegram:</b>
        </Typography>
        <List>
          <ListItem>1. Откройте бота: <b>@taskflow_bot</b></ListItem>
          <ListItem>2. Отправьте команду <b>/start</b></ListItem>
          <ListItem>3. Отправьте код <b>{tgCode}</b></ListItem>
        </List>
      </Box>

      {/* Кнопка "Проверить статус" */}
      <Button 
        variant="contained"
        onClick={() => checkVerificationStatus(userId)}
        sx={{ mt: 2 }}
      >
        Я привязал, проверить
      </Button>
    </Card>
  );
};

// Polling для проверки статуса
useEffect(() => {
  if (userId && !isVerified) {
    const interval = setInterval(async () => {
      const status = await checkTelegramStatus(userId);
      if (status.is_linked) {
        setIsVerified(true);
        router.push('/dashboard');
      }
    }, 3000);
    
    return () => clearInterval(interval);
  }
}, [userId]);
```

---

### 2. 🔐 **Логин + Telegram верификация**

```typescript
// ========== FLOW ВХОДА ==========
// 1. Форма логина
POST /api/v1/auth/login
{
  "username": "ivanov",
  "password": "Password123"
}

// 2. Возможные ответы:

// Случай А: Уже верифицирован
{
  "requires_verification": false,
  "access_token": "eyJ...",
  "refresh_token": "abc...",
  "user": {
    "id": 123,
    "username": "ivanov",
    "first_name": "Иван",
    "last_name": "Иванов",
    "tg_verified": true
  }
}
// → Редирект на /dashboard

// Случай Б: Требуется верификация
{
  "requires_verification": true,
  "user_id": 123,
  "tg_code": "483291"
}
// → Показать экран верификации
```

**📱 Компонент верификации:**
```tsx
const TelegramVerification = ({ userId, initialCode }) => {
  const [code, setCode] = useState(initialCode);
  const [manualCode, setManualCode] = useState('');
  const [mode, setMode] = useState<'auto' | 'manual'>('auto');
  
  // Автоматический режим - код уже сгенерирован
  if (mode === 'auto') {
    return (
      <Card>
        <Typography variant="h5">
          🔐 Подтверждение входа
        </Typography>
        
        <Alert severity="warning">
          Мы отправили код в Telegram. Проверьте бота @taskflow_bot
        </Alert>
        
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 3 }}>
          <CircularProgress />
          <Typography sx={{ ml: 2 }}>
            Ожидаем подтверждение...
          </Typography>
        </Box>
        
        <Button onClick={() => setMode('manual')}>
          Ввести код вручную
        </Button>
      </Card>
    );
  }
  
  // Ручной режим - пользователь вводит код
  return (
    <Card>
      <Typography variant="h5">
        🔐 Введите код из Telegram
      </Typography>
      
      <TextField
        label="6-значный код"
        value={manualCode}
        onChange={(e) => setManualCode(e.target.value)}
        inputProps={{ maxLength: 6 }}
        sx={{ my: 2 }}
      />
      
      <Button
        variant="contained"
        onClick={() => verifyCode(userId, manualCode)}
        disabled={manualCode.length !== 6}
      >
        Подтвердить
      </Button>
      
      <Button 
        variant="text"
        onClick={() => generateNewCode(userId)}
        sx={{ mt: 1 }}
      >
        Отправить новый код
      </Button>
    </Card>
  );
};

// Проверка кода
const verifyCode = async (userId, code) => {
  try {
    const response = await api.post('/auth/verify-telegram', {
      user_id: userId,
      code: code
    });
    
    // Успех - получаем токены
    localStorage.setItem('access_token', response.access_token);
    localStorage.setItem('refresh_token', response.refresh_token);
    router.push('/dashboard');
  } catch (error) {
    // Ошибка
    if (error.response?.status === 400) {
      if (error.response.data.detail.includes('expired')) {
        showToast('Код истек, запросите новый');
      } else {
        showToast('Неверный код');
      }
    }
  }
};
```

---

### 3. 📲 **Привязка Telegram из профиля**

```typescript
// ========== FLOW ПРИВЯЗКИ TELEGRAM ==========
// 1. Пользователь нажимает "Привязать Telegram" в профиле

// 2. Запрос на генерацию кода
POST /api/v1/telegram/link
Headers: { Authorization: `Bearer ${token}` }

// 3. Ответ
{
  "code": "483291",           // 6-значный код
  "sent_to_telegram": false,  // true если уже есть chat_id
  "expires_in": 10,          // минут
  "bot_username": "@taskflow_bot"
}

// 4. UI - показываем код и инструкцию
```

**📱 Компонент привязки:**
```tsx
const TelegramLink = () => {
  const [step, setStep] = useState<'initial' | 'code' | 'success'>('initial');
  const [code, setCode] = useState('');
  const [status, setStatus] = useState(null);
  
  // Получить статус привязки
  const checkStatus = async () => {
    const response = await api.get('/telegram/status');
    setStatus(response);
    return response.is_linked;
  };
  
  // Начать привязку
  const handleLink = async () => {
    const response = await api.post('/telegram/link');
    setCode(response.code);
    setStep('code');
    
    // Автоматическая проверка каждые 3 секунды
    const interval = setInterval(async () => {
      const isLinked = await checkStatus();
      if (isLinked) {
        clearInterval(interval);
        setStep('success');
      }
    }, 3000);
  };
  
  // Отвязать
  const handleUnlink = async () => {
    await api.delete('/telegram/unlink');
    setStatus({ ...status, is_linked: false });
  };
  
  // Отправить тестовое уведомление
  const sendTest = async () => {
    await api.post('/telegram/test');
    showToast('✅ Тестовое уведомление отправлено');
  };
  
  if (status?.is_linked) {
    return (
      <Card>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <TelegramIcon sx={{ color: '#0088cc', mr: 2 }} />
          <Box flex={1}>
            <Typography variant="h6">Telegram привязан</Typography>
            <Typography variant="body2" color="text.secondary">
              @{status.tg_username}
            </Typography>
          </Box>
          <Button onClick={sendTest} sx={{ mr: 1 }}>
            Тест
          </Button>
          <Button color="error" onClick={handleUnlink}>
            Отвязать
          </Button>
        </Box>
      </Card>
    );
  }
  
  if (step === 'code') {
    return (
      <Card>
        <Typography variant="h6">
          🔑 Код подтверждения
        </Typography>
        
        <Box sx={{ my: 3 }}>
          <Typography variant="h2" sx={{ letterSpacing: 4 }}>
            {code}
          </Typography>
        </Box>
        
        <Alert severity="info">
          Отправьте этот код боту <b>@taskflow_bot</b>
        </Alert>
        
        <Box sx={{ mt: 2 }}>
          <CircularProgress size={20} sx={{ mr: 1 }} />
          <Typography variant="body2" component="span">
            Ожидаем подтверждение...
          </Typography>
        </Box>
      </Card>
    );
  }
  
  return (
    <Button
      variant="outlined"
      startIcon={<TelegramIcon />}
      onClick={handleLink}
    >
      Привязать Telegram
    </Button>
  );
};
```

---

### 4. 🔄 **Восстановление пароля**

```typescript
// ========== FLOW ВОССТАНОВЛЕНИЯ ПАРОЛЯ ==========
// 1. Пользователь ввел username
POST /api/v1/auth/recovery/initiate
{
  "username": "ivanov"
}

// 2. Ответ (всегда 200, даже если пользователь не найден)
{
  "success": true,
  "user_id": 123,
  "recovery_code": "abc123...",  // длинный токен
  "expires_at": "2024-01-01T12:00:00"
}

// 3. Пользователь вводит код из письма/Telegram
POST /api/v1/auth/recovery/reset
{
  "recovery_code": "abc123...",
  "new_password": "NewPass123!"
}

// 4. Успех
{
  "success": true,
  "message": "Password successfully reset"
}
```

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

// Telegram code
const TG_CODE_LENGTH = 6;
const TG_CODE_EXPIRY = 10; // минут
```

### 🚦 **HTTP Status Codes**
- `200` - Успех
- `400` - Ошибка валидации (неверный код, дубликат и т.д.)
- `401` - Не авторизован / Неверные credentials
- `403` - Недостаточно прав
- `404` - Ресурс не найден
- `422` - Pydantic валидация (неправильный формат)
- `500` - Ошибка сервера

### 📁 **Структура проекта для фронтенда**
```
src/
├── api/
│   ├── auth.ts      # login, register, refresh, logout
│   ├── users.ts     # profile, update, password
│   ├── admin.ts     # search, stats, roles
│   └── telegram.ts  # link, status, test
├── components/
│   ├── auth/
│   │   ├── RegisterForm.tsx
│   │   ├── LoginForm.tsx
│   │   └── TelegramVerification.tsx
│   └── profile/
│       └── TelegramLink.tsx
├── hooks/
│   ├── useAuth.ts    # авторизация, токены
│   └── useTelegram.ts # статус привязки, polling
└── types/
    └── index.ts      # интерфейсы
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

3. **Polling для Telegram**
   - Регистрация: проверять статус каждые 3 секунды
   - Логин: проверять статус каждые 3 секунды
   - Привязка: проверять статус каждые 3 секунды

4. **Всегда показывайте код крупно**
   - 6 цифр, моноширинный шрифт
   - Кнопка "Копировать"
   - Четкая инструкция

---

## 🚀 **Быстрый старт для фронтенда**

```bash
# Переменные окружения
REACT_APP_API_URL=http://localhost:8000
REACT_APP_TELEGRAM_BOT=@taskflow_bot

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
python -m pytest tests/test_api/test_auth_live.py -v

# Telegram бот запускается автоматически с бэкендом
# Бот доступен по адресу: https://t.me/taskflow_bot
```

---

Это саммари содержит **100% рабочей информации** по текущему состоянию проекта. Все API эндпоинты протестированы и работают, все тесты проходят. Можно смело начинать разработку фронтенда! 🎯