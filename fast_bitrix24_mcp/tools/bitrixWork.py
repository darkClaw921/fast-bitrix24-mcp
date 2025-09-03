from fast_bitrix24 import Bitrix
import os
from dotenv import load_dotenv
from pprint import pprint
from datetime import datetime, timedelta
from loguru import logger
import asyncio
import traceback
load_dotenv()
webhook = os.getenv('WEBHOOK')
if webhook:
    bit = Bitrix(webhook, ssl=False, verbose=False)
else:
    raise ValueError("WEBHOOK environment variable is required")

logger.add("logs/workBitrix_{time}.log",format="{time:YYYY-MM-DD HH:mm}:{level}:{file}:{line}:{message} ", rotation="100 MB", retention="10 days", level="DEBUG")


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
    pprint(fields)
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

async def get_deals_by_filter(filter_fields: dict, select_fields: list[str]) -> list[dict] | dict:
    """
    Получает сделку по фильтру
    """
    deal = await bit.get_all('crm.deal.list', params={'filter': filter_fields, 'select': select_fields})
    pprint(deal)
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
        pprint(items)
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


if __name__ == "__main__":
    # a=asyncio.run(get_fields_by_user())
    # pprint(a)
    # a=asyncio.run(get_fields_by_company())
    # pprint(a)

    # a=asyncio.run(get_fields_by_deal())
    # pprint(a)
    
    # Тест функций задач
    b={'POST_MESSAGE': 'message',
    'AUTHOR_ID': 1}
    # a=asyncio.run(add_task_comment(13, b))
    a=asyncio.run(get_fields_by_task())
    pprint(a)


