from mcp.server.fastmcp import FastMCP, Context
from dotenv import load_dotenv
load_dotenv()
import os
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Union
import asyncio
from pprint import pprint
from pathlib import Path
# from userfields import get_all_info_fields
# from bitrixWork import bit, get_deals_by_filter
from .userfields import get_all_info_fields
from .bitrixWork import bit, get_deals_by_filter, get_deal_stages, get_deal_categories, get_all_deal_stages_by_categories, get_stage_history, get_crm_activities_by_filter, get_tasks_by_filter

from .helper import prepare_fields_to_humman_format
from loguru import logger
# bitrix=Bitrix(WEBHOOK)
WEBHOOK=os.getenv("WEBHOOK")
# class Deal(_Deal):
#     pass
# Deal.get_manager(bitrix)
BATCH_SIZE = 50
DELAY_BETWEEN_BATCHES = 0.5  # секунды задержки между батчами
mcp = FastMCP("bitrix24")




@mcp.tool()
async def list_deal(filter_fields: dict[str,str]={}, fields_id: list[str]=["ID", "TITLE"]) -> dict:
    """Список сделок 
    filter_fields: dict[str, str] поля для фильтрации сделок 
    example:
    {
        "TITLE": "test"
        ">=DATE_CREATE": "2025-06-09"
        "<CLOSEDATE": "2025-06-11"
    }
    fields_id: list[str] id всех полей которые нужно получить (в том числе и из фильтра), если * то все поля
    example (если нужно получить все поля):
    [
        "*",
        "UF_*"
    ]
    """

    all_info_fields=await get_all_info_fields(['deal'], isText=False)
    all_info_fields=all_info_fields['deal']
    # pprint(all_info_fields)
    # 1/0
    prepare_deals=[]
    if '*' not in fields_id:     
        fields_id.append('ID')
        fields_id.append('TITLE')

    text=f'Список сделок по фильтру {filter_fields}:\n'
    deals = await get_deals_by_filter(filter_fields, fields_id)
    # print("================")
    # pprint(deals)
    # 1/0
    if '*' in fields_id:
        for deal in deals:
            prepare_deals.append(deal)
    else:
        for deal in deals:
            prepare_deal={}
            for field in fields_id:
                if field in deal:
                    prepare_deal[field] = deal[field]
                else:
                    prepare_deal[field] = None
            prepare_deals.append(prepare_deal)

    # pprint(prepare_deals)
    # 1/0
    for deal in prepare_deals:
        
        text+=f'=={deal["TITLE"]}==\n'
        # pprint(deal)
        prepare_deal=await prepare_fields_to_humman_format(deal, all_info_fields)
        for key, value in prepare_deal.items():
            text+=f'  {key}: {value}\n'
        text+='\n'
    return text


@mcp.tool()
async def get_stages(entity_id: str = "DEAL_STAGE") -> dict:
    """Получение стадий в человекочитаемом виде, сгруппированных по воронкам
    
    Args:
        entity_id: Тип сущности (по умолчанию DEAL_STAGE для стадий сделок)
                   Возможные значения: DEAL_STAGE, LEAD_STATUS, QUOTE_STATUS и т.д.
    
    Returns:
        Словарь в формате:
        {
            "category_id": {
                "name": "Название воронки",
                "stages": {"STATUS_ID": "название стадии"}
            }
        }
        Для стадий без воронки используется ключ "0" или "None"
    """
    # Если это стадии сделок, получаем стадии из всех воронок
    if entity_id == "DEAL_STAGE":
        stages = await get_all_deal_stages_by_categories(entity_id)
    else:
        stages = await get_deal_stages(entity_id)
    
    # Если это стадии сделок, получаем воронки и группируем
    if entity_id == "DEAL_STAGE":
        categories = await get_deal_categories()
        
        # Создаем словарь воронок для быстрого поиска
        categories_dict = {}
        for category in categories:
            cat_id = str(category.get('ID', ''))
            cat_name = category.get('NAME', 'Без названия')
            categories_dict[cat_id] = cat_name
        
        # Добавляем общую воронку (стадии без категории)
        categories_dict['0'] = 'Общая воронка'
        categories_dict['None'] = 'Общая воронка'
        
        # Группируем стадии по воронкам
        result = {}
        for stage in stages:
            category_id = stage.get('CATEGORY_ID')
            if category_id is None:
                category_id = '0'
            else:
                category_id = str(category_id)
            
            if category_id not in result:
                category_name = categories_dict.get(category_id, f'Воронка {category_id}')
                result[category_id] = {
                    'name': category_name,
                    'stages': {}
                }
            
            status_id = stage.get('STATUS_ID', '')
            name = stage.get('NAME', '')
            if status_id:
                result[category_id]['stages'][status_id] = name
    else:
        # Для других типов сущностей просто возвращаем плоский словарь
        result = {'0': {'name': 'Все стадии', 'stages': {}}}
        for stage in stages:
            status_id = stage.get('STATUS_ID', '')
            name = stage.get('NAME', '')
            if status_id:
                result['0']['stages'][status_id] = name
    
    return result


def _format_timedelta(delta: timedelta) -> str:
    """Форматирование timedelta в человекочитаемый вид"""
    total_seconds = int(delta.total_seconds())
    
    if total_seconds < 60:
        return f"{total_seconds} сек"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes} мин {seconds} сек"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours} ч {minutes} мин"
    else:
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 86400) % 3600 // 60
        if hours == 0:
            return f"{days} дн {minutes} мин"
        return f"{days} дн {hours} ч {minutes} мин"


def _parse_datetime_from_bitrix(dt_str: str) -> datetime:
    """Парсинг даты/времени из формата Bitrix24"""
    # Bitrix24 возвращает даты в формате YYYY-MM-DD HH:MM:SS или ISO-8601
    try:
        if 'T' in dt_str:
            # ISO-8601 формат
            if dt_str.endswith('Z'):
                dt_str = dt_str[:-1] + '+00:00'
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        else:
            # Формат YYYY-MM-DD HH:MM:SS
            return datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    except Exception as e:
        # Если не удалось распарсить, возвращаем текущее время
        return datetime.now(timezone.utc)


@mcp.tool()
async def get_stage_history_human(entity_type_id: int, owner_id: int = None, from_date: str = None, to_date: str = None) -> str:
    """Получение истории движения по стадиям в человекочитаемом виде с расчетом времени нахождения в каждой стадии
    
    Args:
        entity_type_id: Тип сущности (1 - лид, 2 - сделка, 5 - счет старый, 31 - счет новый)
        owner_id: ID объекта (сделки, лида и т.д.). Если не указан, возвращается агрегированная статистика по всем объектам данного типа
        from_date: Начальная дата диапазона в формате YYYY-MM-DD или YYYY-MM-DDTHH:MM:SS. Если не указана, фильтрация по началу не применяется
        to_date: Конечная дата диапазона в формате YYYY-MM-DD или YYYY-MM-DDTHH:MM:SS. Если не указана, фильтрация по концу не применяется
    
    Returns:
        Текстовая строка с историей стадий в человекочитаемом виде:
        - Если owner_id указан: детальная история для конкретного объекта
        - Если owner_id не указан: агрегированная статистика - среднее время нахождения в каждой стадии
    """
    # Формируем фильтры по датам
    filter_fields = {}
    
    if from_date:
        # Если указана только дата без времени, добавляем начало дня
        if 'T' not in from_date and len(from_date) == 10:
            from_date = f"{from_date}T00:00:00"
        filter_fields['>=CREATED_TIME'] = from_date
    
    if to_date:
        # Если указана только дата без времени, добавляем конец дня
        if 'T' not in to_date and len(to_date) == 10:
            to_date = f"{to_date}T23:59:59"
        filter_fields['<=CREATED_TIME'] = to_date
    
    # Получаем историю стадий
    history = await get_stage_history(entity_type_id=entity_type_id, owner_id=owner_id, filter_fields=filter_fields if filter_fields else None)
    
    if not history:
        entity_names = {1: "лид", 2: "сделка", 5: "счет (старый)", 31: "счет (новый)"}
        entity_name = entity_names.get(entity_type_id, f"сущность типа {entity_type_id}")
        if owner_id:
            return f"История стадий для {entity_name} с ID {owner_id} не найдена."
        else:
            return f"История стадий для {entity_name} не найдена."
    
    # Определяем тип сущности для получения названий стадий
    entity_id_map = {
        1: "LEAD_STATUS",  # лид
        2: "DEAL_STAGE",  # сделка
        5: "QUOTE_STATUS",  # счет старый
        31: "INVOICE_STATUS"  # счет новый
    }
    entity_id = entity_id_map.get(entity_type_id, "DEAL_STAGE")
    
    # Получаем названия стадий
    stages_info = await get_stages(entity_id)
    
    # Создаем словарь для быстрого поиска названий стадий
    stages_dict = {}
    for category_data in stages_info.values():
        stages_dict.update(category_data.get('stages', {}))
    
    entity_names = {1: "лид", 2: "сделка", 5: "счет (старый)", 31: "счет (новый)"}
    entity_name = entity_names.get(entity_type_id, f"сущность типа {entity_type_id}")
    
    # Если owner_id указан - показываем детальную историю для конкретного объекта
    if owner_id:
        # Группируем историю по объектам (OWNER_ID)
        history_by_owner = {}
        for record in history:
            owner = record.get('OWNER_ID')
            if owner not in history_by_owner:
                history_by_owner[owner] = []
            history_by_owner[owner].append(record)
        
        # Сортируем записи по времени для каждого объекта
        for owner in history_by_owner:
            history_by_owner[owner].sort(key=lambda x: _parse_datetime_from_bitrix(x.get('CREATED_TIME', '')))
        
        # Формируем результат
        result_text = ""
        
        for owner_id_item, records in history_by_owner.items():
            result_text += f"\n=== История стадий для {entity_name} ID: {owner_id_item} ===\n\n"
            
            # Добавляем информацию о диапазоне дат, если он указан
            if from_date or to_date:
                date_range_info = "Период: "
                if from_date:
                    date_range_info += f"с {from_date}"
                if to_date:
                    if from_date:
                        date_range_info += f" по {to_date}"
                    else:
                        date_range_info += f"до {to_date}"
                result_text += f"{date_range_info}\n\n"
            
            if len(records) == 1:
                # Только одна запись - элемент только создан
                record = records[0]
                created_time = _parse_datetime_from_bitrix(record.get('CREATED_TIME', ''))
                stage_id = record.get('STAGE_ID') or record.get('STATUS_ID', 'Неизвестно')
                stage_name = stages_dict.get(stage_id, stage_id)
                result_text += f"Создан: {created_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                result_text += f"Текущая стадия: {stage_name} ({stage_id})\n"
                result_text += f"Время на текущей стадии: рассчитывается от момента создания\n"
            else:
                # Несколько записей - есть история переходов
                total_time = timedelta(0)
                
                for i, record in enumerate(records):
                    created_time = _parse_datetime_from_bitrix(record.get('CREATED_TIME', ''))
                    stage_id = record.get('STAGE_ID') or record.get('STATUS_ID', 'Неизвестно')
                    stage_name = stages_dict.get(stage_id, stage_id)
                    type_id = record.get('TYPE_ID', 0)
                    
                    # Определяем тип события
                    type_names = {
                        1: "Создание",
                        2: "Переход на промежуточную стадию",
                        3: "Переход на финальную стадию",
                        5: "Смена воронки"
                    }
                    type_name = type_names.get(type_id, f"Событие типа {type_id}")
                    
                    # Вычисляем время нахождения в стадии
                    if i < len(records) - 1:
                        # Есть следующая запись - вычисляем разницу
                        next_time = _parse_datetime_from_bitrix(records[i + 1].get('CREATED_TIME', ''))
                        time_in_stage = next_time - created_time
                        total_time += time_in_stage
                        time_str = _format_timedelta(time_in_stage)
                    else:
                        # Последняя запись - текущая стадия
                        now = datetime.now(timezone.utc)
                        time_in_stage = now - created_time
                        total_time += time_in_stage
                        time_str = _format_timedelta(time_in_stage) + " (текущая стадия)"
                    
                    result_text += f"{i + 1}. {type_name}\n"
                    result_text += f"   Стадия: {stage_name} ({stage_id})\n"
                    result_text += f"   Дата/время: {created_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    result_text += f"   Время на стадии: {time_str}\n\n"
                
                result_text += f"Общее время в стадиях: {_format_timedelta(total_time)}\n"
        
        return result_text
    
    # Если owner_id не указан - показываем агрегированную статистику по всем сущностям
    # Группируем историю по объектам (OWNER_ID)
    history_by_owner = {}
    for record in history:
        owner = record.get('OWNER_ID')
        if owner not in history_by_owner:
            history_by_owner[owner] = []
        history_by_owner[owner].append(record)
    
    # Сортируем записи по времени для каждого объекта
    for owner in history_by_owner:
        history_by_owner[owner].sort(key=lambda x: _parse_datetime_from_bitrix(x.get('CREATED_TIME', '')))
    
    # Собираем статистику по стадиям: для каждой стадии собираем все периоды нахождения
    stage_times = {}  # {stage_id: [timedelta1, timedelta2, ...]}
    
    for owner_id_item, records in history_by_owner.items():
        for i, record in enumerate(records):
            created_time = _parse_datetime_from_bitrix(record.get('CREATED_TIME', ''))
            stage_id = record.get('STAGE_ID') or record.get('STATUS_ID', 'Неизвестно')
            
            if stage_id not in stage_times:
                stage_times[stage_id] = []
            
            # Вычисляем время нахождения в стадии
            if i < len(records) - 1:
                # Есть следующая запись - вычисляем разницу
                next_time = _parse_datetime_from_bitrix(records[i + 1].get('CREATED_TIME', ''))
                time_in_stage = next_time - created_time
                stage_times[stage_id].append(time_in_stage)
            else:
                # Последняя запись - текущая стадия (исключаем из статистики, так как время еще не завершено)
                # Можно включить, но это будет искажать среднее значение
                pass
    
    # Формируем результат с агрегированной статистикой
    result_text = f"=== Статистика по стадиям для {entity_name} ===\n\n"
    
    # Добавляем информацию о диапазоне дат, если он указан
    if from_date or to_date:
        date_range_info = "Период: "
        if from_date:
            date_range_info += f"с {from_date}"
        if to_date:
            if from_date:
                date_range_info += f" по {to_date}"
            else:
                date_range_info += f"до {to_date}"
        result_text += f"{date_range_info}\n\n"
    
    result_text += f"Всего сущностей: {len(history_by_owner)}\n\n"
    
    if not stage_times:
        result_text += "Недостаточно данных для расчета статистики (все сущности находятся в текущей стадии).\n"
        return result_text
    
    # Сортируем стадии по среднему времени (от большего к меньшему)
    stage_stats = []
    for stage_id, times in stage_times.items():
        if times:
            total_time = sum(times, timedelta(0))
            avg_time = total_time / len(times)
            stage_name = stages_dict.get(stage_id, stage_id)
            stage_stats.append({
                'stage_id': stage_id,
                'stage_name': stage_name,
                'avg_time': avg_time,
                'count': len(times),
                'total_time': total_time
            })
    
    stage_stats.sort(key=lambda x: x['avg_time'], reverse=True)
    
    result_text += "Среднее время нахождения в стадиях:\n\n"
    for stat in stage_stats:
        result_text += f"• {stat['stage_name']} ({stat['stage_id']})\n"
        result_text += f"  Среднее время: {_format_timedelta(stat['avg_time'])}\n"
        result_text += f"  Количество переходов: {stat['count']}\n"
        result_text += f"  Общее время: {_format_timedelta(stat['total_time'])}\n\n"
    
    return result_text


def _count_workdays(start_date: datetime, end_date: datetime) -> int:
    """Подсчет рабочих дней между двумя датами (исключая субботу и воскресенье)"""
    if start_date > end_date:
        return 0
    
    workdays = 0
    current_date = start_date.date()
    end_date_only = end_date.date()
    
    while current_date <= end_date_only:
        # Понедельник = 0, Воскресенье = 6
        weekday = current_date.weekday()
        if weekday < 5:  # Понедельник-Пятница
            workdays += 1
        current_date += timedelta(days=1)
    
    return workdays


async def _get_deal_activity(deal_id: int, days: int = 3) -> dict:
    """Получение активности по сделке за указанный период (звонки, комментарии, задачи)
    
    Args:
        deal_id: ID сделки
        days: Количество дней для проверки активности (по умолчанию 3)
    
    Returns:
        Словарь с информацией об активности:
        {
            'has_activity': bool,
            'last_activity_date': datetime | None,
            'activities': {
                'calls': int,
                'comments': int,
                'tasks': int
            }
        }
    """
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    from_date_iso = f"{from_date}T00:00:00"
    
    activities_count = {
        'calls': 0,
        'comments': 0,
        'tasks': 0
    }
    
    last_activity_date = None
    
    try:
        # Получаем активности CRM (звонки, встречи, email) по сделке
        activities_filter = {
            'ENTITY_TYPE': 'DEAL',
            'ENTITY_ID': deal_id,
            '>=CREATED': from_date_iso
        }
        activities = await get_crm_activities_by_filter(activities_filter, select_fields=['ID', 'TYPE_ID', 'CREATED'])
        
        # Подсчитываем звонки (TYPE_ID = '2')
        calls = [a for a in activities if str(a.get('TYPE_ID', '')) == '2']
        activities_count['calls'] = len(calls)
        
        # Находим последнюю активность
        for activity in activities:
            created_str = activity.get('CREATED', '')
            if created_str:
                try:
                    activity_date = _parse_datetime_from_bitrix(created_str)
                    if last_activity_date is None or activity_date > last_activity_date:
                        last_activity_date = activity_date
                except Exception:
                    pass
        
        # Получаем комментарии по сделке
        try:
            comments_params = {
                'filter': {
                    'ENTITY_TYPE': 'DEAL',
                    'ENTITY_ID': deal_id
                }
            }
            comments_result = await bit.call('crm.timeline.comment.list', comments_params, raw=True)
            
            if comments_result and 'result' in comments_result:
                comments = comments_result['result'] if isinstance(comments_result['result'], list) else []
                # Фильтруем по дате
                recent_comments = [
                    c for c in comments
                    if c.get('CREATED', '') >= from_date_iso
                ]
                activities_count['comments'] = len(recent_comments)
                
                # Обновляем последнюю активность
                for comment in recent_comments:
                    created_str = comment.get('CREATED', '')
                    if created_str:
                        try:
                            comment_date = _parse_datetime_from_bitrix(created_str)
                            if last_activity_date is None or comment_date > last_activity_date:
                                last_activity_date = comment_date
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Ошибка при получении комментариев для сделки {deal_id}: {e}")
        
        # Получаем задачи, связанные со сделкой
        try:
            # Задачи связаны через поле UF_CRM_TASK в формате ["D_10"] где D_ - Deal, 10 - ID сделки
            tasks_filter = {
                '>=CREATED_DATE': from_date_iso
            }
            tasks = await get_tasks_by_filter(
                tasks_filter,
                select_fields=['ID', 'TITLE', 'CREATED_DATE', 'UF_CRM_TASK']
            )
            
            # Фильтруем задачи, связанные с нашей сделкой
            deal_tasks = []
            deal_prefix = f"D_{deal_id}"
            for task in tasks:
                uf_crm_task = task.get('UF_CRM_TASK') or task.get('ufCrmTask')
                if uf_crm_task:
                    if isinstance(uf_crm_task, list):
                        if any(str(item).startswith(deal_prefix) for item in uf_crm_task):
                            deal_tasks.append(task)
                    elif isinstance(uf_crm_task, str) and uf_crm_task.startswith(deal_prefix):
                        deal_tasks.append(task)
            
            activities_count['tasks'] = len(deal_tasks)
            
            # Обновляем последнюю активность
            for task in deal_tasks:
                created_str = task.get('CREATED_DATE') or task.get('createdDate')
                if created_str:
                    try:
                        task_date = _parse_datetime_from_bitrix(created_str)
                        if last_activity_date is None or task_date > last_activity_date:
                            last_activity_date = task_date
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Ошибка при получении задач для сделки {deal_id}: {e}")
        
    except Exception as e:
        logger.error(f"Ошибка при получении активности для сделки {deal_id}: {e}")
    
    total_activities = activities_count['calls'] + activities_count['comments'] + activities_count['tasks']
    has_activity = total_activities > 0
    
    return {
        'has_activity': has_activity,
        'last_activity_date': last_activity_date,
        'activities': activities_count
    }


async def _get_all_deals_activity_batch(deal_ids: list[int | str], days: int = 3, include_comments: bool = True) -> dict[int, dict]:
    """Получение активности для всех сделок батчами (оптимизированная версия)
    
    Получает активность для всех сделок одним набором запросов вместо последовательных вызовов.
    Это значительно ускоряет работу при большом количестве сделок.
    
    Args:
        deal_ids: Список ID сделок
        days: Количество дней для проверки активности (по умолчанию 3)
        include_comments: Получать комментарии для всех сделок (по умолчанию True). Если False, комментарии пропускаются для ускорения работы
    
    Returns:
        Словарь {deal_id: activity_info}, где activity_info имеет структуру:
        {
            'has_activity': bool,
            'last_activity_date': datetime | None,
            'activities': {
                'deals': int,      # Все дела (активности) в таймлайне: встречи, звонки, письма, действия и т.д.
                'calls': int,       # Звонки (TYPE_ID = 2)
                'comments': int,    # Комментарии
                'tasks': int        # Задачи
            }
        }
    """
    if not deal_ids:
        return {}
    
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    from_date_iso = f"{from_date}T00:00:00"
    
    # Нормализуем deal_ids (приводим к int для сравнения)
    deal_ids_normalized = [int(did) for did in deal_ids]
    deal_ids_set = set(deal_ids_normalized)
    
    # Инициализируем результат для всех сделок
    result = {}
    for deal_id in deal_ids_normalized:
        result[deal_id] = {
            'has_activity': False,
            'last_activity_date': None,
            'activities': {
                'deals': 0,  # Все дела (активности) в таймлайне: встречи, звонки, письма, действия и т.д.
                'calls': 0,  # Звонки (TYPE_ID = 2)
                'comments': 0,
                'tasks': 0
            }
        }
    
    try:
        # Шаг 1: Получаем все активности CRM для всех сделок одним запросом
        # Bitrix24 поддерживает фильтр по нескольким ENTITY_ID через оператор @
        # Но лучше использовать фильтр по дате и затем группировать на клиенте
        logger.info(
            f"Получение активностей CRM для {len(deal_ids_normalized)} сделок "
            f"(период: с {from_date_iso}, сделки: {deal_ids_normalized[:5]}{'...' if len(deal_ids_normalized) > 5 else ''})"
        )
        activities_filter = {
            'ENTITY_TYPE': 'DEAL',
            '>=CREATED': from_date_iso
        }
        all_activities = await get_crm_activities_by_filter(
            activities_filter, 
            select_fields=['ID', 'TYPE_ID', 'CREATED', 'ENTITY_ID', 'OWNER_ID', 'OWNER_TYPE_ID', 'PROVIDER_ID', 'PROVIDER_TYPE_ID']
        )
        
        # Нормализуем all_activities в список
        if not isinstance(all_activities, list):
            all_activities = []
        
        logger.info(f"Получено активностей CRM: {len(all_activities)}")
        
        # Группируем активности по сделкам
        # Активности могут быть связаны со сделкой через:
        # 1. OWNER_ID (при OWNER_TYPE_ID='2' - сделка) - основной способ
        # 2. ENTITY_ID (как fallback)
        deal_activities = {}
        activities_without_link = 0
        activities_not_in_deals = 0
        
        for activity in all_activities:
            deal_id_int = None
            
            # Сначала проверяем OWNER_ID (основной способ связи со сделкой)
            owner_id = activity.get('OWNER_ID')
            owner_type_id = activity.get('OWNER_TYPE_ID')
            
            if owner_id and str(owner_type_id) == '2':  # OWNER_TYPE_ID='2' означает сделку
                try:
                    deal_id_int = int(owner_id)
                except (ValueError, TypeError):
                    pass
            
            # Если не нашли через OWNER_ID, проверяем ENTITY_ID как fallback
            if deal_id_int is None:
                entity_id = activity.get('ENTITY_ID')
                if entity_id:
                    try:
                        deal_id_int = int(entity_id)
                    except (ValueError, TypeError):
                        pass
            
            # Если нашли ID сделки и она в нашем списке, добавляем активность
            if deal_id_int and deal_id_int in deal_ids_set:
                if deal_id_int not in deal_activities:
                    deal_activities[deal_id_int] = []
                deal_activities[deal_id_int].append(activity)
            elif deal_id_int:
                activities_not_in_deals += 1
            else:
                activities_without_link += 1
        
        logger.info(
            f"Группировка активностей: всего {len(all_activities)}, "
            f"сгруппировано по {len(deal_activities)} сделкам, "
            f"без связи со сделкой: {activities_without_link}, "
            f"не в списке сделок: {activities_not_in_deals}"
        )
        
        # Обрабатываем активности для каждой сделки
        # Дела в таймлайне - это все активности (activities) разных типов:
        # TYPE_ID = 1: Встреча, TYPE_ID = 2: Звонок, TYPE_ID = 3: Задача, 
        # TYPE_ID = 4: Письмо, TYPE_ID = 5: Действие, TYPE_ID = 6: Пользовательское действие
        for deal_id, activities in deal_activities.items():
            # Подсчитываем звонки (TYPE_ID = '2')
            calls = [a for a in activities if str(a.get('TYPE_ID', '')) == '2']
            result[deal_id]['activities']['calls'] = len(calls)
            
            # Подсчитываем задачи из активностей CRM
            # Это включает TYPE_ID='3' (задачи) и TYPE_ID='6' с PROVIDER_ID='CRM_TODO' (задачи CRM)
            crm_tasks = [
                a for a in activities 
                if str(a.get('TYPE_ID', '')) == '3' or 
                (str(a.get('TYPE_ID', '')) == '6' and 
                 a.get('PROVIDER_ID') == 'CRM_TODO' and 
                 a.get('PROVIDER_TYPE_ID') == 'TODO')
            ]
            result[deal_id]['activities']['tasks'] += len(crm_tasks)
            
            # Подсчитываем все дела (активности) в таймлайне
            # Это включает все типы: встречи, звонки, задачи, письма, действия и т.д.
            result[deal_id]['activities']['deals'] = len(activities)
            
            # logger.debug(
            #     f"Сделка {deal_id}: активностей {len(activities)}, "
            #     f"звонков {len(calls)}, задач {len(crm_tasks)}, дел {len(activities)}"
            # )
            
            # Находим последнюю активность
            for activity in activities:
                created_str = activity.get('CREATED', '')
                if created_str:
                    try:
                        activity_date = _parse_datetime_from_bitrix(created_str)
                        if result[deal_id]['last_activity_date'] is None or activity_date > result[deal_id]['last_activity_date']:
                            result[deal_id]['last_activity_date'] = activity_date
                    except Exception:
                        pass
        
        # Шаг 2: Получаем комментарии батчами с ограниченным параллелизмом (если включено)
        # Обрабатываем батчами по 10 запросов параллельно с задержкой между батчами
        # Это предотвращает перегрузку API Bitrix24
        if include_comments:
            semaphore = asyncio.Semaphore(BATCH_SIZE)
            
            logger.info(f"Получение комментариев для {len(deal_ids_normalized)} сделок батчами (размер батча: {BATCH_SIZE}, задержка: {DELAY_BETWEEN_BATCHES}с)")
            
            async def get_comments_for_deal(deal_id: int) -> tuple[int, list]:
                """Получает комментарии для одной сделки с ограничением через семафор"""
                async with semaphore:  # Ограничиваем количество одновременных запросов
                    try:
                        comments_params = {
                            'filter': {
                                'ENTITY_TYPE': 'DEAL',
                                'ENTITY_ID': deal_id
                            }
                        }
                        comments_result = await bit.call('crm.timeline.comment.list', comments_params, raw=True)
                        
                        comments = []
                        if isinstance(comments_result, dict):
                            if 'result' in comments_result and isinstance(comments_result['result'], list):
                                comments = comments_result['result']
                            elif 'error' in comments_result:
                                logger.warning(f"Ошибка при получении комментариев для сделки {deal_id}: {comments_result.get('error')}")
                        elif isinstance(comments_result, list):
                            comments = comments_result
                        
                        return deal_id, comments
                    except Exception as e:
                        logger.warning(f"Ошибка при получении комментариев для сделки {deal_id}: {e}")
                        return deal_id, []
            
            # Обрабатываем батчами с задержками
            total_batches = (len(deal_ids_normalized) + BATCH_SIZE - 1) // BATCH_SIZE
            all_comments_results = []
            
            for batch_idx in range(0, len(deal_ids_normalized), BATCH_SIZE):
                batch_deal_ids = deal_ids_normalized[batch_idx:batch_idx + BATCH_SIZE]
                batch_num = (batch_idx // BATCH_SIZE) + 1
                
                logger.info(f"Обработка батча комментариев {batch_num}/{total_batches}: сделки {batch_idx+1}-{min(batch_idx+BATCH_SIZE, len(deal_ids_normalized))} из {len(deal_ids_normalized)}")
                
                # Выполняем запросы для текущего батча
                comments_tasks = [get_comments_for_deal(deal_id) for deal_id in batch_deal_ids]
                batch_results = await asyncio.gather(*comments_tasks)
                all_comments_results.extend(batch_results)
                
                # Добавляем задержку между батчами (кроме последнего)
                if batch_idx + BATCH_SIZE < len(deal_ids_normalized):
                    await asyncio.sleep(DELAY_BETWEEN_BATCHES)
            
            # Обрабатываем результаты
            for deal_id, comments in all_comments_results:
                # Фильтруем по дате
                recent_comments = [
                    c for c in comments
                    if c.get('CREATED', '') >= from_date_iso
                ]
                result[deal_id]['activities']['comments'] = len(recent_comments)
                
                # Обновляем последнюю активность
                for comment in recent_comments:
                    created_str = comment.get('CREATED', '')
                    if created_str:
                        try:
                            comment_date = _parse_datetime_from_bitrix(created_str)
                            if result[deal_id]['last_activity_date'] is None or comment_date > result[deal_id]['last_activity_date']:
                                result[deal_id]['last_activity_date'] = comment_date
                        except Exception:
                            pass
        else:
            logger.info(f"Получение комментариев пропущено (include_comments=False)")
        
        # Шаг 3: Получаем все задачи за период один раз
        # Получаем задачи, созданные или измененные за период (задачи - это тоже активность)
        logger.info(f"Получение задач за период для {len(deal_ids)} сделок")
        # Фильтруем по дате создания ИЛИ дате изменения (задачи могут быть созданы раньше, но изменены недавно)
        tasks_filter = {
            '>=CREATED_DATE': from_date_iso
        }
        all_tasks = await get_tasks_by_filter(
            tasks_filter,
            select_fields=['ID', 'TITLE', 'CREATED_DATE', 'CHANGED_DATE', 'CLOSED_DATE', 'UF_CRM_TASK']
        )
        
        # Нормализуем all_tasks в список
        if not isinstance(all_tasks, list):
            all_tasks = []
        
        # Группируем задачи по сделкам
        deal_tasks_dict = {}
        for deal_id in deal_ids_normalized:
            deal_tasks_dict[deal_id] = []
        
        for task in all_tasks:
            uf_crm_task = task.get('UF_CRM_TASK') or task.get('ufCrmTask')
            if uf_crm_task:
                # Проверяем все сделки
                for deal_id in deal_ids_normalized:
                    deal_prefix = f"D_{deal_id}"
                    task_matched = False
                    
                    if isinstance(uf_crm_task, list):
                        if any(str(item).startswith(deal_prefix) for item in uf_crm_task):
                            task_matched = True
                    elif isinstance(uf_crm_task, str) and uf_crm_task.startswith(deal_prefix):
                        task_matched = True
                    
                    if task_matched:
                        # Проверяем, что задача была активна в указанный период
                        # (создана или изменена в период)
                        created_str = task.get('CREATED_DATE') or task.get('createdDate')
                        changed_str = task.get('CHANGED_DATE') or task.get('changedDate') or task.get('CLOSED_DATE') or task.get('closedDate')
                        
                        task_in_period = False
                        if created_str and created_str >= from_date_iso:
                            task_in_period = True
                        elif changed_str and changed_str >= from_date_iso:
                            task_in_period = True
                        
                        # Если задача связана со сделкой и была активна в период, добавляем её
                        if task_in_period:
                            deal_tasks_dict[deal_id].append(task)
                            break  # Задача может быть связана с несколькими сделками, но считаем один раз
        
        # Обновляем результаты для задач (добавляем к уже подсчитанным из активностей CRM)
        for deal_id, deal_tasks in deal_tasks_dict.items():
            result[deal_id]['activities']['tasks'] += len(deal_tasks)
            
            # Обновляем последнюю активность (используем максимальную дату из создания, изменения или закрытия)
            for task in deal_tasks:
                created_str = task.get('CREATED_DATE') or task.get('createdDate')
                changed_str = task.get('CHANGED_DATE') or task.get('changedDate')
                closed_str = task.get('CLOSED_DATE') or task.get('closedDate')
                
                # Берем самую позднюю дату из всех доступных
                task_dates = []
                for date_str in [created_str, changed_str, closed_str]:
                    if date_str:
                        try:
                            task_date = _parse_datetime_from_bitrix(date_str)
                            task_dates.append(task_date)
                        except Exception:
                            pass
                
                if task_dates:
                    max_task_date = max(task_dates)
                    if result[deal_id]['last_activity_date'] is None or max_task_date > result[deal_id]['last_activity_date']:
                        result[deal_id]['last_activity_date'] = max_task_date
        
        # Вычисляем has_activity для каждой сделки
        # Учитываем все виды активности: дела (activities), комментарии, задачи
        deals_with_activities = 0
        deals_without_activities = 0
        for deal_id in deal_ids_normalized:
            total_activities = (
                result[deal_id]['activities'].get('deals', 0) + 
                result[deal_id]['activities']['comments'] + 
                result[deal_id]['activities']['tasks']
            )
            result[deal_id]['has_activity'] = total_activities > 0
            
            if total_activities > 0:
                deals_with_activities += 1
            else:
                deals_without_activities += 1
            
            # Логируем для сделок с нулевой активностью
            # if result[deal_id]['activities'].get('deals', 0) == 0:
                # logger.debug(
                #     f"Сделка {deal_id}: deals=0, calls={result[deal_id]['activities']['calls']}, "
                #     f"comments={result[deal_id]['activities']['comments']}, "
                #     f"tasks={result[deal_id]['activities']['tasks']}"
                # )
        
        logger.info(
            f"Получена активность для {len(deal_ids_normalized)} сделок батчами: "
            f"с активностью: {deals_with_activities}, без активности: {deals_without_activities}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении активности для сделок батчами: {e}")
    
    return result


@mcp.tool()
async def get_deals_at_risk(filter_fields: dict[str, str] = None, fields_id: list[str] = None, include_comments: bool = False, exclude_funnel_keyword: str = "архив") -> str:
    """Получение сделок, находящихся в риске
    
    Сделка считается «в риске», если выполняется одно или несколько условий:
    • статус сделки не менялся более 5 рабочих дней;
    • отсутствует активность (звонки, комментарии, задачи) более 3 дней;
    
    Args:
        filter_fields: Дополнительные фильтры для сделок (по умолчанию {'STAGE_SEMANTIC_ID': 'P'} - только сделки в работе)
        fields_id: Список полей для получения информации о сделках (по умолчанию ["ID", "TITLE", "STAGE_ID", "DATE_MODIFY"])
        include_comments: Получать комментарии для всех сделок (по умолчанию True). Если False, комментарии пропускаются для ускорения работы
        exclude_funnel_keyword: Ключевое слово для исключения воронок. Если указано, все воронки, в названии которых содержится это слово (без учета регистра), будут исключены из анализа. Сделки из этих воронок не будут проверяться
    
    Returns:
        Текстовая строка со списком сделок в риске с указанием причин
    """
    try:
        # Устанавливаем значения по умолчанию (создаем новые объекты, чтобы избежать проблем с изменяемыми значениями по умолчанию)
        if filter_fields is None:
            filter_fields = {'STAGE_SEMANTIC_ID': 'P'}
        else:
            # Создаем копию, чтобы не изменять оригинальный словарь
            filter_fields = dict(filter_fields)
            # Добавляем дефолтный фильтр, если его нет
            # if "CLOSED" not in filter_fields:
            #     filter_fields["CLOSED"] = "N"
            if "STAGE_SEMANTIC_ID" not in filter_fields:
                filter_fields["STAGE_SEMANTIC_ID"] = "P"
        
        if fields_id is None:
            fields_id = ["ID", "TITLE", "STAGE_ID", "DATE_MODIFY"]
        else:
            # Создаем копию списка
            fields_id = list(fields_id)
        
        # Добавляем обязательные поля
        required_fields = ['ID', 'TITLE', 'STAGE_ID', 'DATE_MODIFY', 'CATEGORY_ID']
        for field in required_fields:
            if field not in fields_id:
                fields_id.append(field)
        
        # Если указано ключевое слово для исключения воронок, получаем список воронок для фильтрации
        excluded_category_ids = set()
        if exclude_funnel_keyword:
            logger.info(f"Поиск воронок для исключения по ключевому слову: '{exclude_funnel_keyword}'")
            categories = await get_deal_categories()
            keyword_lower = exclude_funnel_keyword.lower()
            for category in categories:
                category_name = category.get('NAME', '')
                category_id = category.get('ID')
                if category_id and keyword_lower in category_name.lower():
                    excluded_category_ids.add(str(category_id))
                    logger.info(f"Воронка исключена: '{category_name}' (ID: {category_id})")
            
            if excluded_category_ids:
                logger.info(f"Исключено воронок: {len(excluded_category_ids)} (ID: {', '.join(excluded_category_ids)})")
            else:
                logger.info(f"Воронки с ключевым словом '{exclude_funnel_keyword}' не найдены")
        
        # Получаем все сделки по фильтру
        deals = await get_deals_by_filter(filter_fields, fields_id)
        
        if isinstance(deals, dict):
            if deals.get('order0000000000'):
                deals = deals['order0000000000']
        
        if not isinstance(deals, list):
            deals = []
        
        # Фильтруем сделки по исключаемым воронкам, если указано ключевое слово
        if exclude_funnel_keyword and excluded_category_ids:
            original_count = len(deals)
            deals = [
                deal for deal in deals
                if str(deal.get('CATEGORY_ID', '')) not in excluded_category_ids
            ]
            filtered_count = original_count - len(deals)
            if filtered_count > 0:
                logger.info(f"Отфильтровано сделок из исключенных воронок: {filtered_count} из {original_count}")
        
        if not deals:
            return "Сделки по указанным фильтрам не найдены."
        
        # Получаем названия стадий и воронок
        stages_info = await get_stages("DEAL_STAGE")
        stages_dict = {}
        categories_dict = {}  # Словарь для быстрого поиска названия воронки по ID
        for category_id, category_data in stages_info.items():
            # Сохраняем название воронки
            categories_dict[str(category_id)] = category_data.get('name', f'Воронка {category_id}')
            # Сохраняем стадии
            stages_dict.update(category_data.get('stages', {}))
        
        deals_at_risk = []
        now = datetime.now(timezone.utc)
        
        # Получаем ID всех сделок и нормализуем их
        deal_ids = []
        deal_id_to_deal = {}  # Маппинг для восстановления данных сделки
        for deal in deals:
            deal_id = deal.get('ID')
            if deal_id:
                try:
                    deal_id_int = int(deal_id)
                    deal_ids.append(deal_id_int)
                    deal_id_to_deal[deal_id_int] = deal
                except (ValueError, TypeError):
                    pass
        
        # Получаем активность для всех сделок батчами (оптимизация)
        logger.info(f"Получение активности для {len(deal_ids)} сделок батчами (включая комментарии: {include_comments})")
        all_activities = await _get_all_deals_activity_batch(deal_ids, days=3, include_comments=include_comments)
        
        # Проверяем каждую сделку
        for deal_id_int, deal in deal_id_to_deal.items():
            deal_id = deal.get('ID')
            if not deal_id:
                continue
                
            deal_title = deal.get('TITLE', f'Сделка #{deal_id}')
            risk_reasons = []
            
            # Проверка 1: Статус не менялся более 5 рабочих дней
            date_modify_str = deal.get('DATE_MODIFY') or deal.get('DATE_CREATE')
            if date_modify_str:
                try:
                    date_modify = _parse_datetime_from_bitrix(date_modify_str)
                    workdays_since_modify = _count_workdays(date_modify, now)
                    
                    if workdays_since_modify > 5:
                        risk_reasons.append(f"Статус не менялся {workdays_since_modify} рабочих дней (последнее изменение: {date_modify.strftime('%Y-%m-%d %H:%M:%S')})")
                except Exception as e:
                    logger.warning(f"Ошибка при проверке даты изменения сделки {deal_id}: {e}")
            
            # Проверка 2: Отсутствует активность более 3 дней
            # Используем нормализованный ID для получения активности
            activity_info = all_activities.get(deal_id_int, {
                'has_activity': False,
                'last_activity_date': None,
                'activities': {'deals': 0, 'calls': 0, 'comments': 0, 'tasks': 0}
            })
            
            # Логируем информацию об активности для отладки
            # logger.debug(
            #     f"Сделка {deal_id_int} (ID из сделки: {deal_id}): "
            #     f"активность найдена в all_activities: {deal_id_int in all_activities}, "
            #     f"deals: {activity_info.get('activities', {}).get('deals', 0)}, "
            #     f"calls: {activity_info.get('activities', {}).get('calls', 0)}, "
            #     f"comments: {activity_info.get('activities', {}).get('comments', 0)}, "
            #     f"tasks: {activity_info.get('activities', {}).get('tasks', 0)}"
            # )
            
            if not activity_info['has_activity']:
                risk_reasons.append("Отсутствует активность (звонки, комментарии, задачи) более 3 дней")
            elif activity_info['last_activity_date']:
                # Проверяем, что последняя активность была более 3 дней назад
                # Используем timedelta для точного сравнения (3 дня = 72 часа)
                time_since_activity = now - activity_info['last_activity_date']
                if time_since_activity > timedelta(days=3):
                    days_since_activity = time_since_activity.days
                    risk_reasons.append(f"Последняя активность была {days_since_activity} дней назад ({activity_info['last_activity_date'].strftime('%Y-%m-%d %H:%M:%S')})")
            
            # Если есть причины риска, добавляем сделку в список
            if risk_reasons:
                stage_id = deal.get('STAGE_ID', 'Неизвестно')
                stage_name = stages_dict.get(stage_id, stage_id)
                
                # Получаем название воронки
                category_id = str(deal.get('CATEGORY_ID', '0') or '0')
                funnel_name = categories_dict.get(category_id, f'Воронка {category_id}')
                
                deals_at_risk.append({
                    'deal_id': deal_id,
                    'title': deal_title,
                    'stage': stage_name,
                    'stage_id': stage_id,
                    'funnel': funnel_name,
                    'funnel_id': category_id,
                    'reasons': risk_reasons,
                    'activity_info': activity_info
                })
        
        # Формируем результат
        if not deals_at_risk:
            return f"Сделок в риске не найдено. Проверено сделок: {len(deals)}."
        
        result_text = f"=== Сделки в риске ===\n\n"
        result_text += f"Всего проверено сделок: {len(deals)}\n"
        result_text += f"Сделок в риске: {len(deals_at_risk)}\n\n"
        
        for idx, deal_info in enumerate(deals_at_risk, 1):
            result_text += f"{idx}. {deal_info['title']} (ID: {deal_info['deal_id']})\n"
            result_text += f"   Воронка: {deal_info['funnel']}\n"
            result_text += f"   Стадия: {deal_info['stage']} ({deal_info['stage_id']})\n"
            result_text += f"   Причины риска:\n"
            for reason in deal_info['reasons']:
                result_text += f"     • {reason}\n"
            
            # Добавляем информацию об активности
            activity_info_data = deal_info.get('activity_info', {})
            activity = activity_info_data.get('activities', {})
            
            # Логируем для отладки
            # logger.debug(
            #     f"Вывод результата для сделки {deal_info['deal_id']}: "
            #     f"activity_info keys: {list(activity_info_data.keys())}, "
            #     f"activities keys: {list(activity.keys()) if isinstance(activity, dict) else 'not a dict'}, "
            #     f"deals value: {activity.get('deals', 'NOT_FOUND')}"
            # )
            
            # Безопасное получение значений с проверкой
            deals_count = activity.get('deals', 0) if isinstance(activity, dict) else 0
            calls_count = activity.get('calls', 0) if isinstance(activity, dict) else 0
            comments_count = activity.get('comments', 0) if isinstance(activity, dict) else 0
            tasks_count = activity.get('tasks', 0) if isinstance(activity, dict) else 0
            
            result_text += f"   Активность за последние 3 дня:\n"
            result_text += f"     • Дела в таймлайне: {deals_count} (встречи, звонки, письма, действия и т.д.)\n"
            result_text += f"     • Звонки: {calls_count}\n"
            result_text += f"     • Комментарии: {comments_count}\n"
            result_text += f"     • Задачи: {tasks_count}\n"
            
            if deal_info['activity_info']['last_activity_date']:
                result_text += f"   Последняя активность: {deal_info['activity_info']['last_activity_date'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            result_text += "\n"
        
        return result_text
        
    except Exception as e:
        logger.error(f"Ошибка при получении сделок в риске: {e}")
        return f"Ошибка при получении сделок в риске: {str(e)}"


if __name__ == "__main__":
    # mcp.run(transport="sse", host="0.0.0.0", port=8000)
    a=asyncio.run(get_stages())
    pass
    # b=asyncio.run(list_deal(fields_id=['OPPORTUNITY']))
    # b=asyncio.run(list_deal(fields_id=['*','UF_*'], filter_fields={">=DATE_CREATE": "2025-06-11"}))
    # print(b)
    # b=asyncio.run(analyze_export_file(file_path='../../exports/deal_export_20250818_195707.json', operation='count', fields=['OPPORTUNITY', 'TITLE'], condition={"OPPORTUNITY": "123.00"}, group_by=['OPPORTUNITY']))
    # pprint(b)
    
    # Тест функции prepare_deal_fields_to_humman_format
    # async def test_prepare_fields():
    #     all_info_fields = await get_all_info_fields(['deal'], isText=False)
        
    #     # Тестовые данные
    #     test_fields = {
    #         'UF_CRM_1749724770090': '47',
    #         'TITLE': 'тестовая сделка',
    #         'OPPORTUNITY': '10000'
    #     }
        
    #     result = await prepare_deal_fields_to_humman_format(test_fields, all_info_fields)
    #     print("Исходные поля:", test_fields)
    #     print("Преобразованные поля:", result)
        
    # asyncio.run(test_prepare_fields())