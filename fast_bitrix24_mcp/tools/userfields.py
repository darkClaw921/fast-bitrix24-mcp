import asyncio
import os
import traceback
from pprint import pprint
from dotenv import load_dotenv
import json
# from bitrixWork import get_fields_by_deal
from .bitrixWork import get_fields_by_deal, get_fields_by_user, get_fields_by_contact, get_fields_by_company, get_fields_by_task, get_fields_by_lead
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
async def get_all_info_fields(entity:list[str]=['all'], isText:bool=True) -> str | dict:
    """
    Получение всех ID, названий и значений полей сделки, контакта, компании, задач, лида
    args:
        entity: list[str] - ['deal', 'contact', 'company', 'task', 'user', 'lead'] or ['all']
        isText: bool - True - возвращает текст, False - возвращает словарь
    return:
        allText: str - все ID, названий и значения полей сделки, контакта, компании, задач, лида и также id,value значений полей типа enumeration
    """
    
    # bitrix = Bitrix(webhook)
    # Инициализация Portal
    # portal = Portal(bitrix)

    all_fields = {
        'deal': [],
        'contact': [],
        'company': [],
        'user': [],
        'task': [],
        'lead': []
    }

    if entity == ['all']:
        entity = ['deal', 'contact', 'company', 'task', 'user', 'lead']

    for item in entity:
        fields = []  # инициализация по умолчанию
        if item == 'deal':
            fields = await get_fields_by_deal()
        elif item == 'contact':
            fields = await get_fields_by_contact()
        elif item == 'company':
            fields = await get_fields_by_company()
        elif item == 'task':
            fields = await get_fields_by_task()
        elif item == 'user':
            fields = await get_fields_by_user()
        elif item == 'lead':
            fields = await get_fields_by_lead()
        for field in fields:
            if field["type"] == 'enumeration':
                text=f'{field["NAME"]} ({field["type"]})'
                for value in field["items"]:
                    text+=f':\n  {value["VALUE"]} (ID: {value["ID"]})' if value["ID"] else f'\n  {value["VALUE"]}'
                all_fields[item].append({
                    field["formLabel"]:text
                })
            else:
                all_fields[item].append({
                    field["title"]:f'{field["NAME"]} ({field["type"]})'
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





if __name__ == "__main__":
    pprint(asyncio.run(get_all_info_fields(entity=['deal'], isText=False)))