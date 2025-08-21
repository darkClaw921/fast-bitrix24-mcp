from .bitrixWork import bit, get_fields_by_user, get_companies_by_filter
from mcp.server.fastmcp import FastMCP, Context
from pprint import pprint
from .userfields import get_all_info_fields
from .helper import prepare_fields_to_humman_format
import asyncio
mcp = FastMCP("companies")




@mcp.tool()
async def list_company(filter_fields: dict[str,str]={}, select_fields: list[str]=["*", "UF_*"]) -> dict:
    """Список компаний
    filter_fields: dict[str, str] поля для фильтрации компаний 
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
    all_info_fields=await get_all_info_fields(['company'], isText=False)
    all_info_fields=all_info_fields['company']
    companies = await get_companies_by_filter(filter_fields, select_fields)
    text=''
    for company in companies:
        text+=f'=={company["NAME"]}==\n'
        prepare_company=prepare_fields_to_humman_format(company, all_info_fields)
        for key, value in prepare_company.items():
            text+=f'  {key}: {value}\n'
        text+='\n'
    return text


if __name__ == "__main__":
    a=asyncio.run(list_company())
    pprint(a)