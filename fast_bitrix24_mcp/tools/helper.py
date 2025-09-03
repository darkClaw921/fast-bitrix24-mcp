from mcp.server.fastmcp.server import FastMCP
import pytz

from mcp.server.fastmcp import FastMCP, Context
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
import json
from dotenv import load_dotenv
load_dotenv()
import os
from .bitrixWork import bit


mcp = FastMCP("helper")


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

    try:
        if entity == "task":
            # Используем кастомную функцию для задач
            order = {"ID": "DESC"}  # По умолчанию
            if 'order' in filter_fields:
                order = filter_fields.pop('order')
            items = await get_tasks_by_filter(filter_fields, select_fields, order)
        else:
            # Стандартные сущности CRM
            params: Dict[str, Any] = {"filter": filter_fields}
            if select_fields and select_fields != ["*"]:
                params["select"] = select_fields
            items = await bit.get_all(method_map[entity], params=params)
    except Exception as exc:
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
        if rdt is None and isinstance(rhs, str):
            # Поддержка ключевых слов относительно локального времени и TZ левого операнда
            tz = ldt.tzinfo if isinstance(ldt, datetime) else None
            rdt = _keyword_to_datetime(rhs, tz=tz)
        if ldt is not None and rdt is not None:
            # Выравниваем TZ: если один aware, другой naive — переносим tzinfo
            if (ldt.tzinfo is not None) and (rdt.tzinfo is None):
                rdt = rdt.replace(tzinfo=ldt.tzinfo)
            if (ldt.tzinfo is None) and (rdt.tzinfo is not None):
                ldt = ldt.replace(tzinfo=rdt.tzinfo)
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
            lhs = record.get(field)
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


def _apply_condition(records: List[Dict[str, Any]], condition: Optional[Union[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
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
            lhs = r.get(field)
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


def _ensure_list(value: Optional[Union[str, List[str]]]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


@mcp.tool()
async def analyze_export_file(file_path: str, operation: str, fields: Optional[Union[str, List[str]]] = None, condition: Optional[Union[str, Dict[str, Any]]] = None, group_by: Optional[List[str]] = None) -> Dict[str, Any]:
    """Анализ экспортированных данных из файла JSON
    - file_path: путь к файлу JSON
    - operation: операция анализа ('count', 'sum', 'avg', 'min', 'max')
    - fields: список полей для анализа (например ['UF_CRM_1749724770090', 'TITLE'])
    - condition: условие фильтрации (например {'UF_CRM_1749724770090': '47'}) это значит что найдет все записи где UF_CRM_1749724770090 равно 47
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

    filtered = _apply_condition(data, condition)
    groups = _ensure_list(group_by) if group_by else []
    op = operation.lower()
    fields_list = _ensure_list(fields)

    def group_key(rec: Dict[str, Any]) -> tuple:
        return tuple(rec.get(g) for g in groups) if groups else tuple()

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
                v = r.get(fld)
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


@mcp.tool()
async def analyze_tasks_export(file_path: str, operation: str, fields: Optional[Union[str, List[str]]] = None, condition: Optional[Union[str, Dict[str, Any]]] = None, group_by: Optional[List[str]] = None) -> Dict[str, Any]:
    """Анализ экспортированных задач из файла JSON
    - file_path: путь к файлу JSON с экспортом задач
    - operation: операция анализа ('count', 'sum', 'avg', 'min', 'max')
    - fields: список полей для анализа (например ['TIME_ESTIMATE', 'DURATION_FACT'])
    - condition: условие фильтрации (например {'STATUS': '5'} для завершённых задач)
    - group_by: группировка по полям (например ['RESPONSIBLE_ID', 'STATUS'])
    """
    return await analyze_export_file(file_path, operation, fields, condition, group_by)


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
    
