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
- `analyze_file.py`: скрипт командной строки для анализа экспортированных JSON файлов. Поддерживает операции count, sum, avg, min, max с фильтрацией по условиям и группировкой по полям
- `exports/`: папка для экспортированных JSON файлов
- `cache/`: папка для файлового кэша запросов к Bitrix24 API (TTL 1 час, создается автоматически)

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

- `fast_bitrix24_mcp/tools/lead.py`
  - Сервер MCP с именем `lead`.
  - Инструменты:
    - `list_lead(filter_fields: dict[str, any] = {}, fields_id: list[str] = ["ID", "TITLE"])` — выборка лидов по фильтрам, поддержка `*` и `select`, форматирование полей в человеко-читаемом виде (включая `enumeration`).
  - Вспомогательные детали:
    - Получение схемы полей лида через `crm.lead.fields` с унификацией структуры под `prepare_fields_to_humman_format`.
    - Экспорт лидов поддерживается через общий инструмент `export_entities_to_json(entity="lead", ...)` из `tools/helper.py`.

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

### Аутентификация
- Все HTTP-запросы к агрегатору `bitrix24-main` защищены проверкой токена по схеме Bearer.
- Провайдер: `StaticTokenVerifier` (модуль `fastmcp.server.auth.providers.jwt`), инициализируется в `fast_bitrix24_mcp/main.py` с использованием `AUTH_TOKEN`.
- Источник токена: переменная окружения `AUTH_TOKEN` (загрузка через `python-dotenv`).
- Ожидается заголовок `Authorization: Bearer <AUTH_TOKEN>`.
- При отсутствии `AUTH_TOKEN` сервер не запускается.

### Конфигурация окружения
- Переменная окружения `WEBHOOK` — URL вебхука Bitrix24. Загружается через `python-dotenv` (`.env`).
- Зависимости (см. `pyproject.toml`): `fastmcp`, `orm-bitrix24`, `fast-bitrix24`, `langchain-mcp-adapters`, `langchain[openai]`, `langgraph`, `loguru`, `python-dotenv`.

### Примеры и вспомогательные материалы
- `example_chats/deal.md` — примеры запросов/диалогов.
- `README.md` — инструкции по установке/использованию.

- `fast_bitrix24_mcp/tools/helper.py`
  - Сервер MCP с именем `helper`.
  - Вспомогательные функции для экспорта и анализа данных:
    - `export_entities_to_json(entity, filter_fields, select_fields, filename)` — экспорт сущностей (`deal`, `contact`, `company`, `user`, `task`) в JSON файлы в папку `exports/`. **Особенность**: использует файловый кэш с TTL 1 час для избежания повторных запросов к Bitrix24 API при ограничениях. Кэш хранится в папке `cache/`, ключ кэша генерируется на основе параметров запроса (entity, filter_fields, select_fields). При повторном запросе с теми же параметрами данные загружаются из кэша, если он не устарел.
    - `analyze_export_file(file_path, operation, fields, condition, group_by)` — анализ экспортированных данных с операциями `count`, `sum`, `avg`, `min`, `max`. Поддерживает сложные условия фильтрации:
      - Строка с операторами: `'DATE_CREATE >= "2025-11-03 00:00:00" and DATE_CREATE <= "2025-11-09 23:59:59"'`
      - Словарь с операторами: `{'DATE_CREATE': {'>=': '2025-11-03T00:00:00', '<=': '2025-11-09T23:59:59'}}`
      - Словарь с операторами в строках: `{'DATE_CREATE': '>= 2025-11-03T00:00:00'}` (автоматически преобразуется)
      - JSON строка: `'{"DATE_CREATE": ">= 2025-11-03T00:00:00"}'` (автоматически распарсивается, поддерживает дублирующиеся ключи)
      - JSON строка с операторами в ключах: `'{"<DEADLINE": "2025-11-10T12:08:36", "!STATUS": "5"}'` (операторы в ключах автоматически извлекаются и преобразуются в нормализованный формат)
    - `analyze_tasks_export(file_path, operation, fields, condition, group_by)` — специализированный анализ для задач. **Особенность**: автоматически преобразует имена полей из формата UPPER_SNAKE_CASE (например, `RESPONSIBLE_ID`, `STATUS`) в camelCase (например, `responsibleId`, `status`) для совместимости с форматом полей в JSON файлах задач. Поддерживает оба формата имен полей в параметрах. Корректно обрабатывает случай, когда `fields` равен `None` (например, для операции `count`).
    - `export_task_fields_to_json(filename)` — экспорт описания полей задач
    - `datetime_now()` — получение текущей даты и времени в московской зоне
    - `prepare_fields_to_humman_format(fields, all_info_fields)` — преобразование технических ключей полей в человеко-читаемые названия
  - Поддерживает сложные условия фильтрации с операторами сравнения и логическими `and`/`or`.
  - Поддерживает сравнение дат с ключевыми словами `today`, `tomorrow`, `yesterday`.
  - Вспомогательные функции для работы с датами:
    - `_parse_datetime(value)` — парсинг дат/времени: ISO-8601, `YYYY-MM-DD`, `YYYY-MM-DD HH:MM:SS`.
    - `_keyword_to_datetime(keyword, tz)` — преобразование ключевых слов `today`/`tomorrow`/`yesterday` в начало соответствующего дня с учётом TZ.
    - `_compare(lhs, op, rhs)` — сравнение чисел, дат/времени и строк; для дат поддерживаются операторы `>`, `>=`, `<`, `<=`. **Особенность**: при сравнении дат naive datetime (без часового пояса) интерпретируются как московское время (Europe/Moscow), aware datetime с разными часовыми поясами конвертируются в московское время для корректного сравнения. **Особенность**: для операторов `<` и `>` с датами без времени (формат `YYYY-MM-DD`) интерпретация следующая: `"< 2025-11-11"` означает "до конца дня 11 ноября" (т.е. `< 2025-11-12 00:00:00`), `"> 2025-11-11"` означает "после конца дня 11 ноября" (т.е. `> 2025-11-11 23:59:59`). Это позволяет корректно обрабатывать условия с несколькими операторами для одного поля даты.
    - `_normalize_condition(condition)` — нормализация условий фильтрации: парсит JSON строки, обрабатывает дублирующиеся ключи, преобразует операторы в строках в правильный формат словаря. **Особенность**: поддерживает операторы в ключах JSON (`<DEADLINE`, `!STATUS`, `>=DATE`, и т.д.), автоматически извлекает их и преобразует в нормализованный формат. Нормализует имена полей в нижний регистр для совместимости.
    - `_normalize_condition_for_task(condition)` — нормализация условий фильтрации для задач: преобразует имена полей из UPPER_SNAKE_CASE в camelCase для совместимости с форматом полей в JSON файлах задач.
    - `_snake_to_camel(snake_str)` — преобразование UPPER_SNAKE_CASE или lower_snake_case в camelCase (например, `RESPONSIBLE_ID` → `responsibleId`).
    - `_get_field_value_case_insensitive(record, field_name)` — получение значения поля из записи независимо от регистра ключа. Используется для совместимости с данными, где поля могут быть в разных регистрах.
    - `_apply_condition(records, condition)` — применение условия к записям с поддержкой поиска полей без учета регистра. **Особенность**: при наличии нескольких операторов для одного поля (например, `{'DATE_CREATE': {'<=': '2025-11-11 23:59:59', '<': '2025-11-11'}}`) проверяются ВСЕ операторы одновременно (AND логика) - запись проходит фильтр только если все операторы выполняются.
    - `_get_field_value_for_task(record, field_name)` — получение значения поля из записи задачи с поддержкой преобразования UPPER_SNAKE_CASE в camelCase. Используется для анализа задач.
    - `_apply_condition_for_task(records, condition)` — применение условия к записям задач с поддержкой преобразования форматов полей.
    - `_record_matches_simple_expr_for_task(record, expr)` — проверка соответствия записи задачи условию с поддержкой преобразования форматов полей.
    - `_extract_operator_from_key(key)` — извлечение оператора из ключа JSON, если он есть (например, `<DEADLINE` → оператор `<`, поле `DEADLINE`).
  - Функции кэширования для `export_entities_to_json`:
    - `_generate_cache_key(entity, filter_fields, select_fields)` — генерация уникального ключа кэша на основе параметров запроса с использованием MD5 хеша
    - `_get_cache_path(cache_key)` — получение пути к файлу кэша в папке `cache/`
    - `_load_from_cache(cache_key)` — загрузка данных из кэша с проверкой TTL (1 час), возвращает `None` если кэш устарел или отсутствует
    - `_save_to_cache(cache_key, data)` — сохранение данных в кэш с метаданными времени создания
  - Логирование операций с кэшем через `loguru` (уровень `INFO`).

- `fast_bitrix24_mcp/tools/bitrixWork.py`
  - Вспомогательные функции для работы с API Bitrix24.
  - Настройка логирования: уровень логирования библиотеки `fast_bitrix24` установлен на `WARNING` для подавления DEBUG сообщений (используется стандартный модуль `logging`). Логирование проекта через `loguru` настроено на уровень `INFO` с записью в файлы `logs/workBitrix_{time}.log`.
  - Функции для работы с задачами:
    - `get_fields_by_task()` — получение полей задач через `tasks.task.getFields`
    - `get_task_by_id(task_id: int)` — получение задачи по ID через `tasks.task.get`
    - `get_tasks_by_filter(filter_fields: dict, select_fields: list, order: dict)` — получение задач по фильтру с поддержкой сортировки. Использует `get_all()` без параметра `order` (поскольку он не поддерживается библиотекой), с клиентской сортировкой. При ошибке переключается на `call()` с ручной пагинацией. **Особенность**: фильтрация по полю `STATUS` выполняется на клиенте (получает все задачи и фильтрует локально) из-за проблем с Bitrix24 API, остальные фильтры работают на сервере.
    - `create_task(fields: dict)` — создание задачи через `tasks.task.add`
    - `update_task(task_id: int, fields: dict)` — обновление задачи через `tasks.task.update`
    - `delete_task(task_id: int)` — удаление задачи через `tasks.task.delete`
    - Функции для работы с комментариями, чеклистами и учётом времени задач
  - Функции для работы с CRM: сделки, контакты, компании, пользователи.








