from .bitrixWork import (
    bit,
    get_deals_by_filter,
    get_contacts_by_filter,
    get_companies_by_filter
)
import asyncio
from mcp.server.fastmcp import FastMCP
from datetime import datetime, timedelta, timezone
from loguru import logger
from typing import Dict, List
import pytz
from collections import defaultdict

mcp = FastMCP("top_clients")


def _normalize_optional_date(date_value: str | None) -> str | None:
    """Нормализация опционального параметра даты
    
    Преобразует строки 'null', 'None', пустые строки в None.
    Это необходимо для корректной обработки параметров, переданных как строки 'null' вместо None.
    
    Args:
        date_value: Значение даты (может быть строкой, None или строкой 'null'/'None')
    
    Returns:
        None если date_value является None, 'null', 'None' или пустой строкой, иначе date_value
    """
    if date_value is None:
        return None
    if isinstance(date_value, str):
        normalized = date_value.strip().lower()
        if normalized in ('null', 'none', ''):
            return None
    return date_value


def _parse_datetime_from_bitrix(dt_str: str) -> datetime:
    """Парсинг даты/времени из формата Bitrix24"""
    if not dt_str:
        return None
    
    # Пробуем разные форматы
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",  # ISO-8601 с timezone
        "%Y-%m-%dT%H:%M:%S",     # ISO-8601 без timezone
        "%Y-%m-%d %H:%M:%S",     # Стандартный формат
        "%Y-%m-%d"               # Только дата
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            # Если нет timezone, считаем UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    
    return None


@mcp.tool()
async def get_top_clients_by_deals_sum(
    n: int = 10,
    from_date: str = None,
    to_date: str = None,
    isText: bool = True
) -> dict | str:
    """Получение топ-N клиентов по сумме сделок (оптимизированная версия с батчами)
    
    Функция получает все сделки за указанный период, группирует их по клиентам
    (контактам или компаниям) и возвращает топ-N клиентов по сумме всех сделок.
    
    Оптимизация: получает все данные одним набором запросов вместо последовательных вызовов.
    Это значительно ускоряет работу при большом количестве сделок.
    
    Args:
        n: Количество клиентов в топе (по умолчанию 10)
        from_date: Начало периода в формате YYYY-MM-DD. Если не указана, фильтр по дате не применяется (все время)
        to_date: Конец периода в формате YYYY-MM-DD. Если не указана, фильтр по дате не применяется (все время)
        isText: Если True (по умолчанию), возвращает человекочитаемый текст; если False, возвращает структурированный словарь
    
    Returns:
        Если isText=False: dict с данными топ-N клиентов:
        {
            'period': {
                'from_date': str | None,
                'to_date': str | None
            },
            'top_clients': [
                {
                    'rank': int,
                    'client_type': str,  # 'contact' или 'company'
                    'client_id': int,
                    'client_name': str,
                    'total_deals_sum': float,
                    'deals_count': int
                }
            ],
            'summary': {
                'total_clients': int,
                'total_deals': int,
                'total_sum': float
            }
        }
        
        Если isText=True: str с человекочитаемым текстом топ-N клиентов
    """
    try:
        # Нормализация опциональных параметров дат (преобразование 'null'/'None' в None)
        from_date = _normalize_optional_date(from_date)
        to_date = _normalize_optional_date(to_date)
        
        # Определение периода - если даты не указаны, фильтр не применяется
        moscow_tz = pytz.timezone("Europe/Moscow")
        from_dt = None
        to_dt = None
        from_date_iso = None
        to_date_iso = None
        from_date_str = None
        to_date_str = None
        
        # Обработка from_date
        if from_date:
            try:
                from_dt = datetime.strptime(from_date, "%Y-%m-%d")
                from_dt = moscow_tz.localize(from_dt).replace(hour=0, minute=0, second=0, microsecond=0)
                from_dt_utc = from_dt.astimezone(timezone.utc)
                from_date_iso = from_dt_utc.strftime("%Y-%m-%dT%H:%M:%S")
                from_date_str = from_dt.strftime("%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Неверный формат from_date: {from_date}. Используйте формат YYYY-MM-DD")
        
        # Обработка to_date
        if to_date:
            try:
                to_dt = datetime.strptime(to_date, "%Y-%m-%d")
                to_dt = moscow_tz.localize(to_dt).replace(hour=23, minute=59, second=59, microsecond=999999)
                to_dt_utc = to_dt.astimezone(timezone.utc)
                to_date_iso = to_dt_utc.strftime("%Y-%m-%dT%H:%M:%S")
                to_date_str = to_dt.strftime("%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Неверный формат to_date: {to_date}. Используйте формат YYYY-MM-DD")
        
        # Формируем фильтр для сделок
        deals_filter = {}
        if from_date_iso:
            deals_filter['>=DATE_CREATE'] = from_date_iso
        if to_date_iso:
            deals_filter['<=DATE_CREATE'] = to_date_iso
        
        period_info = f"за период {from_date_str} - {to_date_str}" if (from_date_str or to_date_str) else "за все время"
        logger.info(f"Получение топ-{n} клиентов по сумме сделок {period_info}")
        
        # Получаем все сделки одним запросом (с фильтром по дате или без него)
        if deals_filter:
            logger.info(f"Получение всех сделок с фильтром: {deals_filter}")
        else:
            logger.info("Получение всех сделок без фильтра по дате")
        deals = await get_deals_by_filter(
            deals_filter,
            select_fields=['ID', 'TITLE', 'OPPORTUNITY', 'CONTACT_ID', 'COMPANY_ID', 'DATE_CREATE']
        )
        
        # Нормализуем результат
        if isinstance(deals, dict):
            if deals.get('order0000000000'):
                deals = deals['order0000000000']
        deals = deals if isinstance(deals, list) else []
        
        logger.info(f"Получено сделок: {len(deals)}")
        
        if not deals:
            period_text = f"{from_date_str} - {to_date_str}" if (from_date_str or to_date_str) else "все время"
            if isText:
                return (
                    f"=== Топ-{n} клиентов по сумме сделок ===\n\n"
                    f"Период: {period_text}\n\n"
                    f"Сделки не найдены."
                )
            return {
                'period': {
                    'from_date': from_date_str,
                    'to_date': to_date_str
                },
                'top_clients': [],
                'summary': {
                    'total_clients': 0,
                    'total_deals': 0,
                    'total_sum': 0.0
                }
            }
        
        # Группируем сделки по клиентам
        # Структура: {client_type: {client_id: {'sum': float, 'count': int, 'deal_ids': list}}}
        clients_data = {
            'contact': defaultdict(lambda: {'sum': 0.0, 'count': 0, 'deal_ids': []}),
            'company': defaultdict(lambda: {'sum': 0.0, 'count': 0, 'deal_ids': []})
        }
        
        contact_ids = set()
        company_ids = set()
        
        for deal in deals:
            opportunity = deal.get('OPPORTUNITY', 0)
            try:
                opportunity = float(opportunity) if opportunity else 0.0
            except (ValueError, TypeError):
                opportunity = 0.0
            
            contact_id = deal.get('CONTACT_ID')
            company_id = deal.get('COMPANY_ID')
            
            # Приоритет: сначала компания, потом контакт
            if company_id:
                try:
                    company_id = int(company_id)
                    company_ids.add(company_id)
                    clients_data['company'][company_id]['sum'] += opportunity
                    clients_data['company'][company_id]['count'] += 1
                    clients_data['company'][company_id]['deal_ids'].append(deal.get('ID'))
                except (ValueError, TypeError):
                    pass
            
            if contact_id and not company_id:
                try:
                    contact_id = int(contact_id)
                    contact_ids.add(contact_id)
                    clients_data['contact'][contact_id]['sum'] += opportunity
                    clients_data['contact'][contact_id]['count'] += 1
                    clients_data['contact'][contact_id]['deal_ids'].append(deal.get('ID'))
                except (ValueError, TypeError):
                    pass
        
        logger.info(
            f"Группировка завершена: {len(contact_ids)} контактов, {len(company_ids)} компаний"
        )
        
        # Получаем информацию о клиентах параллельно
        contacts_info = {}
        companies_info = {}
        
        if contact_ids:
            logger.info(f"Получение информации о {len(contact_ids)} контактах")
            contacts = await get_contacts_by_filter(
                {'ID': list(contact_ids)},
                select_fields=['ID', 'NAME', 'LAST_NAME', 'SECOND_NAME']
            )
            if isinstance(contacts, dict):
                if contacts.get('order0000000000'):
                    contacts = contacts['order0000000000']
            contacts = contacts if isinstance(contacts, list) else []
            
            for contact in contacts:
                contact_id = contact.get('ID')
                if contact_id:
                    contacts_info[int(contact_id)] = contact
        
        if company_ids:
            logger.info(f"Получение информации о {len(company_ids)} компаниях")
            companies = await get_companies_by_filter(
                {'ID': list(company_ids)},
                select_fields=['ID', 'TITLE']
            )
            if isinstance(companies, dict):
                if companies.get('order0000000000'):
                    companies = companies['order0000000000']
            companies = companies if isinstance(companies, list) else []
            
            for company in companies:
                company_id = company.get('ID')
                if company_id:
                    companies_info[int(company_id)] = company
        
        # Формируем список всех клиентов с суммами
        all_clients = []
        
        for contact_id, data in clients_data['contact'].items():
            contact_info = contacts_info.get(contact_id, {})
            name_parts = [
                contact_info.get('NAME', ''),
                contact_info.get('SECOND_NAME', ''),
                contact_info.get('LAST_NAME', '')
            ]
            name = ' '.join([p for p in name_parts if p]).strip() or f"Контакт #{contact_id}"
            
            all_clients.append({
                'client_type': 'contact',
                'client_id': contact_id,
                'client_name': name,
                'total_deals_sum': data['sum'],
                'deals_count': data['count']
            })
        
        for company_id, data in clients_data['company'].items():
            company_info = companies_info.get(company_id, {})
            name = company_info.get('TITLE', f"Компания #{company_id}")
            
            all_clients.append({
                'client_type': 'company',
                'client_id': company_id,
                'client_name': name,
                'total_deals_sum': data['sum'],
                'deals_count': data['count']
            })
        
        # Сортируем по сумме сделок (по убыванию) и берем топ-N
        all_clients.sort(key=lambda x: x['total_deals_sum'], reverse=True)
        top_clients = all_clients[:n]
        
        # Добавляем ранги
        for idx, client in enumerate(top_clients, 1):
            client['rank'] = idx
        
        # Подсчитываем общую статистику
        total_sum = sum(c['total_deals_sum'] for c in all_clients)
        total_deals = len(deals)
        total_clients = len(all_clients)
        
        logger.info(
            f"Топ-{n} клиентов сформирован: {len(top_clients)} клиентов, "
            f"общая сумма: {total_sum:.2f}"
        )
        
        # Если запрошен текстовый формат, форматируем результат
        if isText:
            period_text = f"{from_date_str} - {to_date_str}" if (from_date_str or to_date_str) else "все время"
            if not top_clients:
                return (
                    f"=== Топ-{n} клиентов по сумме сделок ===\n\n"
                    f"Период: {period_text}\n\n"
                    f"Клиенты не найдены."
                )
            
            result_text = f"=== Топ-{n} клиентов по сумме сделок ===\n\n"
            result_text += f"Период: {period_text}\n\n"
            result_text += f"Общая статистика:\n"
            result_text += f"  • Всего клиентов: {total_clients}\n"
            result_text += f"  • Всего сделок: {total_deals}\n"
            result_text += f"  • Общая сумма: {total_sum:,.2f}\n\n"
            
            result_text += f"Топ-{len(top_clients)} клиентов:\n\n"
            
            for client in top_clients:
                result_text += f"{client['rank']}. {client['client_name']}"
                if client['client_type'] == 'contact':
                    result_text += " (Контакт)"
                else:
                    result_text += " (Компания)"
                result_text += f"\n"
                
                result_text += f"   ID: {client['client_id']}\n"
                result_text += f"   Сумма сделок: {client['total_deals_sum']:,.2f}\n"
                result_text += f"   Количество сделок: {client['deals_count']}\n"
                result_text += "\n"
            
            return result_text
        
        # Возвращаем структурированный словарь
        return {
            'period': {
                'from_date': from_date_str,
                'to_date': to_date_str
            },
            'top_clients': top_clients,
            'summary': {
                'total_clients': total_clients,
                'total_deals': total_deals,
                'total_sum': round(total_sum, 2)
            }
        }
        
    except Exception as e:
        logger.error(f"Ошибка при получении топ-{n} клиентов по сумме сделок: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(get_top_clients_by_deals_sum(n=5, isText=True))
    print(result)

