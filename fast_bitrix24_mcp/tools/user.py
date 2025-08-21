from .bitrixWork import bit, get_fields_by_user, get_users_by_filter
from mcp.server.fastmcp import FastMCP, Context
from pprint import pprint
from .userfields import get_all_info_fields
from .helper import prepare_fields_to_humman_format
import asyncio
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
    pprint(all_info_fields)
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



if __name__ == "__main__":
    a=asyncio.run(list_user())
    pprint(a)
    # mcp.run(transport="sse", host="0.0.0.0", port=8000)