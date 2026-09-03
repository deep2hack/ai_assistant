import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

# GEMINI_API_KEY .env se load hoga
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


async def summarize_messages(messages: list) -> str:
    """Generate an executive bullet-point summary of unread messages."""
    if not messages:
        return "No new messages."

    if not client:
        return "⚠️ GEMINI_API_KEY is not configured in .env."

    # Format messages for the prompt
    content_lines = []
    for m in messages:
        content_lines.append(f"- [{m.platform.upper()}] From: {m.sender} | Text: {m.content}")
    formatted_input = "\n".join(content_lines)

    prompt = f"""
You are an executive AI assistant. Analyze these incoming messages and provide a concise, highly structured briefing for the executive.

MESSAGES:
{formatted_input}

OUTPUT FORMAT:
🎯 **Executive Briefing**
- Group by sender or urgent action items.
- Mention key points clearly with bold tags.
- Highlight any pending tasks, meetings, or critical questions.
Keep it strictly factual and concise.
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"Error generating summary with Gemini: {e}")
        return "⚠️ Failed to generate summary due to an API error."


async def generate_draft_replies(messages: list) -> list[dict]:
    """Generate suggested draft replies for messages that require a response."""
    if not messages or not client:
        return []

    content_lines = []
    for m in messages:
        content_lines.append(
            f'{{"id": {m.id}, "platform": "{m.platform}", "sender": "{m.sender}", "content": "{m.content}"}}'
        )
    formatted_input = "\n".join(content_lines)

    prompt = f"""
You are an executive assistant drafting quick, polite, and professional replies to incoming messages.

MESSAGES:
{formatted_input}

TASK:
Identify each message that requires an acknowledgement, answer, or reply. 
Return ONLY a valid JSON list of objects. Do not include markdown code block backticks (like ```json), just the raw JSON.

JSON schema per item:
[
  {{
    "platform": "whatsapp",
    "recipient": "sender_phone_or_email",
    "proposed_reply": "drafted reply text here"
  }}
]
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        raw_text = response.text.strip()

        # Clean code block backticks if returned by the model
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`").replace("json\n", "", 1).strip()

        drafts = json.loads(raw_text)
        if isinstance(drafts, list):
            return drafts
        return []
    except Exception as e:
        print(f"Error generating draft replies: {e}")
        # Fallback empty list so pipeline doesn't crash
        return []


# Backward compatibility alias
generate_summary = summarize_messages
