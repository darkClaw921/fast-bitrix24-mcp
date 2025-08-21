from fast_bitrix24 import Bitrix
import os
from dotenv import load_dotenv
from pprint import pprint
from datetime import datetime, timedelta
from loguru import logger
import asyncio
import traceback
load_dotenv()
webhook = os.getenv('WEBHOOK')
bit = Bitrix(webhook, ssl=False, verbose=False)

logger.add("logs/workBitrix_{time}.log",format="{time:YYYY-MM-DD HH:mm}:{level}:{file}:{line}:{message} ", rotation="100 MB", retention="10 days", level="DEBUG")


async def get_deal_by_id(deal_id: int) -> dict:
    """
    Получает сделку по ID
    """
    deal = await bit.call('crm.deal.get', {'ID': deal_id})
    return deal



async def get_fields_by_deal() -> list[dict]:
        """Получение всех полей для сделки (включая пользовательские)"""
        try:
            logger.info(f"Получение всех полей для сделки")
            # Метод .fields не требует параметров, используем get_all
            result = await bit.get_all(f'crm.deal.fields')
            
            if not result:
                logger.warning(f"Не получены поля для сделки")
                return []
            
            # result приходит в виде списка словарей, а не словаря словарей
            if isinstance(result, dict):
                # Если результат - словарь полей (ключ = имя поля, значение = данные поля)
                fields = []
                for field_name, field_data in result.items():
                    if isinstance(field_data, dict):
                        # Добавляем имя поля в данные, если его там нет
                        if 'NAME' not in field_data:
                            field_data['NAME'] = field_name

                        fields.append(field_data)
            else:
                # Если результат - список полей
                fields = [field_data for field_data in result]
            
            
            
            logger.info(f"Получено {len(fields)} полей для сделки")
            return fields
            
        except Exception as e:
            logger.error(f"Ошибка при получении полей для сделки: {e}")
            raise

async def get_fields_by_user() -> list[dict]:
    """Получение всех пользовательских полей"""
    # userfieldsUser = await bit.call('user.userfield.list', raw=True)
    # pprint(userfieldsUser)
    
    userfields = await bit.call('user.fields', raw=True)
    userfields=userfields['result']
    userfieldsTemp=[]
    for key, value in userfields.items():
        userfieldsTemp.append({
            'NAME': key,
            'title': value,
            'type': 'string'
        })
        # userfieldsTemp.append(value)
    return userfieldsTemp
    
async def get_fields_by_contact() -> list[dict]:
    """Получение всех полей для контакта (включая пользовательские)"""
    fields = await bit.get_all('crm.contact.fields')
    pprint(fields)
    fieldsTemp=[]
    for key, value in fields.items():

        fieldsTemp.append({
            'NAME': key,
            **value
        })
    return fieldsTemp

async def get_fields_by_company() -> list[dict]:
    """Получение всех полей для компании (включая пользовательские)"""
    fields = await bit.get_all('crm.company.fields')
    # pprint(fields)
    fieldsTemp=[]
    for key, value in fields.items():
        fieldsTemp.append({
            'NAME': key,
            **value
        })
    return fieldsTemp




async def get_users_by_filter(filter_fields: dict={}) -> list[dict]:
    """Получение пользователей по фильтру"""
    users = await bit.get_all('user.get', params={'filter': filter_fields})

    return users

async def get_deals_by_filter(filter_fields: dict, select_fields: list[str]) -> list[dict]:
    """
    Получает сделку по фильтру
    """
    deal = await bit.get_all('crm.deal.list', params={'filter': filter_fields, 'select': select_fields})
    pprint(deal)
    if isinstance(deal, dict):
        if deal.get('order0000000000'):
            deal=deal['order0000000000']
    
    return deal

async def get_contacts_by_filter(filter_fields: dict={}, select_fields: list[str]=["*", "UF_*"]) -> list[dict]:
    """Получение контактов по фильтру"""
    contacts = await bit.get_all('crm.contact.list', params={'filter': filter_fields, 'select': select_fields})

    return contacts

async def get_companies_by_filter(filter_fields: dict={}, select_fields: list[str]=["*", "UF_*"]) -> list[dict]:
    """Получение компаний по фильтру"""
    companies = await bit.get_all('crm.company.list', params={'filter': filter_fields, 'select': select_fields})

    return companies


if __name__ == "__main__":
    # a=asyncio.run(get_fields_by_user())
    # pprint(a)
    a=asyncio.run(get_fields_by_company())
    pprint(a)

    # a=asyncio.run(get_fields_by_deal())
    # pprint(a)


