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
    get_users_by_filter,
    get_crm_activities_by_filter,
    get_tasks_by_filter,
    get_deals_by_filter
)

mcp = FastMCP("manager_support")

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


async def _get_all_managers_data_batch(
    days: int = 30,
    production_stage_id: str = None
) -> dict:
    """Получение данных всех менеджеров батчами (оптимизированная версия)
    
    Получает все данные одним набором запросов вместо последовательных вызовов для каждого менеджера.
    Это значительно ускоряет работу при большом количестве менеджеров.
    
    Args:
        days: Количество дней для анализа активности (по умолчанию 30)
        production_stage_id: ID стадии "передано в производство" для проверки сделок (опционально)
    
    Returns:
        Словарь {manager_id: manager_data}, где manager_data имеет структуру:
        {
            'manager_id': int,
            'manager_name': str,
            'manager_email': str,
            'overdue_tasks_count': int,
            'total_activities': int,
            'calls_count': int,
            'production_deals_count': int,
            'tasks': list,  # Все задачи менеджера
            'activities': list,  # Все активности менеджера
            'deals': list  # Все сделки менеджера
        }
    """
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    from_date_iso = f"{from_date}T00:00:00"
    
    # Инициализируем результат
    result = {}
    
    try:
        # Шаг 1: Получаем всех активных менеджеров
        logger.info("Получение списка всех менеджеров")
        all_users = await get_users_by_filter({'ACTIVE': 'Y'})
        
        if not isinstance(all_users, list):
            if isinstance(all_users, dict) and all_users.get('order0000000000'):
                all_users = all_users['order0000000000']
            else:
                all_users = []
        
        # Инициализируем результат для всех менеджеров
        manager_ids = []
        for user in all_users:
            user_id = user.get('ID')
            if user_id:
                try:
                    user_id_int = int(user_id)
                    manager_ids.append(user_id_int)
                    
                    # Формируем имя менеджера
                    name_parts = [
                        user.get('NAME', ''),
                        user.get('LAST_NAME', ''),
                        user.get('SECOND_NAME', '')
                    ]
                    manager_name = ' '.join([p for p in name_parts if p]).strip() or f'Пользователь #{user_id}'
                    
                    result[user_id_int] = {
                        'manager_id': user_id_int,
                        'manager_name': manager_name,
                        'manager_email': user.get('EMAIL', ''),
                        'overdue_tasks_count': 0,
                        'total_activities': 0,
                        'calls_count': 0,
                        'production_deals_count': 0,
                        'tasks': [],
                        'activities': [],
                        'deals': []
                    }
                except (ValueError, TypeError):
                    pass
        
        if not manager_ids:
            logger.warning("Не найдено активных менеджеров")
            return result
        
        logger.info(f"Найдено {len(manager_ids)} активных менеджеров")
        
        # Шаг 2: Получаем все задачи за период одним запросом
        logger.info(f"Получение всех задач за период (с {from_date_iso})")
        tasks_filter = {
            '>=CREATED_DATE': from_date_iso
        }
        all_tasks = await get_tasks_by_filter(
            tasks_filter,
            select_fields=['ID', 'TITLE', 'STATUS', 'CREATED_DATE', 'DEADLINE', 'RESPONSIBLE_ID', 'CLOSED_DATE']
        )
        
        if not isinstance(all_tasks, list):
            all_tasks = []
        
        logger.info(f"Получено задач: {len(all_tasks)}")
        
        # Группируем задачи по менеджерам и проверяем просроченные
        now_utc = datetime.now(timezone.utc)
        for task in all_tasks:
            responsible_id = task.get('RESPONSIBLE_ID') or task.get('responsibleId')
            if not responsible_id:
                continue
            
            try:
                responsible_id_int = int(responsible_id)
                if responsible_id_int not in result:
                    continue
                
                # Добавляем задачу к менеджеру
                result[responsible_id_int]['tasks'].append(task)
                
                # Проверяем просроченность задачи
                # Задача считается просроченной, если:
                # 1. Есть DEADLINE
                # 2. DEADLINE < текущего времени
                # 3. Статус не завершен (STATUS != '5')
                deadline_str = task.get('DEADLINE') or task.get('deadline')
                status = str(task.get('STATUS') or task.get('status', ''))
                
                if deadline_str and status != '5':
                    try:
                        deadline_dt = _parse_datetime_from_bitrix(deadline_str)
                        if deadline_dt < now_utc:
                            result[responsible_id_int]['overdue_tasks_count'] += 1
                    except Exception:
                        pass
            except (ValueError, TypeError):
                pass
        
        # Шаг 3: Получаем все активности CRM за период одним запросом
        logger.info(f"Получение всех активностей CRM за период (с {from_date_iso})")
        activities_filter = {
            '>=CREATED': from_date_iso
        }
        all_activities = await get_crm_activities_by_filter(
            activities_filter,
            select_fields=['ID', 'TYPE_ID', 'CREATED', 'RESPONSIBLE_ID', 'DIRECTION']
        )
        
        if not isinstance(all_activities, list):
            all_activities = []
        
        logger.info(f"Получено активностей CRM: {len(all_activities)}")
        
        # Группируем активности по менеджерам
        for activity in all_activities:
            responsible_id = activity.get('RESPONSIBLE_ID')
            if not responsible_id:
                continue
            
            try:
                responsible_id_int = int(responsible_id)
                if responsible_id_int not in result:
                    continue
                
                # Добавляем активность к менеджеру
                result[responsible_id_int]['activities'].append(activity)
                result[responsible_id_int]['total_activities'] += 1
                
                # Подсчитываем звонки (TYPE_ID = '2')
                type_id = str(activity.get('TYPE_ID', ''))
                if type_id == '2':
                    result[responsible_id_int]['calls_count'] += 1
            except (ValueError, TypeError):
                pass
        
        # Шаг 4: Получаем все сделки за период одним запросом (если нужна проверка стадии производства)
        if production_stage_id:
            logger.info(f"Получение всех сделок за период (с {from_date_iso}) для проверки стадии производства")
            deals_filter = {
                '>=DATE_CREATE': from_date_iso
            }
            all_deals = await get_deals_by_filter(
                deals_filter,
                select_fields=['ID', 'TITLE', 'STAGE_ID', 'DATE_CREATE', 'ASSIGNED_BY_ID']
            )
            
            if not isinstance(all_deals, list):
                if isinstance(all_deals, dict) and all_deals.get('order0000000000'):
                    all_deals = all_deals['order0000000000']
                else:
                    all_deals = []
            
            logger.info(f"Получено сделок: {len(all_deals)}")
            
            # Группируем сделки по менеджерам и проверяем стадию производства
            for deal in all_deals:
                assigned_by_id = deal.get('ASSIGNED_BY_ID')
                stage_id = deal.get('STAGE_ID')
                
                if not assigned_by_id:
                    continue
                
                try:
                    assigned_by_id_int = int(assigned_by_id)
                    if assigned_by_id_int not in result:
                        continue
                    
                    # Добавляем сделку к менеджеру
                    result[assigned_by_id_int]['deals'].append(deal)
                    
                    # Проверяем стадию производства
                    if stage_id == production_stage_id:
                        result[assigned_by_id_int]['production_deals_count'] += 1
                except (ValueError, TypeError):
                    pass
        
        logger.info(f"Получены данные для {len(result)} менеджеров батчами")
        
    except Exception as e:
        logger.error(f"Ошибка при получении данных менеджеров батчами: {e}")
    
    return result


@mcp.tool()
async def get_managers_needing_support(
    days: int = 30,
    overdue_tasks_threshold: int = 5,
    low_activity_threshold: int = 10,
    low_calls_threshold: int = 5,
    production_stage_id: str = 'C3:WON',
    isText: bool = True
) -> dict | str:
    """Получение менеджеров, которым нужна помощь или поддержка
    
    Менеджер считается нуждающимся в поддержке, если выполняется одно или несколько условий:
    • много просроченных задач (больше или равно overdue_tasks_threshold);
    • мало активности (меньше low_activity_threshold активностей за период);
    • плохое качество звонков (меньше low_calls_threshold звонков за период);
    • нет сделок переданных в производство (если production_stage_id указан).
    
    Args:
        days: Количество дней для анализа активности (по умолчанию 30)
        overdue_tasks_threshold: Порог количества просроченных задач (по умолчанию 5)
        low_activity_threshold: Порог низкой активности (по умолчанию 10 активностей)
        low_calls_threshold: Порог низкого количества звонков (по умолчанию 5 звонков)
        production_stage_id: ID стадии "передано в производство" для проверки сделок (опционально)
        isText: Если True (по умолчанию), возвращает человекочитаемый текст; если False, возвращает структурированный словарь
    
    Returns:
        Если isText=False — словарь с данными менеджеров, нуждающихся в поддержке:
        {
            'period': {'days': 30},
            'thresholds': {
                'overdue_tasks': 5,
                'low_activity': 10,
                'low_calls': 5,
                'production_stage_id': '...' | None
            },
            'managers_needing_support': [
                {
                    'manager_id': int,
                    'manager_name': str,
                    'manager_email': str,
                    'reasons': list[str],  # Список причин, почему менеджер нуждается в поддержке
                    'metrics': {
                        'overdue_tasks_count': int,
                        'total_activities': int,
                        'calls_count': int,
                        'production_deals_count': int
                    }
                }
            ],
            'summary': {
                'total_checked': int,
                'needing_support': int
            }
        }
        Если isText=True — человекочитаемый текст с форматированным списком менеджеров
    """
    try:
        # Получаем данные всех менеджеров батчами
        logger.info(f"Получение данных всех менеджеров за {days} дней батчами")
        all_managers_data = await _get_all_managers_data_batch(
            days=days,
            production_stage_id=production_stage_id
        )
        
        if not all_managers_data:
            if isText:
                return "Менеджеры не найдены."
            return {
                'period': {'days': days},
                'thresholds': {
                    'overdue_tasks': overdue_tasks_threshold,
                    'low_activity': low_activity_threshold,
                    'low_calls': low_calls_threshold,
                    'production_stage_id': production_stage_id
                },
                'managers_needing_support': [],
                'summary': {
                    'total_checked': 0,
                    'needing_support': 0
                }
            }
        
        # Проверяем каждого менеджера на критерии
        managers_needing_support = []
        
        for manager_id, manager_data in all_managers_data.items():
            reasons = []
            
            # Проверка 1: Много просроченных задач
            if manager_data['overdue_tasks_count'] >= overdue_tasks_threshold:
                reasons.append(f"Много просроченных задач ({manager_data['overdue_tasks_count']} >= {overdue_tasks_threshold})")
            
            # Проверка 2: Мало активности
            if manager_data['total_activities'] < low_activity_threshold:
                reasons.append(f"Низкая активность ({manager_data['total_activities']} < {low_activity_threshold})")
            
            # Проверка 3: Мало звонков
            if manager_data['calls_count'] < low_calls_threshold:
                reasons.append(f"Мало звонков ({manager_data['calls_count']} < {low_calls_threshold})")
            
            # Проверка 4: Нет сделок в производстве (если стадия указана)
            if production_stage_id and manager_data['production_deals_count'] == 0:
                reasons.append(f"Нет сделок в производстве (стадия {production_stage_id})")
            
            # Если есть хотя бы одна причина, добавляем менеджера в список
            if reasons:
                managers_needing_support.append({
                    'manager_id': manager_id,
                    'manager_name': manager_data['manager_name'],
                    'manager_email': manager_data['manager_email'],
                    'reasons': reasons,
                    'metrics': {
                        'overdue_tasks_count': manager_data['overdue_tasks_count'],
                        'total_activities': manager_data['total_activities'],
                        'calls_count': manager_data['calls_count'],
                        'production_deals_count': manager_data['production_deals_count']
                    }
                })
        
        total_checked = len(all_managers_data)
        
        # Формируем результат
        if isText:
            if not managers_needing_support:
                return f"Менеджеров, нуждающихся в поддержке, не найдено. Проверено менеджеров: {total_checked}."
            
            result_text = f"=== Менеджеры, нуждающиеся в поддержке (период: {days} дней) ===\n\n"
            result_text += f"Всего проверено менеджеров: {total_checked}\n"
            result_text += f"Нуждающихся в поддержке: {len(managers_needing_support)}\n\n"
            result_text += f"Пороги:\n"
            result_text += f"  • Просроченные задачи: >= {overdue_tasks_threshold}\n"
            result_text += f"  • Низкая активность: < {low_activity_threshold}\n"
            result_text += f"  • Мало звонков: < {low_calls_threshold}\n"
            if production_stage_id:
                result_text += f"  • Стадия производства: {production_stage_id}\n"
            result_text += "\n"
            
            for idx, manager_info in enumerate(managers_needing_support, 1):
                result_text += f"{idx}. {manager_info['manager_name']} (ID: {manager_info['manager_id']})\n"
                if manager_info['manager_email']:
                    result_text += f"   Email: {manager_info['manager_email']}\n"
                
                result_text += f"   Причины:\n"
                for reason in manager_info['reasons']:
                    result_text += f"     • {reason}\n"
                
                metrics = manager_info['metrics']
                result_text += f"   Метрики:\n"
                result_text += f"     • Просроченных задач: {metrics['overdue_tasks_count']}\n"
                result_text += f"     • Всего активностей: {metrics['total_activities']}\n"
                result_text += f"     • Звонков: {metrics['calls_count']}\n"
                if production_stage_id:
                    result_text += f"     • Сделок в производстве: {metrics['production_deals_count']}\n"
                
                result_text += "\n"
            
            return result_text
        else:
            return {
                'period': {'days': days},
                'thresholds': {
                    'overdue_tasks': overdue_tasks_threshold,
                    'low_activity': low_activity_threshold,
                    'low_calls': low_calls_threshold,
                    'production_stage_id': production_stage_id
                },
                'managers_needing_support': managers_needing_support,
                'summary': {
                    'total_checked': total_checked,
                    'needing_support': len(managers_needing_support)
                }
            }
        
    except Exception as e:
        logger.error(f"Ошибка при получении менеджеров, нуждающихся в поддержке: {e}")
        if isText:
            return f"Ошибка при получении менеджеров, нуждающихся в поддержке: {str(e)}"
        return {
            'error': str(e),
            'period': {'days': days},
            'thresholds': {
                'overdue_tasks': overdue_tasks_threshold,
                'low_activity': low_activity_threshold,
                'low_calls': low_calls_threshold,
                'production_stage_id': production_stage_id
            },
            'managers_needing_support': [],
            'summary': {
                'total_checked': 0,
                'needing_support': 0
            }
        }

