from mcp.server.fastmcp import FastMCP, Context
from dotenv import load_dotenv
load_dotenv()
import os
from orm_bitrix24.entity import _Deal
from fast_bitrix24 import Bitrix
from typing import List
import asyncio
from pprint import pprint
from .userfields import get_all_info_fields
WEBHOOK=os.getenv("WEBHOOK")
bitrix=Bitrix(WEBHOOK)

class Deal(_Deal):
    pass
Deal.get_manager(bitrix)

mcp = FastMCP("bitrix24")


async def prepare_deal_fields_to_humman_format(fields: dict, all_info_fields: dict) -> dict:
    """
    Преобразует словарь с техническими ключами в словарь с человеческими названиями
    
    Args:
        fields: dict - словарь полей, например {'UF_CRM_1749724770090': '47', 'TITLE': 'тестовая сделка'}
        all_info_fields: dict - структура полей из get_all_info_fields
    
    Returns:
        dict - словарь с человеческими названиями, например {'этаж доставки': '1', 'Название': 'тестовая сделка'}
    """
    
    # Создаем маппинг: технический_ключ -> человеческое_название
    field_mapping = {}
    enumeration_values = {}  # Храним значения для полей типа enumeration
    
    # deal_fields = all_info_fields.get('deal', [])
    deal_fields=all_info_fields
    for field_info in deal_fields:
        for human_name, technical_info in field_info.items():
            # Извлекаем технический ключ из строки вида "TITLE (string)" или "UF_CRM_1749724770090 (enumeration):..."
            if '(' in technical_info:
                technical_key = technical_info.split(' (')[0]
                field_mapping[technical_key] = human_name
                
                # Если это поле типа enumeration, извлекаем значения
                if 'enumeration' in technical_info and ':\n' in technical_info:
                    values_part = technical_info.split(':\n', 1)[1]
                    enum_values = {}
                    for line in values_part.split(':\n'):
                        if '(ID: ' in line:
                            value_text = line.strip().split(' (ID: ')[0]
                            value_id = line.split('(ID: ')[1].split(')')[0]
                            enum_values[value_id] = value_text
                    enumeration_values[technical_key] = enum_values
    
    # Преобразуем входной словарь
    result = {}
    
    for tech_key, value in fields.items():
        # Получаем человеческое название
        human_name = field_mapping.get(tech_key, tech_key)
        
        # Если это поле enumeration и значение это ID, заменяем на текст
        if tech_key in enumeration_values and str(value) in enumeration_values[tech_key]:
            human_value = enumeration_values[tech_key][str(value)]
        else:
            human_value = value
            
        result[human_name] = human_value
    
    return result


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
    deals : List[Deal] = await Deal.objects.filter(**filter_fields)
    if '*' in fields_id:
        for deal in deals:
            prepare_deals.append(deal._data)
    else:
        
        for deal in deals:
            prepare_deal={}
            for field in fields_id:
                if field in deal._data:
                    prepare_deal[field] = deal._data[field]
                else:
                    prepare_deal[field] = None
            prepare_deals.append(prepare_deal)

    for deal in prepare_deals:
        text+=f'=={deal["TITLE"]}==\n'
        pprint(deal)
        prepare_deal=await prepare_deal_fields_to_humman_format(deal, all_info_fields)
        for key, value in prepare_deal.items():
            text+=f'  {key}: {value}\n'
        text+='\n'
    return text

if __name__ == "__main__":
    # mcp.run(transport="sse", host="0.0.0.0", port=8000)
    # b=asyncio.run(list_deal(fields_id=['OPPORTUNITY']))
    b=asyncio.run(list_deal(fields_id=['*','UF_*'], filter_fields={">=DATE_CREATE": "2025-06-11"}))
    print(b)
    
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