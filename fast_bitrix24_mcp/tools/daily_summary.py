from .bitrixWork import (
    bit, 
    get_crm_activities_by_filter, 
    get_tasks_by_filter, 
    get_leads_by_filter, 
    get_deals_by_filter,
    get_users_by_filter
)
import asyncio
from mcp.server.fastmcp import FastMCP
from datetime import datetime, timedelta
from loguru import logger
from typing import Dict, List
import pytz

mcp = FastMCP("daily_summary")


def _normalize_optional_date(date_value: str | None) -> str | None:
    """Нормализация опционального параметра даты
    
    Преобразует строки 'null', 'None', пустые строки в None.
    Это необходимо для корректной обработки параметров, переданных как строки 'null' вместо None.
    
    Args:
        date_value: Значение даты (может быть строкой, None или строкой 'null'/'None')
    
    Returns:
        None если date_value является None, 'null', 'None' или пустой строкой, иначе date_value
    """
    if date_value is None:
        return None
    if isinstance(date_value, str):
        normalized = date_value.strip().lower()
        if normalized in ('null', 'none', ''):
            return None
    return date_value


def _parse_datetime_from_bitrix(dt_str: str) -> datetime:
    """Парсинг даты/времени из формата Bitrix24"""
    if not dt_str:
        return None
    
    # Пробуем разные форматы
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",  # ISO-8601 с timezone
        "%Y-%m-%dT%H:%M:%S",     # ISO-8601 без timezone
        "%Y-%m-%d %H:%M:%S",     # Стандартный формат
        "%Y-%m-%d"               # Только дата
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            # Если нет timezone, считаем UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
            return dt
        except ValueError:
            continue
    
    return None


@mcp.tool()
async def get_daily_summary(date: str = None, group_by_managers: bool = False, isText: bool = True) -> dict | str:
    """Получение сводки по итогам дня (оптимизированная версия с батчами)
    
    Сводка включает:
    - Кол-во новых лидов и сделок
    - Сколько задач создано и выполнено
    - Кол-во звонков (входящих/исходящих)
    
    Оптимизация: получает все данные одним набором запросов вместо последовательных вызовов.
    Это значительно ускоряет работу при большом количестве данных.
    
    Args:
        date: Дата для сводки в формате YYYY-MM-DD. Если не указана, используется сегодняшний день (московское время)
        group_by_managers: Если True, возвращает сводку с группировкой по менеджерам. Если False, возвращает общую сводку (по умолчанию False)
        isText: Если True (по умолчанию), возвращает человекочитаемый текст; если False, возвращает структурированный словарь
    
    Returns:
        Если group_by_managers=False и isText=False: dict с общей сводкой:
        {
            'date': str,
            'leads': {'new': int},
            'deals': {'new': int},
            'tasks': {'created': int, 'completed': int},
            'calls': {'total': int, 'incoming': int, 'outgoing': int}
        }
        
        Если group_by_managers=True и isText=False: dict с группировкой по менеджерам:
        {
            'date': str,
            'summary': {
                'leads': {'new': int},
                'deals': {'new': int},
                'tasks': {'created': int, 'completed': int},
                'calls': {'total': int, 'incoming': int, 'outgoing': int}
            },
            'managers': [
                {
                    'manager_id': int,
                    'name': str,
                    'email': str,
                    'work_position': str,
                    'leads': {'new': int},
                    'deals': {'new': int},
                    'tasks': {'created': int, 'completed': int},
                    'calls': {'total': int, 'incoming': int, 'outgoing': int}
                }
            ]
        }
        
        Если isText=True: str с человекочитаемым текстом сводки
    """
    try:
        # Нормализация опционального параметра даты (преобразование 'null'/'None' в None)
        date = _normalize_optional_date(date)
        
        # Определение даты для сводки
        moscow_tz = pytz.timezone("Europe/Moscow")
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
                target_date = moscow_tz.localize(target_date)
            except ValueError:
                logger.error(f"Неверный формат даты: {date}. Используется формат YYYY-MM-DD")
                raise ValueError("Неверный формат даты. Используйте формат YYYY-MM-DD")
        else:
            target_date = datetime.now(moscow_tz)
        
        # Границы дня (начало и конец дня в московском времени)
        day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Конвертируем в UTC для запросов к API
        day_start_utc = day_start.astimezone(pytz.UTC)
        day_end_utc = day_end.astimezone(pytz.UTC)
        
        # Форматируем для фильтров API
        day_start_str = day_start_utc.strftime("%Y-%m-%dT%H:%M:%S")
        day_end_str = day_end_utc.strftime("%Y-%m-%dT%H:%M:%S")
        date_str = target_date.strftime("%Y-%m-%d")
        
        logger.info(
            f"Получение сводки за день: {date_str} "
            f"(период: {day_start_str} - {day_end_str} UTC)"
        )
        
        # Получаем все данные параллельно одним набором запросов
        logger.info("Получение всех данных за день...")
        
        # 1. Новые лиды за день
        leads_filter = {
            '>=DATE_CREATE': day_start_str,
            '<=DATE_CREATE': day_end_str
        }
        
        # 2. Новые сделки за день
        deals_filter = {
            '>=DATE_CREATE': day_start_str,
            '<=DATE_CREATE': day_end_str
        }
        
        # 3. Задачи созданные за день
        tasks_created_filter = {
            '>=CREATED_DATE': day_start_str,
            '<=CREATED_DATE': day_end_str
        }
        
        # 4. Звонки за день
        calls_filter = {
            '>=CREATED': day_start_str,
            '<=CREATED': day_end_str,
            'TYPE_ID': '2'  # Звонки
        }
        
        # Выполняем все запросы параллельно
        leads_task = get_leads_by_filter(leads_filter, select_fields=['ID', 'DATE_CREATE', 'CREATED_BY'])
        deals_task = get_deals_by_filter(deals_filter, select_fields=['ID', 'DATE_CREATE', 'CREATED_BY'])
        tasks_task = get_tasks_by_filter(tasks_created_filter, select_fields=['ID', 'CREATED_DATE', 'RESPONSIBLE_ID', 'STATUS'])
        calls_task = get_crm_activities_by_filter(calls_filter, select_fields=['ID', 'CREATED', 'RESPONSIBLE_ID', 'DIRECTION'])
        
        leads, deals, tasks, calls = await asyncio.gather(
            leads_task, deals_task, tasks_task, calls_task
        )
        
        # Нормализация данных
        if isinstance(leads, dict):
            if leads.get('order0000000000'):
                leads = leads['order0000000000']
        leads = leads if isinstance(leads, list) else []
        
        if isinstance(deals, dict):
            if deals.get('order0000000000'):
                deals = deals['order0000000000']
        deals = deals if isinstance(deals, list) else []
        
        tasks = tasks if isinstance(tasks, list) else []
        calls = calls if isinstance(calls, list) else []
        
        logger.info(
            f"Получено данных: лидов={len(leads)}, сделок={len(deals)}, "
            f"задач={len(tasks)}, звонков={len(calls)}"
        )
        
        # Подсчет выполненных задач (STATUS = '5')
        tasks_completed = [
            t for t in tasks 
            if str(t.get('STATUS', t.get('status', ''))) == '5'
        ]
        
        # Подсчет звонков по направлениям
        calls_incoming = [
            c for c in calls 
            if str(c.get('DIRECTION', '')) == '2'
        ]
        calls_outgoing = [
            c for c in calls 
            if str(c.get('DIRECTION', '')) == '1'
        ]
        
        if not group_by_managers:
            # Общая сводка без группировки по менеджерам
            summary = {
                'date': date_str,
                'leads': {'new': len(leads)},
                'deals': {'new': len(deals)},
                'tasks': {
                    'created': len(tasks),
                    'completed': len(tasks_completed)
                },
                'calls': {
                    'total': len(calls),
                    'incoming': len(calls_incoming),
                    'outgoing': len(calls_outgoing)
                }
            }
            
            if isText:
                result_text = f"=== Сводка по итогам дня {date_str} ===\n\n"
                result_text += f"📊 Лиды:\n"
                result_text += f"  • Новых лидов: {summary['leads']['new']}\n\n"
                result_text += f"💼 Сделки:\n"
                result_text += f"  • Новых сделок: {summary['deals']['new']}\n\n"
                result_text += f"✅ Задачи:\n"
                result_text += f"  • Создано задач: {summary['tasks']['created']}\n"
                result_text += f"  • Выполнено задач: {summary['tasks']['completed']}\n\n"
                result_text += f"📞 Звонки:\n"
                result_text += f"  • Всего звонков: {summary['calls']['total']}\n"
                result_text += f"  • Входящих: {summary['calls']['incoming']}\n"
                result_text += f"  • Исходящих: {summary['calls']['outgoing']}\n"
                return result_text
            
            return summary
        
        else:
            # Группировка по менеджерам
            # Получаем список всех менеджеров
            users = await get_users_by_filter({'ACTIVE': True})
            if isinstance(users, dict):
                if users.get('order0000000000'):
                    users = users['order0000000000']
            users = users if isinstance(users, list) else []
            
            managers = {
                int(u.get('ID', 0)): u 
                for u in users 
                if u.get('ID') and int(u.get('ID', 0)) > 0 and u.get('ACTIVE') == True
            }
            
            # Инициализация структуры данных по менеджерам
            managers_data = {}
            for manager_id, manager in managers.items():
                managers_data[manager_id] = {
                    'manager_id': manager_id,
                    'name': f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip(),
                    'email': manager.get('EMAIL', ''),
                    'work_position': manager.get('WORK_POSITION', ''),
                    'leads': {'new': 0},
                    'deals': {'new': 0},
                    'tasks': {'created': 0, 'completed': 0},
                    'calls': {'total': 0, 'incoming': 0, 'outgoing': 0}
                }
            
            # Группируем лиды по менеджерам (CREATED_BY)
            for lead in leads:
                created_by = lead.get('CREATED_BY')
                if created_by:
                    try:
                        manager_id = int(created_by)
                        if manager_id in managers_data:
                            managers_data[manager_id]['leads']['new'] += 1
                    except (ValueError, TypeError):
                        continue
            
            # Группируем сделки по менеджерам (CREATED_BY)
            for deal in deals:
                created_by = deal.get('CREATED_BY')
                if created_by:
                    try:
                        manager_id = int(created_by)
                        if manager_id in managers_data:
                            managers_data[manager_id]['deals']['new'] += 1
                    except (ValueError, TypeError):
                        continue
            
            # Группируем задачи по менеджерам (RESPONSIBLE_ID)
            for task in tasks:
                responsible_id = task.get('RESPONSIBLE_ID') or task.get('responsibleId')
                if responsible_id:
                    try:
                        manager_id = int(responsible_id)
                        if manager_id in managers_data:
                            managers_data[manager_id]['tasks']['created'] += 1
                            # Проверяем статус задачи
                            task_status = str(task.get('STATUS', task.get('status', '')))
                            if task_status == '5':
                                managers_data[manager_id]['tasks']['completed'] += 1
                    except (ValueError, TypeError):
                        continue
            
            # Группируем звонки по менеджерам (RESPONSIBLE_ID)
            for call in calls:
                responsible_id = call.get('RESPONSIBLE_ID')
                if responsible_id:
                    try:
                        manager_id = int(responsible_id)
                        if manager_id in managers_data:
                            managers_data[manager_id]['calls']['total'] += 1
                            direction = str(call.get('DIRECTION', ''))
                            if direction == '2':
                                managers_data[manager_id]['calls']['incoming'] += 1
                            elif direction == '1':
                                managers_data[manager_id]['calls']['outgoing'] += 1
                    except (ValueError, TypeError):
                        continue
            
            # Формируем итоговую структуру
            managers_list = [
                data for data in managers_data.values()
                if (data['leads']['new'] > 0 or 
                    data['deals']['new'] > 0 or 
                    data['tasks']['created'] > 0 or 
                    data['calls']['total'] > 0)
            ]
            
            # Общая сводка
            summary_data = {
                'leads': {'new': len(leads)},
                'deals': {'new': len(deals)},
                'tasks': {
                    'created': len(tasks),
                    'completed': len(tasks_completed)
                },
                'calls': {
                    'total': len(calls),
                    'incoming': len(calls_incoming),
                    'outgoing': len(calls_outgoing)
                }
            }
            
            result = {
                'date': date_str,
                'summary': summary_data,
                'managers': managers_list
            }
            
            if isText:
                result_text = f"=== Сводка по итогам дня {date_str} ===\n\n"
                result_text += f"📊 Общая статистика:\n"
                result_text += f"  • Новых лидов: {summary_data['leads']['new']}\n"
                result_text += f"  • Новых сделок: {summary_data['deals']['new']}\n"
                result_text += f"  • Создано задач: {summary_data['tasks']['created']}\n"
                result_text += f"  • Выполнено задач: {summary_data['tasks']['completed']}\n"
                result_text += f"  • Всего звонков: {summary_data['calls']['total']}\n"
                result_text += f"  • Входящих: {summary_data['calls']['incoming']}\n"
                result_text += f"  • Исходящих: {summary_data['calls']['outgoing']}\n\n"
                
                if managers_list:
                    result_text += f"👥 По менеджерам:\n\n"
                    for idx, manager in enumerate(managers_list, 1):
                        result_text += f"{idx}. {manager['name']}"
                        if manager.get('work_position'):
                            result_text += f" ({manager['work_position']})"
                        result_text += f"\n"
                        
                        if manager.get('email'):
                            result_text += f"   Email: {manager['email']}\n"
                        result_text += f"   ID: {manager['manager_id']}\n"
                        result_text += f"   • Лидов: {manager['leads']['new']}\n"
                        result_text += f"   • Сделок: {manager['deals']['new']}\n"
                        result_text += f"   • Задач создано: {manager['tasks']['created']}\n"
                        result_text += f"   • Задач выполнено: {manager['tasks']['completed']}\n"
                        result_text += f"   • Звонков всего: {manager['calls']['total']}\n"
                        result_text += f"   • Входящих: {manager['calls']['incoming']}\n"
                        result_text += f"   • Исходящих: {manager['calls']['outgoing']}\n\n"
                else:
                    result_text += f"Менеджеры с активностью не найдены.\n"
                
                return result_text
            
            return result
        
    except Exception as e:
        logger.error(f"Ошибка при получении сводки по итогам дня: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(get_daily_summary())
    from pprint import pprint
    pprint(result)

