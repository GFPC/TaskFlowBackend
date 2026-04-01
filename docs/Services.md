# 🏆 ПОЛНАЯ ПАМЯТКА ПО BACKEND АРХИТЕКТУРЕ - TASKFLOW
## Опыт, проблемы и решения

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                   ВЕРСИЯ: 1.0 - СТАБИЛЬНАЯ РЕАЛИЗАЦИЯ                         ║
║                   ДАТА: 13.02.2026                                           ║
║                   ТЕСТЫ: 234/234 - 100% ПРОЙДЕНО                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

# 📋 СОДЕРЖАНИЕ
1. [Общая архитектура](#-общая-архитектура)
2. [Сервисы - детальное описание](#-сервисы---детальное-описание)
3. [Модели данных](#-модели-данных)
4. [REST API](#-rest-api)
5. [Проблемы и их решения (ОПЫТ)](#-проблемы-и-их-решения-опыт)
6. [Тестирование](#-тестирование)
7. [Чек-листы для разработки](#-чек-листы-для-разработки)

---

# 🏗 ОБЩАЯ АРХИТЕКТУРА

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT (React)                              │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP/JSON
┌───────────────────────────────▼─────────────────────────────────────┐
│                         FASTAPI (ROUTES)                           │
│  ┌─────────────┬─────────────┬─────────────┬─────────────────────┐ │
│  │  Auth/User  │   Teams     │  Projects   │       Tasks         │ │
│  └─────────────┴─────────────┴─────────────┴─────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                      SERVICES (БИЗНЕС-ЛОГИКА)                      │
│  ┌─────────────┬─────────────┬─────────────┬─────────────────────┐ │
│  │ UserService │ TeamService │ProjectService│    TaskService      │ │
│  └─────────────┴─────────────┴─────────────┴─────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                      MODELS (Peewee ORM)                           │
│  ┌─────────────┬─────────────┬─────────────┬─────────────────────┐ │
│  │  user.py    │   team.py   │  project.py │      task.py        │ │
│  └─────────────┴─────────────┴─────────────┴─────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │     DATABASE (MySQL)   │
                    └───────────────────────┘
```

---

# 🧠 СЕРВИСЫ - ДЕТАЛЬНОЕ ОПИСАНИЕ

## 🔷 1. USER SERVICE

### 📌 Назначение
**Единственный сервис, отвечающий за идентификацию пользователей в системе**

### 🗃️ Модели
- `User` - пользователи
- `UserRole` - глобальные роли (Работник, Менеджер, Хозяин)
- `AuthSession` - сессии (access/refresh токены)
- `RecoveryCode` - восстановление пароля
- `AuthLog` - аудит безопасности

### 🔥 КРИТИЧЕСКИЕ МОМЕНТЫ (ОПЫТ)

#### ⚠️ ПРОБЛЕМА 1: Email не подтверждён — нет сессии после логина
**Симптомы:** После `login` приходит `requires_verification`, а не токены.
**Причина:** `user.email_verified == False` — нужен код из письма.
**Решение:** Фронт показывает ввод 6-значного кода и вызывает `verify_email_code` (`POST /auth/verify-email`). В `DEBUG` на бэкенде возможна авто-верификация только для разработки.

#### ⚠️ ПРОБЛЕМА 2: Письма не уходят
**Симптомы:** `email_sent: false`, код может прийти в ответе API (режим отладки).
**Причина:** не задан `RESEND_API_KEY` или не настроен SMTP (`SMTP_HOST`, пароль `EMAIL_PASSWORD` / `SMTP_PASSWORD`).
**Решение:** см. `core/config.py` и переменные окружения в [First.md](./First.md).

### ✅ КЛЮЧЕВЫЕ МЕТОДЫ
```python
# Регистрация и вход
register()            # → создаёт пользователя, шлёт OTP на email
login()               # → если email не подтверждён, шлёт новый OTP
verify_email_code()   # → подтверждает email и создаёт сессию

# Сессии
validate_token()
refresh_session()
logout_all()

# Восстановление
initiate_password_recovery()  # → код на email + RecoveryCode в БД
reset_password()              # → сброс по коду
```

---

## 🔷 2. TEAM SERVICE

### 📌 Назначение
**Управление группами пользователей и их ролями внутри команд**

### 🗃️ Модели
- `Team` - команда
- `TeamMember` - участник команды
- `TeamMemberRole` - роли (owner, admin, member)
- `TeamInvitation` - приглашения

### 👑 РОЛИ В КОМАНДЕ

| Роль | priority | can_manage_team | can_manage_projects | can_invite | can_remove |
|------|----------|-----------------|---------------------|------------|------------|
| **owner** | 100 | ✅ | ✅ | ✅ | ✅ |
| **admin** | 80 | ❌ | ✅ | ✅ | ✅ |
| **member** | 50 | ❌ | ❌ | ❌ | ❌ |

### 🔥 КРИТИЧЕСКИЕ МОМЕНТЫ (ОПЫТ)

#### ⚠️ ПРОБЛЕМА 1: Двойное определение router
**Симптомы:** Эндпоинты возвращали 404, хотя в коде были
**Причина:** 
```python
router = APIRouter()  # первое определение
# ... код ...
router = APIRouter()  # ВТОРОЕ ОПРЕДЕЛЕНИЕ - ПЕРЕЗАПИСЬ!
```
**Решение:** Одно определение router в начале файла

#### ⚠️ ПРОБЛЕМА 2: Метод .refresh() в тестах
**Симптомы:** AttributeError: 'Team' object has no attribute 'refresh'
**Причина:** В Peewee нет метода refresh()
**Решение:** 
```python
# ❌ Неправильно
team.refresh()

# ✅ Правильно
team = Team.get_by_id(team.id)
```

#### ⚠️ ПРОБЛЕМА 3: UNIQUE constraint при реактивации
**Симптомы:** IntegrityError: UNIQUE constraint failed
**Причина:** Попытка создать дубликат (team_id, user_id)
**Решение:** 
```python
# Проверяем существующего участника (даже неактивного)
existing = TeamMember.select().where(
    (TeamMember.team == team) & 
    (TeamMember.user == user)
).first()

if existing:
    if existing.is_active:
        raise ValueError("Already member")
    else:
        # Реактивируем
        existing.is_active = True
        existing.left_at = None
        existing.save()
```

### ✅ КЛЮЧЕВЫЕ МЕТОДЫ
```python
# Создание и управление
create_team()      # → владелец становится owner
update_team()      # → только owner/admin
delete_team()      # → мягкое удаление, деактивация участников

# Участники
add_member()       # → проверка прав, уникальность
remove_member()    # → нельзя удалить owner
transfer_ownership()  # → передача прав

# Коды приглашений (публичные, 1 час)
get_invite_code()  # → автообновление при истечении
join_by_code()     # → вступление, роль member

# Приглашения (персональные, 7 дней)
create_invitation()
accept_invitation()
decline_invitation()
```

---

## 🔷 3. PROJECT SERVICE

### 📌 Назначение
**Управление проектами внутри команд и ролями в проектах**

### 🗃️ Модели
- `Project` - проект (принадлежит Team)
- `ProjectMember` - участник проекта
- `ProjectRole` - роли (owner, manager, developer, observer)
- `ProjectInvitation` - приглашения

### 👑 РОЛИ В ПРОЕКТЕ

| Роль | priority | create_tasks | edit_any_task | delete_any_task | create_deps | manage_members |
|------|----------|--------------|---------------|-----------------|-------------|----------------|
| **owner** | 100 | ✅ | ✅ | ✅ | ✅ | ✅ |
| **manager** | 80 | ✅ | ✅ | ✅ | ✅ | ✅ |
| **developer** | 60 | ✅ | ❌ | ❌ | ✅ | ❌ |
| **observer** | 40 | ❌ | ❌ | ❌ | ❌ | ❌ |

### 🔥 КРИТИЧЕСКИЕ МОМЕНТЫ (ОПЫТ)

#### ⚠️ ПРОБЛЕМА 1: Права developer
**Симптомы:** Developer мог редактировать любые задачи
**Причина:** Неправильная логика в `can_edit_task()`
**Решение:**
```python
def can_edit_task(self, user: User, task) -> bool:
    role = self.get_user_role_in_project(user, task.project)
    
    # Owner/Manager - могут всё
    if role.can_edit_any_task:
        return True
    
    # Developer - только свои задачи (creator или assignee)
    if role.can_edit_own_task:
        return task.creator_id == user.id or task.assignee_id == user.id
    
    return False
```

#### ⚠️ ПРОБЛЕМА 2: Developer может менять имя задачи
**Симптомы:** Тест ожидал 403, получал 200
**Причина:** Не было проверки в эндпоинте
**Решение:**
```python
# В эндпоинте update_task
if role and role.name == 'developer':
    if task_in.name is not None and task_in.name != task.name:
        raise HTTPException(
            status_code=403,
            detail="Developer cannot change task name"
        )
```

#### ⚠️ ПРОБЛЕМА 3: Проект исчезал после архивации
**Симптомы:** GET /projects/{slug} возвращал 404 после archive
**Причина:** `archive_project()` удалял проект, а не менял статус
**Решение:**
```python
def archive_project(self, project: Project, archived_by: User) -> bool:
    project.status = 'archived'
    project.archived_at = datetime.now()
    project.save()  # Не удаляем!
    return True
```

#### ⚠️ ПРОБЛЕМА 4: find_project_by_slug не находил архивированные проекты
**Симптомы:** После архивации нельзя было восстановить
**Причина:** Фильтр `project.status == 'active'`
**Решение:**
```python
async def find_project_by_slug(..., include_archived=False):
    if include_archived:
        return project  # Возвращаем любой статус
    if project.status == 'active':
        return project
```

### ✅ КЛЮЧЕВЫЕ МЕТОДЫ
```python
# Создание и управление
create_project()     # → владелец становится owner
update_project()     # → owner/manager
archive_project()    # → меняет статус, НЕ УДАЛЯЕТ!
delete_project()     # → мягкое удаление

# Участники
add_member()        # → пользователь ОБЯЗАН быть в команде!
remove_member()     # → нельзя удалить owner
transfer_ownership()  # → передача прав

# Проверка прав (CRITICAL!)
can_edit_task()     # → различает owner/manager/developer
can_delete_task()   # → developer может удалять ТОЛЬКО свои
```

---

## 🔷 4. TASK SERVICE - САМЫЙ СЛОЖНЫЙ

### 📌 Назначение
**Управление задачами, графом зависимостей и действиями на ребрах**

### 🗃️ Модели
- `Task` - задача (составной ключ: project_id + id)
- `TaskStatus` - статусы (todo, in_progress, review, completed, blocked)
- `TaskDependency` - ребра графа
- `DependencyAction` - действия на ребрах
- `DependencyActionType` - типы действий
- `TaskEvent` - логирование
- `ScheduledAction` - отложенные уведомления

### 📊 СТАТУСЫ ЗАДАЧ

| Статус | is_final | is_blocking | Описание |
|--------|----------|-------------|----------|
| **todo** | ❌ | ❌ | К выполнению |
| **in_progress** | ❌ | ❌ | В работе |
| **review** | ❌ | ❌ | На проверке |
| **completed** | ✅ | ❌ | Выполнена |
| **blocked** | ❌ | ✅ | Заблокирована |

### 🎯 ТИПЫ ДЕЙСТВИЙ

| code | requires_target_user | requires_template | supports_delay |
|------|---------------------|-------------------|----------------|
| **notify_assignee** | ❌ | ✅ | ❌ |
| **notify_creator** | ❌ | ✅ | ❌ |
| **notify_custom** | ✅ | ✅ | ✅ |
| **change_status** | ❌ | ❌ | ✅ |
| **create_subtask** | ✅ | ❌ | ❌ |

### 🔥 КРИТИЧЕСКИЕ МОМЕНТЫ (ОПЫТ)

#### ⚠️ ПРОБЛЕМА 1: Порядок роутов в FastAPI
**Симптомы:** POST `/tasks/{id}/archive` перехватывался GET `/tasks/{id}`
**Причина:** FastAPI обрабатывает роуты в порядке объявления
**Решение:**
```python
# ✅ ПРАВИЛЬНЫЙ ПОРЯДОК
@router.get("/graph")  # 1. Специальные эндпоинты
@router.get("/stats")
@router.delete("/dependencies/{id}")  # 2. Эндпоинты с dependency_id
@router.post("/dependencies/{id}/actions")
@router.get("/{task_id}")  # 3. ПОСЛЕДНИМИ - с task_id!
```

#### ⚠️ ПРОБЛЕМА 2: 404 в тестах зависимостей
**Симптомы:** DELETE `/projects/{slug}/dependencies/{id}` - 404 Not Found
**Причина:** Неправильный URL (пропущен `/tasks/`)
**Решение:**
```python
# ❌ Неправильно
/projects/{slug}/dependencies/{id}

# ✅ Правильно
/projects/{slug}/tasks/dependencies/{id}
```

#### ⚠️ ПРОБЛЕМА 3: Логика готовности задач
**Симптомы:** Все задачи всегда `is_ready = True`
**Причина:** Не учитывались зависимости
**Решение:**
```python
def check_task_readiness(self, task: Task) -> bool:
    # 1. Только задачи со статусом 'todo'
    if task.status.name != 'todo':
        return False
    
    # 2. Получаем входящие зависимости
    incoming = self.dependency_model.select().where(
        (self.dependency_model.project == task.project) &
        (self.dependency_model.target_task == task)
    )
    
    # 3. Нет зависимостей - задача готова!
    if not incoming:
        return True
    
    # 4. Проверяем все зависимости
    for dep in incoming:
        if dep.source_task.status.name != 'completed':
            return False
    
    return True
```

#### ⚠️ ПРОБЛЕМА 4: Developer не мог удалить свою задачу
**Симптомы:** DELETE `/tasks/{id}` от developer возвращал 403
**Причина:** В тесте задача создавалась от owner, удалял developer
**Решение:**
```python
# В тесте: создаем задачу от имени developer!
create_response = requests.post(
    f"{BASE_URL}/projects/{slug}/tasks",
    headers=developer_headers,  # ← ВАЖНО!
    json={"name": "Task"}
)
```

#### ⚠️ ПРОБЛЕМА 5: Ошибка 500 при change_status
**Симптомы:** POST `/tasks/{id}/status` с тем же статусом - 500
**Причина:** Не обрабатывался случай `old_status == new_status`
**Решение:**
```python
def change_task_status(...):
    if old_status.id == new_status.id:
        return {
            'status_changed': False,
            'task': task,
            'old_status': old_status,
            'new_status': new_status
        }  # ← НЕ выбрасываем исключение!
```

#### ⚠️ ПРОБЛЕМА 6: Составной ключ Task
**Симптомы:** ValueError: over-determined primary key Task
**Причина:** Неправильное определение primary key в модели
**Решение:**
```python
class Task(BaseModel):
    id = AutoField()
    project = ForeignKeyField(Project)
    
    class Meta:
        indexes = (
            (('project', 'id'), True),  # ← Уникальность, НЕ primary key!
        )
```

---

# 🗄 МОДЕЛИ ДАННЫХ

## 📁 user.py - КЛЮЧЕВЫЕ МОМЕНТЫ

```python
class User(BaseModel):
    email = CharField(null=True)
    email_verified = BooleanField(default=False)
    email_code = CharField(null=True)
    # ... сроки и попытки кода — см. модель
    
    @property
    def theme_preferences_dict(self):
        # Всегда возвращаем dict, даже если в БД строка
        if self.theme_preferences:
            return json.loads(self.theme_preferences)
        return {"mode": "light", "primary_color": "#1976d2", "language": "ru"}
```

## 📁 team.py - КЛЮЧЕВЫЕ МОМЕНТЫ

```python
class TeamMember(BaseModel):
    # Составной уникальный ключ!
    class Meta:
        indexes = (
            (('team', 'user'), True),  # Один пользователь - одна запись
        )

class TeamInvitation(BaseModel):
    status = CharField(
        choices=[
            ('pending', 'Ожидает'),
            ('accepted', 'Принято'),
            ('declined', 'Отклонено'),
            ('expired', 'Истекло'),
            ('cancelled', 'Отменено')
        ],
        default='pending'
    )
```

## 📁 project.py - КЛЮЧЕВЫЕ МОМЕНТЫ

```python
class Project(BaseModel):
    status = CharField(
        choices=[
            ('active', 'Активен'),
            ('archived', 'В архиве'),
            ('deleted', 'Удален')
        ],
        default='active'
    )
    
    # Slack: уникален в рамках команды
    slug = CharField(max_length=200)
    
    class Meta:
        indexes = (
            (('team', 'slug'), True),  # ← Уникальность!
        )
```

## 📁 task.py - КЛЮЧЕВЫЕ МОМЕНТЫ

```python
class Task(BaseModel):
    id = AutoField()
    project = ForeignKeyField(Project)
    
    class Meta:
        # НЕ primary_key = CompositeKey!
        indexes = (
            (('project', 'id'), True),  # ← Уникальность
        )

class ScheduledAction(BaseModel):
    @classmethod
    def schedule_deadline_notification(cls, task: Task, hours_before: int):
        """Метод класса, НЕ атрибут!"""
        notify_time = task.deadline - timedelta(hours=hours_before)
        return cls.create(
            task=task,
            scheduled_for=notify_time,
            action_type='deadline_approaching'
        )
```

---

# 🌐 REST API - ПАТТЕРНЫ

## 📁 deps.py - ПРАВИЛЬНЫЕ ЗАВИСИМОСТИ

```python
# ✅ Всегда так!
from ..services.TeamService import TeamService  # с большой буквы
from ..services.ProjectService import ProjectService
from ..services.TaskService import TaskService

def get_team_service():
    service = TeamService()
    yield service
```

## 📁 routes/__init__.py

```python
# ✅ Все роутеры здесь!
from . import auth, users, teams, projects, tasks

__all__ = ['auth', 'users', 'teams', 'projects', 'tasks']
```

## 📁 main.py

```python
# ✅ Подключаем все роутеры!
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(teams.router)     # ← НЕ ЗАБЫТЬ!
app.include_router(projects.router)  # ← НЕ ЗАБЫТЬ!
app.include_router(tasks.router)     # ← НЕ ЗАБЫТЬ!
```

---

# 🧪 ТЕСТИРОВАНИЕ - ОПЫТ И ПАТТЕРНЫ

## 🔥 ПРОБЛЕМА 1: Тесты идут 17+ минут
**Решение:** Использовать TestClient вместо реального HTTP
```python
# ❌ Медленно (200-500ms на запрос)
requests.post("http://localhost:8000/api/v1/auth/login")

# ✅ Быстро (5-20ms на запрос)
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
response = client.post("/api/v1/auth/login", json=...)
```

## 🔥 ПРОБЛЕМА 2: Каждый тест создает новых пользователей
**Решение:** Переиспользовать на уровне класса
```python
class TestProjectsLive:
    @classmethod
    def setup_class(cls):
        """Один раз для всех тестов"""
        cls.owner = create_test_user()
        cls.project = create_test_project(cls.owner)
    
    def test_1(self):
        # Используем cls.owner, cls.project
        pass
```

## 🔥 ПРОБЛЕМА 3: .refresh() не работает в Peewee
**Решение:** 
```python
# ❌ Неправильно
team.refresh()

# ✅ Правильно
team = Team.get_by_id(team.id)
```

## 🔥 ПРОБЛЕМА 4: Сообщения об ошибках не совпадают
**Решение:** Всегда проверяйте точный текст!
```python
# ❌ Неправильно
with pytest.raises(PermissionError, match='no permission'):

# ✅ Правильно
with pytest.raises(PermissionError, match="You don't have permission to add members"):
```

## 🔥 ПРОБЛЕМА 5: Тесты зависят друг от друга
**Решение:** Каждый тест должен быть изолирован!
```python
def setup_method(self):
    # КАЖДЫЙ тест создает свои уникальные данные
    self.owner_username = f"owner_{random_string()}_{int(time.time())}"
    self.owner_password = "OwnerPass123!"
    # ... уникальные для каждого теста!
```

---

# 📋 ЧЕК-ЛИСТЫ ДЛЯ РАЗРАБОТКИ

## ✅ ПРИ СОЗДАНИИ НОВОГО СЕРВИСА:

- [ ] Определить модели данных
- [ ] Написать миграции/init_db
- [ ] Создать service с методами
- [ ] Создать schemas (Pydantic)
- [ ] Создать routes
- [ ] Подключить routes в main.py
- [ ] Подключить в __init__.py
- [ ] Написать unit-тесты
- [ ] Написать API тесты

## ✅ ПРИ ДОБАВЛЕНИИ НОВОГО ЭНДПОИНТА:

- [ ] Проверить порядок роутов (специальные ДО общих)
- [ ] Добавить проверку прав
- [ ] Добавить try/except
- [ ] Добавить логирование
- [ ] Добавить schema response_model
- [ ] Написать тест

## ✅ ПРИ НАПИСАНИИ ТЕСТОВ:

- [ ] Каждый тест изолирован (уникальные данные)
- [ ] Проверять точный код статуса
- [ ] Проверять точное сообщение об ошибке
- [ ] Нет .refresh() - использовать .get_by_id()
- [ ] Сохранять ID созданных объектов

---

# 🚨 ТОП-10 ОШИБОК И ИХ РЕШЕНИЙ

| # | Ошибка | Симптомы | Решение |
|---|--------|----------|---------|
| 1 | **Порядок роутов** | 404 для специальных эндпоинтов | Специальные ДО общих |
| 2 | **.refresh()** | AttributeError | `obj = Model.get_by_id(obj.id)` |
| 3 | **Составной ключ** | over-determined primary key | Использовать indexes, НЕ CompositeKey |
| 4 | **Дубликат email** | IntegrityError | Проверка уникальности до INSERT |
| 5 | **Права developer** | 200 вместо 403 | Добавить проверку в эндпоинт |
| 6 | **URL зависимостей** | 404 Not Found | `/tasks/dependencies/` а не `/dependencies/` |
| 7 | **Архивация проекта** | Проект исчезает | Менять статус, НЕ удалять |
| 8 | **Готовность задач** | Всегда True | Проверять зависимости |
| 9 | **Двойной router** | 404 для половины эндпоинтов | Одно определение в начале файла |
| 10 | **Тестовый tg_id** | Conflict при логине | Уникальный для каждого теста |

---

# 🎯 ФИНАЛЬНЫЕ РЕКОМЕНДАЦИИ

## 1. **Всегда проверяйте порядок роутов**
Специальные эндпоинты (`/graph`, `/stats`, `/dependencies/{id}`) должны быть ДО общих (`/{task_id}`).

## 2. **Никогда не используйте `.refresh()`**
В Peewee его нет. Используйте `Model.get_by_id()`.

## 3. **Всегда проверяйте права в начале метода**
```python
def update_task(...):
    if not project_service.can_edit_task(user, task):
        raise PermissionError(...)
    # ... остальная логика
```

## 4. **Всегда логируйте ошибки**
```python
try:
    # ...
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    raise
```

## 5. **Всегда проверяйте URL в тестах**
```python
print(f"Request URL: {url}")  # Добавляйте диагностику!
```

## 6. **Всегда изолируйте тесты**
Каждый тест - свои уникальные данные. Никаких зависимостей между тестами.

## 7. **Всегда проверяйте точные сообщения об ошибках**
Не пишите `match='no permission'`, пишите точный текст из сервиса.

---

# 📚 ПОЛЕЗНЫЕ ССЫЛКИ

- [Pydantic Validation Errors](https://errors.pydantic.dev)
- [FastAPI Routing Order](https://fastapi.tiangolo.com/tutorial/path-params/#order-matters)
- [Peewee Queries](http://docs.peewee-orm.com/en/latest/peewee/querying.html)

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                    234 ТЕСТА - 100% ПРОЙДЕНО                                ║
║                                                                              ║
║                    АРХИТЕКТУРА ГОТОВА К ПРОДУ                             ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**Сохрани эту памятку. В следующий раз просто скажи: "У нас есть готовая архитектура с 234 тестами, все проблемы решены" - и я сразу восстановлю контекст!** 🚀🎯🏆