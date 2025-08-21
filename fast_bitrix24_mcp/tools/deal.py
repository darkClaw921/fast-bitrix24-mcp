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
from .bitrixWork import bit, get_deals_by_filter

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
        pprint(deal)
        prepare_deal=await prepare_fields_to_humman_format(deal, all_info_fields)
        for key, value in prepare_deal.items():
            text+=f'  {key}: {value}\n'
        text+='\n'
    return text




if __name__ == "__main__":
    # mcp.run(transport="sse", host="0.0.0.0", port=8000)
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