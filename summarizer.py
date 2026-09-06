import os
import json
import re
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
MODEL_NAME = "llama-3.1-8b-instant" 


def extract_json_array(text: str) -> list:
    """Safely extracts a JSON array even if the model outputs thoughts or extra text."""
    if not text:
        return []

    # 1. Strip reasoning tags if model outputs <think>...</think>
    clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # 2. Strip code fences
    if "```" in clean_text:
        match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", clean_text, re.DOTALL)
        if match:
            clean_text = match.group(1).strip()
        else:
            clean_text = clean_text.strip("`").replace("json\n", "", 1).strip()

    # 3. Find first [ and last ]
    start = clean_text.find("[")
    end = clean_text.rfind("]")

    if start != -1 and end != -1 and end > start:
        candidate = clean_text[start : end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # 4. Fallback: json.JSONDecoder raw decode to ignore trailing extra data
    try:
        decoder = json.JSONDecoder()
        if start != -1:
            obj, _ = decoder.raw_decode(clean_text[start:])
            if isinstance(obj, list):
                return obj
    except Exception as e:
        print(f"Fallback JSON parser failed: {e}")

    return []


def extract_json_object(text: str) -> dict:
    """Safely extracts a single JSON object from raw LLM output."""
    if not text:
        return {}

    clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    if "```" in clean_text:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_text, re.DOTALL)
        if match:
            clean_text = match.group(1).strip()

    start = clean_text.find("{")
    end = clean_text.rfind("}")

    if start != -1 and end != -1 and end > start:
        candidate = clean_text[start : end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    try:
        decoder = json.JSONDecoder()
        if start != -1:
            obj, _ = decoder.raw_decode(clean_text[start:])
            if isinstance(obj, dict):
                return obj
    except Exception as e:
        print(f"Fallback JSON object parser failed: {e}")

    return {}


async def summarize_messages(messages: list) -> str:
    """Generate an executive bullet-point summary using Groq."""
    if not messages:
        return "No new messages."

    if not client:
        return "⚠️ GROQ_API_KEY is not configured in .env."

    content_lines = []
    for m in messages:
        # Strict Token Safety: Max 500 characters per message
        trimmed_content = (m.content[:500] + "...") if len(m.content) > 500 else m.content
        content_lines.append(f"- [{m.platform.upper()}] From: {m.sender} | Text: {trimmed_content}")
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
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a concise executive assistant. Do not output thinking tokens."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.3,
        )
        raw_text = chat_completion.choices[0].message.content.strip()
        return re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    except Exception as e:
        print(f"Error generating summary with Groq: {e}")
        return "⚠️ Failed to generate summary due to an API error."


async def generate_draft_replies(messages: list) -> list[dict]:
    """
    Classifies incoming messages into:
    1. Safe auto-replies (low risk) -> can_auto_reply: True
    2. High-risk decisions requiring review -> can_auto_reply: False
    """
    if not messages or not client:
        return []

    content_lines = []
    for m in messages:
        # Strict Token & Formatting Safety
        safe_content = (m.content[:500] + "...") if len(m.content) > 500 else m.content
        safe_content = safe_content.replace('"', "'").replace("\n", " ")
        content_lines.append(
            f'{{"id": {m.id}, "platform": "{m.platform}", "sender": "{m.sender}", "content": "{safe_content}"}}'
        )
    formatted_input = "\n".join(content_lines)

    prompt = f"""
You are an executive AI assistant managing communications across WhatsApp and Email.
Draft an appropriate professional reply for each message, and decide whether it is safe to AUTO-REPLY without human intervention.

CRITERIA FOR AUTO-REPLY (can_auto_reply: true):
- Routine greetings ("Hi", "Hello", "Good morning")
- Simple acknowledgments ("Received", "Thank you", "Noted", "Okay")
- Standard automated receipts/confirmations

CRITERIA FOR HUMAN REVIEW (can_auto_reply: false):
- Financials, pricing, quotes, invoices, payment queries
- Project commitments, deadlines, contracts, scope discussions
- Rescheduling meetings or complaints/escalations

MESSAGES:
{formatted_input}

TASK:
Output ONLY a raw JSON array. No explanations, no markdown fences, no thinking tags.
Example output format:
[
  {{
    "platform": "email",
    "recipient": "sender@domain.com",
    "proposed_reply": "Hi, thanks for reaching out. Here is the requested update...",
    "can_auto_reply": false,
    "intent_reason": "Quotation and pricing requires human review"
  }}
]
"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a JSON-only API. You output strictly valid raw JSON arrays without preamble or thinking steps."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.1,
        )
        raw_text = chat_completion.choices[0].message.content.strip()
        drafts = extract_json_array(raw_text)
        return drafts
    except Exception as e:
        print(f"Error classifying and drafting replies with Groq: {e}")
        return []


async def process_user_chat_command(user_text: str) -> dict:
    """
    User ke typed message ko process karta hai:
    - Normal queries/questions ka smart, concise jawab deta hai.
    - Message/Email dispatch commands (e.g. 'X ko mail bhej do...') par structured action draft banata hai.
    """
    if not client:
        return {"intent": "chat", "reply": "⚠️ GROQ_API_KEY configure nahi hai."}

    prompt = f"""
You are an intelligent executive AI assistant. The user typed the following input in the control chat:
"{user_text}"

Analyze intent:
1. ACTION INTENT: If the user is asking you to compose, draft, or send an email or WhatsApp message.
   Return ONLY JSON:
   {{
     "intent": "action",
     "platform": "email" or "whatsapp",
     "recipient": "extracted email or phone or contact name",
     "subject": "subject line if email, otherwise null",
     "draft": "the actual drafted text body"
   }}

2. CHAT/QUERY INTENT: If the user is asking a general question, asking for help, drafting assistance, or conversational queries.
   Return ONLY JSON:
   {{
     "intent": "chat",
     "reply": "clear, professional, direct response"
   }}

Output strictly valid JSON with no preamble, markdown fences, or thinking tags.
"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a JSON-only assistant. Output strictly a JSON object."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.2,
        )
        raw_text = chat_completion.choices[0].message.content.strip()
        result = extract_json_object(raw_text)
        if result:
            return result
    except Exception as e:
        print(f"Error processing custom chat command: {e}")

    return {
        "intent": "chat",
        "reply": "Samajh nahi paya, kripya thoda aur clearly likhein ya command use karein."
    }


generate_summary = summarize_messages

async def check_important_emails_summary(emails: list) -> str:
    """Live inbox emails me se urgent/important identify karke brief deta hai."""
    if not emails:
        return "Inbox me abhi koi naya email nahi mila."
    if not client:
        return "⚠️ Groq API key configured nahi hai."

    content_lines = []
    for idx, mail in enumerate(emails, start=1):
        content_lines.append(f"{idx}. From: {mail.get('sender')} | Subject: {mail.get('subject')} | Snippet: {mail.get('snippet')}")
    mails_text = "\n".join(content_lines)

    prompt = f"""
You are an executive assistant. Review these recent emails and tell the user if there is anything urgent or important requiring attention (e.g. work requests, meetings, deadlines, payments, client inquiries). 

Ignore newsletters, ads, or routine system notifications.

EMAILS:
{mails_text}

Respond in simple Hinglish or English:
- If important emails exist, highlight who sent them and what urgent action is required.
- If none are important, state that all recent emails are routine or non-urgent.
Keep it under 3-4 bullet points.
"""

    try:
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a concise executive assistant."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.2,
        )
        raw = completion.choices[0].message.content.strip()
        return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    except Exception as e:
        return f"Error analyzing emails: {e}"
async def check_important_whatsapp_summary(messages: list) -> str:
    """Recent WhatsApp messages me se urgent/actionable chats filter karta hai."""
    if not messages:
        return "Database me abhi koi WhatsApp message nahi mila."
    if not client:
        return "⚠️ Groq API key configured nahi hai."

    content_lines = []
    for idx, m in enumerate(messages, start=1):
        content_lines.append(f"{idx}. From: {m.sender} | Text: {m.content}")
    chats_text = "\n".join(content_lines)

    prompt = f"""
You are an executive assistant. Analyze these recent WhatsApp messages and report if there is anything urgent or important requiring immediate response (e.g. client requests, deadlines, meetings, questions).

Ignore routine greetings, small talk, or casual chatter.

MESSAGES:
{chats_text}

Respond in clean Hinglish or English:
- If urgent items exist, mention the sender and what action is needed.
- If no urgent items exist, state that all recent WhatsApp messages are casual or routine.
Keep it strictly under 3-4 bullet points.
"""

    try:
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a concise executive assistant."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.2,
        )
        raw = completion.choices[0].message.content.strip()
        return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    except Exception as e:
        return f"Error analyzing WhatsApp messages: {e}"
