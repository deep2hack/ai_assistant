import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


async def summarize_messages(messages: list) -> str:
    """Generate an executive bullet-point summary of incoming messages."""
    if not messages:
        return "No new messages."

    if not client:
        return "⚠️ GEMINI_API_KEY is not configured in .env."

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
    """
    Classifies incoming messages into:
    1. Safe auto-replies (low risk routine messages) -> can_auto_reply: True
    2. High-risk decisions requiring human review -> can_auto_reply: False
    """
    if not messages or not client:
        return []

    content_lines = []
    for m in messages:
        content_lines.append(
            f'{{"id": {m.id}, "platform": "{m.platform}", "sender": "{m.sender}", "content": "{m.content}"}}'
        )
    formatted_input = "\n".join(content_lines)

    prompt = f"""
You are an executive AI assistant managing client communications across WhatsApp and Email.
Draft an appropriate professional reply for each message, and decide whether it is safe to AUTO-REPLY without human intervention.

CRITERIA FOR AUTO-REPLY (can_auto_reply: true):
- Routine greetings ("Hi", "Hello", "Good morning", "Hope you're well")
- Simple acknowledgments ("Received", "Thank you", "Noted", "Will check", "Okay")
- Standard receipt confirmations
- General availability checks without commitments ("Are you free to talk later?")

CRITERIA FOR HUMAN REVIEW (can_auto_reply: false):
- Financials, pricing, quotes, invoices, payment queries, discounts
- Project commitments, deadlines, contracts, scope discussions
- Rescheduling or confirming formal client meetings
- Complaints, escalations, critical bugs, or sensitive discussions
- Any ambiguous message where an incorrect reply causes business risk

MESSAGES:
{formatted_input}

TASK:
Return ONLY a valid JSON list of objects without markdown block formatting (no ```json):
[
  {{
    "platform": "whatsapp",
    "recipient": "sender_phone_or_email",
    "proposed_reply": "drafted reply text",
    "can_auto_reply": true,
    "intent_reason": "Routine greeting or acknowledgment"
  }}
]
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        raw_text = response.text.strip()

        # Clean code block backticks if present
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json\n"):
                raw_text = raw_text[5:]
            raw_text = raw_text.strip()

        drafts = json.loads(raw_text)
        if isinstance(drafts, list):
            return drafts
        return []
    except Exception as e:
        print(f"Error classifying and drafting replies: {e}")
        return []


# Backward compatibility alias
generate_summary = summarize_messages
