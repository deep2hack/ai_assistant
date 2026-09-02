import os
from database import fetch_unsummarized_messages, mark_messages_as_summarized
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


async def generate_summary():
    records = await fetch_unsummarized_messages()
    if not records:
        return "ℹ️ *No new unread messages or emails to summarize.*"

    compiled_context = ""
    processed_ids = []

    for r in records:
        processed_ids.append(r.id)
        compiled_context += (
            f"\n[Platform: {r.platform.upper()}] From: {r.sender}\n"
            f"Content: {r.content}\n"
            f"Time: {r.timestamp}\n"
            "-------------------"
        )

    prompt = f"""
    You are an executive assistant. Analyze these incoming messages from email and chat platforms:

    {compiled_context}

    Provide a concise, mobile-friendly Telegram briefing formatted in clean Markdown:
    🚨 *Urgent & Action Items*
    - Highlight critical updates, deadlines, or actionable leads.

    📊 *Platform Breakdown*
    - Categorize key points by channel (Email / WhatsApp / Telegram).

    💡 *Recommended Next Steps*
    - 1-2 quick action steps.
    """

    try:
        chat = client.chats.create(model="gemini-3.6-flash")
        response = chat.send_message(prompt)
        summary_text = response.text

        await mark_messages_as_summarized(processed_ids)
        return summary_text

    except Exception as e:
        print(f"Gemini API Error: {e}")
        return f"⚠️ *Error generating briefing:* {e}"