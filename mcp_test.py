from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
from pprint import pprint

client = OpenAI()

resp = client.responses.create(
    # model="gpt-4.1-nano-2025-04-14",
    model="gpt-4.1-mini-2025-04-14",
    # model="o4-mini-2025-04-16",
    # model="o3-mini-2025-01-31",
    reasoning={'effort':None, 'generate_summary':None, 'summary':'auto'},
    tools=[
        {
            "type": "mcp",
            "server_label": "bitrix24-main",
            "server_url": "https://ea37-212-193-1-146.ngrok-free.app/sse",
            "require_approval": "never",
        },
    ],
    input="Сколько сделок нужно доставить в подвал? Покажи все поля сделки",
)

print("=========="*20)
pprint(resp.__dict__)
pprint(resp.output_text)