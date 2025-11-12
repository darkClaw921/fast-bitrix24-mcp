from .bitrixWork import bit, get_fields_by_user, get_users_by_filter, get_manager_full_activity, get_all_managers_activity
from mcp.server.fastmcp import FastMCP, Context
from pprint import pprint
from .userfields import get_all_info_fields
from .helper import prepare_fields_to_humman_format
import asyncio
import json
mcp = FastMCP("users")




@mcp.tool()
async def list_user(filter_fields: dict[str,str]={}) -> dict:
    """Список пользователей
    filter_fields: dict[str, str] поля для фильтрации пользователей 
    example:
    {
        "TITLE": "test",
        "!%LAST_NAME": "ов",
        "@PERSONAL_CITY": ["Москва", "Санкт-Петербург"]
    
    }
    """
    all_info_fields=await get_all_info_fields(['user'], isText=False)
    all_info_fields=all_info_fields['user']
    # pprint(all_info_fields)
    # userfields = await get_fields_by_user()
    users = await get_users_by_filter(filter_fields)
    text=''
    for user in users:
        text+=f'=={user["NAME"]}==\n'
        # pprint(user)
        prepare_user=prepare_fields_to_humman_format(user, all_info_fields)
        for key, value in prepare_user.items():
            text+=f'  {key}: {value}\n'
        text+='\n'
    return text


@mcp.tool()
async def get_user_activity(manager_id: int, days: int = 30) -> dict:
    """Получение полной активности пользователя за указанный период
    
    Возвращает детальную статистику активности менеджера:
    - Звонки (входящие, исходящие, пропущенные)
    - Встречи
    - Email-сообщения
    - Задачи (всего, завершено, в работе)
    - Сделки (создано, выиграно)
    - Лиды (создано, конвертировано)
    - События календаря
    - Комментарии во всех сущностях CRM
    
    Args:
        manager_id: ID пользователя/менеджера в Bitrix24
        days: Количество дней для анализа (по умолчанию 30)
    
    Returns:
        dict: Словарь с полной статистикой активности пользователя
    """
    activity = await get_manager_full_activity(manager_id, days)
    return activity


@mcp.tool()
async def get_all_managers_activity_report(days: int = 30, include_inactive: bool = True, only_inactive: bool = False) -> dict:
    """Получение активности всех менеджеров за указанный период с определением неактивных пользователей
    
    Возвращает детальную статистику активности всех менеджеров:
    - Общая статистика по всем менеджерам (звонки, встречи, email, задачи, сделки, лиды, комментарии)
    - Список активных менеджеров с детальной статистикой
    - Список неактивных менеджеров (без активности за период)
    
    Args:
        days: Количество дней для анализа (по умолчанию 30)
        include_inactive: Включать ли информацию о неактивных менеджерах (по умолчанию True)
        only_inactive: Если True, возвращает только список неактивных менеджеров без детальной статистики активных (по умолчанию False)
    
    Returns:
        dict: Словарь с общей статистикой, списком активных и неактивных менеджеров (или только неактивных, если only_inactive=True)
    """
    result = await get_all_managers_activity(days, include_inactive, only_inactive)
    return result


if __name__ == "__main__":
    a=asyncio.run(list_user())
    pprint(a)
    # mcp.run(transport="sse", host="0.0.0.0", port=8000)