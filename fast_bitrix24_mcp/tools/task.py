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
from .userfields import get_all_info_fields
from .bitrixWork import (
    bit, 
    get_task_by_id, 
    get_tasks_by_filter, 
    create_task, 
    update_task, 
    delete_task,
    get_task_comments,
    add_task_comment,
    update_task_comment,
    delete_task_comment,
    get_task_checklist,
    add_checklist_item,
    delete_checklist_item,
    get_task_elapsed_time,
    add_elapsed_time,
    delete_elapsed_time
)
from .helper import prepare_fields_to_humman_format, export_entities_to_json, analyze_export_file

WEBHOOK = os.getenv("WEBHOOK")

mcp = FastMCP("tasks")


@mcp.tool()
async def list_tasks(filter_fields: dict[str, str] = {}, fields_id: list[str] = ["ID", "TITLE"], order: dict[str, str] = {"ID": "DESC"}) -> str:
    """Список задач 
    filter_fields: dict[str, str] поля для фильтрации задач
    Доступные поля для фильтра:
    - ID: идентификатор задачи
    - TITLE: название задачи
    - DESCRIPTION: описание задачи  
    - STATUS: статус задачи (1-новая, 2-ждёт выполнения, 3-выполняется, 4-ждёт контроля, 5-завершена, 6-отложена, 7-отклонена)
    - PRIORITY: приоритет (1-низкий, 2-обычный, 3-высокий)
    - RESPONSIBLE_ID: исполнитель
    - CREATED_BY: постановщик
    - GROUP_ID: рабочая группа
    - STAGE_ID: стадия канбан
    - CREATED_DATE: дата создания (поддерживает операторы >=, <=, >, <)
    - CLOSED_DATE: дата завершения
    - DEADLINE: крайний срок
    - START_DATE_PLAN: планируемая дата начала
    - END_DATE_PLAN: планируемая дата завершения
    
    Примеры фильтрации:
    {
        "TITLE": "test",
        "STATUS": "3",
        ">=CREATED_DATE": "2025-01-01",
        "RESPONSIBLE_ID": "1"
    }
    
    fields_id: list[str] id всех полей которые нужно получить, если ["*"] то все поля
    Основные поля: ID, TITLE, DESCRIPTION, STATUS, PRIORITY, RESPONSIBLE_ID, CREATED_BY, 
    CREATED_DATE, CLOSED_DATE, DEADLINE, START_DATE_PLAN, END_DATE_PLAN, GROUP_ID, STAGE_ID
    
    order: dict[str, str] сортировка, например {"ID": "DESC"} или {"CREATED_DATE": "ASC"}
    """
    
    all_info_fields = await get_all_info_fields(['task'], isText=False)
    all_info_fields = all_info_fields['task']
    
    prepare_tasks = []
    if '*' not in fields_id:     
        fields_id.append('ID')
        
    if fields_id == ["*"]:
        fields_id = ["*", "UF_*"]
    
    tasks = await get_tasks_by_filter(filter_fields, fields_id, order)
    
    if not tasks:
        return "Задачи не найдены"
    
    text = ''
    for task in tasks:
        text += f'== ID: {task.get("id", task.get("ID", "N/A"))} - {task.get("title", task.get("TITLE", "Без названия"))} ==\n'
        prepare_task = prepare_fields_to_humman_format(task, all_info_fields)
        for key, value in prepare_task.items():
            text += f'  {key}: {value}\n'
        text += '\n'
    
    return text


@mcp.tool()
async def get_task(task_id: int) -> str:
    """Получить детальную информацию о задаче по ID
    task_id: int - идентификатор задачи
    """
    try:
        task = await get_task_by_id(task_id)
        if not task:
            return f"Задача с ID {task_id} не найдена"
            
        all_info_fields = await get_all_info_fields(['task'], isText=False)
        all_info_fields = all_info_fields['task']
        
        prepare_task = prepare_fields_to_humman_format(task, all_info_fields)
        
        text = f'== ЗАДАЧА ID: {task_id} ==\n'
        for key, value in prepare_task.items():
            text += f'{key}: {value}\n'
            
        return text
    except Exception as e:
        return f"Ошибка при получении задачи {task_id}: {str(e)}"


# @mcp.tool()
async def create_new_task(fields: dict[str, Any]) -> str:
    """Создать новую задачу
    fields: dict[str, Any] - поля задачи
    Обязательные поля:
    - TITLE: название задачи
    - RESPONSIBLE_ID: ID исполнителя
    
    Опциональные поля:
    - DESCRIPTION: описание задачи
    - DEADLINE: крайний срок (формат: YYYY-MM-DD или YYYY-MM-DD HH:MM:SS)
    - START_DATE_PLAN: планируемая дата начала
    - END_DATE_PLAN: планируемая дата завершения  
    - PRIORITY: приоритет (1-низкий, 2-обычный, 3-высокий)
    - GROUP_ID: ID рабочей группы
    - PARENT_ID: ID родительской задачи
    - DEPENDS_ON: массив ID задач, от которых зависит данная
    - UF_CRM_TASK: связь с CRM (["L_4", "C_7", "CO_5", "D_10"] для связи с лидом, контактом, компанией, сделкой)
    
    Пример:
    {
        "TITLE": "Новая задача",
        "DESCRIPTION": "Описание задачи", 
        "RESPONSIBLE_ID": 1,
        "DEADLINE": "2025-12-31",
        "PRIORITY": 2
    }
    """
    try:
        if 'TITLE' not in fields:
            return "Ошибка: поле TITLE обязательно для создания задачи"
        if 'RESPONSIBLE_ID' not in fields:
            return "Ошибка: поле RESPONSIBLE_ID обязательно для создания задачи"
            
        result = await create_task(fields)
        
        # task_data = result.get('task', {})
        task_id = result.get('id', 'неизвестно')
        
        return f"Задача успешно создана с ID: {task_id}"
    except Exception as e:
        return f"Ошибка при создании задачи: {str(e)}"


# @mcp.tool()
async def update_existing_task(task_id: int, fields: dict[str, Any]) -> str:
    """Обновить существующую задачу
    task_id: int - идентификатор задачи
    fields: dict[str, Any] - поля для обновления
    
    Поля для обновления:
    - TITLE: название задачи
    - DESCRIPTION: описание задачи
    - RESPONSIBLE_ID: ID исполнителя
    - STATUS: статус задачи (1-новая, 2-ждёт выполнения, 3-выполняется, 4-ждёт контроля, 5-завершена, 6-отложена, 7-отклонена)
    - PRIORITY: приоритет (1-низкий, 2-обычный, 3-высокий)
    - DEADLINE: крайний срок
    - START_DATE_PLAN: планируемая дата начала
    - END_DATE_PLAN: планируемая дата завершения
    - UF_CRM_TASK: связь с CRM
    
    Пример:
    {
        "TITLE": "Обновленное название",
        "STATUS": 3,
        "PRIORITY": 3
    }
    """
    try:
        result = await update_task(task_id, fields)
        return f"Задача {task_id} успешно обновлена"
    except Exception as e:
        return f"Ошибка при обновлении задачи {task_id}: {str(e)}"


# @mcp.tool()
async def delete_existing_task(task_id: int) -> str:
    """Удалить задачу
    task_id: int - идентификатор задачи
    """
    try:
        result = await delete_task(task_id)
        return f"Задача {task_id} успешно удалена"
    except Exception as e:
        return f"Ошибка при удалении задачи {task_id}: {str(e)}"


@mcp.tool()
async def get_task_comments_list(task_id: int) -> str:
    """Получить список комментариев к задаче
    task_id: int - идентификатор задачи
    """
    try:
        comments = await get_task_comments(task_id)
        if not comments:
            return f"У задачи {task_id} нет комментариев"
            
        text = f'== КОММЕНТАРИИ К ЗАДАЧЕ {task_id} ==\n'
        for comment in comments:
            author_id = comment.get('AUTHOR_ID', 'неизвестно')
            message = comment.get('POST_MESSAGE', '')
            date = comment.get('POST_DATE', '')
            comment_id = comment.get('ID', '')
            
            text += f'Комментарий ID: {comment_id}\n'
            text += f'Автор: {author_id}\n'
            text += f'Дата: {date}\n'
            text += f'Сообщение: {message}\n'
            text += '---\n'
            
        return text
    except Exception as e:
        return f"Ошибка при получении комментариев к задаче {task_id}: {str(e)}"


# @mcp.tool()
async def add_comment_to_task(task_id: int, message: str, author_id: Optional[int] = None) -> str:
    """Добавить комментарий к задаче
    task_id: int - идентификатор задачи
    message: str - текст комментария
    author_id: Optional[int] - ID автора комментария (если не указан, будет использован текущий пользователь)
    """
    try:
        fields = {'POST_MESSAGE': message}
        if author_id:
            fields['AUTHOR_ID'] = str(author_id)
            
        result = await add_task_comment(task_id, fields)
        return f"Комментарий добавлен к задаче {task_id}"
    except Exception as e:
        return f"Ошибка при добавлении комментария к задаче {task_id}: {str(e)}"


# @mcp.tool()
async def update_comment_in_task(task_id: int, comment_id: int, message: str) -> str:
    """Обновить комментарий к задаче
    task_id: int - идентификатор задачи
    comment_id: int - идентификатор комментария
    message: str - новый текст комментария
    """
    try:
        fields = {'POST_MESSAGE': message}
        result = await update_task_comment(task_id, comment_id, fields)
        return f"Комментарий {comment_id} к задаче {task_id} обновлен"
    except Exception as e:
        return f"Ошибка при обновлении комментария {comment_id} к задаче {task_id}: {str(e)}"


# @mcp.tool()
async def delete_comment_from_task(task_id: int, comment_id: int) -> str:
    """Удалить комментарий к задаче
    task_id: int - идентификатор задачи  
    comment_id: int - идентификатор комментария
    """
    try:
        result = await delete_task_comment(task_id, comment_id)
        return f"Комментарий {comment_id} к задаче {task_id} удален"
    except Exception as e:
        return f"Ошибка при удалении комментария {comment_id} к задаче {task_id}: {str(e)}"


@mcp.tool()
async def get_task_checklist_items(task_id: int) -> str:
    """Получить чеклист задачи
    task_id: int - идентификатор задачи
    """
    try:
        checklist = await get_task_checklist(task_id)
        if not checklist:
            return f"У задачи {task_id} нет чеклиста"
            
        text = f'== ЧЕКЛИСТ ЗАДАЧИ {task_id} ==\n'
        for item in checklist:
            item_id = item.get('ID', '')
            title = item.get('TITLE', '')
            is_complete = item.get('IS_COMPLETE', 'N')
            status = 'Выполнено' if is_complete == 'Y' else 'Не выполнено'
            
            text += f'Пункт ID: {item_id}\n'
            text += f'Название: {title}\n'
            text += f'Статус: {status}\n'
            text += '---\n'
            
        return text
    except Exception as e:
        return f"Ошибка при получении чеклиста задачи {task_id}: {str(e)}"


# @mcp.tool()
async def add_checklist_item_to_task(task_id: int, title: str, is_complete: bool = False) -> str:
    """Добавить пункт в чеклист задачи
    task_id: int - идентификатор задачи
    title: str - название пункта чеклиста
    is_complete: bool - выполнен ли пункт (по умолчанию False)
    """
    try:
        fields = {
            'TITLE': title,
            'IS_COMPLETE': 'Y' if is_complete else 'N'
        }
        result = await add_checklist_item(task_id, fields)
        return f"Пункт '{title}' добавлен в чеклист задачи {task_id}"
    except Exception as e:
        return f"Ошибка при добавлении пункта в чеклист задачи {task_id}: {str(e)}"


# @mcp.tool()
async def delete_checklist_item_from_task(task_id: int, item_id: int) -> str:
    """Удалить пункт из чеклиста задачи
    task_id: int - идентификатор задачи
    item_id: int - идентификатор пункта чеклиста
    """
    try:
        result = await delete_checklist_item(task_id, item_id)
        return f"Пункт {item_id} удален из чеклиста задачи {task_id}"
    except Exception as e:
        return f"Ошибка при удалении пункта {item_id} из чеклиста задачи {task_id}: {str(e)}"


@mcp.tool()
async def get_task_time_tracking(task_id: int) -> str:
    """Получить записи о затраченном времени по задаче
    task_id: int - идентификатор задачи
    """
    try:
        elapsed = await get_task_elapsed_time(task_id)
        if not elapsed:
            return f"У задачи {task_id} нет записей о времени"
            
        text = f'== ЗАТРАЧЕННОЕ ВРЕМЯ ПО ЗАДАЧЕ {task_id} ==\n'
        total_seconds = 0
        
        for item in elapsed:
            item_id = item.get('ID', '')
            user_id = item.get('USER_ID', '')
            seconds = int(item.get('SECONDS', 0))
            comment = item.get('COMMENT_TEXT', '')
            date = item.get('CREATED_DATE', '')
            
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            seconds_remainder = seconds % 60
            
            total_seconds += seconds
            
            text += f'Запись ID: {item_id}\n'
            text += f'Пользователь: {user_id}\n'
            text += f'Время: {hours}ч {minutes}м {seconds_remainder}с\n'
            text += f'Комментарий: {comment}\n'
            text += f'Дата: {date}\n'
            text += '---\n'
            
        # Общее время
        total_hours = total_seconds // 3600
        total_minutes = (total_seconds % 3600) // 60
        total_seconds_remainder = total_seconds % 60
        
        text += f'\nОБЩЕЕ ВРЕМЯ: {total_hours}ч {total_minutes}м {total_seconds_remainder}с\n'
            
        return text
    except Exception as e:
        return f"Ошибка при получении времени выполнения задачи {task_id}: {str(e)}"


# @mcp.tool()
async def add_time_to_task(task_id: int, seconds: int, comment: str = "", user_id: Optional[int] = None) -> str:
    """Добавить запись о затраченном времени к задаче
    task_id: int - идентификатор задачи
    seconds: int - затраченное время в секундах
    comment: str - комментарий к записи времени
    user_id: Optional[int] - ID пользователя (если не указан, будет использован текущий)
    """
    try:
        fields = {
            'SECONDS': seconds,
            'COMMENT_TEXT': comment
        }
        if user_id:
            fields['USER_ID'] = user_id
            
        result = await add_elapsed_time(task_id, fields)
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds_remainder = seconds % 60
        
        return f"Добавлено время к задаче {task_id}: {hours}ч {minutes}м {seconds_remainder}с"
    except Exception as e:
        return f"Ошибка при добавлении времени к задаче {task_id}: {str(e)}"


# @mcp.tool()
async def delete_time_from_task(task_id: int, item_id: int) -> str:
    """Удалить запись о затраченном времени
    task_id: int - идентификатор задачи
    item_id: int - идентификатор записи времени
    """
    try:
        result = await delete_elapsed_time(task_id, item_id)
        return f"Запись времени {item_id} удалена из задачи {task_id}"
    except Exception as e:
        return f"Ошибка при удалении записи времени {item_id} из задачи {task_id}: {str(e)}"



if __name__ == "__main__":
    # Тест функций
    # asyncio.run(list_tasks())
    pass