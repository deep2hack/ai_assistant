import asyncio
from database import init_db, fetch_unsummarized_messages
from email_reader import check_new_emails

async def main():
    await init_db()
    count = await check_new_emails(limit=3)
    
    records = await fetch_unsummarized_messages()
    print(f"\n--- Ab Database me Total Unsummarized Items: {len(records)} ---")

if __name__ == "__main__":
    asyncio.run(main())