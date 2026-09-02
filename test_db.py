import asyncio
from database import init_db, save_message, fetch_unsummarized_messages

async def main():
    print("Database initialize ho raha hai...")
    await init_db()

    # Ek dummy message save karke dekhte hain
    await save_message("whatsapp", "+919876543210", "Hey, do you have time for a call?")
    await save_message("email", "client@company.com", "Project proposal update attached.")

    # Unsummarized records fetch karte hain
    records = await fetch_unsummarized_messages()
    print(f"\nTotal Unsummarized Messages in DB: {len(records)}")
    for r in records:
        print(f"[{r.platform.upper()}] from {r.sender}: {r.content}")

if __name__ == "__main__":
    asyncio.run(main())