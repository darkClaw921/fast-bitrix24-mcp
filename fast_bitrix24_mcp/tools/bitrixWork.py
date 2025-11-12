from fast_bitrix24 import Bitrix
import os
from dotenv import load_dotenv
from pprint import pprint
from datetime import datetime, timedelta
from loguru import logger
import asyncio
import traceback
import logging
import json
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any

# Настройка уровня логирования для библиотеки fast_bitrix24 - отключаем DEBUG логи
logging.getLogger('fast_bitrix24').setLevel(logging.WARNING)

load_dotenv()
webhook = os.getenv('WEBHOOK')
if webhook:
    bit = Bitrix(webhook, ssl=False, verbose=False)
else:
    raise ValueError("WEBHOOK environment variable is required")

logger.add("logs/workBitrix_{time}.log",format="{time:YYYY-MM-DD HH:mm}:{level}:{file}:{line}:{message} ", rotation="100 MB", retention="10 days", level="INFO")

# Настройка кэша для активности
CACHE_DIR = Path("cache")
CACHE_TTL_SECONDS = 3600  # 1 час


def _generate_activity_cache_key(prefix: str, **kwargs) -> str:
    """Генерирует ключ кэша на основе параметров запроса активности"""
    cache_data = {
        "prefix": prefix,
        **{k: json.dumps(v, sort_keys=True, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v) 
           for k, v in sorted(kwargs.items())}
    }
    cache_string = json.dumps(cache_data, sort_keys=True, ensure_ascii=False)
    cache_hash = hashlib.md5(cache_string.encode('utf-8')).hexdigest()
    return f"{prefix}_{cache_hash}"


def _get_cache_path(cache_key: str) -> Path:
    """Возвращает путь к файлу кэша"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{cache_key}.json"


def _load_from_cache(cache_key: str) -> Optional[Any]:
    """Загружает данные из кэша, если они не устарели"""
    cache_path = _get_cache_path(cache_key)
    if not cache_path.exists():
        return None
    
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            cache_data = json.load(f)
        
        # Проверяем TTL
        cached_at = datetime.fromisoformat(cache_data["cached_at"])
        age = (datetime.now() - cached_at).total_seconds()
        
        if age > CACHE_TTL_SECONDS:
            logger.info(f"Кэш для ключа {cache_key} устарел (возраст: {age:.0f} сек), удаляем")
            cache_path.unlink()
            return None
        
        logger.info(f"Используем кэш для ключа {cache_key} (возраст: {age:.0f} сек)")
        return cache_data["data"]
    except Exception as e:
        logger.warning(f"Ошибка при чтении кэша {cache_key}: {e}")
        return None


def _save_to_cache(cache_key: str, data: Any) -> None:
    """Сохраняет данные в кэш"""
    try:
        cache_path = _get_cache_path(cache_key)
        cache_data = {
            "cached_at": datetime.now().isoformat(),
            "data": data
        }
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Данные сохранены в кэш для ключа {cache_key}")
    except Exception as e:
        logger.warning(f"Ошибка при сохранении кэша {cache_key}: {e}")


async def get_deal_by_id(deal_id: int) -> dict:
    """
    Получает сделку по ID
    """
    deal = await bit.call('crm.deal.get', {'ID': deal_id})
    return deal



async def get_fields_by_deal() -> list[dict]:
        """Получение всех полей для сделки (включая пользовательские)"""
        try:
            logger.info(f"Получение всех полей для сделки")
            # Метод .fields не требует параметров, используем get_all
            result = await bit.get_all(f'crm.deal.fields')
            
            if not result:
                logger.warning(f"Не получены поля для сделки")
                return []
            
            # result приходит в виде списка словарей, а не словаря словарей
            if isinstance(result, dict):
                # Если результат - словарь полей (ключ = имя поля, значение = данные поля)
                fields = []
                for field_name, field_data in result.items():
                    if isinstance(field_data, dict):
                        # Добавляем имя поля в данные, если его там нет
                        if 'NAME' not in field_data:
                            field_data['NAME'] = field_name

                        fields.append(field_data)
            else:
                # Если результат - список полей
                fields = [field_data for field_data in result]
            
            
            
            logger.info(f"Получено {len(fields)} полей для сделки")
            return fields
            
        except Exception as e:
            logger.error(f"Ошибка при получении полей для сделки: {e}")
            raise

async def get_fields_by_user() -> list[dict]:
    """Получение всех пользовательских полей"""
    # userfieldsUser = await bit.call('user.userfield.list', raw=True)
    # pprint(userfieldsUser)
    
    userfields = await bit.call('user.fields', raw=True)
    userfields=userfields['result']
    userfieldsTemp=[]
    for key, value in userfields.items():
        userfieldsTemp.append({
            'NAME': key,
            'title': value,
            'type': 'string'
        })
        # userfieldsTemp.append(value)
    return userfieldsTemp
    
async def get_fields_by_contact() -> list[dict]:
    """Получение всех полей для контакта (включая пользовательские)"""
    fields = await bit.get_all('crm.contact.fields')
    # pprint(fields)
    fieldsTemp=[]
    
    # Handle both dict and list responses
    if isinstance(fields, dict):
        for key, value in fields.items():
            fieldsTemp.append({
                'NAME': key,
                **value
            })
    elif isinstance(fields, list):
        for field in fields:
            if isinstance(field, dict):
                fieldsTemp.append(field)
    
    return fieldsTemp

async def get_fields_by_company() -> list[dict]:
    """Получение всех полей для компании (включая пользовательские)"""
    fields = await bit.get_all('crm.company.fields')
    # pprint(fields)
    fieldsTemp=[]
    
    # Handle both dict and list responses
    if isinstance(fields, dict):
        for key, value in fields.items():
            fieldsTemp.append({
                'NAME': key,
                **value
            })
    elif isinstance(fields, list):
        for field in fields:
            if isinstance(field, dict):
                fieldsTemp.append(field)
    
    return fieldsTemp


async def get_fields_by_lead() -> list[dict]:
    """Получение всех полей для лида (включая пользовательские)"""
    try:
        logger.info(f"Получение всех полей для сделки")
        # Метод .fields не требует параметров, используем get_all
        result = await bit.get_all(f'crm.lead.fields')
        
        if not result:
            logger.warning(f"Не получены поля для лида")
            return []
        
        # result приходит в виде списка словарей, а не словаря словарей
        if isinstance(result, dict):
            # Если результат - словарь полей (ключ = имя поля, значение = данные поля)
            fields = []
            for field_name, field_data in result.items():
                if isinstance(field_data, dict):
                    # Добавляем имя поля в данные, если его там нет
                    if 'NAME' not in field_data:
                        field_data['NAME'] = field_name

                    fields.append(field_data)
        else:
            # Если результат - список полей
            fields = [field_data for field_data in result]
        
        
        
        logger.info(f"Получено {len(fields)} полей для лида")
        return fields
        
    except Exception as e:
        logger.error(f"Ошибка при получении полей для сделки: {e}")
        raise


async def get_users_by_filter(filter_fields: dict={}) -> list[dict] | dict:
    """Получение пользователей по фильтру"""
    users = await bit.get_all('user.get', params={'filter': filter_fields})
    if isinstance(users, dict):
        if users.get('order0000000000'):
            users=users['order0000000000']
    return users

async def get_deal_categories() -> list[dict]:
    """Получение всех воронок сделок через crm.dealcategory.list
    
    Returns:
        Список словарей с информацией о воронках
    """
    try:
        logger.info(f"Получение воронок сделок")
        result = await bit.get_all('crm.dealcategory.list')
        
        if not result:
            logger.warning(f"Не получены воронки сделок")
            return []
        
        # result может быть словарем или списком
        if isinstance(result, dict):
            if result.get('order0000000000'):
                categories = result['order0000000000']
            else:
                categories = list(result.values()) if result else []
        else:
            categories = result if isinstance(result, list) else []
        
        logger.info(f"Получено {len(categories)} воронок сделок")
        return categories
        
    except Exception as e:
        logger.error(f"Ошибка при получении воронок сделок: {e}")
        raise

async def get_deal_stages(entity_id: str = "DEAL_STAGE", category_id: str | None = None) -> list[dict]:
    """Получение стадий сделок через crm.status.list
    
    Args:
        entity_id: Тип сущности (по умолчанию DEAL_STAGE для стадий сделок)
        category_id: ID воронки (категории). Если None, возвращаются стадии без категории или общие
    
    Returns:
        Список словарей с информацией о стадиях
    """
    try:
        filter_params = {'ENTITY_ID': entity_id}
        if category_id is not None:
            filter_params['CATEGORY_ID'] = category_id
        
        logger.info(f"Получение стадий для сущности {entity_id}, воронка: {category_id}")
        result = await bit.get_all('crm.status.list', params={'filter': filter_params})
        
        if not result:
            logger.warning(f"Не получены стадии для сущности {entity_id}, воронка: {category_id}")
            return []
        
        # result может быть словарем или списком
        if isinstance(result, dict):
            if result.get('order0000000000'):
                stages = result['order0000000000']
            else:
                stages = list(result.values()) if result else []
        else:
            stages = result if isinstance(result, list) else []
        
        logger.info(f"Получено {len(stages)} стадий для сущности {entity_id}, воронка: {category_id}")
        return stages
        
    except Exception as e:
        logger.error(f"Ошибка при получении стадий для сущности {entity_id}, воронка: {category_id}: {e}")
        raise

async def get_category_stages(category_id: int) -> list[dict]:
    """Получение стадий для конкретной воронки через crm.status.list с фильтром по CATEGORY_ID
    
    Args:
        category_id: ID воронки
    
    Returns:
        Список словарей с информацией о стадиях воронки
    """
    try:
        logger.info(f"Получение стадий для воронки {category_id} через crm.status.list")
        # Пробуем получить стадии через crm.status.list с фильтром по CATEGORY_ID
        result = await bit.get_all('crm.status.list', params={
            'filter': {
                '%ENTITY_ID': 'DEAL_STAGE',
                'CATEGORY_ID': str(category_id)
            }
        })
        
        if not result:
            logger.warning(f"Не получены стадии для воронки {category_id}")
            return []
        
        # result может быть словарем или списком
        if isinstance(result, dict):
            if result.get('order0000000000'):
                stages = result['order0000000000']
            else:
                stages = list(result.values()) if result else []
        else:
            stages = result if isinstance(result, list) else []
        
        logger.info(f"Получено {len(stages)} стадий для воронки {category_id}")
        return stages
        
    except Exception as e:
        logger.warning(f"Ошибка при получении стадий для воронки {category_id}: {e}")
        return []

async def get_all_deal_stages_by_categories(entity_id: str = "DEAL_STAGE") -> list[dict]:
    """Получение всех стадий сделок для всех воронок
    
    Args:
        entity_id: Тип сущности (по умолчанию DEAL_STAGE для стадий сделок)
    
    Returns:
        Список словарей с информацией о стадиях из всех воронок
    
    Особенность: Получает все стадии через crm.status.list без фильтра, затем для каждой воронки
    пытается получить стадии через crm.status.list с фильтром по CATEGORY_ID. Если стадии для
    конкретной воронки не найдены, использует общие стадии (без категории).
    """
    try:
        logger.info(f"Получение всех стадий для сущности {entity_id} из всех воронок")
        
        # Получаем все воронки
        categories = await get_deal_categories()
        
        # Получаем все стадии без фильтра (общие стадии)
        all_stages = await get_deal_stages(entity_id, None)
        seen_stage_keys = set()
        
        # Добавляем общие стадии в результат
        for stage in all_stages:
            stage_id = stage.get('STATUS_ID') or stage.get('ID')
            category_id = stage.get('CATEGORY_ID')
            if stage_id:
                # Нормализуем CATEGORY_ID: None -> '0'
                if category_id is None:
                    category_id = '0'
                    stage['CATEGORY_ID'] = '0'
                else:
                    category_id = str(category_id)
                
                unique_key = f"{stage_id}_{category_id}"
                seen_stage_keys.add(unique_key)
        
        # Получаем стадии для каждой воронки отдельно
        for category in categories:
            category_id = category.get('ID')
            if category_id:
                try:
                    category_id_int = int(category_id)
                    category_stages = await get_category_stages(category_id_int)
                    
                    # Добавляем стадии этой воронки
                    for stage in category_stages:
                        stage_id = stage.get('STATUS_ID') or stage.get('ID')
                        if stage_id:
                            # Убеждаемся, что у стадии есть CATEGORY_ID
                            if 'CATEGORY_ID' not in stage or stage.get('CATEGORY_ID') is None:
                                stage['CATEGORY_ID'] = str(category_id)
                            
                            unique_key = f"{stage_id}_{stage.get('CATEGORY_ID', '')}"
                            if unique_key not in seen_stage_keys:
                                all_stages.append(stage)
                                seen_stage_keys.add(unique_key)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Не удалось получить стадии для воронки {category_id}: {e}")
                    continue
        
        logger.info(f"Получено всего {len(all_stages)} уникальных стадий для сущности {entity_id} из всех воронок")
        return all_stages
        
    except Exception as e:
        logger.error(f"Ошибка при получении всех стадий для сущности {entity_id}: {e}")
        raise

async def get_stage_history(entity_type_id: int, owner_id: int = None, filter_fields: dict = None, select_fields: list[str] = None) -> list[dict]:
    """Получение истории движения по стадиям через crm.stagehistory.list
    
    Args:
        entity_type_id: Тип сущности (1 - лид, 2 - сделка, 5 - счет старый, 31 - счет новый)
        owner_id: ID объекта (сделки, лида и т.д.). Если указан, фильтрует историю только для этого объекта
        filter_fields: Дополнительные фильтры для запроса
        select_fields: Поля для выборки (по умолчанию все)
    
    Returns:
        Список словарей с историей стадий, отсортированный по ID (ASC)
    """
    try:
        params = {}
        
        if entity_type_id:
            params['entityTypeId'] = entity_type_id
        
        if filter_fields is None:
            filter_fields = {}
        
        if owner_id:
            filter_fields['OWNER_ID'] = owner_id
        
        if filter_fields:
            params['filter'] = filter_fields
        
        if select_fields:
            params['select'] = select_fields
        
        logger.info(f"Получение истории стадий для entity_type_id={entity_type_id}, owner_id={owner_id}")
        result = await bit.get_all('crm.stagehistory.list', params=params)
        
        if not result:
            logger.warning(f"Не получена история стадий для entity_type_id={entity_type_id}, owner_id={owner_id}")
            return []
        
        # result может быть словарем с items или списком
        if isinstance(result, dict):
            if 'items' in result:
                history = result['items']
            elif result.get('order0000000000'):
                history = result['order0000000000']
            else:
                history = list(result.values()) if result else []
        else:
            history = result if isinstance(result, list) else []
        
        # Сортируем результаты по ID (ASC) вручную, так как get_all не поддерживает order
        history.sort(key=lambda x: x.get('ID', 0))
        
        logger.info(f"Получено {len(history)} записей истории стадий для entity_type_id={entity_type_id}, owner_id={owner_id}")
        return history
        
    except Exception as e:
        logger.error(f"Ошибка при получении истории стадий для entity_type_id={entity_type_id}, owner_id={owner_id}: {e}")
        raise

async def get_deals_by_filter(filter_fields: dict, select_fields: list[str]) -> list[dict] | dict:
    """
    Получает сделку по фильтру
    """
    deal = await bit.get_all('crm.deal.list', params={'filter': filter_fields, 'select': select_fields})
    # pprint(deal)
    if isinstance(deal, dict):
        if deal.get('order0000000000'):
            deal=deal['order0000000000']
    
    return deal

async def get_contacts_by_filter(filter_fields: dict={}, select_fields: list[str]=["*", "UF_*"]) -> list[dict] | dict:
    """Получение контактов по фильтру"""
    contacts = await bit.get_all('crm.contact.list', params={'filter': filter_fields, 'select': select_fields})
    if isinstance(contacts, dict):
        if contacts.get('order0000000000'):
            contacts=contacts['order0000000000']
    return contacts

async def get_companies_by_filter(filter_fields: dict={}, select_fields: list[str]=["*", "UF_*"]) -> list[dict] | dict:
    """Получение компаний по фильтру"""
    companies = await bit.get_all('crm.company.list', params={'filter': filter_fields, 'select': select_fields})
    if isinstance(companies, dict):
        if companies.get('order0000000000'):
            companies=companies['order0000000000']
    return companies


# === ЗАДАЧИ ===

async def get_fields_by_task() -> list[dict]:
    """Получение всех полей для задач (включая пользовательские)"""
    try:
        logger.info(f"Получение всех полей для задач")
        # Fix: use correct API method without parameters
        result = await bit.call('tasks.task.getFields', raw=True)
        # pprint(result)  # Отключаем для чистоты вывода
        
        if not result:
            logger.warning(f"Не получены поля для задач")
            return []
        
        # Правильное извлечение полей из ответа
        fields = []
        
        # Ответ содержит поля в result.fields
        if isinstance(result, dict) and 'result' in result:
            result_data = result['result']
            if isinstance(result_data, dict) and 'fields' in result_data:
                task_fields = result_data['fields']
                if isinstance(task_fields, dict):
                    for field_name, field_data in task_fields.items():
                        if isinstance(field_data, dict):
                            # Создаем структуру поля как в других сущностях
                            field_info = {
                                'NAME': field_name,
                                'title': field_data.get('title', field_name),
                                'type': field_data.get('type', 'string'),
                                'formLabel': field_data.get('title', field_name)
                            }
                            
                            # Добавляем дополнительные поля если они есть
                            if 'default' in field_data:
                                field_info['default'] = field_data['default']
                            if 'required' in field_data:
                                field_info['required'] = field_data['required']
                            if 'values' in field_data:
                                field_info['values'] = field_data['values']
                                # Для enum полей создаем items массив
                                if field_data.get('type') == 'enum':
                                    field_info['type'] = 'enumeration'
                                    field_info['items'] = []
                                    values = field_data['values']
                                    
                                    # Обрабатываем как dict, так и list значения
                                    if isinstance(values, dict):
                                        for value_id, value_text in values.items():
                                            field_info['items'].append({
                                                'ID': value_id,
                                                'VALUE': value_text
                                            })
                                    elif isinstance(values, list):
                                        for i, value_text in enumerate(values):
                                            field_info['items'].append({
                                                'ID': str(i),
                                                'VALUE': value_text
                                            })
                            
                            fields.append(field_info)
        
        logger.info(f"Получено {len(fields)} полей для задач")
        return fields
        
    except Exception as e:
        logger.error(f"Ошибка при получении полей для задач: {e}")
        raise


async def get_task_by_id(task_id: int) -> dict:
    """Получает задачу по ID"""
    try:
        task = await bit.call('tasks.task.get', {'taskId': task_id})
        return task
    except Exception as e:
        logger.error(f"Ошибка при получении задачи {task_id}: {e}")
        raise


async def get_tasks_by_filter(filter_fields: dict={}, select_fields: list[str]=["*"], order: dict={'ID': 'DESC'}) -> list[dict]:
    """Получение задач по фильтру"""
    try:
        # Проверяем есть ли фильтр по STATUS (известная проблема API)
        status_filter = None
        other_filters = {}
        
        for key, value in filter_fields.items():
            if key.upper() == 'STATUS':
                status_filter = value
            else:
                other_filters[key] = value
        
        # Если есть фильтр по STATUS, получаем все задачи и фильтруем на клиенте
        if status_filter is not None:
            logger.info(f"Обнаружен фильтр по STATUS: {status_filter}, используем клиентскую фильтрацию")
            
            # Получаем все задачи с остальными фильтрами
            all_tasks = await get_tasks_by_filter(other_filters, select_fields, order)
            
            # Фильтруем по STATUS на клиенте
            filtered_tasks = []
            for task in all_tasks:
                task_status = task.get('status', task.get('STATUS'))
                if str(task_status) == str(status_filter):
                    filtered_tasks.append(task)
            
            logger.info(f"Клиентская фильтрация: найдено {len(filtered_tasks)} задач с STATUS={status_filter} из {len(all_tasks)} общих")
            return filtered_tasks
        
        # Для остальных фильтров используем get_all() без order
        try:
            params = {
                'filter': filter_fields, 
                'select': select_fields
            }
            
            result = await bit.get_all('tasks.task.list', params=params)
            
            # Обрабатываем результат
            if isinstance(result, dict):
                # Если get_all вернул словарь с ключом order000...
                if result.get('order0000000000'):
                    tasks = result['order0000000000']
                    if isinstance(tasks, dict) and 'tasks' in tasks:
                        tasks = tasks['tasks']
                # Если это структура с result -> tasks
                elif 'result' in result and 'tasks' in result['result']:
                    tasks = result['result']['tasks']
                # Если есть прямой ключ tasks
                elif 'tasks' in result:
                    tasks = result['tasks']
                # Если это единичная задача
                elif 'id' in result:
                    tasks = [result]  
                else:
                    tasks = []
            elif isinstance(result, list):
                tasks = result
            else:
                tasks = []
                
            # Убеждаемся что tasks всегда список
            if not isinstance(tasks, list):
                tasks = []
            
            # Применяем сортировку на клиенте
            if tasks and order:
                # Простая сортировка по ID
                if 'ID' in order:
                    reverse = order['ID'].upper() == 'DESC'
                    tasks = sorted(tasks, key=lambda x: int(x.get('id', x.get('ID', 0))), reverse=reverse)
            
            return tasks
            
        except Exception as get_all_error:
            logger.warning(f"get_all failed: {get_all_error}, переключаемся на call() метод")
            
            # Если get_all не сработал, используем call() с ручной пагинацией
            start = 0
            limit = 50
            all_tasks = []
            
            while True:
                params = {
                    'filter': filter_fields, 
                    'select': select_fields,
                    'order': order,
                    'start': start
                }
                
                # Добавляем limit для пагинации
                if start > 0:
                    params['limit'] = limit
                
                result = await bit.call('tasks.task.list', params)
                
                if isinstance(result, dict):
                    # Обрабатываем пакетный ответ с order0000000000
                    if 'result' in result and isinstance(result['result'], dict):
                        batch_result = result['result']
                        if 'order0000000000' in batch_result and isinstance(batch_result['order0000000000'], dict):
                            order_result = batch_result['order0000000000']
                            if 'tasks' in order_result:
                                tasks = order_result['tasks']
                            else:
                                tasks = []
                        else:
                            tasks = []
                    # Если это структура с result -> tasks
                    elif 'result' in result and 'tasks' in result['result']:
                        tasks = result['result']['tasks']
                    # Если есть прямой ключ tasks
                    elif 'tasks' in result:
                        tasks = result['tasks']
                    # Если это единичная задача
                    elif 'id' in result:
                        tasks = [result]
                        all_tasks.extend(tasks)
                        break
                    else:
                        tasks = []
                elif isinstance(result, list):
                    tasks = result
                else:
                    tasks = []
                
                if not tasks:
                    break
                    
                all_tasks.extend(tasks)
                
                # Проверяем, есть ли ещё данные
                if len(tasks) < limit:
                    break
                    
                start += limit
            
            return all_tasks
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка задач: {e}")
        raise


async def create_task(fields: dict) -> dict:
    """Создание новой задачи"""
    try:
        result = await bit.call('tasks.task.add', {'fields': fields})
        
        # Правильное извлечение ID задачи из ответа
        task_id = result.get('id')
        # pprint(result)
        
        logger.info(f"Создана задача с ID: {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при создании задачи: {e}")
        raise


async def update_task(task_id: int, fields: dict) -> dict:
    """Обновление задачи"""
    try:
        result = await bit.call('tasks.task.update', {'taskId': task_id, 'fields': fields})
        logger.info(f"Обновлена задача с ID: {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при обновлении задачи {task_id}: {e}")
        raise


async def delete_task(task_id: int) -> dict:
    """Удаление задачи"""
    try:
        result = await bit.call('tasks.task.delete', {'taskId': task_id})
        logger.info(f"Удалена задача с ID: {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при удалении задачи {task_id}: {e}")
        raise


# === КОММЕНТАРИИ К ЗАДАЧАМ ===

async def get_task_comments(task_id: int) -> list[dict]:
    """Получение комментариев к задаче"""
    try:
        # Fix: Use correct API method
        comments = await bit.get_all('task.commentitem.getlist', params={'TASKID': int(task_id)})
        return comments if isinstance(comments, list) else []
    except Exception as e:
        logger.error(f"Ошибка при получении комментариев для задачи {task_id}: {e}")
        raise


async def add_task_comment(task_id: int, fields: dict) -> dict:
    """Добавление комментария к задаче"""
    try:
        # Fix: Use correct API method
        items={'TASKID': int(task_id), 'FIELDS': fields}
        
        result = await bit.call('task.commentitem.add', items, raw=True)
        logger.info(f"Добавлен комментарий к задаче {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при добавлении комментария к задаче {task_id}: {e}")
        raise


async def update_task_comment(task_id: int, comment_id: int, fields: dict) -> dict:
    """Обновление комментария к задаче"""
    try:
        # Fix: Use correct API method
        result = await bit.call('task.commentitem.update', [int(task_id), int(comment_id), fields])
        logger.info(f"Обновлен комментарий {comment_id} к задаче {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при обновлении комментария {comment_id} к задаче {task_id}: {e}")
        raise


async def delete_task_comment(task_id: int, comment_id: int) -> dict:
    """Удаление комментария к задаче"""
    try:
        # Fix: Use correct API method
        result = await bit.call('task.commentitem.delete', [int(task_id), int(comment_id)])
        logger.info(f"Удален комментарий {comment_id} к задаче {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при удалении комментария {comment_id} к задаче {task_id}: {e}")
        raise


# === ЧЕКЛИСТЫ ЗАДАЧ ===

async def get_task_checklist(task_id: int) -> list[dict]:
    """Получение чеклиста задачи"""
    try:
        # Fix: Use correct API method
        checklist = await bit.get_all('task.checklistitem.list', params={'TASKID': int(task_id)})
        return checklist if isinstance(checklist, list) else []
    except Exception as e:
        logger.error(f"Ошибка при получении чеклиста для задачи {task_id}: {e}")
        raise


async def add_checklist_item(task_id: int, fields: dict) -> dict:
    """Добавление пункта в чеклист задачи"""
    try:
        # Fix: Use correct API method
        result = await bit.call('task.checklistitem.add', {'TASKID': int(task_id), 'FIELDS': fields})
        logger.info(f"Добавлен пункт в чеклист задачи {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при добавлении пункта в чеклист задачи {task_id}: {e}")
        raise


async def delete_checklist_item(task_id: int, item_id: int) -> dict:
    """Удаление пункта из чеклиста задачи"""
    try:
        # Fix: Use correct API method
        result = await bit.call('task.checklistitem.delete', [int(task_id), int(item_id)])
        logger.info(f"Удален пункт {item_id} из чеклиста задачи {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при удалении пункта {item_id} из чеклиста задачи {task_id}: {e}")
        raise


# === ЗАТРАЧЕННОЕ ВРЕМЯ ===

async def get_task_elapsed_time(task_id: int) -> list[dict]:
    """Получение записей затраченного времени по задаче"""
    try:
        # Fix: Use correct API method
        elapsed = await bit.get_all('task.elapseditem.list', params={'TASKID': int(task_id)})
        return elapsed if isinstance(elapsed, list) else []
    except Exception as e:
        logger.error(f"Ошибка при получении затраченного времени для задачи {task_id}: {e}")
        raise


async def add_elapsed_time(task_id: int, fields: dict) -> dict:
    """Добавление записи о затраченном времени"""
    try:
        # Fix: Use correct API method
        result = await bit.call('task.elapseditem.add', {'TASKID': int(task_id), 'FIELDS': fields})
        logger.info(f"Добавлена запись о времени для задачи {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при добавлении времени для задачи {task_id}: {e}")
        raise


async def delete_elapsed_time(task_id: int, item_id: int) -> dict:
    """Удаление записи о затраченном времени"""
    try:
        # Fix: Use correct API method
        result = await bit.call('task.elapseditem.delete', {'TASKID': int(task_id), 'ITEMID': int(item_id)})
        logger.info(f"Удалена запись {item_id} о времени для задачи {task_id}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при удалении записи {item_id} о времени для задачи {task_id}: {e}")
        raise


# === АКТИВНОСТИ CRM ===

async def get_crm_activities_by_filter(filter_fields: dict={}, select_fields: list[str]=["*"]) -> list[dict]:
    """Получение активностей CRM (звонки, встречи, email-письма) по фильтру с кэшированием"""
    try:
        # Генерируем ключ кэша
        cache_key = _generate_activity_cache_key(
            "crm_activities",
            filter_fields=filter_fields,
            select_fields=select_fields
        )
        
        # Проверяем кэш
        cached_activities = _load_from_cache(cache_key)
        if cached_activities is not None:
            return cached_activities
        
        # Выполняем запрос
        params = {
            'filter': filter_fields,
            'select': select_fields
        }
        
        activities = await bit.get_all('crm.activity.list', params=params)
        
        # Обрабатываем возможный словарь с ключом order0000000000
        if isinstance(activities, dict):
            if activities.get('order0000000000'):
                activities = activities['order0000000000']
        
        activities = activities if isinstance(activities, list) else []
        
        # Сохраняем в кэш
        _save_to_cache(cache_key, activities)
        
        return activities
    except Exception as e:
        logger.error(f"Ошибка при получении активностей CRM: {e}")
        raise


async def get_leads_by_filter(filter_fields: dict={}, select_fields: list[str]=["*", "UF_*"]) -> list[dict] | dict:
    """Получение лидов по фильтру"""
    try:
        leads = await bit.get_all('crm.lead.list', params={'filter': filter_fields, 'select': select_fields})
        if isinstance(leads, dict):
            if leads.get('order0000000000'):
                leads = leads['order0000000000']
        return leads
    except Exception as e:
        logger.error(f"Ошибка при получении лидов: {e}")
        raise


async def get_all_entity_comments(entity_type: str, author_id: int, from_date: str = None, date_filter: dict = None) -> list[dict]:
    """Получение всех комментариев пользователя в сущностях CRM (deal, lead, contact, company) с использованием батчей и кэширования"""
    try:
        logger.info(f"Получение комментариев {entity_type} для автора {author_id}")
        
        # Генерируем ключ кэша
        cache_key = _generate_activity_cache_key(
            f"comments_{entity_type}",
            author_id=author_id,
            from_date=from_date,
            date_filter=date_filter
        )
        
        # Проверяем кэш
        cached_comments = _load_from_cache(cache_key)
        if cached_comments is not None:
            logger.info(f"Использованы кэшированные комментарии {entity_type} для автора {author_id}")
            return cached_comments
        
        all_comments = []
        
        # Шаг 1: Получаем список сущностей нужного типа с фильтрацией по дате
        entity_list = []
        filter_params = date_filter.copy() if date_filter is not None else {}
        
        if entity_type == 'deal':
            entity_list = await get_deals_by_filter(filter_params, select_fields=['ID'])
        elif entity_type == 'lead':
            entity_list = await get_leads_by_filter(filter_params, select_fields=['ID'])
        elif entity_type == 'contact':
            entity_list = await get_contacts_by_filter(filter_params, select_fields=['ID'])
        elif entity_type == 'company':
            entity_list = await get_companies_by_filter(filter_params, select_fields=['ID'])
        else:
            logger.warning(f"Неподдерживаемый тип сущности: {entity_type}")
            return []
        
        # Нормализуем entity_list в список
        if isinstance(entity_list, dict):
            if entity_list.get('order0000000000'):
                entity_list = entity_list['order0000000000']
            else:
                entity_list = []
        
        if not isinstance(entity_list, list):
            entity_list = []
        
        logger.info(f"Найдено {len(entity_list)} {entity_type} для проверки")
        
        if not entity_list:
            return []
        
        # Шаг 2: Формируем список запросов для батчинга
        batch_requests = []
        for entity in entity_list:
            entity_id = entity.get('ID')
            if not entity_id:
                continue
            
            params = {
                'filter': {
                    'ENTITY_TYPE': entity_type,
                    'ENTITY_ID': entity_id
                }
            }
            batch_requests.append(params)
        
        # Шаг 3: Выполняем запросы батчами (fast-bitrix24 автоматически разобьет на батчи по 50)
        logger.info(f"Выполнение {len(batch_requests)} запросов комментариев через батчи")
        
        # Используем call() с массивом запросов для автоматического батчинга
        results = await bit.call('crm.timeline.comment.list', batch_requests, raw=True)
        
        # Обрабатываем результаты батчей
        if isinstance(results, list):
            # Если результаты пришли как список (каждый элемент - результат одного запроса)
            for result in results:
                if result and 'result' in result and isinstance(result['result'], list):
                    # Фильтруем по автору
                    entity_comments = [
                        c for c in result['result'] 
                        if str(c.get('AUTHOR_ID')) == str(author_id)
                    ]
                    
                    # Фильтруем по дате, если указана
                    if from_date:
                        entity_comments = [
                            c for c in entity_comments
                            if c.get('CREATED', '') >= from_date
                        ]
                    
                    all_comments.extend(entity_comments)
        elif isinstance(results, dict):
            # Если результат - словарь (один запрос)
            if 'result' in results and isinstance(results['result'], list):
                entity_comments = [
                    c for c in results['result'] 
                    if str(c.get('AUTHOR_ID')) == str(author_id)
                ]
                
                if from_date:
                    entity_comments = [
                        c for c in entity_comments
                        if c.get('CREATED', '') >= from_date
                    ]
                
                all_comments.extend(entity_comments)
        
        logger.info(f"Получено {len(all_comments)} комментариев {entity_type} от автора {author_id}")
        
        # Сохраняем в кэш
        _save_to_cache(cache_key, all_comments)
        
        return all_comments
        
    except Exception as e:
        logger.error(f"Ошибка при получении комментариев {entity_type} для автора {author_id}: {e}")
        raise


async def get_calendar_events(from_date: str, to_date: str, owner_id: int = None) -> list[dict]:
    """Получение событий календаря пользователя через секции с кэшированием"""
    try:
        logger.info(f"Получение событий календаря для пользователя {owner_id} с {from_date} по {to_date}")
        
        # Генерируем ключ кэша
        cache_key = _generate_activity_cache_key(
            "calendar_events",
            owner_id=owner_id,
            from_date=from_date,
            to_date=to_date
        )
        
        # Проверяем кэш
        cached_events = _load_from_cache(cache_key)
        if cached_events is not None:
            logger.info(f"Использованы кэшированные события календаря для пользователя {owner_id}")
            return cached_events
        
        all_events = []
        
        # Этап 1: Получение секций календаря
        sections_params = {
            'type': 'user',
            'ownerId': owner_id if owner_id else 1
        }
        sections_result = await bit.call('calendar.section.get', sections_params, raw=True)
        
        sections = []
        if sections_result and 'result' in sections_result:
            sections = sections_result['result'] if isinstance(sections_result['result'], list) else [sections_result['result']]
        
        logger.info(f"Найдено {len(sections)} секций календаря")
        
        # Этап 2: Получение событий для каждой секции
        for section in sections:
            section_id = section.get('ID')
            if not section_id:
                continue
            
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
        
        logger.info(f"Получено {len(all_events)} событий календаря")
        
        # Сохраняем в кэш
        _save_to_cache(cache_key, all_events)
        
        return all_events
        
    except Exception as e:
        logger.error(f"Ошибка при получении событий календаря: {e}")
        raise


async def get_manager_full_activity(manager_id: int, days: int = 30) -> dict:
    """Получение полной активности менеджера за указанный период с кэшированием"""
    try:
        logger.info(f"Получение активности менеджера {manager_id} за {days} дней")
        
        # Генерируем ключ кэша для полной активности
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        cache_key = _generate_activity_cache_key(
            "manager_full_activity",
            manager_id=manager_id,
            days=days,
            start_date=start_date,
            end_date=end_date
        )
        
        # Проверяем кэш
        cached_activity = _load_from_cache(cache_key)
        if cached_activity is not None:
            logger.info(f"Использована кэшированная активность менеджера {manager_id}")
            return cached_activity
        
        # Получение информации о менеджере
        managers = await get_users_by_filter({'ID': manager_id})
        manager = managers[0] if isinstance(managers, list) and len(managers) > 0 else (managers if isinstance(managers, dict) else {})
        manager_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip()
        
        # Установка периода анализа
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Получение активностей CRM
        date_filter = {
            '>=CREATED': f"{start_date}T00:00:00",
            '<=CREATED': f"{end_date}T23:59:59",
            'RESPONSIBLE_ID': manager_id
        }
        activities = await get_crm_activities_by_filter(date_filter)
        
        # Анализ типов активностей
        calls_total = 0
        calls_incoming = 0
        calls_outgoing = 0
        calls_missed = 0
        meetings = 0
        emails = 0
        
        for activity in activities:
            type_id = str(activity.get('TYPE_ID', ''))
            if type_id == '2':  # Звонки
                calls_total += 1
                direction = str(activity.get('DIRECTION', ''))
                if direction == '1':
                    calls_outgoing += 1
                elif direction == '2':
                    calls_incoming += 1
                elif direction == '0':
                    calls_missed += 1
            elif type_id == '1':  # Встречи
                meetings += 1
            elif type_id == '4':  # Email
                emails += 1
        
        # Получение задач с фильтрацией по ответственному и дате создания
        tasks_filter = {
            'RESPONSIBLE_ID': manager_id,
            '>=CREATED_DATE': f"{start_date}T00:00:00",
            '<=CREATED_DATE': f"{end_date}T23:59:59"
        }
        tasks = await get_tasks_by_filter(
            tasks_filter,
            select_fields=['ID', 'TITLE', 'STATUS', 'CREATED_DATE', 'CLOSED_DATE', 'RESPONSIBLE_ID']
        )
        
        # Дополнительная проверка на клиенте для убедительности, что задачи принадлежат менеджеру
        tasks = [
            t for t in tasks 
            if str(t.get('RESPONSIBLE_ID', t.get('responsibleId', ''))) == str(manager_id)
        ]
        
        logger.info(f"Получено {len(tasks)} задач для менеджера {manager_id} за период {start_date} - {end_date}")
        
        tasks_completed = len([t for t in tasks if str(t.get('STATUS', t.get('status', ''))) == '5'])
        tasks_in_progress = len([t for t in tasks if str(t.get('STATUS', t.get('status', ''))) in ['2', '3']])
        
        # Получение сделок
        deals_filter = {
            '>=DATE_CREATE': f"{start_date}T00:00:00",
            '<=DATE_CREATE': f"{end_date}T23:59:59",
            'ASSIGNED_BY_ID': manager_id
        }
        deals = await get_deals_by_filter(deals_filter, select_fields=['ID', 'TITLE', 'STAGE_ID', 'DATE_CREATE'])
        if isinstance(deals, dict):
            if deals.get('order0000000000'):
                deals = deals['order0000000000']
        deals = deals if isinstance(deals, list) else []
        deals_won = len([d for d in deals if 'WON' in str(d.get('STAGE_ID', '')).upper()])
        
        # Получение лидов
        leads_filter = {
            '>=DATE_CREATE': f"{start_date}T00:00:00",
            '<=DATE_CREATE': f"{end_date}T23:59:59",
            'ASSIGNED_BY_ID': manager_id
        }
        leads = await get_leads_by_filter(leads_filter, select_fields=['ID', 'TITLE', 'STATUS_ID', 'DATE_CREATE'])
        if isinstance(leads, dict):
            if leads.get('order0000000000'):
                leads = leads['order0000000000']
        leads = leads if isinstance(leads, list) else []
        leads_converted = len([l for l in leads if str(l.get('STATUS_ID', '')) == 'CONVERTED'])
        
        # Получение событий календаря
        calendar_events = await get_calendar_events(
            from_date=f"{start_date}T00:00:00",
            to_date=f"{end_date}T23:59:59",
            owner_id=manager_id
        )
        calendar_meetings = len([
            e for e in calendar_events 
            if e.get('CAL_TYPE') == 'user' or e.get('MEETING_STATUS') == 'Y'
        ])
        
        # Получение комментариев с фильтрацией по дате для оптимизации
        date_filter_for_comments = {
            '>=DATE_CREATE': f"{start_date}T00:00:00",
            '<=DATE_CREATE': f"{end_date}T23:59:59"
        }
        deal_comments = await get_all_entity_comments('deal', manager_id, from_date=None, date_filter=date_filter_for_comments)
        lead_comments = await get_all_entity_comments('lead', manager_id, from_date=None, date_filter=date_filter_for_comments)
        contact_comments = await get_all_entity_comments('contact', manager_id, from_date=None, date_filter=date_filter_for_comments)
        company_comments = await get_all_entity_comments('company', manager_id, from_date=None, date_filter=date_filter_for_comments)
        
        total_comments = len(deal_comments) + len(lead_comments) + len(contact_comments) + len(company_comments)
        
        # Формирование списка комментариев для сделок
        deal_comments_list = [
            {
                'entity_id': c.get('ENTITY_ID'),
                'text': c.get('COMMENT', ''),
                'created': c.get('CREATED', '')
            }
            for c in deal_comments
        ]
        
        # Подсчет общей активности
        total_activities = (
            calls_total + meetings + emails + 
            len(tasks) + len(deals) + len(leads) + 
            len(calendar_events) + total_comments
        )
        
        result = {
            'manager_id': manager_id,
            'name': manager_name,
            'email': manager.get('EMAIL', ''),
            'work_position': manager.get('WORK_POSITION', ''),
            'period': {
                'start_date': start_date,
                'end_date': end_date,
                'days': days
            },
            'calls': {
                'total': calls_total,
                'incoming': calls_incoming,
                'outgoing': calls_outgoing,
                'missed': calls_missed
            },
            'meetings': meetings,
            'emails': emails,
            'tasks': {
                'total': len(tasks),
                'completed': tasks_completed,
                'in_progress': tasks_in_progress
            },
            'deals': {
                'created': len(deals),
                'won': deals_won
            },
            'leads': {
                'created': len(leads),
                'converted': leads_converted
            },
            'calendar': {
                'total_events': len(calendar_events),
                'meetings': calendar_meetings
            },
            'comments': {
                'total': total_comments,
                'deals': len(deal_comments),
                'leads': len(lead_comments),
                'contacts': len(contact_comments),
                'companies': len(company_comments),
                # 'deal_comments_list': deal_comments_list
            },
            'total_activities': total_activities
        }
        
        logger.info(f"Активность менеджера {manager_id} собрана: {total_activities} активностей")
        
        # Сохраняем в кэш
        _save_to_cache(cache_key, result)
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при получении активности менеджера {manager_id}: {e}")
        raise


async def get_all_managers_activity(days: int = 30, include_inactive: bool = True, only_inactive: bool = False) -> dict:
    """Получение активности всех менеджеров за указанный период с определением неактивных пользователей
    
    Оптимизированная версия: получает все сущности за период один раз, затем группирует по менеджерам на клиенте
    
    Args:
        days: Количество дней для анализа
        include_inactive: Включать ли информацию о неактивных менеджерах в результат
        only_inactive: Если True, возвращает только список неактивных менеджеров без детальной статистики активных
    """
    try:
        logger.info(f"Получение активности всех менеджеров за {days} дней (оптимизированная версия)")
        
        # Генерируем ключ кэша
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        cache_key = _generate_activity_cache_key(
            "all_managers_activity",
            days=days,
            start_date=start_date,
            end_date=end_date,
            include_inactive=include_inactive,
            only_inactive=only_inactive
        )
        
        # Проверяем кэш
        cached_result = _load_from_cache(cache_key)
        if cached_result is not None:
            logger.info(f"Использована кэшированная активность всех менеджеров")
            return cached_result
        
        # Получаем список всех пользователей
        all_users = await get_users_by_filter({})
        
        # Нормализуем список пользователей
        if isinstance(all_users, dict):
            if all_users.get('order0000000000'):
                all_users = all_users['order0000000000']
            else:
                all_users = []
        
        if not isinstance(all_users, list):
            all_users = []
        
        logger.info(f"Найдено {len(all_users)} пользователей для анализа активности")
        
        # Шаг 1: Получаем все сущности за период один раз (оптимизация)
        logger.info("Получение всех сущностей за период для группировки по менеджерам")
        
        # Получаем все сделки за период
        deals_filter = {
            '>=DATE_CREATE': f"{start_date}T00:00:00",
            '<=DATE_CREATE': f"{end_date}T23:59:59"
        }
        all_deals = await get_deals_by_filter(deals_filter, select_fields=['ID', 'TITLE', 'STAGE_ID', 'DATE_CREATE', 'ASSIGNED_BY_ID'])
        if isinstance(all_deals, dict):
            if all_deals.get('order0000000000'):
                all_deals = all_deals['order0000000000']
        all_deals = all_deals if isinstance(all_deals, list) else []
        
        # Получаем все лиды за период
        leads_filter = {
            '>=DATE_CREATE': f"{start_date}T00:00:00",
            '<=DATE_CREATE': f"{end_date}T23:59:59"
        }
        all_leads = await get_leads_by_filter(leads_filter, select_fields=['ID', 'TITLE', 'STATUS_ID', 'DATE_CREATE', 'ASSIGNED_BY_ID'])
        if isinstance(all_leads, dict):
            if all_leads.get('order0000000000'):
                all_leads = all_leads['order0000000000']
        all_leads = all_leads if isinstance(all_leads, list) else []
        
        # Получаем все задачи за период
        tasks_filter = {
            '>=CREATED_DATE': f"{start_date}T00:00:00",
            '<=CREATED_DATE': f"{end_date}T23:59:59"
        }
        all_tasks = await get_tasks_by_filter(
            tasks_filter,
            select_fields=['ID', 'TITLE', 'STATUS', 'CREATED_DATE', 'CLOSED_DATE', 'RESPONSIBLE_ID']
        )
        
        # Получаем все активности CRM за период
        activities_filter = {
            '>=CREATED': f"{start_date}T00:00:00",
            '<=CREATED': f"{end_date}T23:59:59"
        }
        all_activities = await get_crm_activities_by_filter(activities_filter)
        
        logger.info(f"Получено: {len(all_deals)} сделок, {len(all_leads)} лидов, {len(all_tasks)} задач, {len(all_activities)} активностей CRM")
        
        # Шаг 2: Группируем сущности по менеджерам
        managers_data = {}
        for user in all_users:
            user_id = user.get('ID')
            if not user_id:
                continue
            managers_data[str(user_id)] = {
                'user': user,
                'deals': [],
                'leads': [],
                'tasks': [],
                'activities': []
            }
        
        # Группируем сделки по менеджерам
        for deal in all_deals:
            assigned_by_id = str(deal.get('ASSIGNED_BY_ID', ''))
            if assigned_by_id in managers_data:
                managers_data[assigned_by_id]['deals'].append(deal)
        
        # Группируем лиды по менеджерам
        for lead in all_leads:
            assigned_by_id = str(lead.get('ASSIGNED_BY_ID', ''))
            if assigned_by_id in managers_data:
                managers_data[assigned_by_id]['leads'].append(lead)
        
        # Группируем задачи по менеджерам
        for task in all_tasks:
            responsible_id = str(task.get('RESPONSIBLE_ID', task.get('responsibleId', '')))
            if responsible_id in managers_data:
                managers_data[responsible_id]['tasks'].append(task)
        
        # Группируем активности CRM по менеджерам
        for activity in all_activities:
            responsible_id = str(activity.get('RESPONSIBLE_ID', ''))
            if responsible_id in managers_data:
                managers_data[responsible_id]['activities'].append(activity)
        
        # Шаг 3: Формируем активность для каждого менеджера
        managers_activity = []
        inactive_managers = []
        total_calls = 0
        total_meetings = 0
        total_emails = 0
        total_tasks = 0
        total_deals = 0
        total_leads = 0
        total_comments = 0
        
        for user_id_str, manager_data in managers_data.items():
            user_id = int(user_id_str)
            user = manager_data['user']
            deals = manager_data['deals']
            leads = manager_data['leads']
            tasks = manager_data['tasks']
            activities = manager_data['activities']
            
            try:
                # Получаем информацию о менеджере
                manager_name = f"{user.get('NAME', '')} {user.get('LAST_NAME', '')}".strip()
                
                # Анализ активностей CRM
                calls_total = 0
                calls_incoming = 0
                calls_outgoing = 0
                calls_missed = 0
                meetings = 0
                emails = 0
                
                for activity in activities:
                    type_id = str(activity.get('TYPE_ID', ''))
                    if type_id == '2':  # Звонки
                        calls_total += 1
                        direction = str(activity.get('DIRECTION', ''))
                        if direction == '1':
                            calls_outgoing += 1
                        elif direction == '2':
                            calls_incoming += 1
                        elif direction == '0':
                            calls_missed += 1
                    elif type_id == '1':  # Встречи
                        meetings += 1
                    elif type_id == '4':  # Email
                        emails += 1
                
                # Анализ задач
                tasks_completed = len([t for t in tasks if str(t.get('STATUS', t.get('status', ''))) == '5'])
                tasks_in_progress = len([t for t in tasks if str(t.get('STATUS', t.get('status', ''))) in ['2', '3']])
                
                # Анализ сделок
                deals_won = len([d for d in deals if 'WON' in str(d.get('STAGE_ID', '')).upper()])
                
                # Анализ лидов
                leads_converted = len([l for l in leads if str(l.get('STATUS_ID', '')) == 'CONVERTED'])
                
                # Подсчет общей активности без комментариев и календаря (для быстрой проверки)
                total_activities_count_basic = (
                    calls_total + meetings + emails + 
                    len(tasks) + len(deals) + len(leads)
                )
                
                # Если only_inactive=True и есть базовая активность, пропускаем детальную обработку
                if only_inactive and total_activities_count_basic > 0:
                    # Менеджер активен, пропускаем его
                    continue
                
                # Получаем события календаря и комментарии (эти запросы остаются индивидуальными, так как требуют специфичных параметров)
                calendar_events = await get_calendar_events(
                    from_date=f"{start_date}T00:00:00",
                    to_date=f"{end_date}T23:59:59",
                    owner_id=user_id
                )
                calendar_meetings = len([
                    e for e in calendar_events 
                    if e.get('CAL_TYPE') == 'user' or e.get('MEETING_STATUS') == 'Y'
                ])
                
                # Получаем комментарии
                date_filter_for_comments = {
                    '>=DATE_CREATE': f"{start_date}T00:00:00",
                    '<=DATE_CREATE': f"{end_date}T23:59:59"
                }
                deal_comments = await get_all_entity_comments('deal', user_id, from_date=None, date_filter=date_filter_for_comments)
                lead_comments = await get_all_entity_comments('lead', user_id, from_date=None, date_filter=date_filter_for_comments)
                contact_comments = await get_all_entity_comments('contact', user_id, from_date=None, date_filter=date_filter_for_comments)
                company_comments = await get_all_entity_comments('company', user_id, from_date=None, date_filter=date_filter_for_comments)
                
                total_comments_count = len(deal_comments) + len(lead_comments) + len(contact_comments) + len(company_comments)
                
                # Подсчет общей активности
                total_activities_count = (
                    calls_total + meetings + emails + 
                    len(tasks) + len(deals) + len(leads) + 
                    len(calendar_events) + total_comments_count
                )
                
                if total_activities_count == 0:
                    # Менеджер без активности
                    inactive_managers.append({
                        'manager_id': user_id,
                        'name': manager_name,
                        'email': user.get('EMAIL', ''),
                        'work_position': user.get('WORK_POSITION', '')
                    })
                else:
                    # Формируем активность менеджера
                    activity_data = {
                        'manager_id': user_id,
                        'name': manager_name,
                        'email': user.get('EMAIL', ''),
                        'work_position': user.get('WORK_POSITION', ''),
                        'period': {
                            'start_date': start_date,
                            'end_date': end_date,
                            'days': days
                        },
                        'calls': {
                            'total': calls_total,
                            'incoming': calls_incoming,
                            'outgoing': calls_outgoing,
                            'missed': calls_missed
                        },
                        'meetings': meetings,
                        'emails': emails,
                        'tasks': {
                            'total': len(tasks),
                            'completed': tasks_completed,
                            'in_progress': tasks_in_progress
                        },
                        'deals': {
                            'created': len(deals),
                            'won': deals_won
                        },
                        'leads': {
                            'created': len(leads),
                            'converted': leads_converted
                        },
                        'calendar': {
                            'total_events': len(calendar_events),
                            'meetings': calendar_meetings
                        },
                        'comments': {
                            'total': total_comments_count,
                            'deals': len(deal_comments),
                            'leads': len(lead_comments),
                            'contacts': len(contact_comments),
                            'companies': len(company_comments)
                        },
                        'total_activities': total_activities_count
                    }
                    
                    managers_activity.append(activity_data)
                    
                    # Суммируем статистику
                    total_calls += calls_total
                    total_meetings += meetings
                    total_emails += emails
                    total_tasks += len(tasks)
                    total_deals += len(deals)
                    total_leads += len(leads)
                    total_comments += total_comments_count
                
            except Exception as e:
                logger.warning(f"Ошибка при обработке активности менеджера {user_id}: {e}")
                # Добавляем в список неактивных при ошибке
                inactive_managers.append({
                    'manager_id': user_id,
                    'name': f"{user.get('NAME', '')} {user.get('LAST_NAME', '')}".strip(),
                    'email': user.get('EMAIL', ''),
                    'work_position': user.get('WORK_POSITION', ''),
                    'error': str(e)
                })
        
        # Формируем результат
        if only_inactive:
            # Возвращаем только неактивных менеджеров
            result = {
                'period': {
                    'start_date': start_date,
                    'end_date': end_date,
                    'days': days
                },
                'summary': {
                    'total_managers': len(all_users),
                    'active_managers': len(managers_activity),
                    'inactive_managers': len(inactive_managers)
                },
                'inactive_managers': inactive_managers if include_inactive else []
            }
            logger.info(f"Возвращен список неактивных менеджеров: {len(inactive_managers)} неактивных из {len(all_users)} всего")
        else:
            # Возвращаем полную статистику
            result = {
                'period': {
                    'start_date': start_date,
                    'end_date': end_date,
                    'days': days
                },
                'summary': {
                    'total_managers': len(all_users),
                    'active_managers': len(managers_activity),
                    'inactive_managers': len(inactive_managers),
                    'total_calls': total_calls,
                    'total_meetings': total_meetings,
                    'total_emails': total_emails,
                    'total_tasks': total_tasks,
                    'total_deals': total_deals,
                    'total_leads': total_leads,
                    'total_comments': total_comments
                },
                'managers_activity': managers_activity,
                'inactive_managers': inactive_managers if include_inactive else []
            }
            logger.info(f"Активность всех менеджеров собрана: {len(managers_activity)} активных, {len(inactive_managers)} неактивных")
        
        # Сохраняем в кэш
        _save_to_cache(cache_key, result)
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при получении активности всех менеджеров: {e}")
        raise


if __name__ == "__main__":
    # a=asyncio.run(get_fields_by_user())
    # pprint(a)
    # a=asyncio.run(get_fields_by_company())
    # pprint(a)

    # a=asyncio.run(get_fields_by_deal())
    # pprint(a)
    
    # Тест функций задач
    # b={'POST_MESSAGE': 'message',
    # 'AUTHOR_ID': 1}
    # a=asyncio.run(add_task_comment(13, b))
    # a=asyncio.run(get_manager_full_activity(9, 30))
    # a=asyncio.run(get_all_managers_activity(30, only_inactive=True))
    # a=asyncio.run(get_all_deal_stages_by_categories())
    a=asyncio.run(get_stage_history(2, filter_fields={'>=CREATED_TIME': '2025-11-01T00:00:00', '<=CREATED_TIME': '2025-11-12T23:59:59'}))
    pprint(a)


