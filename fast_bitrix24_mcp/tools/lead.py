from mcp.server.fastmcp import FastMCP, Context
from dotenv import load_dotenv
load_dotenv()
import os
from typing import List, Dict, Any
from pprint import pprint

from .bitrixWork import bit
from .helper import prepare_fields_to_humman_format
from .userfields import get_all_info_fields

mcp = FastMCP("lead")




@mcp.tool()
async def list_lead(filter_fields: Dict[str, Any] = {}, fields_id: List[str] = ["ID", "TITLE"]) -> str:
    """Список лидов
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

    # Получаем описание полей лида в человеко-читаемом виде
    all_info_fields = await get_all_info_fields(['lead'], isText=False)
    lead_fields_info = all_info_fields["lead"]

    # Гарантируем базовые поля при частичном выборе
    if "*" not in fields_id:
        if "ID" not in fields_id:
            fields_id.append("ID")
        if "TITLE" not in fields_id:
            fields_id.append("TITLE")

    text = f"Список лидов по фильтру {filter_fields}:\n"

    # Получение лидов напрямую через Bitrix API
    params: Dict[str, Any] = {"filter": filter_fields}
    if "*" not in fields_id:
        params["select"] = fields_id

    leads = await bit.get_all('crm.lead.list', params=params)

    prepared_leads: List[Dict[str, Any]] = []
    if "*" in fields_id:
        for lead in leads:
            prepared_leads.append(lead)
    else:
        for lead in leads:
            subset: Dict[str, Any] = {}
            for field in fields_id:
                subset[field] = lead.get(field)
            prepared_leads.append(subset)

    for lead in prepared_leads:
        title = lead.get("TITLE", "<без названия>")
        text += f"=={title}==\n"
        pprint(lead)
        human = prepare_fields_to_humman_format(lead, lead_fields_info)
        for key, value in human.items():
            text += f"  {key}: {value}\n"
        text += "\n"

    return text


if __name__ == "__main__":
    pass


