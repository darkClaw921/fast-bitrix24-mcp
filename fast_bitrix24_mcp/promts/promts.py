from mcp.server.fastmcp import FastMCP, Context
from datetime import datetime
today=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
mcp = FastMCP("PromptServer")

# @mcp.resource("config://version")
# def get_version(): 
#     return "1.0.0"

@mcp.prompt()
def fields_for_entity(entity: list[str]=['all'], ctx: Context=None) -> str:
    """Информация о полях сущностей CRM"""
    return f"""
    Текущая дата: {today}
  При получении полей {entity} используйте следующий формат: \n\ndeal:
  {'ID': 'ID (integer)'}
  {'Название': 'TITLE (string)'}
  {'Тип': 'TYPE_ID (crm_status)'}
  {'Воронка': 'CATEGORY_ID (crm_category)'}
  {'Стадия сделки': 'STAGE_ID (crm_status)'}
  {'этаж доставки': 'UF_CRM_1749724770090 (enumeration):\n  на крышу (ID: 45):\n  1 (ID: 47):\n  3 (ID: 49):\n  в подвал (ID: 51)'}
  
  если польльзователь хочет взаимодействовать с полем типа enumeration, то учти что в ответе будет список значений и их ID например UF_CRM_1749724770090:49 - это значит что этаж доставки это 3
  для получения списка полей используйте ресурс get_fields_for_entity и передайте в него entity: list[str]
  Request ID: {ctx.request_id}
  """


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8000)