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
from .bitrixWork import bit, get_deals_by_filter, get_deal_stages, get_deal_categories, get_all_deal_stages_by_categories, get_stage_history

from .helper import prepare_fields_to_humman_format
# bitrix=Bitrix(WEBHOOK)
WEBHOOK=os.getenv("WEBHOOK")
# class Deal(_Deal):
#     pass
# Deal.get_manager(bitrix)

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