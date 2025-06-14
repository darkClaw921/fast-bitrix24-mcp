# math_server.py
from fastmcp import FastMCP, Context
from .promts.promts import mcp as promts_mcp
from .resources.userfields import mcp as userfields_mcp_resource
from .tools.deal import mcp as deal_mcp
from .tools.userfields import mcp as userfields_mcp
from fastmcp.prompts.prompt import Message, PromptMessage, TextContent
from datetime import datetime
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


# mcp = FastMCP("bitrix24", auth=auth)
mcp = FastMCP("bitrix24-main")


mcp.mount("userfields", userfields_mcp_resource, True)
mcp.mount("promts", promts_mcp, True)
mcp.mount("deal", deal_mcp, True)
mcp.mount('fields', userfields_mcp, True)


@mcp.prompt(description="главный промт для взаимодействия с сервером который нужно использовать каждый раз при взаимодействии с сервером")
def main_prompt() -> str:
    print('==========='*20)
    content= f"""
    Текущая дата: {today}
    при любом взаимодействии с сущностями сначало нужно получить все доступные поля сущности,
    используй get_all_info_fields. 
    если поле имеет тип enumeration, то значения полях это id значений поля а чтобы получить значение нужно использовать информацию из get_all_info_fields
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
   mcp.run(transport="sse", host="0.0.0.0", port=8000, timeout=600)
