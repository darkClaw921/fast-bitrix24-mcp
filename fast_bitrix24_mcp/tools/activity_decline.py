from .bitrixWork import bit, get_users_by_filter, get_crm_activities_by_filter, get_tasks_by_filter, get_leads_by_filter, get_deals_by_filter
import asyncio
from mcp.server.fastmcp import FastMCP
from datetime import datetime, timedelta, timezone
from loguru import logger
from typing import Dict, List

mcp = FastMCP("activity_decline")


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
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    
    return None


@mcp.tool()
async def get_managers_with_declined_activity(isText: bool = True) -> dict | str:
    """Выявление менеджеров со сниженной активностью 
    
    Менеджер считается снизившим активность, если за последние 7 дней у него:
    - количество задач упало на 30%+ по сравнению с предыдущей неделей
    - количество звонков снизилось на 25%+
    
    Оптимизация: получает все данные одним набором запросов вместо последовательных вызовов для каждого менеджера.
    Это значительно ускоряет работу при большом количестве менеджеров.
    
    Args:
        isText: Если True (по умолчанию), возвращает человекочитаемый текст с информацией о менеджерах; если False, возвращает структурированный словарь
    
    Returns:
        Если isText=False: dict с информацией о менеджерах со сниженной активностью:
        {
            'period': {
                'current_week_start': str,
                'current_week_end': str,
                'previous_week_start': str,
                'previous_week_end': str
            },
            'managers': [
                {
                    'manager_id': int,
                    'name': str,
                    'email': str,
                    'work_position': str,
                    'current_week': {
                        'tasks': int,
                        'calls': int
                    },
                    'previous_week': {
                        'tasks': int,
                        'calls': int
                    },
                    'decline': {
                        'tasks_percent': float,
                        'calls_percent': float
                    },
                    'reasons': list[str]  # Причины снижения активности
                }
            ],
            'summary': {
                'total_checked': int,
                'with_decline': int
            }
        }
        Если isText=True: str с человекочитаемым текстом о менеджерах со сниженной активностью
    """
    try:
        # Определение периодов
        today = datetime.now(timezone.utc)
        current_week_end = today.strftime("%Y-%m-%d")
        current_week_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        previous_week_end = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        previous_week_start = (today - timedelta(days=14)).strftime("%Y-%m-%d")
        
        # Границы для получения всех данных за 14 дней
        period_start_iso = f"{previous_week_start}T00:00:00"
        period_end_iso = f"{current_week_end}T23:59:59"
        
        logger.info(
            f"Анализ снижения активности: текущая неделя {current_week_start} - {current_week_end}, "
            f"предыдущая неделя {previous_week_start} - {previous_week_end}"
        )
        
        # Получение всех активных менеджеров
        users = await get_users_by_filter({'ACTIVE': True})
        if isinstance(users, dict):
            if users.get('order0000000000'):
                users = users['order0000000000']
        users = users if isinstance(users, list) else []
        
        # Исключаем системных пользователей
        managers = [
            u for u in users 
            if u.get('ID') and int(u.get('ID', 0)) > 0 and u.get('ACTIVE') == True
        ]
        
        if not managers:
            if isText:
                return "Активные менеджеры не найдены."
            return {
                'period': {
                    'current_week_start': current_week_start,
                    'current_week_end': current_week_end,
                    'previous_week_start': previous_week_start,
                    'previous_week_end': previous_week_end
                },
                'managers': [],
                'summary': {
                    'total_checked': 0,
                    'with_decline': 0
                }
            }
        
        manager_ids = [int(m.get('ID', 0)) for m in managers]
        manager_ids_set = set(manager_ids)
        
        logger.info(f"Найдено {len(managers)} активных менеджеров для проверки")
        
        # Шаг 1: Получаем все звонки за весь период одним запросом
        logger.info(f"Получение всех звонков за период {period_start_iso} - {period_end_iso}")
        calls_filter = {
            '>=CREATED': period_start_iso,
            '<=CREATED': period_end_iso,
            'TYPE_ID': '2'  # Звонки
        }
        all_calls = await get_crm_activities_by_filter(
            calls_filter, 
            select_fields=['ID', 'TYPE_ID', 'CREATED', 'RESPONSIBLE_ID']
        )
        
        if not isinstance(all_calls, list):
            all_calls = []
        
        logger.info(f"Получено звонков: {len(all_calls)}")
        
        # Шаг 2: Получаем все задачи за весь период одним запросом
        logger.info(f"Получение всех задач за период {period_start_iso} - {period_end_iso}")
        tasks_filter = {
            '>=CREATED_DATE': period_start_iso,
            '<=CREATED_DATE': period_end_iso
        }
        all_tasks = await get_tasks_by_filter(
            tasks_filter,
            select_fields=['ID', 'CREATED_DATE', 'RESPONSIBLE_ID']
        )
        
        if not isinstance(all_tasks, list):
            all_tasks = []
        
        logger.info(f"Получено задач: {len(all_tasks)}")
        
        # Шаг 3: Группируем данные по менеджерам и неделям на клиенте
        # Структура: {manager_id: {'current': {'tasks': 0, 'calls': 0}, 'previous': {'tasks': 0, 'calls': 0}}}
        manager_activity = {}
        for manager_id in manager_ids:
            manager_activity[manager_id] = {
                'current': {'tasks': 0, 'calls': 0},
                'previous': {'tasks': 0, 'calls': 0}
            }
        
        # Границы дат для разделения на недели
        current_week_start_dt = datetime.strptime(current_week_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        previous_week_start_dt = datetime.strptime(previous_week_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        
        # Группируем звонки
        for call in all_calls:
            responsible_id = call.get('RESPONSIBLE_ID')
            if not responsible_id:
                continue
            
            try:
                manager_id = int(responsible_id)
                if manager_id not in manager_ids_set:
                    continue
                
                created_str = call.get('CREATED', '')
                if not created_str:
                    continue
                
                created_dt = _parse_datetime_from_bitrix(created_str)
                if not created_dt:
                    continue
                
                # Определяем, к какой неделе относится звонок
                if created_dt >= current_week_start_dt:
                    manager_activity[manager_id]['current']['calls'] += 1
                elif created_dt >= previous_week_start_dt:
                    manager_activity[manager_id]['previous']['calls'] += 1
            except (ValueError, TypeError):
                continue
        
        # Группируем задачи
        for task in all_tasks:
            responsible_id = task.get('RESPONSIBLE_ID') or task.get('responsibleId')
            if not responsible_id:
                continue
            
            try:
                manager_id = int(responsible_id)
                if manager_id not in manager_ids_set:
                    continue
                
                created_str = task.get('CREATED_DATE') or task.get('createdDate')
                if not created_str:
                    continue
                
                created_dt = _parse_datetime_from_bitrix(created_str)
                if not created_dt:
                    continue
                
                # Определяем, к какой неделе относится задача
                if created_dt >= current_week_start_dt:
                    manager_activity[manager_id]['current']['tasks'] += 1
                elif created_dt >= previous_week_start_dt:
                    manager_activity[manager_id]['previous']['tasks'] += 1
            except (ValueError, TypeError):
                continue
        
        logger.info(f"Группировка данных завершена для {len(manager_activity)} менеджеров")
        
        # Шаг 4: Анализируем снижение активности для каждого менеджера
        managers_with_decline = []
        
        for manager in managers:
            manager_id = int(manager.get('ID', 0))
            manager_name = f"{manager.get('NAME', '')} {manager.get('LAST_NAME', '')}".strip()
            manager_email = manager.get('EMAIL', '')
            manager_position = manager.get('WORK_POSITION', '')
            
            activity = manager_activity.get(manager_id, {
                'current': {'tasks': 0, 'calls': 0},
                'previous': {'tasks': 0, 'calls': 0}
            })
            
            current_tasks = activity['current']['tasks']
            current_calls = activity['current']['calls']
            previous_tasks = activity['previous']['tasks']
            previous_calls = activity['previous']['calls']
            
            # Расчет процентов снижения
            tasks_decline_percent = 0.0
            calls_decline_percent = 0.0
            
            if previous_tasks > 0:
                tasks_decline_percent = ((previous_tasks - current_tasks) / previous_tasks) * 100
            elif current_tasks == 0 and previous_tasks == 0:
                tasks_decline_percent = 0.0
            else:
                tasks_decline_percent = 0.0
            
            if previous_calls > 0:
                calls_decline_percent = ((previous_calls - current_calls) / previous_calls) * 100
            elif current_calls == 0 and previous_calls == 0:
                calls_decline_percent = 0.0
            else:
                calls_decline_percent = 0.0
            
            # Проверка критериев снижения активности
            reasons = []
            has_decline = False
            
            if tasks_decline_percent >= 30.0:
                reasons.append(f"Задачи упали на {tasks_decline_percent:.1f}%")
                has_decline = True
            
            if calls_decline_percent >= 25.0:
                reasons.append(f"Звонки снизились на {calls_decline_percent:.1f}%")
                has_decline = True
            
            # Если менеджер снизил активность, добавляем в список
            if has_decline:
                managers_with_decline.append({
                    'manager_id': manager_id,
                    'name': manager_name,
                    'email': manager_email,
                    'work_position': manager_position,
                    'current_week': {
                        'tasks': current_tasks,
                        'calls': current_calls
                    },
                    'previous_week': {
                        'tasks': previous_tasks,
                        'calls': previous_calls
                    },
                    'decline': {
                        'tasks_percent': round(tasks_decline_percent, 1),
                        'calls_percent': round(calls_decline_percent, 1)
                    },
                    'reasons': reasons
                })
        
        logger.info(
            f"Анализ завершен: проверено {len(managers)} менеджеров, "
            f"снижение активности у {len(managers_with_decline)}"
        )
        
        # Если запрошен текстовый формат, форматируем результат
        if isText:
            if not managers_with_decline:
                return (
                    f"=== Менеджеры со сниженной активностью ===\n\n"
                    f"Всего проверено менеджеров: {len(managers)}\n"
                    f"Менеджеров со сниженной активностью: 0\n\n"
                    f"Период анализа:\n"
                    f"  Текущая неделя: {current_week_start} - {current_week_end}\n"
                    f"  Предыдущая неделя: {previous_week_start} - {previous_week_end}\n\n"
                    f"Снижения активности не обнаружено."
                )
            
            result_text = f"=== Менеджеры со сниженной активностью ===\n\n"
            result_text += f"Всего проверено менеджеров: {len(managers)}\n"
            result_text += f"Менеджеров со сниженной активностью: {len(managers_with_decline)}\n\n"
            result_text += f"Период анализа:\n"
            result_text += f"  Текущая неделя: {current_week_start} - {current_week_end}\n"
            result_text += f"  Предыдущая неделя: {previous_week_start} - {previous_week_end}\n\n"
            
            for idx, manager_info in enumerate(managers_with_decline, 1):
                result_text += f"{idx}. {manager_info['name']}"
                if manager_info.get('work_position'):
                    result_text += f" ({manager_info['work_position']})"
                result_text += f"\n"
                
                if manager_info.get('email'):
                    result_text += f"   Email: {manager_info['email']}\n"
                result_text += f"   ID менеджера: {manager_info['manager_id']}\n\n"
                
                result_text += f"   Текущая неделя ({current_week_start} - {current_week_end}):\n"
                result_text += f"     • Задачи: {manager_info['current_week']['tasks']}\n"
                result_text += f"     • Звонки: {manager_info['current_week']['calls']}\n\n"
                
                result_text += f"   Предыдущая неделя ({previous_week_start} - {previous_week_end}):\n"
                result_text += f"     • Задачи: {manager_info['previous_week']['tasks']}\n"
                result_text += f"     • Звонки: {manager_info['previous_week']['calls']}\n\n"
                
                result_text += f"   Снижение активности:\n"
                if manager_info['decline']['tasks_percent'] > 0:
                    result_text += f"     • Задачи упали на {manager_info['decline']['tasks_percent']:.1f}%\n"
                if manager_info['decline']['calls_percent'] > 0:
                    result_text += f"     • Звонки снизились на {manager_info['decline']['calls_percent']:.1f}%\n"
                
                result_text += f"   Причины снижения:\n"
                for reason in manager_info['reasons']:
                    result_text += f"     • {reason}\n"
                
                result_text += "\n"
            
            return result_text
        
        # Возвращаем структурированный словарь
        return {
            'period': {
                'current_week_start': current_week_start,
                'current_week_end': current_week_end,
                'previous_week_start': previous_week_start,
                'previous_week_end': previous_week_end
            },
            'managers': managers_with_decline,
            'summary': {
                'total_checked': len(managers),
                'with_decline': len(managers_with_decline)
            }
        }
        
    except Exception as e:
        logger.error(f"Ошибка при выявлении менеджеров со сниженной активностью: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(get_managers_with_declined_activity())
    from pprint import pprint
    pprint(result)

