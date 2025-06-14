from mcp.server.fastmcp import FastMCP, Context
from ..tools.userfields import get_all_info_fields
mcp = FastMCP("userfields")

@mcp.resource("config://version")
def get_version(): 
    return "1.0.0"


@mcp.resource("fields://{entity}")
async def get_fields_for_entity(entity: list[str]) -> str:
    """Получение всех полей сделки, контакта, компании
    args:
        entity: list[str] - ['deal', 'contact', 'company'] or ['all']
    return:
        allText: str - все поля сделки, контакта, компании
    """
    return await get_all_info_fields(entity)

