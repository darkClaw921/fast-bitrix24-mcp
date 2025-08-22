### Архитектура проекта

Проект представляет собой MCP-сервер для работы с Bitrix24 (REST) на базе `fastmcp`, с агрегирующим сервером, который монтирует подсервера с инструментами (tools), ресурсами (resources) и промптами (prompts).

### Корневая структура
- `fast_bitrix24_mcp/`: пакет с кодом серверов MCP
- `main.py`: точка запуска, импортирует `mcp` из `fast_bitrix24_mcp.main` и стартует сервер
- `README.md`: документация по установке и использованию
- `pyproject.toml`: метаданные и зависимости проекта
- `uv.lock`: lock-файл зависимостей
- `CHANGELOG.md`: журнал изменений
- `example_chats/`: примеры сценариев (диалогов)
- `test_mcp.py`, `mcp_test.py`: утилиты/скрипты для проверки/демонстрации работы

### Пакет `fast_bitrix24_mcp`

- `fast_bitrix24_mcp/main.py`
  - Агрегирующий сервер MCP с именем `bitrix24-main`.
  - Регистрирует главный промпт `main_prompt`.
  - Монтирует подсервера:
    - `userfields` → `resources/userfields.py`
    - `promts` → `promts/promts.py`
    - `deal` → `tools/deal.py`
    - `fields` → `tools/userfields.py`
    - `task` → `tools/task.py`

- `fast_bitrix24_mcp/tools/userfields.py`
  - Сервер MCP с именем `userfields`.
  - Инструменты:
    - `get_all_info_fields(entity: list[str] = ['all'], isText: bool = True)` — получение ID/названий/типов полей CRM (`deal`, `contact`, `company`, `task`), включая развёрнутые значения для `enumeration`. Может возвращать текст или словарь; сохраняет выгрузки в файлы `bitrix_fields_{entity}.json`.

- `fast_bitrix24_mcp/tools/deal.py`
  - Сервер MCP с именем `bitrix24`.
  - Инструменты:
    - `list_deal(filter_fields: dict[str, str] = {}, fields_id: list[str] = ["ID", "TITLE"])` — выборка сделок по фильтрам с возможностью вернуть все или указанные поля; вывод в человеко-читаемом виде (в том числе значения `enumeration`).
    - `export_entities_to_json(entity: str, filter_fields: dict = {}, select_fields: list[str] = ["*"], filename: str | None = None)` — экспорт элементов сущности (`deal`/`contact`/`company`) по фильтру в JSON-файл в `exports/`; ответ содержит сущность, количество и путь к файлу.
    - `analyze_export_file(file_path: str, operation: str, fields: str | list[str] | None = None, condition: str | dict | None = None, group_by: list[str] | None = None)` — операции над JSON: `count`, `sum`, `avg`, `min`, `max`; поддерживает условие (например, `"CLOSED == 'N' and ID > 2"`) и группировку по полям (`group_by`).
  - Вспомогательные функции:
    - `prepare_deal_fields_to_humman_format(fields: dict, all_info_fields: dict)` — преобразование технических ключей полей в человеко-читаемые названия и значений перечислений в текст.
    - `_parse_datetime(value)` — парсинг дат/времени: ISO-8601, `YYYY-MM-DD`, `YYYY-MM-DD HH:MM:SS`.
    - `_keyword_to_datetime(keyword, tz)` — преобразование ключевых слов `today`/`tomorrow`/`yesterday` в начало соответствующего дня с учётом TZ.
    - `_compare(lhs, op, rhs)` — сравнение чисел, дат/времени и строк; для дат поддерживаются операторы `>`, `>=`, `<`, `<=` и ключевые слова `today`/`tomorrow`/`yesterday`.
  - Особенности `analyze_export_file`:
    - Условие в виде строки разбирается парсером: поддерживаются `and`/`or`, операторы `==`, `!=`, `>`, `>=`, `<`, `<=`, `=` (как `==`).
    - Для дат можно писать: `"DATE_CREATE >= today and DATE_CREATE < tomorrow"` или использовать точные ISO-строки.
  - Использует `orm-bitrix24` (`Deal.get_manager(bitrix)`) и тул `get_all_info_fields` из `tools/userfields.py`.

- `fast_bitrix24_mcp/tools/task.py`
  - Сервер MCP с именем `tasks`.
  - Инструменты для управления задачами: создание, обновление, удаление, получение списка и деталей.
  - Инструменты для работы с комментариями, чеклистами и учётом времени выполнения задач.
  - Поддержка экспорта задач в JSON и их анализа с фильтрацией и группировкой.

- `fast_bitrix24_mcp/resources/userfields.py`
  - Сервер MCP с именем `userfields` (ресурсы):
    - `config://version` — версия ресурса
    - `fields://{entity}` — проксирует к `get_all_info_fields`, возвращает описание полей запрошенной сущности

- `fast_bitrix24_mcp/promts/promts.py`
  - Сервер MCP с именем `PromptServer`.
  - Промпты:
    - `fields_for_entity(entity: list[str] = ['all'], ctx)` — текстовая подсказка по работе с полями CRM и форматам значений (`enumeration`).

- `fast_bitrix24_mcp/tools/math_server.py`
  - Учебный/примерный сервер MCP с базовыми инструментами (`add`, `multiply`), ресурсами и демонстрацией работы `Context`.

- `fast_bitrix24_mcp/tools/main.py`
  - Учебный пример динамического монтирования подпроцессов MCP и вызова инструментов через `Client`.

### Взаимодействие компонентов
- Агрегатор `bitrix24-main` монтирует подсервера как пространства имён (`userfields`, `promts`, `deal`, `task`, `fields`).
- Клиент может:
  - получать метаданные полей через ресурс `fields://{entity}` (`resources/userfields.py`),
  - вызывать инструменты работы с полями (`tools/userfields.py`), со сделками (`tools/deal.py`) и с задачами (`tools/task.py`),
  - запрашивать промпты (`promts/promts.py`) и использовать главный промпт `main_prompt` (`fast_bitrix24_mcp/main.py`).

### Конфигурация окружения
- Переменная окружения `WEBHOOK` — URL вебхука Bitrix24. Загружается через `python-dotenv` (`.env`).
- Зависимости (см. `pyproject.toml`): `fastmcp`, `orm-bitrix24`, `fast-bitrix24`, `langchain-mcp-adapters`, `langchain[openai]`, `langgraph`, `loguru`, `python-dotenv`.

### Примеры и вспомогательные материалы
- `example_chats/deal.md` — примеры запросов/диалогов.
- `README.md` — инструкции по установке/использованию.

- `fast_bitrix24_mcp/tools/helper.py`
  - Сервер MCP с именем `helper`.
  - Вспомогательные функции для экспорта и анализа данных:
    - `export_entities_to_json(entity, filter_fields, select_fields, filename)` — экспорт сущностей (`deal`, `contact`, `company`, `user`, `task`) в JSON файлы в папку `exports/`
    - `analyze_export_file(file_path, operation, fields, condition, group_by)` — анализ экспортированных данных с операциями `count`, `sum`, `avg`, `min`, `max`
    - `analyze_tasks_export(file_path, operation, fields, condition, group_by)` — специализированный анализ для задач
    - `export_task_fields_to_json(filename)` — экспорт описания полей задач
    - `datetime_now()` — получение текущей даты и времени в московской зоне
    - `prepare_fields_to_humman_format(fields, all_info_fields)` — преобразование технических ключей полей в человеко-читаемые названия
  - Поддерживает сложные условия фильтрации с операторами сравнения и логическими `and`/`or`.
  - Поддерживает сравнение дат с ключевыми словами `today`, `tomorrow`, `yesterday`.

- `fast_bitrix24_mcp/tools/bitrixWork.py`
  - Вспомогательные функции для работы с API Bitrix24.
  - Функции для работы с задачами:
    - `get_fields_by_task()` — получение полей задач через `tasks.task.getFields`
    - `get_task_by_id(task_id: int)` — получение задачи по ID через `tasks.task.get`
    - `get_tasks_by_filter(filter_fields: dict, select_fields: list, order: dict)` — получение задач по фильтру с поддержкой сортировки. Использует `get_all()` без параметра `order` (поскольку он не поддерживается библиотекой), с клиентской сортировкой. При ошибке переключается на `call()` с ручной пагинацией. **Особенность**: фильтрация по полю `STATUS` выполняется на клиенте (получает все задачи и фильтрует локально) из-за проблем с Bitrix24 API, остальные фильтры работают на сервере.
    - `create_task(fields: dict)` — создание задачи через `tasks.task.add`
    - `update_task(task_id: int, fields: dict)` — обновление задачи через `tasks.task.update`
    - `delete_task(task_id: int)` — удаление задачи через `tasks.task.delete`
    - Функции для работы с комментариями, чеклистами и учётом времени задач
  - Функции для работы с CRM: сделки, контакты, компании, пользователи.








