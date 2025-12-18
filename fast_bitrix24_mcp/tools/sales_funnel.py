from .bitrixWork import (
    bit,
    get_leads_by_filter,
    get_deals_by_filter,
    get_stage_history
)
from .deal import get_stages
import asyncio
from mcp.server.fastmcp import FastMCP
from datetime import datetime, timedelta, timezone
from loguru import logger
from typing import Dict, List
import pytz

mcp = FastMCP("sales_funnel")


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
async def get_sales_funnel(from_date: str = None, to_date: str = None, isText: bool = True) -> dict | str:
    """Построение воронки продаж за период (оптимизированная версия с батчами)
    
    Воронка показывает:
    - Количество созданных лидов
    - Количество конвертированных лидов в сделки
    - Количество сделок по стадиям
    - Количество выигранных сделок
    - Конверсию по стадиям
    
    Оптимизация: получает все данные одним набором запросов вместо последовательных вызовов.
    Это значительно ускоряет работу при большом количестве данных.
    
    Args:
        from_date: Начало периода в формате YYYY-MM-DD. Если не указана, используется начало текущего месяца (московское время)
        to_date: Конец периода в формате YYYY-MM-DD. Если не указана, используется конец текущего месяца (московское время)
        isText: Если True (по умолчанию), возвращает человекочитаемый текст; если False, возвращает структурированный словарь
    
    Returns:
        Если isText=False: dict с данными воронки:
        {
            'period': {
                'from_date': str,
                'to_date': str
            },
            'leads': {
                'total_created': int,
                'converted': int,
                'conversion_rate': float  # процент конверсии
            },
            'deals': {
                'total_created': int,
                'won': int,
                'won_rate': float,  # процент выигранных
                'by_stage': {
                    'STAGE_ID': {
                        'name': str,
                        'count': int,
                        'conversion_rate': float  # процент от общего количества сделок
                    }
                }
            },
            'funnel': {
                'leads_created': int,
                'leads_to_deals': int,  # конвертированные лиды
                'deals_by_stage': dict,  # сделки по стадиям
                'deals_won': int
            }
        }
        
        Если isText=True: str с человекочитаемым текстом воронки
    """
    try:
        # Нормализация опциональных параметров дат (преобразование 'null'/'None' в None)
        from_date = _normalize_optional_date(from_date)
        to_date = _normalize_optional_date(to_date)
        
        # Определение периода (по умолчанию текущий месяц)
        moscow_tz = pytz.timezone("Europe/Moscow")
        now_moscow = datetime.now(moscow_tz)
        
        if from_date:
            try:
                from_dt = datetime.strptime(from_date, "%Y-%m-%d")
                from_dt = moscow_tz.localize(from_dt).replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                raise ValueError(f"Неверный формат from_date: {from_date}. Используйте формат YYYY-MM-DD")
        else:
            # Начало текущего месяца
            from_dt = now_moscow.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if to_date:
            try:
                to_dt = datetime.strptime(to_date, "%Y-%m-%d")
                to_dt = moscow_tz.localize(to_dt).replace(hour=23, minute=59, second=59, microsecond=999999)
            except ValueError:
                raise ValueError(f"Неверный формат to_date: {to_date}. Используйте формат YYYY-MM-DD")
        else:
            # Конец текущего месяца
            if now_moscow.month == 12:
                to_dt = now_moscow.replace(year=now_moscow.year + 1, month=1, day=1) - timedelta(microseconds=1)
            else:
                to_dt = now_moscow.replace(month=now_moscow.month + 1, day=1) - timedelta(microseconds=1)
            to_dt = to_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Конвертируем в UTC для запросов к API
        from_dt_utc = from_dt.astimezone(timezone.utc)
        to_dt_utc = to_dt.astimezone(timezone.utc)
        
        from_date_iso = from_dt_utc.strftime("%Y-%m-%dT%H:%M:%S")
        to_date_iso = to_dt_utc.strftime("%Y-%m-%dT%H:%M:%S")
        
        from_date_str = from_dt.strftime("%Y-%m-%d")
        to_date_str = to_dt.strftime("%Y-%m-%d")
        
        logger.info(
            f"Построение воронки продаж за период {from_date_str} - {to_date_str} "
            f"(UTC: {from_date_iso} - {to_date_iso})"
        )
        
        # Оптимизация: получаем все данные параллельно одним набором запросов
        logger.info("Параллельное получение лидов, сделок и стадий")
        leads_filter = {
            '>=DATE_CREATE': from_date_iso,
            '<=DATE_CREATE': to_date_iso
        }
        deals_filter = {
            '>=DATE_CREATE': from_date_iso,
            '<=DATE_CREATE': to_date_iso
        }
        
        # Выполняем запросы параллельно
        all_leads_result, all_deals_result, stages_info = await asyncio.gather(
            get_leads_by_filter(
                leads_filter,
                select_fields=['ID', 'DATE_CREATE', 'STATUS_ID', 'TITLE']
            ),
            get_deals_by_filter(
                deals_filter,
                select_fields=['ID', 'DATE_CREATE', 'STAGE_ID', 'TITLE', 'CATEGORY_ID']
            ),
            get_stages("DEAL_STAGE")
        )
        
        # Нормализуем лиды
        all_leads = all_leads_result
        if not isinstance(all_leads, list):
            if isinstance(all_leads, dict) and all_leads.get('order0000000000'):
                all_leads = all_leads['order0000000000']
            else:
                all_leads = []
        
        # Дополнительная проверка: фильтруем лиды по дате создания на клиенте
        filtered_leads = []
        for lead in all_leads:
            date_create_str = lead.get('DATE_CREATE')
            if date_create_str:
                date_create = _parse_datetime_from_bitrix(date_create_str)
                if date_create and from_dt_utc <= date_create <= to_dt_utc:
                    filtered_leads.append(lead)
        all_leads = filtered_leads
        
        logger.info(f"Получено лидов: {len(all_leads)} (после фильтрации по дате создания)")
        
        # Нормализуем сделки
        all_deals = all_deals_result
        if not isinstance(all_deals, list):
            if isinstance(all_deals, dict) and all_deals.get('order0000000000'):
                all_deals = all_deals['order0000000000']
            else:
                all_deals = []
        
        # Дополнительная проверка: фильтруем сделки по дате создания на клиенте
        filtered_deals = []
        for deal in all_deals:
            date_create_str = deal.get('DATE_CREATE')
            if date_create_str:
                date_create = _parse_datetime_from_bitrix(date_create_str)
                if date_create and from_dt_utc <= date_create <= to_dt_utc:
                    filtered_deals.append(deal)
        all_deals = filtered_deals
        
        logger.info(f"Получено сделок: {len(all_deals)} (после фильтрации по дате создания)")
        
        # Создаем множество ID сделок, созданных в период (для фильтрации истории)
        deal_ids_set = set()
        deal_id_to_category = {}  # Маппинг ID сделки -> category_id
        for deal in all_deals:
            deal_id = deal.get('ID')
            if deal_id:
                try:
                    deal_id_int = int(deal_id)
                    deal_ids_set.add(deal_id_int)
                    deal_id_to_category[deal_id_int] = str(deal.get('CATEGORY_ID', '0'))
                except (ValueError, TypeError):
                    pass
        
        logger.info(f"Получение истории движения по стадиям для {len(deal_ids_set)} сделок")
        
        # Получаем историю движения по стадиям за период
        # Фильтруем по дате перехода в стадию (CREATED_TIME)
        stage_history_filter = {
            '>=CREATED_TIME': from_date_iso,
            '<=CREATED_TIME': to_date_iso
        }
        stage_history = await get_stage_history(
            entity_type_id=2,  # сделки
            owner_id=None,
            filter_fields=stage_history_filter,
            select_fields=['ID', 'OWNER_ID', 'STAGE_ID', 'CREATED_TIME', 'CATEGORY_ID']
        )
        
        logger.info(f"Получено записей истории стадий: {len(stage_history)}")
        
        # Фильтруем историю только для сделок, созданных в период
        filtered_history = []
        for history_item in stage_history:
            owner_id = history_item.get('OWNER_ID')
            if owner_id:
                try:
                    owner_id_int = int(owner_id)
                    if owner_id_int in deal_ids_set:
                        filtered_history.append(history_item)
                except (ValueError, TypeError):
                    pass
        
        logger.info(f"Отфильтровано записей истории для сделок периода: {len(filtered_history)}")
        
        # Создаем словарь стадий для быстрого поиска (как в get_deals_at_risk)
        stages_dict = {}
        # Создаем маппинг порядка стадий для каждой воронки (используем порядок из stages_info)
        # Структура: {category_id: {stage_id: order_index}}
        stages_order = {}
        for category_id, category_data in stages_info.items():
            # Сохраняем стадии из всех воронок
            category_stages = category_data.get('stages', {})
            stages_dict.update(category_stages)
            
            # Сохраняем порядок стадий (по порядку появления в словаре)
            if category_id not in stages_order:
                stages_order[category_id] = {}
            for order_index, (stage_id, stage_name) in enumerate(category_stages.items()):
                stages_order[category_id][stage_id] = order_index
        
        logger.info(f"Получено стадий: {len(stages_dict)}")
        
        # Шаг 4: Анализируем данные на клиенте
        # Подсчет лидов
        total_leads = len(all_leads)
        converted_leads = sum(1 for lead in all_leads if str(lead.get('STATUS_ID', '')).upper() == 'CONVERTED')
        leads_conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0.0
        
        # Подсчет сделок
        total_deals = len(all_deals)
        won_deals = sum(1 for deal in all_deals if 'WON' in str(deal.get('STAGE_ID', '')).upper())
        deals_won_rate = (won_deals / total_deals * 100) if total_deals > 0 else 0.0
        
        # Группировка сделок по воронкам и стадиям на основе истории движения
        # Структура: {category_id: {stage_id: {name, count, conversion_rate}}}
        deals_by_category_stage = {}
        for history_item in filtered_history:
            stage_id = history_item.get('STAGE_ID')
            if not stage_id:
                continue
            
            owner_id = history_item.get('OWNER_ID')
            if not owner_id:
                continue
            
            try:
                owner_id_int = int(owner_id)
                # Используем category_id из истории или из маппинга сделок
                category_id = str(history_item.get('CATEGORY_ID', deal_id_to_category.get(owner_id_int, '0')))
            except (ValueError, TypeError):
                continue
            
            if category_id not in deals_by_category_stage:
                deals_by_category_stage[category_id] = {}
            
            if stage_id not in deals_by_category_stage[category_id]:
                # Используем stages_dict для получения названия стадии
                stage_name = stages_dict.get(stage_id, stage_id)
                deals_by_category_stage[category_id][stage_id] = {
                    'name': stage_name,
                    'count': 0,
                    'conversion_rate': 0.0,
                    'sort_order': stages_order.get(category_id, {}).get(stage_id, 999999)
                }
            
            deals_by_category_stage[category_id][stage_id]['count'] += 1
        
        # Расчет конверсии по стадиям (процент от общего количества сделок)
        for category_id, stages in deals_by_category_stage.items():
            for stage_id, stage_data in stages.items():
                if total_deals > 0:
                    stage_data['conversion_rate'] = (stage_data['count'] / total_deals) * 100
        
        # Сортируем стадии внутри каждой воронки по порядку (sort_order)
        deals_by_category_sorted = {}
        for category_id in sorted(deals_by_category_stage.keys()):
            category_stages = deals_by_category_stage[category_id]
            # Сортируем по sort_order
            sorted_stages = dict(
                sorted(category_stages.items(), key=lambda x: x[1].get('sort_order', 999999))
            )
            deals_by_category_sorted[category_id] = sorted_stages
        
        # Также создаем плоский словарь для обратной совместимости
        deals_by_stage_sorted = {}
        for category_id, stages in deals_by_category_sorted.items():
            for stage_id, stage_data in stages.items():
                deals_by_stage_sorted[stage_id] = stage_data
        
        logger.info(
            f"Анализ завершен: лидов создано {total_leads}, конвертировано {converted_leads}, "
            f"сделок создано {total_deals}, выиграно {won_deals}"
        )
        
        # Формируем результат
        result = {
            'period': {
                'from_date': from_date_str,
                'to_date': to_date_str
            },
            'leads': {
                'total_created': total_leads,
                'converted': converted_leads,
                'conversion_rate': round(leads_conversion_rate, 2)
            },
            'deals': {
                'total_created': total_deals,
                'won': won_deals,
                'won_rate': round(deals_won_rate, 2),
                'by_stage': deals_by_stage_sorted,
                'by_category_stage': deals_by_category_sorted
            },
            'funnel': {
                'leads_created': total_leads,
                'leads_to_deals': converted_leads,
                'deals_by_stage': deals_by_stage_sorted,
                'deals_won': won_deals
            }
        }
        
        # Если запрошен текстовый формат, форматируем результат
        if isText:
            result_text = f"=== Воронка продаж ===\n\n"
            result_text += f"Период: {from_date_str} - {to_date_str}\n\n"
            
            result_text += f"📊 ЛИДЫ:\n"
            result_text += f"  • Создано лидов: {total_leads}\n"
            result_text += f"  • Конвертировано в сделки: {converted_leads}\n"
            result_text += f"  • Конверсия лидов: {leads_conversion_rate:.2f}%\n\n"
            
            result_text += f"💼 СДЕЛКИ:\n"
            result_text += f"  • Создано сделок: {total_deals}\n"
            result_text += f"  • Выиграно сделок: {won_deals}\n"
            result_text += f"  • Конверсия выигрыша: {deals_won_rate:.2f}%\n\n"
            
            if deals_by_category_sorted:
                result_text += f"📈 СДЕЛКИ ПО СТАДИЯМ:\n"
                for category_id in sorted(deals_by_category_sorted.keys()):
                    category_name = stages_info.get(category_id, {}).get('name', f'Воронка {category_id}')
                    category_stages = deals_by_category_sorted[category_id]
                    
                    if category_stages:
                        result_text += f"\n  🎯 {category_name}:\n"
                        for stage_id, stage_data in category_stages.items():
                            result_text += f"    • {stage_data['name']}: {stage_data['count']} ({stage_data['conversion_rate']:.2f}%)\n"
                result_text += "\n"
            
            result_text += f"🔄 ВОРОНКА:\n"
            result_text += f"  Лиды → Сделки: {total_leads} → {converted_leads}\n"
            result_text += f"  Сделки → Выиграно: {total_deals} → {won_deals}\n"
            
            return result_text
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при построении воронки продаж: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(get_sales_funnel())
    from pprint import pprint
    pprint(result)

