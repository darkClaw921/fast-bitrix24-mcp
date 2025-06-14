import asyncio
import os
import traceback
from fast_bitrix24 import Bitrix
from orm_bitrix24.entity import Portal
from pprint import pprint
from dotenv import load_dotenv
import json
load_dotenv()
# Инициализация клиента Bitrix24
webhook = os.getenv("WEBHOOK")
if not webhook:
    print("Необходимо установить переменную окружения WEBHOOK")
    exit()

from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("userfields")





# async def get_all_info_fields(bitrix:Bitrix, entity:list[str]=['all']) -> str:
@mcp.tool()
async def get_all_info_fields(entity:list[str]=['all'], isText:bool=True) -> str:
    """
    Получение всех ID и названий полей сделки, контакта, компании
    args:
        bitrix: Bitrix - клиент Bitrix24
        entity: list[str] - ['deal', 'contact', 'company'] or ['all']
    return:
        allText: str - все ID и названия полей сделки, контакта, компании и также id значений полей типа enumeration
    """
    
    bitrix = Bitrix(webhook)
    # Инициализация Portal
    portal = Portal(bitrix)

    all_fields = {
        'deal': [],
        'contact': [],
        'company': []
    }

    if entity == ['all']:
        entity = ['deal', 'contact', 'company']

    for item in entity:
        if item == 'deal':
            fields = await portal.deal.fields.get_all()
        elif item == 'contact':
            fields = await portal.contact.fields.get_all()
        elif item == 'company':
            fields = await portal.company.fields.get_all()

        for field in fields:
            if field.type == 'enumeration':
                text=f'{field.name} ({field.type})'
                for value in field.values:
                    text+=f':\n  {value.value} (ID: {value.id})' if value.id else f'\n  {value.value}'
                all_fields[item].append({
                    field.title:text
                })
            else:
                all_fields[item].append({
                    field.title:f'{field.name} ({field.type})'
                })


    if entity == 'all':
        with open('bitrix_fields.json', 'w', encoding='utf-8') as f:
            json.dump(all_fields, f, indent=4, ensure_ascii=False)
    else:
        with open(f'bitrix_fields_{entity[0]}.json', 'w', encoding='utf-8') as f:
            json.dump(all_fields, f, indent=4, ensure_ascii=False)


    allText=''
    for key, value in all_fields.items():
        allText+=f'{key}:\n'
        for item in value:
            allText+=f'  {item}\n'
    
    if isText:
        return allText
    else:
        return all_fields





# if __name__ == "__main__":
    # asyncio.run(get_all_info_fields(bitrix, ['deal', 'company']))