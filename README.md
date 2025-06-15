![PyPI - Format](https://img.shields.io/pypi/format/fast-bitrix24-mcp)
![PyPI - Status](https://img.shields.io/pypi/status/fast-bitrix24-mcp)
![PyPI - Downloads](https://img.shields.io/pypi/dm/fast-bitrix24-mcp)

# MCP сервер для взаимодействия с Bitrix24 rest api на основе fast-bitrix24
Сервер находится в стадии разработки и тестирования. Рекомендуется использовать только в локальной частной сети.

На данный момент сервер поддерживает следsующие сущности:
- сделки
- пользовательские поля 

поддержка человеческого названия полей даже для полей типа список
например:
- какая сумма сделок где поле 'этаж доставки' равно 'в подвал'?
- какая сумма сделок которые нужно доставить в подвал
- как называется поле у сделки с id UF_CRM_1749724770090?
- сколько сделок с названием Обновленная тестовая сделка?

# Установка и запуск сервера
установите переменные окружения из файла .env.example
```bash
cp .env.example .env
```

установите зависимости 
```bash
uv sync
```
или установите пакет
```bash
uv add fast-bitrix24-mcp
```

создайте файл для запуска сервера
```python
from fast_bitrix24_mcp.main import mcp

if __name__ == "__main__":  
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
    # mcp.run(transport="streamable-http", host="127.0.0.1", port=9000)
```

запустите сервер
```bash
uv run main.py
```


# inspector
ui для тестирования сервера
```bash
npx @modelcontextprotocol/inspector
```



# Пример использования в langchain
```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv
from pprint import pprint
load_dotenv()

client = MultiServerMCPClient(
    {
        
        "bitrix24-main": {
            "url": "http://localhost:8000/sse",
            "transport": "sse",
        }
    }
)
async def main():
    tools = await client.get_tools()
  
    promts = await client.get_prompt('bitrix24-main', 'main_prompt')
    promts=promts[0].content    
    # agent = create_react_agent("openai:gpt-4.1-nano-2025-04-14", tools, prompt=promt)
    agent = create_react_agent("openai:gpt-4.1-nano-2025-04-14", tools, prompt=promts, debug=True)
    # math_response = await agent.ainvoke({"messages": "сколько сделок с названием Обновленная тестовая сделка ?"})
    # math_response = await agent.ainvoke({"messages": "как называется поле у сделки с id UF_CRM_1749724770090?"})
    # math_response = await agent.ainvoke({"messages": "какая сумма сделок где поле 'этаж доставки' равно 'в подвал'"})
    # math_response = await agent.ainvoke({"messages": "какая сумма сделок у которых этаж доставки 'в подвал'?"})
    math_response = await agent.ainvoke({"messages": "покажи статистику по сделкам за сегодня и позавчера"})


    token=0
    for message in math_response["messages"]:
        print(message.content + "\n\n")
        
    # pprint(math_response)
    token=math_response["messages"][-1].usage_metadata['total_tokens']
    print(f'token: {token}')
    
        

    while True:
        message = input("Введите сообщение: ")
        math_response["messages"].append({"role": "user", "content": message})
        math_response = await agent.ainvoke(math_response)
        for message in math_response["messages"]:
            print(message.content + "\n\n")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
``` 

)
