from mcp.server.fastmcp.server import FastMCP
import pytz
import re
import hashlib

from mcp.server.fastmcp import FastMCP, Context
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
import json
from dotenv import load_dotenv
load_dotenv()
import os
from .bitrixWork import bit
from loguru import logger


mcp = FastMCP("helper")

# Настройка кэша
CACHE_DIR = Path("cache")
CACHE_TTL_SECONDS = 3600  # 1 час


def prepare_fields_to_humman_format(fields: dict, all_info_fields: dict) -> dict:
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


def _generate_cache_key(entity: str, filter_fields: Dict[str, Any], select_fields: List[str]) -> str:
    """Генерирует ключ кэша на основе параметров запроса."""
    # Создаем стабильное представление параметров для хеширования
    cache_data = {
        "entity": entity.lower(),
        "filter_fields": json.dumps(filter_fields, sort_keys=True, ensure_ascii=False),
        "select_fields": json.dumps(sorted(select_fields), ensure_ascii=False)
    }
    cache_string = json.dumps(cache_data, sort_keys=True, ensure_ascii=False)
    cache_hash = hashlib.md5(cache_string.encode('utf-8')).hexdigest()
    return f"{entity.lower()}_{cache_hash}"


def _get_cache_path(cache_key: str) -> Path:
    """Возвращает путь к файлу кэша."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{cache_key}.json"


def _load_from_cache(cache_key: str) -> Optional[List[Dict[str, Any]]]:
    """Загружает данные из кэша, если они не устарели."""
    cache_path = _get_cache_path(cache_key)
    if not cache_path.exists():
        return None
    
    try:
        with cache_path.open("r", encoding="utf-8") as f:
            cache_data = json.load(f)
        
        # Проверяем TTL
        cached_at = datetime.fromisoformat(cache_data["cached_at"])
        age = (datetime.now() - cached_at).total_seconds()
        
        if age > CACHE_TTL_SECONDS:
            logger.info(f"Кэш для ключа {cache_key} устарел (возраст: {age:.0f} сек), удаляем")
            cache_path.unlink()
            return None
        
        logger.info(f"Используем кэш для ключа {cache_key} (возраст: {age:.0f} сек)")
        return cache_data["data"]
    except Exception as e:
        logger.warning(f"Ошибка при чтении кэша {cache_key}: {e}")
        return None


def _save_to_cache(cache_key: str, data: List[Dict[str, Any]]) -> None:
    """Сохраняет данные в кэш."""
    try:
        cache_path = _get_cache_path(cache_key)
        cache_data = {
            "cached_at": datetime.now().isoformat(),
            "data": data
        }
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Данные сохранены в кэш для ключа {cache_key}")
    except Exception as e:
        logger.warning(f"Ошибка при сохранении кэша {cache_key}: {e}")


@mcp.tool()
async def export_entities_to_json(entity: str, filter_fields: Dict[str, Any] = {}, select_fields: List[str] = ["*"], filename: Optional[str] = None) -> Dict[str, Any]:
    """Экспорт элементов сущности в JSON
    - entity: 'deal' | 'contact' | 'company' | 'user' | 'task'
    - filter_fields: фильтр Bitrix24 (например {"CLOSED": "N", ">=DATE_CREATE": "2025-06-01"})
    - select_fields: список полей; ['*', 'UF_*'] означает все поля
    - filename: имя файла (опционально). Если не указано, сформируется автоматически в папке exports
    Возвращает: {"entity": str, "count": int, "file": str}
    """
    # Импортируем функции для работы с задачами
    from .bitrixWork import get_tasks_by_filter

    method_map = {
        "deal": "crm.deal.list",
        "lead": "crm.lead.list",
        "contact": "crm.contact.list",
        "company": "crm.company.list",
        "user": "user.get",
        "task": None  # Используем кастомную функцию
    }
    entity = entity.lower()
    if entity not in method_map:
        return {"error": f"unsupported entity: {entity}", "count": 0}

    # Для задач нужно учесть order в ключе кэша
    filter_fields_for_cache = filter_fields.copy()
    
    # Проверяем кэш перед запросом к API
    cache_key = _generate_cache_key(entity, filter_fields_for_cache, select_fields)
    cached_items = _load_from_cache(cache_key)
    
    if cached_items is not None:
        items = cached_items
        logger.info(f"Использованы данные из кэша для {entity}, количество записей: {len(items)}")
    else:
        # Выполняем запрос к API
        try:
            if entity == "task":
                # Используем кастомную функцию для задач
                order = {"ID": "DESC"}  # По умолчанию
                filter_fields_for_api = filter_fields.copy()  # Копия для API запроса
                if 'order' in filter_fields_for_api:
                    order = filter_fields_for_api.pop('order')
                items = await get_tasks_by_filter(filter_fields_for_api, select_fields, order)
            else:
                # Стандартные сущности CRM
                params: Dict[str, Any] = {"filter": filter_fields}
                if select_fields and select_fields != ["*"]:
                    params["select"] = select_fields
                items = await bit.get_all(method_map[entity], params=params)
            
            # Сохраняем в кэш только при успешном запросе
            _save_to_cache(cache_key, items)
        except Exception as exc:
            logger.error(f"Ошибка при запросе к Bitrix24 для {entity}: {exc}")
            return {"error": str(exc), "count": 0}

    # Обработка результата
    if isinstance(items, dict):
        if items.get('order0000000000'):
            items = items['order0000000000']
        elif 'tasks' in items:
            items = items['tasks']
    
    if not isinstance(items, list):
        items = []

    exports_dir = Path("exports")
    exports_dir.mkdir(parents=True, exist_ok=True)
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{entity}_export_{ts}.json"
    file_path = exports_dir / filename

    with file_path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    return {"entity": entity, "count": len(items), "file": str(file_path)}


def _compare(lhs: Any, op: str, rhs: Any) -> bool:
    """Сравнение значений с поддержкой чисел, дат/времени (ISO-8601) и строк.

    Для опов ">", ">=", "<", "<=" последовательно пробуем:
    - числовое сравнение
    - сравнение datetime (включая ключевые слова today/tomorrow/yesterday)
    - лексикографическое сравнение строк (как крайний вариант)
    """
    try:
        if op in ("==", "="):
            return lhs == rhs
        if op == "!=":
            return lhs != rhs

        # 1) Числовое сравнение
        try:
            lnum = float(lhs)
            rnum = float(rhs)
            if op == ">":
                return lnum > rnum
            if op == ">=":
                return lnum >= rnum
            if op == "<":
                return lnum < rnum
            if op == "<=":
                return lnum <= rnum
        except Exception:
            pass

        # 2) Сравнение дат/времени
        ldt = _parse_datetime(lhs)
        rdt = _parse_datetime(rhs)
        # Сохраняем оригинальную строку rhs для проверки формата даты
        rhs_original_str = rhs if isinstance(rhs, str) else None
        if rdt is None and isinstance(rhs, str):
            # Поддержка ключевых слов относительно локального времени и TZ левого операнда
            tz = ldt.tzinfo if isinstance(ldt, datetime) else None
            rdt = _keyword_to_datetime(rhs, tz=tz)
        if ldt is not None and rdt is not None:
            # Выравниваем TZ: если один aware, другой naive — интерпретируем naive как московское время
            moscow_tz = pytz.timezone("Europe/Moscow")
            if (ldt.tzinfo is not None) and (rdt.tzinfo is None):
                # Naive datetime интерпретируем как московское время
                rdt = moscow_tz.localize(rdt)
            if (ldt.tzinfo is None) and (rdt.tzinfo is not None):
                # Naive datetime интерпретируем как московское время
                ldt = moscow_tz.localize(ldt)
            # Если оба aware, но с разными TZ — конвертируем в московское время для сравнения
            if (ldt.tzinfo is not None) and (rdt.tzinfo is not None):
                ldt = ldt.astimezone(moscow_tz)
                rdt = rdt.astimezone(moscow_tz)
            
            # Для операторов < и > с датами без времени: интерпретируем как "до конца дня" для < и "после конца дня" для >
            if rhs_original_str and op in ("<", ">"):
                # Проверяем, является ли rhs датой без времени (формат YYYY-MM-DD)
                rhs_stripped = rhs_original_str.strip()
                if re.match(r'^\d{4}-\d{2}-\d{2}$', rhs_stripped):
                    if op == "<":
                        # "< 2025-11-11" означает "до конца дня 11 ноября", т.е. < 2025-11-12 00:00:00
                        rdt = rdt + timedelta(days=1)
                        rdt = rdt.replace(hour=0, minute=0, second=0, microsecond=0)
                    elif op == ">":
                        # "> 2025-11-11" означает "после конца дня 11 ноября", т.е. > 2025-11-11 23:59:59
                        rdt = rdt.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            if op == ">":
                return ldt > rdt
            if op == ">=":
                return ldt >= rdt
            if op == "<":
                return ldt < rdt
            if op == "<=":
                return ldt <= rdt

        # 3) Лексикографическое сравнение строк (как fallback)
        if isinstance(lhs, str) and isinstance(rhs, str):
            if op == ">":
                return lhs > rhs
            if op == ">=":
                return lhs >= rhs
            if op == "<":
                return lhs < rhs
            if op == "<=":
                return lhs <= rhs
    except Exception:
        return False
    return False


def _parse_value(token: str) -> Any:
    token = token.strip()
    if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
        return token[1:-1]
    try:
        if "." in token:
            return float(token)
        return int(token)
    except Exception:
        return token


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Пытается распарсить значение как datetime (ISO-8601, 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS')."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt
        except Exception:
            continue
    return None


def _keyword_to_datetime(keyword: str, tz: Optional[tzinfo]) -> Optional[datetime]:
    """Преобразует ключевые слова 'today', 'tomorrow', 'yesterday' в начало соответствующего дня."""
    if not isinstance(keyword, str):
        return None
    key = keyword.strip().lower()
    now = datetime.now(tz=tz)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if key == "today":
        return start_of_today
    if key == "tomorrow":
        return start_of_today + timedelta(days=1)
    if key == "yesterday":
        return start_of_today - timedelta(days=1)
    return None


def _record_matches_simple_expr(record: Dict[str, Any], expr: str) -> bool:
    or_parts = [p.strip() for p in expr.split(" or ") if p.strip()]
    def eval_and(and_expr: str) -> bool:
        and_parts = [p.strip() for p in and_expr.split(" and ") if p.strip()]
        for part in and_parts:
            op = None
            for candidate in [">=", "<=", "==", "!=", ">", "<", "="]:
                if candidate in part:
                    op = candidate
                    break
            if not op:
                return False
            field, value = part.split(op, 1)
            field = field.strip()
            rhs = _parse_value(value)
            # Используем поиск поля без учета регистра
            lhs = _get_field_value_case_insensitive(record, field)
            # Превращаем одиночное '=' в '=='
            if op == "=":
                op_to_use = "=="
            else:
                op_to_use = op
            if not _compare(lhs, op_to_use, rhs):
                return False
        return True
    for grp in or_parts:
        if eval_and(grp):
            return True
    return False


def _snake_to_camel(snake_str: str) -> str:
    """Преобразует UPPER_SNAKE_CASE или lower_snake_case в camelCase.
    Если строка уже в camelCase (нет символа '_'), возвращает её без изменений.
    """
    if '_' not in snake_str:
        # Уже в camelCase или другом формате без подчеркиваний
        return snake_str
    components = snake_str.split('_')
    # Первая часть в нижнем регистре, остальные с заглавной первой буквой
    return components[0].lower() + ''.join(x.capitalize() for x in components[1:])


def _get_field_value_case_insensitive(record: Dict[str, Any], field_name: str) -> Any:
    """Получает значение поля из записи независимо от регистра ключа."""
    # Сначала пробуем точное совпадение
    if field_name in record:
        return record[field_name]
    # Затем пробуем в нижнем регистре
    field_lower = field_name.lower()
    if field_lower in record:
        return record[field_lower]
    # Ищем по всем ключам без учета регистра
    for key, value in record.items():
        if key.lower() == field_lower:
            return value
    return None


def _get_field_value_for_task(record: Dict[str, Any], field_name: str) -> Any:
    """Получает значение поля из записи задачи с поддержкой преобразования UPPER_SNAKE_CASE в camelCase."""
    # Сначала пробуем точное совпадение
    if field_name in record:
        return record[field_name]
    # Затем пробуем в нижнем регистре
    field_lower = field_name.lower()
    if field_lower in record:
        return record[field_lower]
    # Пробуем преобразовать UPPER_SNAKE_CASE в camelCase
    camel_case = _snake_to_camel(field_name)
    if camel_case in record:
        return record[camel_case]
    # Ищем по всем ключам без учета регистра
    for key, value in record.items():
        if key.lower() == field_lower:
            return value
    # Ищем по camelCase версии без учета регистра
    camel_lower = camel_case.lower()
    for key, value in record.items():
        if key.lower() == camel_lower:
            return value
    return None


def _record_matches_simple_expr_for_task(record: Dict[str, Any], expr: str) -> bool:
    """Проверяет соответствие записи задачи условию с поддержкой преобразования форматов полей."""
    or_parts = [p.strip() for p in expr.split(" or ") if p.strip()]
    def eval_and(and_expr: str) -> bool:
        and_parts = [p.strip() for p in and_expr.split(" and ") if p.strip()]
        for part in and_parts:
            op = None
            for candidate in [">=", "<=", "==", "!=", ">", "<", "="]:
                if candidate in part:
                    op = candidate
                    break
            if not op:
                return False
            field, value = part.split(op, 1)
            field = field.strip()
            rhs = _parse_value(value)
            # Используем поиск поля для задач с преобразованием формата
            lhs = _get_field_value_for_task(record, field)
            # Превращаем одиночное '=' в '=='
            if op == "=":
                op_to_use = "=="
            else:
                op_to_use = op
            if not _compare(lhs, op_to_use, rhs):
                return False
        return True
    for grp in or_parts:
        if eval_and(grp):
            return True
    return False


def _apply_condition_for_task(records: List[Dict[str, Any]], condition: Optional[Union[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Применяет условие к записям задач с поддержкой преобразования форматов полей."""
    if not condition:
        return records
    filtered: List[Dict[str, Any]] = []
    if isinstance(condition, str):
        for r in records:
            if _record_matches_simple_expr_for_task(r, condition):
                filtered.append(r)
        return filtered
    for r in records:
        matched = True
        for field, expected in condition.items():
            # Получаем значение поля для задачи с преобразованием формата
            lhs = _get_field_value_for_task(r, field)
            if isinstance(expected, dict):
                for op, rhs in expected.items():
                    if not _compare(lhs, op, rhs):
                        matched = False
                        break
                if not matched:
                    break
            else:
                if lhs != expected:
                    matched = False
                    break
        if matched:
            filtered.append(r)
    return filtered


def _apply_condition(records: List[Dict[str, Any]], condition: Optional[Union[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Применяет условие к записям с поддержкой поиска полей без учета регистра."""
    if not condition:
        return records
    filtered: List[Dict[str, Any]] = []
    if isinstance(condition, str):
        for r in records:
            if _record_matches_simple_expr(r, condition):
                filtered.append(r)
        return filtered
    for r in records:
        matched = True
        for field, expected in condition.items():
            # Получаем значение поля независимо от регистра
            lhs = _get_field_value_case_insensitive(r, field)
            if isinstance(expected, dict):
                # Проверяем ВСЕ операторы для поля - все должны выполниться (AND логика)
                for op, rhs in expected.items():
                    if not _compare(lhs, op, rhs):
                        matched = False
                        break
                if not matched:
                    break
            else:
                if lhs != expected:
                    matched = False
                    break
        if matched:
            filtered.append(r)
    return filtered


def _ensure_list(value: Optional[Union[str, List[str]]]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_operator_from_key(key: str) -> tuple[str, str]:
    """Извлекает оператор из ключа, если он есть. Возвращает (оператор, имя_поля)."""
    # Операторы, которые могут быть в начале ключа
    operators = [">=", "<=", "!=", "==", ">", "<", "!"]
    for op in operators:
        if key.startswith(op):
            field_name = key[len(op):]
            # Преобразуем оператор в стандартный формат
            if op == "!":
                return ("!=", field_name)
            return (op, field_name)
    # Нет оператора в ключе
    return ("==", key)


def _normalize_condition(condition: Optional[Union[str, Dict[str, Any]]]) -> Optional[Union[str, Dict[str, Any]]]:
    """Нормализует условие: парсит JSON строку и преобразует формат с операторами в ключах и значениях."""
    if not condition:
        return None
    
    # Если условие - строка, пытаемся распарсить как JSON
    if isinstance(condition, str):
        # Проверяем, не является ли это JSON строкой
        condition_stripped = condition.strip()
        if condition_stripped.startswith('{') and condition_stripped.endswith('}'):
            try:
                # Парсим JSON
                parsed = json.loads(condition_stripped)
                condition = parsed
            except (json.JSONDecodeError, Exception):
                # Если не JSON или ошибка парсинга, оставляем как строку с операторами
                return condition
        else:
            # Обычная строка с операторами
            return condition
    
    # Если условие - словарь, обрабатываем формат с операторами в ключах и значениях
    if isinstance(condition, dict):
        normalized = {}
        for field_key, value in condition.items():
            # Извлекаем оператор из ключа (если есть)
            op, field_name = _extract_operator_from_key(field_key)
            
            # Нормализуем имя поля в нижний регистр для совместимости
            field_name_lower = field_name.lower()
            
            # Если поле уже есть в normalized, создаем словарь с операторами
            if field_name_lower in normalized:
                if not isinstance(normalized[field_name_lower], dict):
                    # Преобразуем существующее значение в словарь
                    normalized[field_name_lower] = {"==": normalized[field_name_lower]}
                normalized[field_name_lower][op] = value
            else:
                # Проверяем, содержит ли значение оператор в начале
                if isinstance(value, str):
                    value_stripped = value.strip()
                    op_found = False
                    for val_op in [">=", "<=", ">", "<", "==", "!=", "="]:
                        if value_stripped.startswith(val_op):
                            # Извлекаем оператор и значение
                            op_value = value_stripped[len(val_op):].strip()
                            # Используем оператор из значения, если он есть
                            normalized[field_name_lower] = {val_op: op_value}
                            op_found = True
                            break
                    if not op_found:
                        # Используем оператор из ключа или равенство
                        normalized[field_name_lower] = {op: value}
                elif isinstance(value, dict):
                    # Уже правильный формат, но нужно добавить оператор из ключа если он есть
                    if op != "==":
                        # Если в ключе был оператор, добавляем его к словарю
                        value[op] = value.get(op, value.get("=="))
                    normalized[field_name_lower] = value
                elif isinstance(value, list):
                    # Список значений - обрабатываем каждое
                    normalized[field_name_lower] = {}
                    for val in value:
                        if isinstance(val, str):
                            val_stripped = val.strip()
                            val_op_found = False
                            for val_op in [">=", "<=", ">", "<", "==", "!=", "="]:
                                if val_stripped.startswith(val_op):
                                    op_value = val_stripped[len(val_op):].strip()
                                    normalized[field_name_lower][val_op] = op_value
                                    val_op_found = True
                                    break
                            if not val_op_found:
                                normalized[field_name_lower][op] = val
                        else:
                            normalized[field_name_lower][op] = val
                else:
                    # Простое значение - используем оператор из ключа или равенство
                    normalized[field_name_lower] = {op: value}
        return normalized
    
    return condition


@mcp.tool()
async def analyze_export_file(file_path: str, operation: str, fields: Optional[Union[str, List[str]]] = None, condition: Optional[Union[str, Dict[str, Any]]] = None, group_by: Optional[List[str]] = None) -> Dict[str, Any]:
    """Анализ экспортированных данных из файла JSON
    - file_path: путь к файлу JSON
    - operation: операция анализа ('count', 'sum', 'avg', 'min', 'max')
    - fields: список полей для анализа (например ['UF_CRM_1749724770090', 'TITLE'])
    - condition: условие фильтрации. Может быть:
      - строкой с операторами: 'DATE_CREATE >= "2025-11-03 00:00:00" and DATE_CREATE <= "2025-11-09 23:59:59"'
      - словарем: {'DATE_CREATE': {'>=': '2025-11-03T00:00:00', '<=': '2025-11-09T23:59:59'}}
      - словарем с операторами в строках: {'DATE_CREATE': '>= 2025-11-03T00:00:00'} (будет автоматически преобразован)
      - JSON строкой: '{"DATE_CREATE": ">= 2025-11-03T00:00:00"}' (будет автоматически распарсена)
    - group_by: группировка по полям (например ['UF_CRM_1749724770090'])
    """
    
    path = Path(file_path)
    if not path.exists():
        return {"error": f"file not found: {file_path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"failed to read json: {exc}"}

    if not isinstance(data, list):
        return {"error": "json must contain a list of records"}

    # Нормализуем условие перед применением
    normalized_condition = _normalize_condition(condition)
    filtered = _apply_condition(data, normalized_condition)
    groups = _ensure_list(group_by) if group_by else []
    op = operation.lower()
    fields_list = _ensure_list(fields)

    def group_key(rec: Dict[str, Any]) -> tuple:
        return tuple(_get_field_value_case_insensitive(rec, g) for g in groups) if groups else tuple()

    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for rec in filtered:
        key = group_key(rec)
        grouped.setdefault(key, []).append(rec)

    def aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if op == "count":
            return {"count": len(records)}
        results: Dict[str, Any] = {}
        if not fields_list:
            return {"error": "fields are required for this operation"}
        for fld in fields_list:
            values: List[float] = []
            for r in records:
                v = _get_field_value_case_insensitive(r, fld)
                try:
                    if v is None:
                        continue
                    values.append(float(v))
                except Exception:
                    continue
            if not values:
                results[fld] = None
                continue
            if op == "sum":
                results[fld] = sum(values)
            elif op == "avg":
                results[fld] = sum(values) / len(values)
            elif op == "min":
                results[fld] = min(values)
            elif op == "max":
                results[fld] = max(values)
            else:
                results[fld] = None
        return results

    output: Dict[str, Any] = {"operation": op}
    if groups:
        output["group_by"] = groups
        output["result"] = []
        for key, records in grouped.items():
            group_obj = {g: key[idx] for idx, g in enumerate(groups)}
            output["result"].append({"group": group_obj, "values": aggregate(records)})
    else:
        output["result"] = aggregate(filtered)

    output["total_records"] = len(filtered)
    return output

@mcp.tool()
async def datetime_now() -> str :
    """Получить Текущую дата и время"""
    timezone = pytz.timezone("Europe/Moscow")

    return datetime.now(timezone).isoformat()


def _normalize_condition_for_task(condition: Optional[Union[str, Dict[str, Any]]]) -> Optional[Union[str, Dict[str, Any]]]:
    """Нормализует условие для задач: преобразует имена полей в camelCase и обрабатывает операторы."""
    normalized = _normalize_condition(condition)
    if not normalized or isinstance(normalized, str):
        return normalized
    
    # Преобразуем имена полей в camelCase для задач
    task_normalized = {}
    for field_key, value in normalized.items():
        # Преобразуем имя поля в camelCase
        camel_field = _snake_to_camel(field_key)
        task_normalized[camel_field] = value
    
    return task_normalized


@mcp.tool()
async def analyze_tasks_export(file_path: str, operation: str, fields: Optional[Union[str, List[str]]] = None, condition: Optional[Union[str, Dict[str, Any]]] = None, group_by: Optional[List[str]] = None) -> Dict[str, Any]:
    """Анализ экспортированных задач из файла JSON
    - file_path: путь к файлу JSON с экспортом задач
    - operation: операция анализа ('count', 'sum', 'avg', 'min', 'max')
    - fields: список полей для анализа (например ['TIME_ESTIMATE', 'DURATION_FACT'] или ['timeEstimate', 'durationFact'])
    - condition: условие фильтрации (например {'STATUS': '5'} или {'status': '5'} для завершённых задач)
    - group_by: группировка по полям (например ['RESPONSIBLE_ID', 'STATUS'] или ['responsibleId', 'status'])
    
    Поддерживает преобразование UPPER_SNAKE_CASE в camelCase для полей задач.
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"file not found: {file_path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"failed to read json: {exc}"}

    if not isinstance(data, list):
        return {"error": "json must contain a list of records"}

    # Нормализуем условие для задач (преобразует имена полей в camelCase)
    normalized_condition = _normalize_condition_for_task(condition)
    filtered = _apply_condition_for_task(data, normalized_condition)
    
    # Преобразуем поля и группировку в camelCase
    groups = _ensure_list(group_by) if group_by else []
    groups_camel = [_snake_to_camel(g) for g in groups]
    
    op = operation.lower()
    fields_list = _ensure_list(fields)
    fields_camel = [_snake_to_camel(f) if isinstance(f, str) else f for f in fields_list] if fields_list else []

    def group_key(rec: Dict[str, Any]) -> tuple:
        return tuple(_get_field_value_for_task(rec, g) for g in groups_camel) if groups_camel else tuple()

    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for rec in filtered:
        key = group_key(rec)
        grouped.setdefault(key, []).append(rec)

    def aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if op == "count":
            return {"count": len(records)}
        results: Dict[str, Any] = {}
        if not fields_camel:
            return {"error": "fields are required for this operation"}
        for fld in fields_camel:
            values: List[float] = []
            for r in records:
                v = _get_field_value_for_task(r, fld)
                try:
                    if v is None:
                        continue
                    values.append(float(v))
                except Exception:
                    continue
            if not values:
                results[fld] = None
                continue
            if op == "sum":
                results[fld] = sum(values)
            elif op == "avg":
                results[fld] = sum(values) / len(values)
            elif op == "min":
                results[fld] = min(values)
            elif op == "max":
                results[fld] = max(values)
            else:
                results[fld] = None
        return results

    output: Dict[str, Any] = {"operation": op}
    if groups_camel:
        output["group_by"] = groups  # Возвращаем оригинальные имена полей
        output["result"] = []
        for key, records in grouped.items():
            group_obj = {groups[idx]: key[idx] for idx, g in enumerate(groups_camel)}
            output["result"].append({"group": group_obj, "values": aggregate(records)})
    else:
        output["result"] = aggregate(filtered)

    output["total_records"] = len(filtered)
    return output


@mcp.tool()
async def export_task_fields_to_json(filename: Optional[str] = None) -> Dict[str, Any]:
    """Экспорт описания полей задач в JSON файл
    - filename: имя файла (опционально). Если не указано, сформируется автоматически
    
    Возвращает информацию об экспорте полей
    """
    from .bitrixWork import get_fields_by_task
    
    try:
        fields = await get_fields_by_task()
        
        exports_dir = Path("exports")
        exports_dir.mkdir(parents=True, exist_ok=True)
        
        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"task_fields_{ts}.json"
        
        file_path = exports_dir / filename
        
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(fields, f, ensure_ascii=False, indent=2)
        
        return {
            "entity": "task_fields", 
            "count": len(fields), 
            "file": str(file_path)
        }
    except Exception as exc:
        return {"error": str(exc), "count": 0}
    
