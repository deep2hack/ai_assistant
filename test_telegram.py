import os
import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def send_test():
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "🚀 Hello from your AI Communication Aggregator! System initialization successful."
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=payload)
        if res.status_code == 200:
            print("SUCCESS: Message sent to telegram!!!")
        else:
            print(f"FAILED: Status {res.status_code}, Details: {res.text}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(send_test())