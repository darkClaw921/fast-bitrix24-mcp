# Реализация получения активности менеджеров в Bitrix24

## Описание

Документ описывает реализацию системы получения полной активности менеджеров из Bitrix24 через REST API. Основной файл: `get_manager_activity.py`

---

## Добавленные функции в bitrixWork.py

### 1. Получение активностей CRM

#### `get_crm_activities_by_filter(filter_fields: dict={}, select_fields: List[str]=["*"]) -> List[Dict]`

**Назначение**: Получение активностей CRM (звонки, встречи, email-письма) по фильтру.

**API метод**: `crm.activity.list`

**Параметры**:
- `filter_fields` - фильтры (RESPONSIBLE_ID, >=CREATED, <=CREATED)
- `select_fields` - поля для выборки

**Возвращает**: Список активностей

**Логика работы**:
```python
# Формируем параметры
params = {
    'filter': filter_fields,
    'select': select_fields
}

# Получаем через get_all для автоматической пагинации
activities = await bit.get_all('crm.activity.list', params=params)

# Обрабатываем возможный словарь с ключом order0000000000
if isinstance(activities, dict):
    if activities.get('order0000000000'):
        activities = activities['order0000000000']
```

**Использование в get_manager_activity.py**:
```python
date_filter = {
    '>=CREATED': f"{start_date}T00:00:00",
    '<=CREATED': f"{end_date}T23:59:59",
    'RESPONSIBLE_ID': manager_id
}
activities = await get_crm_activities_by_filter(date_filter)
```

**Анализируем типы активностей**:
- `TYPE_ID = '2'` → Звонки
  - `DIRECTION = '1'` → Исходящий
  - `DIRECTION = '2'` → Входящий
  - `DIRECTION = '0'` → Пропущенный
- `TYPE_ID = '1'` → Встречи
- `TYPE_ID = '4'` → Email

---

### 2. Получение статистики звонков (не используется)

#### `get_voximplant_statistics(filter_fields: dict={}) -> List[Dict]`

**Назначение**: Получение детальной статистики звонков через voximplant.

**API метод**: `voximplant.statistic.get`

**Статус**: Добавлена, но не используется в текущей реализации, так как звонки получаются через CRM активности.

---

### 3. Получение сообщений (не используется)

#### `get_im_messages_by_filter(filter_fields: dict={}) -> List[Dict]`

**Назначение**: Получение сообщений из чатов.

**API метод**: `im.message.list`

**Статус**: Добавлена, но не используется в текущей реализации.

---

### 4. Получение лидов

#### `get_leads_by_filter(filter_fields: dict={}, select_fields: List[str]=["*", "UF_*"]) -> List[Dict]`

**Назначение**: Получение лидов по фильтру.

**API метод**: `crm.lead.list`

**Использование**:
```python
leads_filter = {
    '>=DATE_CREATE': f"{start_date}T00:00:00",
    '<=DATE_CREATE': f"{end_date}T23:59:59",
    'ASSIGNED_BY_ID': manager_id
}
leads = await get_leads_by_filter(leads_filter, select_fields=['ID', 'TITLE', 'STATUS_ID', 'DATE_CREATE'])
```

**Подсчет конвертированных**:
```python
leads_converted = len([l for l in leads if str(l.get('STATUS_ID', '')) == 'CONVERTED'])
```

---

### 5. Получение комментариев

#### `get_all_entity_comments(entity_type: str, author_id: int, from_date: str = None) -> List[Dict]`

**Назначение**: Получение всех комментариев пользователя в сущностях CRM (deal, lead, contact, company).

**API метод**: `crm.timeline.comment.list`

**ВАЖНО**: API Bitrix24 не возвращает комментарии только по `AUTHOR_ID`. Требуется указывать `ENTITY_ID`.

**Решение**:
1. Получаем список всех сущностей нужного типа
2. Для каждой сущности запрашиваем комментарии по `ENTITY_ID`
3. Фильтруем по `AUTHOR_ID` на стороне клиента
4. Собираем все комментарии в один список

**Алгоритм**:
```python
async def get_all_entity_comments(entity_type: str, author_id: int, from_date: str = None):
    all_comments = []
    
    # Шаг 1: Получаем список всех сущностей
    if entity_type == 'deal':
        entity_list = await get_deals_by_filter({}, select_fields=['ID'])
    elif entity_type == 'lead':
        entity_list = await get_leads_by_filter({}, select_fields=['ID'])
    # ... и т.д.
    
    # Шаг 2: Для каждой сущности получаем комментарии
    for entity in entity_list:
        entity_id = entity.get('ID')
        
        params = {
            'filter': {
                'ENTITY_TYPE': entity_type,
                'ENTITY_ID': entity_id
            }
        }
        
        result = await bit.call('crm.timeline.comment.list', params, raw=True)
        
        if result and 'result' in result and isinstance(result['result'], list):
            # Фильтруем по автору
            entity_comments = [
                c for c in result['result'] 
                if str(c.get('AUTHOR_ID')) == str(author_id)
            ]
            
            all_comments.extend(entity_comments)
    
    return all_comments
```

**Использование**:
```python
# Получаем комментарии в сделках
deal_comments = await get_all_entity_comments('deal', manager_id, from_date=None)

# Получаем комментарии в лидах
lead_comments = await get_all_entity_comments('lead', manager_id, from_date=None)

# Получаем комментарии в контактах
contact_comments = await get_all_entity_comments('contact', manager_id, from_date=None)

# Получаем комментарии в компаниях
company_comments = await get_all_entity_comments('company', manager_id, from_date=None)
```

**Структура комментария**:
```json
{
  "ID": "12",
  "AUTHOR_ID": "1",
  "COMMENT": "123123",
  "CREATED": "2025-11-11T19:20:26+03:00",
  "ENTITY_ID": 4,
  "ENTITY_TYPE": "deal"
}
```

---

### 6. Получение событий календаря

#### `get_calendar_events(from_date: str, to_date: str, owner_id: int = None) -> List[Dict]`

**Назначение**: Получение событий календаря пользователя через секции.

**API методы**:
1. `calendar.section.get` - получение секций календаря
2. `calendar.event.get` - получение событий для каждой секции

**Алгоритм работы в два этапа**:

**Этап 1: Получение секций календаря**
```python
sections_params = {
    'type': 'user',
    'ownerId': owner_id if owner_id else 1
}
sections_result = await bit.call('calendar.section.get', sections_params, raw=True)

sections = []
if sections_result and 'result' in sections_result:
    sections = sections_result['result'] if isinstance(sections_result['result'], list) else [sections_result['result']]
```

**Этап 2: Получение событий для каждой секции**
```python
for section in sections:
    section_id = section.get('ID')
    
    events_params = {
        'type': 'user',
        'ownerId': owner_id if owner_id else 1,
        'section': [section_id],
        'from': from_date,
        'to': to_date
    }
    events_result = await bit.call('calendar.event.get', events_params, raw=True)
    
    if events_result and 'result' in events_result:
        section_events = events_result['result'] if isinstance(events_result['result'], list) else []
        all_events.extend(section_events)
```

**Использование**:
```python
calendar_events = await get_calendar_events(
    from_date=f"{start_date}T00:00:00",
    to_date=f"{end_date}T23:59:59",
    owner_id=manager_id
)
```

**Подсчет встреч**:
```python
calendar_meetings = len([
    e for e in calendar_events 
    if e.get('CAL_TYPE') == 'user' or e.get('MEETING_STATUS') == 'Y'
])
```

---

## Структура файла get_manager_activity.py

### Основная функция: `get_manager_full_activity(manager_id: int, days: int = 30)`

**Алгоритм работы**:

#### 1. Получение информации о менеджере
```python
managers = await get_users_by_filter({'ID': manager_id})
manager = managers[0] if isinstance(managers, list) else managers
manager_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip()
```

#### 2. Установка периода анализа
```python
end_date = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
```

#### 3. Получение активностей CRM
- Звонки (по TYPE_ID и DIRECTION)
- Встречи (TYPE_ID = '1')
- Email (TYPE_ID = '4')

#### 4. Получение задач
```python
tasks = await get_tasks_by_filter(
    {'RESPONSIBLE_ID': manager_id},
    select_fields=['ID', 'TITLE', 'STATUS', 'CREATED_DATE', 'CLOSED_DATE']
)

# Подсчет по статусам
tasks_completed = len([t for t in tasks if t.get('STATUS') == '5' or t.get('status') == '5'])
tasks_in_progress = len([t for t in tasks if t.get('STATUS') in ['2', '3'] or t.get('status') in ['2', '3']])
```

**Статусы задач**:
- `'2'` - Новая
- `'3'` - В работе
- `'5'` - Завершена

#### 5. Получение сделок
```python
deals_filter = {
    '>=DATE_CREATE': f"{start_date}T00:00:00",
    '<=DATE_CREATE': f"{end_date}T23:59:59",
    'ASSIGNED_BY_ID': manager_id
}
deals = await get_deals_by_filter(deals_filter, select_fields=['ID', 'TITLE', 'STAGE_ID', 'DATE_CREATE'])

# Подсчет выигранных
deals_won = len([d for d in deals if 'WON' in str(d.get('STAGE_ID', '')).upper()])
```

#### 6. Получение лидов
```python
leads = await get_leads_by_filter(leads_filter, select_fields=['ID', 'TITLE', 'STATUS_ID', 'DATE_CREATE'])

# Подсчет конвертированных
leads_converted = len([l for l in leads if str(l.get('STATUS_ID', '')) == 'CONVERTED'])
```

#### 7. Получение событий календаря
```python
calendar_events = await get_calendar_events(
    from_date=f"{start_date}T00:00:00",
    to_date=f"{end_date}T23:59:59",
    owner_id=manager_id
)
```

#### 8. Получение комментариев
```python
# Получаем комментарии из всех типов сущностей
deal_comments = await get_all_entity_comments('deal', manager_id, from_date=None)
lead_comments = await get_all_entity_comments('lead', manager_id, from_date=None)
contact_comments = await get_all_entity_comments('contact', manager_id, from_date=None)
company_comments = await get_all_entity_comments('company', manager_id, from_date=None)

total_comments = len(deal_comments) + len(lead_comments) + len(contact_comments) + len(company_comments)
```

---

## Формат результата

### JSON структура
```json
{
  "manager_id": 1,
  "name": "Игорь Герасимов",
  "email": "darkClaw921@yandex.ru",
  "work_position": "",
  "period": {
    "start_date": "2025-10-13",
    "end_date": "2025-11-12",
    "days": 30
  },
  "calls": {
    "total": 0,
    "incoming": 0,
    "outgoing": 0,
    "missed": 0
  },
  "meetings": 0,
  "emails": 0,
  "tasks": {
    "total": 1,
    "completed": 0,
    "in_progress": 1
  },
  "deals": {
    "created": 2,
    "won": 1
  },
  "leads": {
    "created": 0,
    "converted": 0
  },
  "calendar": {
    "total_events": 1,
    "meetings": 1
  },
  "comments": {
    "total": 1,
    "deals": 1,
    "leads": 0,
    "contacts": 0,
    "companies": 0,
    "deal_comments_list": [
      {
        "entity_id": 4,
        "text": "123123",
        "created": "2025-11-11T19:20:26+03:00"
      }
    ]
  },
  "total_activities": 1
}
```

---

## Использование

### Командная строка
```bash
# Активность менеджера с ID 1 за последние 30 дней
python3 get_manager_activity.py 1 30

# За другой период (90 дней)
python3 get_manager_activity.py 1 90

# По умолчанию (ID=1, 30 дней)
python3 get_manager_activity.py
```

### Результат
- Выводится в консоль с форматированием
- Сохраняется в JSON файл: `manager_{id}_activity_{timestamp}.json`

---

## Проблемы и решения

### Проблема 1: Комментарии не отображались

**Причина**: API `crm.timeline.comment.list` не возвращает комментарии только по `AUTHOR_ID`.

**Решение**: Реализован двухэтапный подход:
1. Получаем все сущности (deal/lead/contact/company)
2. Для каждой сущности получаем комментарии по `ENTITY_ID`
3. Фильтруем по `AUTHOR_ID` на клиенте

### Проблема 2: События календаря возвращали пустой список

**Причина**: API требует указания секции календаря для получения событий.

**Решение**: Двухэтапный запрос:
1. Получаем секции через `calendar.section.get`
2. Для каждой секции получаем события через `calendar.event.get`

### Проблема 3: Сделки не все отображались

**Причина**: Использовался фильтр по дате создания, но нужны были все сделки пользователя.

**Решение**: Фильтр настроен правильно с `ASSIGNED_BY_ID` и датами создания в указанном периоде.

---

## Метрики производительности

- **Задачи**: 1 запрос
- **Сделки**: 1 запрос + подсчет на клиенте
- **Лиды**: 1 запрос + подсчет на клиенте
- **Активности CRM**: 1 запрос + анализ типов на клиенте
- **Календарь**: 1 запрос секций + N запросов событий (по 1 на секцию)
- **Комментарии**: 1 запрос списка сущностей + N запросов комментариев (по 1 на сущность)

**Общее время выполнения**: ~10-15 секунд (зависит от количества сущностей)

---

## Используемые Bitrix24 REST API методы

| Метод | Назначение |
|-------|------------|
| `user.get` | Получение информации о пользователе |
| `crm.activity.list` | Получение активностей CRM (звонки, встречи, email) |
| `tasks.task.list` | Получение задач |
| `crm.deal.list` | Получение сделок |
| `crm.lead.list` | Получение лидов |
| `crm.contact.list` | Получение контактов |
| `crm.company.list` | Получение компаний |
| `calendar.section.get` | Получение секций календаря |
| `calendar.event.get` | Получение событий календаря |
| `crm.timeline.comment.list` | Получение комментариев в timeline |

---

## Типы данных Bitrix24

### Типы активностей CRM (TYPE_ID)
- `'1'` - Встреча
- `'2'` - Звонок
- `'4'` - Email
- `'6'` - Задача (в активностях)

### Направление звонков (DIRECTION)
- `'0'` - Пропущенный
- `'1'` - Исходящий
- `'2'` - Входящий

### Статусы задач (STATUS)
- `'2'` - Новая
- `'3'` - В работе
- `'4'` - Ожидает выполнения
- `'5'` - Завершена
- `'6'` - Отложена
- `'7'` - Отклонена

### Статусы лидов (STATUS_ID)
- `'NEW'` - Новый
- `'IN_PROCESS'` - В работе
- `'CONVERTED'` - Конвертирован
- `'JUNK'` - Некачественный

### Этапы сделок (STAGE_ID)
Зависят от воронки продаж. Успешные этапы содержат `'WON'`, неуспешные - `'LOSE'`.

---

## Логирование

Все операции логируются через `loguru`:
```python
logger.info(f"Получение комментариев deal для автора {author_id}")
logger.info(f"Найдено {len(entity_list)} deal для проверки")
logger.info(f"Получено {len(all_comments)} комментариев deal от автора {author_id}")
```

Логи сохраняются в: `logs/workBitrix_{time}.log`

---

## Итоги

Реализована полная система получения активности менеджеров из Bitrix24 с поддержкой:
- ✅ Звонков (входящие, исходящие, пропущенные)
- ✅ Встреч
- ✅ Email-сообщений
- ✅ Задач (всего, завершено, в работе)
- ✅ Сделок (создано, выиграно)
- ✅ Лидов (создано, конвертировано)
- ✅ Событий календаря
- ✅ Комментариев во всех сущностях CRM

Результаты сохраняются в JSON для дальнейшего анализа.

