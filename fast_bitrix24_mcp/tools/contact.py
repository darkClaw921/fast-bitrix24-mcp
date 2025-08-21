from .bitrixWork import bit, get_fields_by_user, get_contacts_by_filter
from mcp.server.fastmcp import FastMCP, Context
from pprint import pprint
from .userfields import get_all_info_fields
from .helper import prepare_fields_to_humman_format
import asyncio
mcp = FastMCP("contacts")




@mcp.tool()
async def list_contact(filter_fields: dict[str,str]={}, select_fields: list[str]=["*", "UF_*"]) -> dict:
    """Список контактов (клиентов)
    filter_fields: dict[str, str] поля для фильтрации контактов (клиентов) 
    example:
    {
        "TITLE": "test"
        ">=DATE_CREATE": "2025-06-09"
        "<CLOSEDATE": "2025-06-11"
    }
    select_fields: list[str] id всех полей которые нужно получить (в том числе и из фильтра), если * то все поля
    example:
    [
        "*",
        "UF_*"
    ]"""
    all_info_fields=await get_all_info_fields(['contact'], isText=False)
    all_info_fields=all_info_fields['contact']
    contacts = await get_contacts_by_filter(filter_fields, select_fields)
    text=''
    for contact in contacts:
        text+=f'=={contact["NAME"]}==\n'
        prepare_contact=prepare_fields_to_humman_format(contact, all_info_fields)
        for key, value in prepare_contact.items():
            text+=f'  {key}: {value}\n'
        text+='\n'
    return text


if __name__ == "__main__":
    a=asyncio.run(list_contact())
    pprint(a)