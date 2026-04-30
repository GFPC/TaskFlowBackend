# Backend acceptance checklist

Документ для быстрой проверки backend перед сдачей TaskFlow.

## Что должно быть готово

- Модели БД создаются без ручных правок: задачи, зависимости, действия зависимостей, заметки, проектные роли.
- `teams.list()` возвращает корректный `projects_count` с учетом активных и архивных проектов, кроме `deleted`.
- `GET /api/v1/projects/{slug}` возвращает актуальные права текущего пользователя:
  - `user_role`
  - `can_create_tasks`
  - `can_edit_tasks`
  - `can_delete_tasks`
  - `can_change_task_status`
  - `can_manage_task_graph`
- Роли проекта соответствуют канонике:
  - `owner` и `manager` могут управлять задачами и графом.
  - `developer` и `observer` читают проект, задачи и граф, могут менять только статус задач.
  - Сервер возвращает `403` на запрещенные мутации, даже если frontend скрывает кнопки.
- Граф задач поддерживает:
  - сохранение позиций и viewport;
  - зависимости с `dependency_id`, типом, описанием и actions;
  - защиту от циклов для blocking-зависимостей;
  - расчет `is_ready`, `blocking_task_ids`, `blocked_reason`.
- Notes поддерживают project/task scope:
  - читать и создавать могут участники проекта;
  - редактировать и удалять могут автор, owner или manager;
  - task note создается только для задачи из этого проекта.
- Auth использует текущий контракт email OTP.

## Проверки для демонстрации

```bash
python -m pytest tests/test_service/test_backend_acceptance.py -q
python -m pytest tests/test_service/test_user_email_acceptance.py -q
python -m pytest tests/test_service/test_task.py tests/test_service/test_project.py -q
python -m pytest tests/test_service -q
python -m compileall core tests
```

Ожидаемый минимум перед сдачей:

- `test_backend_acceptance.py`: проходит матрица ролей, запреты graph/task mutations, смена статуса и notes.
- `test_user_email_acceptance.py`: проходит регистрация, email verification, login, validation.
- `test_task.py` и `test_project.py`: проходят сервисные сценарии задач/графа/проектов.
- `tests/test_service`: зеленый; legacy Telegram tests удалены, потому что заменены email-auth контрактом.
- `compileall`: без синтаксических ошибок.

## Ручной smoke перед показом

1. Зайти owner/manager и создать задачу.
2. Создать developer в проекте и проверить:
   - `GET /projects/{slug}` отдает `user_role: developer`;
   - `can_create_tasks: false`;
   - `can_manage_task_graph: false`;
   - POST/PATCH/DELETE задачи и graph save дают `403`;
   - смена статуса задачи проходит.
3. Проверить observer с теми же запретами и разрешенной сменой статуса.
4. Создать dependency owner/manager, убедиться, что target задача получает readiness-поля.
5. Добавить project note и task note, проверить edit/delete автором и manager.
6. Открыть список teams и убедиться, что количество проектов совпадает с фактическим списком проектов.
