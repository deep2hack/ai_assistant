import asyncio
import os
import httpx
from database import init_db
from dotenv import load_dotenv
from email_reader import check_new_emails
from summarizer import generate_summary

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def send_to_telegram(text: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=payload)
        return res.status_code == 200


async def main():
    print("1. Initializing Database...")
    await init_db()

    print("2. Ingesting Unread Emails...")
    await check_new_emails(limit=3)

    print("3. Generating AI Digest via Gemini...")
    summary = await generate_summary()
    print("\n--- Summary Generated ---\n", summary)

    print("4. Dispatching to Telegram Bot...")
    success = await send_to_telegram(summary)
    if success:
        print("\n✅ SUCCESS: Digest sent to Telegram!")
    else:
        print("\n❌ FAILED: Telegram delivery failed.")


if __name__ == "__main__":
    asyncio.run(main())