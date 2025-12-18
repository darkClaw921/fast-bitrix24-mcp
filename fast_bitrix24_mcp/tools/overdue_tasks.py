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
    get_tasks_by_filter
)

mcp = FastMCP("overdue_tasks")


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


@mcp.tool()
async def get_managers_with_overdue_tasks(
    filter_fields: dict[str, str] = None, 
    exclude_manager_ids: list[int] = [61],
    include_manager_ids: list[int] = None,
    isText: bool = True
) -> str | dict:
    """Получение менеджеров с просроченными задачами
    
    Задача считается просроченной, если:
    • есть поле DEADLINE;
    • DEADLINE < текущего времени (UTC);
    • статус не завершен (STATUS != '5').
    
    Args:
        filter_fields: Дополнительные фильтры для задач (например, по группе, приоритету). По умолчанию None
        exclude_manager_ids: Список ID менеджеров для исключения из анализа. По умолчанию None. Если указан, эти менеджеры будут исключены из анализа
        include_manager_ids: Список ID менеджеров для включения в анализ. По умолчанию None. Если не указан, анализируются все активные менеджеры (кроме тех, кто в exclude_manager_ids). Если указан, анализируются только указанные менеджеры (исключая тех, кто в exclude_manager_ids)
        isText: Если True (по умолчанию), возвращает человекочитаемый текст; если False, возвращает структурированный словарь
    
    Returns:
        Если isText=True — текстовая строка со списком менеджеров с просроченными задачами
        Если isText=False — словарь с данными менеджеров с просроченными задачами
    """
    try:
        # Устанавливаем значения по умолчанию
        if filter_fields is None:
            filter_fields = {}
        else:
            # Создаем копию, чтобы не изменять оригинальный словарь
            filter_fields = dict(filter_fields)
        
        if exclude_manager_ids is None:
            exclude_manager_ids = []
            exclude_manager_ids_set = set()
        else:
            # Создаем копию списка
            exclude_manager_ids = list(exclude_manager_ids)
            # Преобразуем в set для быстрого поиска
            exclude_manager_ids_set = set(exclude_manager_ids)
        
        # Сохраняем оригинальное значение для сообщений об ошибках
        original_include_manager_ids = include_manager_ids
        
        if include_manager_ids is None or (isinstance(include_manager_ids, list) and len(include_manager_ids) == 0):
            include_manager_ids_set = None
        else:
            # Создаем копию списка и преобразуем в set для быстрого поиска
            include_manager_ids = list(include_manager_ids)
            include_manager_ids_set = set(include_manager_ids)
            logger.info(f"Будут анализироваться только указанные менеджеры: {include_manager_ids}")
        
        # Получаем всех активных менеджеров
        logger.info("Получение списка всех активных менеджеров")
        all_users = await get_users_by_filter({'ACTIVE': 'Y'})
        
        if not isinstance(all_users, list):
            if isinstance(all_users, dict) and all_users.get('order0000000000'):
                all_users = all_users['order0000000000']
            else:
                all_users = []
        
        if not all_users:
            if isText:
                return "Активные менеджеры не найдены."
            return {
                'managers_with_overdue_tasks': [],
                'summary': {
                    'total_checked': 0,
                    'with_overdue_tasks': 0
                }
            }
        
        # Формируем словарь менеджеров и фильтруем по include/exclude
        # Логика: если include_manager_ids не указан, анализируются все менеджеры (кроме exclude_manager_ids)
        # Если include_manager_ids указан, анализируются только указанные менеджеры (кроме exclude_manager_ids)
        manager_dict = {}
        for user in all_users:
            user_id = user.get('ID')
            if not user_id:
                continue
            
            try:
                user_id_int = int(user_id)
                
                # Если указан include_manager_ids, проверяем, что менеджер в списке
                # Если не указан, пропускаем эту проверку (анализируем всех)
                if include_manager_ids_set is not None:
                    if user_id_int not in include_manager_ids_set:
                        logger.debug(f"Менеджер {user_id_int} не включен в список для анализа")
                        continue
                
                # Пропускаем исключаемых менеджеров (применяется всегда, независимо от include_manager_ids)
                if user_id_int in exclude_manager_ids_set:
                    logger.info(f"Менеджер {user_id_int} исключен из анализа")
                    continue
                
                # Формируем имя менеджера
                name_parts = [
                    user.get('NAME', ''),
                    user.get('LAST_NAME', ''),
                    user.get('SECOND_NAME', '')
                ]
                manager_name = ' '.join([p for p in name_parts if p]).strip() or f'Пользователь #{user_id}'
                
                manager_dict[user_id_int] = {
                    'manager_id': user_id_int,
                    'manager_name': manager_name,
                    'manager_email': user.get('EMAIL', ''),
                    'overdue_tasks': []
                }
            except (ValueError, TypeError):
                pass
        
        if not manager_dict:
            if isText:
                if include_manager_ids_set is not None:
                    return f"Менеджеры для анализа не найдены. Проверьте список include_manager_ids: {list(include_manager_ids_set)} (возможно, указанные менеджеры не активны или все исключены через exclude_manager_ids)."
                return "Менеджеры для анализа не найдены (возможно, все исключены)."
            return {
                'managers_with_overdue_tasks': [],
                'summary': {
                    'total_checked': 0,
                    'with_overdue_tasks': 0
                }
            }
        
        logger.info(f"Найдено {len(manager_dict)} менеджеров для анализа")
        
        # Оптимизация: если указан include_manager_ids и менеджеров немного, делаем параллельные запросы
        # Это быстрее, чем получать все задачи одним запросом
        manager_ids_list = list(manager_dict.keys())
        
        if include_manager_ids_set is not None and len(manager_ids_list) <= 50:
            # Оптимизация: параллельные запросы по каждому менеджеру
            logger.info(f"Оптимизация: параллельные запросы для {len(manager_ids_list)} менеджеров")
            
            async def get_tasks_for_manager(manager_id: int):
                manager_filter = dict(filter_fields) if filter_fields else {}
                manager_filter['RESPONSIBLE_ID'] = str(manager_id)
                return await get_tasks_by_filter(
                    manager_filter,
                    select_fields=['ID', 'TITLE', 'STATUS', 'DEADLINE', 'RESPONSIBLE_ID', 'CREATED_DATE']
                )
            
            # Выполняем запросы параллельно
            tasks_results = await asyncio.gather(*[get_tasks_for_manager(mid) for mid in manager_ids_list])
            
            # Объединяем результаты
            all_tasks = []
            for tasks in tasks_results:
                if isinstance(tasks, list):
                    all_tasks.extend(tasks)
                elif isinstance(tasks, dict) and tasks.get('order0000000000'):
                    all_tasks.extend(tasks['order0000000000'])
            
            logger.info(f"Получено задач через параллельные запросы: {len(all_tasks)}")
        else:
            # Стандартный подход: один запрос для всех задач
            optimized_filter = dict(filter_fields) if filter_fields else {}
            logger.info(f"Получение всех задач с фильтрами: {optimized_filter}")
            all_tasks = await get_tasks_by_filter(
                optimized_filter,
                select_fields=['ID', 'TITLE', 'STATUS', 'DEADLINE', 'RESPONSIBLE_ID', 'CREATED_DATE']
            )
        
        if not isinstance(all_tasks, list):
            all_tasks = []
        
        logger.info(f"Получено задач: {len(all_tasks)}")
        
        # Проверяем каждую задачу на просроченность
        now_utc = datetime.now(timezone.utc)
        managers_with_overdue = {}
        
        # Предварительная фильтрация: создаем set ID менеджеров для быстрой проверки
        manager_ids_set = set(manager_dict.keys())
        
        for task in all_tasks:
            # Ранняя фильтрация: пропускаем задачи без DEADLINE или завершенные задачи
            deadline_str = task.get('DEADLINE') or task.get('deadline')
            status = str(task.get('STATUS') or task.get('status', ''))
            
            # Пропускаем задачи без дедлайна или завершенные задачи (не проверяем их)
            if not deadline_str or status == '5':
                continue
            
            responsible_id = task.get('RESPONSIBLE_ID') or task.get('responsibleId')
            if not responsible_id:
                continue
            
            try:
                responsible_id_int = int(responsible_id)
                
                # Быстрая проверка через set (O(1) вместо O(n))
                if responsible_id_int not in manager_ids_set:
                    continue
                
                # Проверяем просроченность задачи
                # Задача считается просроченной, если:
                # 1. Есть DEADLINE (уже проверили выше)
                # 2. DEADLINE < текущего времени
                # 3. Статус не завершен (STATUS != '5') (уже проверили выше)
                try:
                    deadline_dt = _parse_datetime_from_bitrix(deadline_str)
                    if deadline_dt < now_utc:
                        # Задача просрочена
                        task_id = task.get('ID') or task.get('id', 'N/A')
                        task_title = task.get('TITLE') or task.get('title', 'Без названия')
                        
                        # Вычисляем количество дней просрочки
                        overdue_delta = now_utc - deadline_dt
                        overdue_days = overdue_delta.days
                        
                        if responsible_id_int not in managers_with_overdue:
                            managers_with_overdue[responsible_id_int] = {
                                'manager_id': responsible_id_int,
                                'manager_name': manager_dict[responsible_id_int]['manager_name'],
                                'manager_email': manager_dict[responsible_id_int]['manager_email'],
                                'overdue_tasks': []
                            }
                        
                        managers_with_overdue[responsible_id_int]['overdue_tasks'].append({
                            'task_id': task_id,
                            'task_title': task_title,
                            'deadline': deadline_dt,
                            'overdue_days': overdue_days
                        })
                except Exception as e:
                    logger.warning(f"Ошибка при проверке просроченности задачи {task.get('ID')}: {e}")
            except (ValueError, TypeError):
                pass
        
        # Сортируем задачи по количеству дней просрочки (от большего к меньшему)
        for manager_id in managers_with_overdue:
            managers_with_overdue[manager_id]['overdue_tasks'].sort(
                key=lambda x: x['overdue_days'], 
                reverse=True
            )
        
        # Формируем результат
        if not managers_with_overdue:
            if isText:
                return f"Менеджеров с просроченными задачами не найдено. Проверено менеджеров: {len(manager_dict)}."
            return {
                'managers_with_overdue_tasks': [],
                'summary': {
                    'total_checked': len(manager_dict),
                    'with_overdue_tasks': 0
                }
            }
        
        # Сортируем менеджеров по количеству просроченных задач (от большего к меньшему)
        sorted_managers = sorted(
            managers_with_overdue.items(),
            key=lambda x: len(x[1]['overdue_tasks']),
            reverse=True
        )
        
        if isText:
            result_text = f"=== Менеджеры с просроченными задачами ===\n\n"
            result_text += f"Всего проверено менеджеров: {len(manager_dict)}\n"
            result_text += f"Менеджеров с просроченными задачами: {len(managers_with_overdue)}\n\n"
            
            for idx, (manager_id, manager_info) in enumerate(sorted_managers, 1):
                result_text += f"{idx}. {manager_info['manager_name']} (ID: {manager_info['manager_id']})\n"
                # if manager_info['manager_email']:
                    # result_text += f"   Email: {manager_info['manager_email']}\n"
                
                overdue_count = len(manager_info['overdue_tasks'])
                result_text += f"   Просроченных задач: {overdue_count}\n"
                result_text += f"   Просроченные задачи:\n"
                
                for task_info in manager_info['overdue_tasks']:
                    deadline_str = task_info['deadline'].strftime('%Y-%m-%d %H:%M:%S')
                    overdue_days = task_info['overdue_days']
                    result_text += f"     • Задача #{task_info['task_id']} - {task_info['task_title']} (просрочена на {overdue_days} дн., DEADLINE: {deadline_str})\n"
                
                result_text += "\n"
            
            return result_text
        else:
            # Формируем структурированный словарь
            managers_list = []
            for manager_id, manager_info in sorted_managers:
                tasks_list = []
                for task_info in manager_info['overdue_tasks']:
                    tasks_list.append({
                        'task_id': task_info['task_id'],
                        'task_title': task_info['task_title'],
                        'deadline': task_info['deadline'].strftime('%Y-%m-%d %H:%M:%S'),
                        'overdue_days': task_info['overdue_days']
                    })
                
                managers_list.append({
                    'manager_id': manager_info['manager_id'],
                    'manager_name': manager_info['manager_name'],
                    'manager_email': manager_info['manager_email'],
                    'overdue_tasks_count': len(manager_info['overdue_tasks']),
                    'overdue_tasks': tasks_list
                })
            
            return {
                'managers_with_overdue_tasks': managers_list,
                'summary': {
                    'total_checked': len(manager_dict),
                    'with_overdue_tasks': len(managers_with_overdue)
                }
            }
        
    except Exception as e:
        logger.error(f"Ошибка при получении менеджеров с просроченными задачами: {e}")
        if isText:
            return f"Ошибка при получении менеджеров с просроченными задачами: {str(e)}"
        return {
            'error': str(e),
            'managers_with_overdue_tasks': [],
            'summary': {
                'total_checked': 0,
                'with_overdue_tasks': 0
            }
        }

