# API TaskFlow: граф задач, зависимости и готовность

## Цель

Бэкенд поддерживает визуальный граф зависимостей, расчет готовности задач к работе, типы зависимостей, действия на зависимостях и стабильные ошибки для фронта.

## Текущий контракт

Базовый префикс: `/api/v1/projects/{slug}/tasks`.

| Метод | Путь | Назначение |
| --- | --- | --- |
| GET | `/graph` | Узлы, ребра и сохраненный `viewport` |
| PUT | `/graph` | Сохранение позиций узлов и `viewport`; зависимости не пересоздаются |
| POST | `/{id}/dependencies` | Создание зависимости `target_task_id`, `dependency_type`, `description` |
| GET | `/{id}/dependencies` | Входящие и исходящие зависимости |
| PATCH | `/dependencies/{dependency_id}` | Обновление типа или описания зависимости |
| DELETE | `/dependencies/{dependency_id}` | Удаление зависимости |
| POST | `/dependencies/{dependency_id}/actions` | Добавление действия на зависимость |
| DELETE | `/dependencies/actions/{action_id}` | Деактивация действия |
| GET | `/{id}` | Деталка задачи, зависимости и события |

Метаданные для UI: `GET /api/v1/meta/task-graph`.

## Права проекта

Канонические роли: `owner`, `manager`, `developer`, `observer`.

| Действие | owner | manager | developer | observer |
| --- | --- | --- | --- | --- |
| Создание задачи | Да | Да | Нет | Нет |
| Редактирование полей задачи | Да | Да | Нет | Нет |
| Удаление задачи | Да | Да | Нет | Нет |
| Смена статуса | Да | Да | Да | Да |
| Чтение задач и графа | Да | Да | Да | Да |
| Создание/удаление зависимостей | Да | Да | Нет | Нет |
| Сохранение раскладки графа | Да | Да | Нет | Нет |

`GET /api/v1/projects/{slug}` возвращает согласованные флаги: `can_create_tasks`, `can_edit_tasks`, `can_delete_tasks`, `can_change_task_status`, `can_manage_task_graph`. Для `developer` и `observer` все флаги мутаций задач/графа равны `false`, кроме `can_change_task_status`.

## Семантика ребра

Ребро `A -> B` означает: задача `A` должна быть завершена до начала `B`, если тип зависимости блокирующий. Фронт может создавать связь с `dependency_type: "blocks"`; этот тип участвует в расчете `is_ready`.

## Готовность задачи

`is_ready = true`, если задача в статусе `todo` и у нее нет незавершенных входящих блокирующих зависимостей.

В ответах задач и графа дополнительно возвращаются:

- `blocking_task_ids`: ID незавершенных задач-блокировщиков.
- `blocked_reason`: сейчас `blocked_by_dependencies` или `null`.

Блокирующие типы: `blocks`, `simple`, `dependency`. Визуальные типы без блокировки: `soft`, `relates_to`.

Попытка перевести заблокированную задачу в `in_progress` отклоняется с:

```json
{
  "detail": {
    "error_code": "TASK_NOT_READY",
    "message": "TASK_NOT_READY: Task is blocked by unfinished dependencies: [1]"
  }
}
```

## Граф

Каждое ребро из БД возвращает `data.dependency_id`, чтобы фронт мог удалить связь:

```json
{
  "id": "dep-333",
  "source": "1",
  "target": "2",
  "type": "blocks",
  "animated": true,
  "label": "Блокирует",
  "data": {
    "dependency_id": 333,
    "description": "Опционально",
    "actions": []
  }
}
```

## Действия на зависимостях

Actions выполняются при переходе `source_task` в финальный статус (`completed` и другие статусы с `is_final = true`). Порядок: `execute_order`, затем `id`. Если `delay_minutes > 0`, действие планируется в `scheduled_actions`; иначе выполняется сразу.

Поддерживаемые `action_type_code`: `notify_assignee`, `notify_creator`, `notify_custom`, `change_status`, `create_subtask`. Обязательные поля и подписи возвращаются в `GET /api/v1/meta/task-graph`.

## Ошибки

Цикл в блокирующих зависимостях отклоняется:

```json
{
  "detail": {
    "error_code": "DEPENDENCY_CYCLE",
    "message": "This dependency would create a cycle"
  }
}
```

Неизвестный `action_type_code` возвращает `UNKNOWN_ACTION_TYPE` и список допустимых кодов в сообщении.
