# math_server.py
from fastmcp import FastMCP, Context
from .promts.promts import mcp as promts_mcp
from .resources.userfields import mcp as userfields_mcp_resource
from .tools.deal import mcp as deal_mcp
from .tools.userfields import mcp as userfields_mcp
from .tools.user import mcp as user_mcp
from .tools.company import mcp as company_mcp
from .tools.contact import mcp as contact_mcp
from .tools.task import mcp as task_mcp
from .tools.helper import mcp as helper_mcp
from .tools.lead import mcp as lead_mcp
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent
from datetime import datetime
import os
from dotenv import load_dotenv
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
today=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# from fastmcp.server.auth import BearerAuthProvider
# from fastmcp.server.auth.providers.bearer import RSAKeyPair

# # Generate a new key pair
# key_pair = RSAKeyPair.generate()

# # Configure the auth provider with the public key
# auth = BearerAuthProvider(
#     public_key=key_pair.public_key,
#     issuer="https://dev.example.com",
#     audience="my-dev-server"
# )


# Аутентификация Bearer токеном из .env (AUTH_TOKEN). Обязательна для запуска.
load_dotenv()
AUTH_TOKEN = os.getenv("AUTH_TOKEN")

if not AUTH_TOKEN:
    raise RuntimeError("AUTH_TOKEN не задан в окружении (.env). Установите AUTH_TOKEN для запуска защищённого сервера.")

# Используем StaticTokenVerifier для проверки фиксированного Bearer токена из окружения
auth = StaticTokenVerifier(
    tokens={
        AUTH_TOKEN: {
            "client_id": "authorized_user",
            "scopes": ["read", "write"]
        }
    },
    required_scopes=["read"]
)
mcp = FastMCP("bitrix24-main", auth=auth)


mcp.mount(prefix="userfields", server=userfields_mcp_resource, as_proxy=True)
mcp.mount(prefix="promts", server=promts_mcp, as_proxy=True)
mcp.mount(prefix="deal", server=deal_mcp, as_proxy=True)
mcp.mount(prefix="fields", server=userfields_mcp, as_proxy=True)
mcp.mount(prefix="user", server=user_mcp, as_proxy=True)
mcp.mount(prefix="company", server=company_mcp, as_proxy=True)
mcp.mount(prefix="contact", server=contact_mcp, as_proxy=True)
mcp.mount(prefix="task", server=task_mcp, as_proxy=True)
mcp.mount(prefix="helper", server=helper_mcp, as_proxy=True)
mcp.mount(prefix="lead", server=lead_mcp, as_proxy=True)

@mcp.prompt(description="главный промт для взаимодействия с сервером который нужно использовать каждый раз при взаимодействии с сервером")
def main_prompt() -> str:
    print('==========='*20)
    content= f"""
    Текущая дата: {today}
    при любом взаимодействии с сущностями сначало нужно получить все доступные поля сущности,
    используй get_all_info_fields. 
    если поле имеет тип enumeration, то значения полях это id значений поля а чтобы получить значение нужно использовать информацию из get_all_info_fields
    чтобы узнать приоритет задачи сначала получи все поля задачь
    чтобы узнать текущую дату и время используй datetime_now

    """
    # return PromptMessage(role="user", content=TextContent(type="text", text=content))
    return content

# mcp.mount("userfields", userfields_mcp, False)
# mcp.mount("promts", promts_mcp, False)
# mcp.mount("deal", deal_mcp, False)

# Generate a token for testing
# token = key_pair.create_token(
#     subject="dev-user",
#     issuer="https://dev.example.com",
#     audience="my-dev-server",
#     scopes=["read", "write"]
# )

# print(f"Test token: {token}")


if __name__ == "__main__":
    # mcp.run(transport="stdio")
    mcp.run(transport="http", host="0.0.0.0", port=8000, timeout=10)
