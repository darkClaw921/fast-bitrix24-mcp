from mcp.server.fastmcp import FastMCP, Context
from dotenv import load_dotenv
load_dotenv()
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Union
import asyncio
from loguru import logger

from .bitrixWork import (
    bit, 
    get_contacts_by_filter, 
    get_companies_by_filter,
    get_crm_activities_by_filter,
    get_tasks_by_filter,
    get_deals_by_filter
)
from .deal import _get_all_deals_activity_batch

mcp = FastMCP("inactive_clients")

BATCH_SIZE = 50
DELAY_BETWEEN_BATCHES = 0.5  # секунды задержки между батчами


def _parse_datetime_from_bitrix(dt_str: str) -> datetime:
    """Парсинг даты/времени из формата Bitrix24"""
    try:
        if 'T' in dt_str:
            if dt_str.endswith('Z'):
                dt_str = dt_str[:-1] + '+00:00'
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        else:
            return datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    except Exception as e:
        return datetime.now(timezone.utc)


async def _get_client_activity_batch(
    contact_ids: list[int] = None,
    company_ids: list[int] = None,
    days: int = 30,
    include_comments: bool = True,
    include_contacts: bool = False,
    include_companies: bool = True
) -> dict:
    """Получение активности для всех клиентов батчами (оптимизированная версия)
    
    Args:
        contact_ids: Список ID контактов
        company_ids: Список ID компаний
        days: Количество дней для проверки активности (по умолчанию 30)
        include_comments: Получать комментарии для всех клиентов (по умолчанию True)
        include_contacts: Включить контакты в проверку (по умолчанию False)
        include_companies: Включить компании в проверку (по умолчанию True)
    
    Returns:
        Словарь {client_id: activity_info}, где client_id имеет формат 'C_{contact_id}' или 'CO_{company_id}',
        а activity_info имеет структуру:
        {
            'has_activity': bool,
            'last_activity_date': datetime | None,
            'activities': {
                'calls': int,
                'emails': int,
                'meetings': int,
                'comments': int,
                'tasks': int,
                'deals': int
            }
        }
    """
    if not contact_ids:
        contact_ids = []
    if not company_ids:
        company_ids = []
    
    if not contact_ids and not company_ids:
        return {}
    
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    from_date_iso = f"{from_date}T00:00:00"
    
    # Инициализируем результат для всех клиентов
    result = {}
    
    # Контакты
    for contact_id in contact_ids:
        client_key = f"C_{contact_id}"
        result[client_key] = {
            'has_activity': False,
            'last_activity_date': None,
            'activities': {
                'calls': 0,
                'emails': 0,
                'meetings': 0,
                'comments': 0,
                'tasks': 0,
                'deals': 0
            }
        }
    
    # Компании
    for company_id in company_ids:
        client_key = f"CO_{company_id}"
        result[client_key] = {
            'has_activity': False,
            'last_activity_date': None,
            'activities': {
                'calls': 0,
                'emails': 0,
                'meetings': 0,
                'comments': 0,
                'tasks': 0,
                'deals': 0
            }
        }
    
    try:
        # Шаг 1: Получаем все активности CRM для контактов и компаний
        all_activities = []
        
        if include_contacts and contact_ids:
            logger.info(f"Получение активностей CRM для {len(contact_ids)} контактов (период: с {from_date_iso})")
            contacts_activities_filter = {
                'ENTITY_TYPE': 'CONTACT',
                '>=CREATED': from_date_iso
            }
            contacts_activities = await get_crm_activities_by_filter(
                contacts_activities_filter,
                select_fields=['ID', 'TYPE_ID', 'CREATED', 'ENTITY_ID', 'OWNER_ID', 'OWNER_TYPE_ID']
            )
            if isinstance(contacts_activities, list):
                all_activities.extend(contacts_activities)
        
        if include_companies and company_ids:
            logger.info(f"Получение активностей CRM для {len(company_ids)} компаний (период: с {from_date_iso})")
            companies_activities_filter = {
                'ENTITY_TYPE': 'COMPANY',
                '>=CREATED': from_date_iso
            }
            companies_activities = await get_crm_activities_by_filter(
                companies_activities_filter,
                select_fields=['ID', 'TYPE_ID', 'CREATED', 'ENTITY_ID', 'OWNER_ID', 'OWNER_TYPE_ID']
            )
            if isinstance(companies_activities, list):
                all_activities.extend(companies_activities)
        
        logger.info(f"Получено активностей CRM: {len(all_activities)}")
        
        # Группируем активности по клиентам
        # Разделяем активности на контакты и компании по фильтру, который использовался при запросе
        contacts_activities_list = []
        companies_activities_list = []
        
        # Разделяем активности по типу сущности
        for activity in all_activities:
            entity_type = activity.get('ENTITY_TYPE', '')
            if entity_type == 'CONTACT':
                contacts_activities_list.append(activity)
            elif entity_type == 'COMPANY':
                companies_activities_list.append(activity)
        
        # Обрабатываем активности контактов
        for activity in contacts_activities_list:
            entity_id = activity.get('ENTITY_ID')
            if entity_id:
                try:
                    entity_id_int = int(entity_id)
                    if entity_id_int in contact_ids:
                        client_key = f"C_{entity_id_int}"
                        
                        if client_key in result:
                            type_id = str(activity.get('TYPE_ID', ''))
                            
                            # Подсчитываем звонки (TYPE_ID = '2')
                            if type_id == '2':
                                result[client_key]['activities']['calls'] += 1
                            
                            # Подсчитываем письма (TYPE_ID = '4')
                            if type_id == '4':
                                result[client_key]['activities']['emails'] += 1
                            
                            # Подсчитываем встречи (TYPE_ID = '1')
                            if type_id == '1':
                                result[client_key]['activities']['meetings'] += 1
                            
                            # Обновляем последнюю активность
                            created_str = activity.get('CREATED', '')
                            if created_str:
                                try:
                                    activity_date = _parse_datetime_from_bitrix(created_str)
                                    if result[client_key]['last_activity_date'] is None or activity_date > result[client_key]['last_activity_date']:
                                        result[client_key]['last_activity_date'] = activity_date
                                except Exception:
                                    pass
                except (ValueError, TypeError):
                    pass
        
        # Обрабатываем активности компаний
        for activity in companies_activities_list:
            entity_id = activity.get('ENTITY_ID')
            if entity_id:
                try:
                    entity_id_int = int(entity_id)
                    if entity_id_int in company_ids:
                        client_key = f"CO_{entity_id_int}"
                        
                        if client_key in result:
                            type_id = str(activity.get('TYPE_ID', ''))
                            
                            # Подсчитываем звонки (TYPE_ID = '2')
                            if type_id == '2':
                                result[client_key]['activities']['calls'] += 1
                            
                            # Подсчитываем письма (TYPE_ID = '4')
                            if type_id == '4':
                                result[client_key]['activities']['emails'] += 1
                            
                            # Подсчитываем встречи (TYPE_ID = '1')
                            if type_id == '1':
                                result[client_key]['activities']['meetings'] += 1
                            
                            # Обновляем последнюю активность
                            created_str = activity.get('CREATED', '')
                            if created_str:
                                try:
                                    activity_date = _parse_datetime_from_bitrix(created_str)
                                    if result[client_key]['last_activity_date'] is None or activity_date > result[client_key]['last_activity_date']:
                                        result[client_key]['last_activity_date'] = activity_date
                                except Exception:
                                    pass
                except (ValueError, TypeError):
                    pass
        
        # Шаг 2: Получаем комментарии батчами (если включено)
        if include_comments:
            semaphore = asyncio.Semaphore(BATCH_SIZE)
            
            async def get_comments_for_client(entity_type: str, entity_id: int) -> tuple[str, list]:
                """Получает комментарии для одного клиента"""
                async with semaphore:
                    try:
                        comments_params = {
                            'filter': {
                                'ENTITY_TYPE': entity_type,
                                'ENTITY_ID': entity_id
                            }
                        }
                        comments_result = await bit.call('crm.timeline.comment.list', comments_params, raw=True)
                        
                        comments = []
                        if isinstance(comments_result, dict):
                            if 'result' in comments_result and isinstance(comments_result['result'], list):
                                comments = comments_result['result']
                            elif 'error' in comments_result:
                                logger.warning(f"Ошибка при получении комментариев для {entity_type} {entity_id}: {comments_result.get('error')}")
                        elif isinstance(comments_result, list):
                            comments = comments_result
                        
                        client_key = f"C_{entity_id}" if entity_type == 'CONTACT' else f"CO_{entity_id}"
                        return client_key, comments
                    except Exception as e:
                        logger.warning(f"Ошибка при получении комментариев для {entity_type} {entity_id}: {e}")
                        client_key = f"C_{entity_id}" if entity_type == 'CONTACT' else f"CO_{entity_id}"
                        return client_key, []
            
            # Обрабатываем контакты батчами
            all_comments_results = []
            if contact_ids:
                total_batches = (len(contact_ids) + BATCH_SIZE - 1) // BATCH_SIZE
                for batch_idx in range(0, len(contact_ids), BATCH_SIZE):
                    batch_contact_ids = contact_ids[batch_idx:batch_idx + BATCH_SIZE]
                    batch_num = (batch_idx // BATCH_SIZE) + 1
                    
                    logger.info(f"Обработка батча комментариев контактов {batch_num}/{total_batches}")
                    
                    comments_tasks = [get_comments_for_client('CONTACT', cid) for cid in batch_contact_ids]
                    batch_results = await asyncio.gather(*comments_tasks)
                    all_comments_results.extend(batch_results)
                    
                    if batch_idx + BATCH_SIZE < len(contact_ids):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)
            
            # Обрабатываем компании батчами
            if include_companies and company_ids:
                total_batches = (len(company_ids) + BATCH_SIZE - 1) // BATCH_SIZE
                for batch_idx in range(0, len(company_ids), BATCH_SIZE):
                    batch_company_ids = company_ids[batch_idx:batch_idx + BATCH_SIZE]
                    batch_num = (batch_idx // BATCH_SIZE) + 1
                    
                    logger.info(f"Обработка батча комментариев компаний {batch_num}/{total_batches}")
                    
                    comments_tasks = [get_comments_for_client('COMPANY', cid) for cid in batch_company_ids]
                    batch_results = await asyncio.gather(*comments_tasks)
                    all_comments_results.extend(batch_results)
                    
                    if batch_idx + BATCH_SIZE < len(company_ids):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)
            
            # Обрабатываем результаты комментариев
            for client_key, comments in all_comments_results:
                if client_key not in result:
                    continue
                
                recent_comments = [
                    c for c in comments
                    if c.get('CREATED', '') >= from_date_iso
                ]
                result[client_key]['activities']['comments'] = len(recent_comments)
                
                # Обновляем последнюю активность
                for comment in recent_comments:
                    created_str = comment.get('CREATED', '')
                    if created_str:
                        try:
                            comment_date = _parse_datetime_from_bitrix(created_str)
                            if result[client_key]['last_activity_date'] is None or comment_date > result[client_key]['last_activity_date']:
                                result[client_key]['last_activity_date'] = comment_date
                        except Exception:
                            pass
        
        # Шаг 3: Получаем задачи за период
        logger.info(f"Получение задач за период для клиентов")
        tasks_filter = {
            '>=CREATED_DATE': from_date_iso
        }
        all_tasks = await get_tasks_by_filter(
            tasks_filter,
            select_fields=['ID', 'TITLE', 'CREATED_DATE', 'UF_CRM_TASK']
        )
        
        if not isinstance(all_tasks, list):
            all_tasks = []
        
        # Группируем задачи по клиентам
        for task in all_tasks:
            uf_crm_task = task.get('UF_CRM_TASK') or task.get('ufCrmTask')
            if uf_crm_task:
                # Проверяем контакты (формат "C_123")
                for contact_id in contact_ids:
                    contact_prefix = f"C_{contact_id}"
                    task_matched = False
                    
                    if isinstance(uf_crm_task, list):
                        if any(str(item).startswith(contact_prefix) for item in uf_crm_task):
                            task_matched = True
                    elif isinstance(uf_crm_task, str) and uf_crm_task.startswith(contact_prefix):
                        task_matched = True
                    
                    if task_matched:
                        client_key = f"C_{contact_id}"
                        if client_key in result:
                            result[client_key]['activities']['tasks'] += 1
                            
                            created_str = task.get('CREATED_DATE') or task.get('createdDate')
                            if created_str:
                                try:
                                    task_date = _parse_datetime_from_bitrix(created_str)
                                    if result[client_key]['last_activity_date'] is None or task_date > result[client_key]['last_activity_date']:
                                        result[client_key]['last_activity_date'] = task_date
                                except Exception:
                                    pass
                            break
                
                # Проверяем компании (формат "CO_123")
                if include_companies:
                    for company_id in company_ids:
                        company_prefix = f"CO_{company_id}"
                        task_matched = False
                        
                        if isinstance(uf_crm_task, list):
                            if any(str(item).startswith(company_prefix) for item in uf_crm_task):
                                task_matched = True
                        elif isinstance(uf_crm_task, str) and uf_crm_task.startswith(company_prefix):
                            task_matched = True
                        
                        if task_matched:
                            client_key = f"CO_{company_id}"
                            if client_key in result:
                                result[client_key]['activities']['tasks'] += 1
                                
                                created_str = task.get('CREATED_DATE') or task.get('createdDate')
                                if created_str:
                                    try:
                                        task_date = _parse_datetime_from_bitrix(created_str)
                                        if result[client_key]['last_activity_date'] is None or task_date > result[client_key]['last_activity_date']:
                                            result[client_key]['last_activity_date'] = task_date
                                    except Exception:
                                        pass
                                break
        
        # Шаг 4: Получаем сделки за период (для контактов и подсчета новых сделок компаний)
        logger.info(f"Получение сделок за период для клиентов")
        deals_filter = {
            '>=DATE_CREATE': from_date_iso
        }
        all_deals = await get_deals_by_filter(
            deals_filter,
            select_fields=['ID', 'CONTACT_ID', 'COMPANY_ID', 'DATE_CREATE']
        )
        
        if not isinstance(all_deals, list):
            if isinstance(all_deals, dict) and all_deals.get('order0000000000'):
                all_deals = all_deals['order0000000000']
            else:
                all_deals = []
        
        # Группируем сделки по клиентам
        for deal in all_deals:
            contact_id = deal.get('CONTACT_ID')
            company_id = deal.get('COMPANY_ID')
            
            # Приоритет компании над контактом
            if include_companies and company_id:
                try:
                    company_id_int = int(company_id)
                    if company_id_int in company_ids:
                        client_key = f"CO_{company_id_int}"
                        if client_key in result:
                            result[client_key]['activities']['deals'] += 1
                            
                            created_str = deal.get('DATE_CREATE')
                            if created_str:
                                try:
                                    deal_date = _parse_datetime_from_bitrix(created_str)
                                    if result[client_key]['last_activity_date'] is None or deal_date > result[client_key]['last_activity_date']:
                                        result[client_key]['last_activity_date'] = deal_date
                                except Exception:
                                    pass
                except (ValueError, TypeError):
                    pass
            elif include_contacts and contact_id:
                try:
                    contact_id_int = int(contact_id)
                    if contact_id_int in contact_ids:
                        client_key = f"C_{contact_id_int}"
                        if client_key in result:
                            result[client_key]['activities']['deals'] += 1
                            
                            created_str = deal.get('DATE_CREATE')
                            if created_str:
                                try:
                                    deal_date = _parse_datetime_from_bitrix(created_str)
                                    if result[client_key]['last_activity_date'] is None or deal_date > result[client_key]['last_activity_date']:
                                        result[client_key]['last_activity_date'] = deal_date
                                except Exception:
                                    pass
                except (ValueError, TypeError):
                    pass
        
        # Шаг 5: Получаем ВСЕ сделки компаний (без фильтра по дате) для проверки активности
        # Активность может быть в старой сделке по компании
        company_deals_map = {}  # {company_id: [deal_ids]}
        
        if include_companies and company_ids:
            logger.info(f"Получение всех сделок компаний (без фильтра по дате) для проверки активности")
            # Получаем все сделки компаний без фильтра по дате
            all_company_deals_filter = {}
            # Можно добавить фильтр только по COMPANY_ID, но Bitrix24 не поддерживает фильтр по списку ID
            # Поэтому получаем все сделки и фильтруем на клиенте
            all_company_deals = await get_deals_by_filter(
                all_company_deals_filter,
                select_fields=['ID', 'COMPANY_ID']
            )
            
            if not isinstance(all_company_deals, list):
                if isinstance(all_company_deals, dict) and all_company_deals.get('order0000000000'):
                    all_company_deals = all_company_deals['order0000000000']
                else:
                    all_company_deals = []
            
            # Фильтруем сделки по компаниям на клиенте
            company_ids_set = set(company_ids)
            for deal in all_company_deals:
                company_id = deal.get('COMPANY_ID')
                deal_id = deal.get('ID')
                
                if company_id:
                    try:
                        company_id_int = int(company_id)
                        if company_id_int in company_ids_set:
                            if company_id_int not in company_deals_map:
                                company_deals_map[company_id_int] = []
                            if deal_id:
                                try:
                                    company_deals_map[company_id_int].append(int(deal_id))
                                except (ValueError, TypeError):
                                    pass
                    except (ValueError, TypeError):
                        pass
        
        # Шаг 6: Получаем активность по сделкам компаний (звонки и задачи)
        if include_companies and company_deals_map:
            # Собираем все уникальные ID сделок компаний
            all_company_deal_ids = []
            for deal_ids_list in company_deals_map.values():
                all_company_deal_ids.extend(deal_ids_list)
            
            if all_company_deal_ids:
                # Убираем дубликаты
                all_company_deal_ids = list(set(all_company_deal_ids))
                
                logger.info(f"Получение активности по сделкам компаний: {len(all_company_deal_ids)} сделок")
                deals_activity = await _get_all_deals_activity_batch(
                    deal_ids=all_company_deal_ids,
                    days=days,
                    include_comments=False  # Комментарии уже учтены выше
                )
                
                # Добавляем активность из сделок к активности компаний
                for company_id_int, deal_ids_list in company_deals_map.items():
                    client_key = f"CO_{company_id_int}"
                    if client_key not in result:
                        continue
                    
                    # Суммируем звонки и задачи из всех сделок компании
                    total_calls_from_deals = 0
                    total_tasks_from_deals = 0
                    max_deal_activity_date = None
                    
                    for deal_id in deal_ids_list:
                        deal_activity = deals_activity.get(deal_id)
                        if deal_activity:
                            # Добавляем звонки из сделки
                            calls_count = deal_activity.get('activities', {}).get('calls', 0)
                            total_calls_from_deals += calls_count
                            
                            # Добавляем задачи из сделки
                            tasks_count = deal_activity.get('activities', {}).get('tasks', 0)
                            total_tasks_from_deals += tasks_count
                            
                            # Обновляем последнюю дату активности
                            deal_last_activity = deal_activity.get('last_activity_date')
                            if deal_last_activity:
                                if max_deal_activity_date is None or deal_last_activity > max_deal_activity_date:
                                    max_deal_activity_date = deal_last_activity
                    
                    # Добавляем к активности компании
                    result[client_key]['activities']['calls'] += total_calls_from_deals
                    result[client_key]['activities']['tasks'] += total_tasks_from_deals
                    
                    # Обновляем последнюю дату активности компании
                    if max_deal_activity_date:
                        if result[client_key]['last_activity_date'] is None or max_deal_activity_date > result[client_key]['last_activity_date']:
                            result[client_key]['last_activity_date'] = max_deal_activity_date
                    
                    logger.debug(
                        f"Компания {company_id_int}: добавлено {total_calls_from_deals} звонков "
                        f"и {total_tasks_from_deals} задач из {len(deal_ids_list)} сделок"
                    )
        
        # Вычисляем has_activity для каждого клиента
        for client_key in result:
            total_activities = sum(result[client_key]['activities'].values())
            result[client_key]['has_activity'] = total_activities > 0
        
        logger.info(f"Получена активность для {len(result)} клиентов батчами")
        
    except Exception as e:
        logger.error(f"Ошибка при получении активности для клиентов батчами: {e}")
    
    return result


@mcp.tool()
async def get_clients_without_activity(
    category_filter: dict[str, str] = {"UF_CRM_1659553251682": "775"},
    days: int = 30,
    isText: bool = True,
    include_comments: bool = False,
    include_contacts: bool = False,
    include_companies: bool = True
) -> dict | str:
    """Получение клиентов категории A без активности за указанный период
    
    Проверяется отсутствие взаимодействий с клиентом более указанного количества дней:
    - Звонки
    - Задачи
    - Сделки
    - Комментарии
    - Письма
    
    Args:
        category_filter: Фильтр для поиска клиентов по категории (пользовательское поле).
                         Пример: {"UF_CRM_CATEGORY": "A"} для контактов или компаний.
                         Если не указан, проверяются все клиенты.
        days: Количество дней без активности (по умолчанию 30)
        isText: Если True, возвращает человекочитаемый текст; если False (по умолчанию), возвращает структурированный словарь
        include_comments: Получать комментарии для всех клиентов (по умолчанию True). Если False, комментарии пропускаются для ускорения работы
        include_contacts: Включить контакты в проверку (по умолчанию True)
        include_companies: Включить компании в проверку (по умолчанию True). Если оба параметра True, возвращается общий список
    
    Returns:
        Если isText=False — словарь с данными клиентов без активности:
        {
            'period': {'days': 30},
            'category_filter': {...},
            'clients_without_activity': [
                {
                    'client_type': 'contact' | 'company',
                    'client_id': int,
                    'client_name': str,
                    'last_activity_date': str | None,
                    'activities': {...}
                }
            ],
            'summary': {
                'total_checked': int,
                'without_activity': int
            }
        }
        Если isText=True — человекочитаемый текст с форматированным списком клиентов
    """
    try:
        if category_filter is None:
            category_filter = {}
        
        # Получаем контакты с фильтром по категории (если включены)
        contacts = []
        if include_contacts:
            logger.info(f"Получение контактов с фильтром: {category_filter}")
            contacts = await get_contacts_by_filter(
                filter_fields=category_filter,
                select_fields=['ID', 'NAME', 'LAST_NAME', 'SECOND_NAME']
            )
            
            if not isinstance(contacts, list):
                if isinstance(contacts, dict) and contacts.get('order0000000000'):
                    contacts = contacts['order0000000000']
                else:
                    contacts = []
        
        # Получаем компании с фильтром по категории (если включены)
        companies = []
        if include_companies:
            logger.info(f"Получение компаний с фильтром: {category_filter}")
            companies = await get_companies_by_filter(
                filter_fields=category_filter,
                select_fields=['ID', 'TITLE']
            )
            
            if not isinstance(companies, list):
                if isinstance(companies, dict) and companies.get('order0000000000'):
                    companies = companies['order0000000000']
                else:
                    companies = []
        
        if not contacts and not companies:
            if isText:
                return f"Клиенты с указанным фильтром категории не найдены."
            return {
                'period': {'days': days},
                'category_filter': category_filter,
                'clients_without_activity': [],
                'summary': {
                    'total_checked': 0,
                    'without_activity': 0
                }
            }
        
        # Получаем ID всех клиентов
        contact_ids = []
        contact_id_to_data = {}
        for contact in contacts:
            contact_id = contact.get('ID')
            if contact_id:
                try:
                    contact_id_int = int(contact_id)
                    contact_ids.append(contact_id_int)
                    # Формируем имя контакта
                    name_parts = [
                        contact.get('NAME', ''),
                        contact.get('LAST_NAME', ''),
                        contact.get('SECOND_NAME', '')
                    ]
                    contact_name = ' '.join([p for p in name_parts if p]).strip() or f'Контакт #{contact_id}'
                    contact_id_to_data[contact_id_int] = {
                        'id': contact_id_int,
                        'name': contact_name,
                        'type': 'contact'
                    }
                except (ValueError, TypeError):
                    pass
        
        company_ids = []
        company_id_to_data = {}
        for company in companies:
            company_id = company.get('ID')
            if company_id:
                try:
                    company_id_int = int(company_id)
                    company_ids.append(company_id_int)
                    company_name = company.get('TITLE', f'Компания #{company_id}')
                    company_id_to_data[company_id_int] = {
                        'id': company_id_int,
                        'name': company_name,
                        'type': 'company'
                    }
                except (ValueError, TypeError):
                    pass
        
        # Получаем активность для всех клиентов батчами
        logger.info(f"Получение активности для {len(contact_ids)} контактов и {len(company_ids)} компаний батчами (включая комментарии: {include_comments})")
        all_activities = await _get_client_activity_batch(
            contact_ids=contact_ids if include_contacts else [],
            company_ids=company_ids if include_companies else [],
            days=days,
            include_comments=include_comments,
            include_contacts=include_contacts,
            include_companies=include_companies
        )
        
        # Находим клиентов без активности
        clients_without_activity = []
        
        # Обрабатываем контакты (если включены)
        if include_contacts:
            for contact_id_int, contact_data in contact_id_to_data.items():
                client_key = f"C_{contact_id_int}"
                activity_info = all_activities.get(client_key, {
                    'has_activity': False,
                    'last_activity_date': None,
                    'activities': {'calls': 0, 'emails': 0, 'meetings': 0, 'comments': 0, 'tasks': 0, 'deals': 0}
                })
                
                if not activity_info['has_activity']:
                    clients_without_activity.append({
                        'client_type': 'contact',
                        'client_id': contact_id_int,
                        'client_name': contact_data['name'],
                        'last_activity_date': activity_info['last_activity_date'].isoformat() if activity_info['last_activity_date'] else None,
                        'activities': activity_info['activities']
                    })
        
        # Обрабатываем компании (если включены)
        if include_companies:
            for company_id_int, company_data in company_id_to_data.items():
                client_key = f"CO_{company_id_int}"
                activity_info = all_activities.get(client_key, {
                    'has_activity': False,
                    'last_activity_date': None,
                    'activities': {'calls': 0, 'emails': 0, 'meetings': 0, 'comments': 0, 'tasks': 0, 'deals': 0}
                })
                
                if not activity_info['has_activity']:
                    clients_without_activity.append({
                        'client_type': 'company',
                        'client_id': company_id_int,
                        'client_name': company_data['name'],
                        'last_activity_date': activity_info['last_activity_date'].isoformat() if activity_info['last_activity_date'] else None,
                        'activities': activity_info['activities']
                    })
        
        total_checked = len(contact_ids) + len(company_ids)
        
        # Формируем результат
        if isText:
            if not clients_without_activity:
                return f"Клиентов без активности за последние {days} дней не найдено. Проверено клиентов: {total_checked}."
            
            result_text = f"=== Клиенты без активности за последние {days} дней ===\n\n"
            result_text += f"Всего проверено клиентов: {total_checked}\n"
            result_text += f"Клиентов без активности: {len(clients_without_activity)}\n\n"
            
            for idx, client_info in enumerate(clients_without_activity, 1):
                client_type_ru = "Контакт" if client_info['client_type'] == 'contact' else "Компания"
                result_text += f"{idx}. {client_info['client_name']} ({client_type_ru}, ID: {client_info['client_id']})\n"
                
                activities = client_info.get('activities', {})
                result_text += f"   Активность за последние {days} дней:\n"
                result_text += f"     • Звонки: {activities.get('calls', 0)}\n"
                result_text += f"     • Письма: {activities.get('emails', 0)}\n"
                result_text += f"     • Встречи: {activities.get('meetings', 0)}\n"
                result_text += f"     • Комментарии: {activities.get('comments', 0)}\n"
                result_text += f"     • Задачи: {activities.get('tasks', 0)}\n"
                result_text += f"     • Сделки: {activities.get('deals', 0)}\n"
                
                if client_info.get('last_activity_date'):
                    result_text += f"   Последняя активность: {client_info['last_activity_date']}\n"
                
                result_text += "\n"
            
            return result_text
        else:
            return {
                'period': {'days': days},
                'category_filter': category_filter,
                'clients_without_activity': clients_without_activity,
                'summary': {
                    'total_checked': total_checked,
                    'without_activity': len(clients_without_activity)
                }
            }
        
    except Exception as e:
        logger.error(f"Ошибка при получении клиентов без активности: {e}")
        if isText:
            return f"Ошибка при получении клиентов без активности: {str(e)}"
        return {
            'error': str(e),
            'period': {'days': days},
            'category_filter': category_filter or {},
            'clients_without_activity': [],
            'summary': {
                'total_checked': 0,
                'without_activity': 0
            }
        }

