import os
import json
import re
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Production-stable model with high throughput on Groq
MODEL_NAME = "openai/gpt-oss-20b"

# ==========================================
# UPSKILLER ACADEMY KNOWLEDGE BASE
# ==========================================
UPSKILLER_KNOWLEDGE_BASE = """
You are the official AI Admissions Counselor & Executive Assistant for Upskiller Academy (Magnum Educorporates, Since 2013).
Website: https://upskilleracademy.com/courses/forex-trading-program
Enrollment Link: https://upskilleracademy.com
Brand Motto: "LEARN. PRACTICE. EARN. REPEAT. Join now & start your journey towards financial freedom!"

COURSE IN FOCUS:
"Professional Forex Trading Program"
- Duration: 3 Months comprehensive live mentorship (Foundation + Advanced + Live Market Practice).
- Batch Timing: Mon–Fri Evening Batch (8:00 PM – 9:30 PM IST) & Weekend Special Batches for working professionals.
- Language of Instruction: Hinglish (Hindi + English) with clean institutional terminology.
- Target Audience: Beginners to advanced traders, intraday & swing traders, aspiring prop firm traders, and anyone serious about institutional trading.
- Overview: Covers institutional price action, Smart Money Concepts (SMC), liquidity sweeps, market structure, high-probability setups, risk management, trader psychology, live trading, and prop firm passing strategies (FTMO style).

Fee & Enrollment Structure:
- Standard Fee: ₹24,999 (Full 3-Month Mentorship).
- Early Bird / Limited-Seat Offer: ₹14,999 one-time (or 2 easy installments of ₹8,000).
- Payment Details: Strict policy — AI never collects bank details directly; tell them our counselor will share the official payment link/QR code upon seat confirmation.

Key Features & Deliverables:
• 3 Months of Live interactive classes with lifetime access to session recordings
• Live Trading Sessions (London & New York market open sessions with mentors)
• Dedicated Doubt Solving Support & Private Community access
• High Probability Strategies (Liquidity sweeps & sniper entries)
• Money & Risk Management + Trader Psychology modules
• Prop Firm Evaluation Support (FTMO & funded account challenge prep)

Full 9-Module Curriculum:
01. Forex Basics & Market Fundamentals
02. Institutional Price Action Trading
03. Smart Money Concepts (SMC) & ICT Frameworks
04. Forex Chart Patterns & Market Cycles
05. Forex Sessions Strategy (London & New York timing)
06. High Probability Setups & Sniper Entries
07. Risk & Capital Management
08. Trader Psychology & Emotional Discipline
09. Advanced Forex Concepts & Prop Firm Challenges (FTMO passing)

Counselor Conversion Flow:
- When leads ask about fee/duration, highlight: 3 Months duration, live London/NY sessions, the special ₹14,999 offer, and ask if they would like to reserve a free demo seat or speak with a senior mentor.
"""


def extract_json_array(text: str) -> list:
    """Safely extracts a JSON array even if the model outputs thoughts or extra text."""
    if not text:
        return []

    # 1. Strip completed <think>...</think> tags
    clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # 2. Strip unclosed <think> blocks
    if "<think>" in clean_text:
        clean_text = re.sub(r"^<think>.*?(?=\[)", "", clean_text, flags=re.DOTALL).strip()

    # 3. Strip markdown code fences
    clean_text = re.sub(r"^```(?:json)?", "", clean_text, flags=re.MULTILINE)
    clean_text = re.sub(r"```$", "", clean_text, flags=re.MULTILINE).strip()

    # 4. If model output a single JSON object instead of a list, wrap it
    if clean_text.startswith("{") and clean_text.endswith("}"):
        try:
            single_obj = json.loads(clean_text)
            return [single_obj]
        except Exception:
            pass

    # 5. Find outermost brackets [ ... ]
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

    # 6. Regex extraction for array blocks
    match = re.search(r"(\[.*\])", clean_text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # 7. Fallback raw decode
    try:
        decoder = json.JSONDecoder()
        if start != -1:
            obj, _ = decoder.raw_decode(clean_text[start:])
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                return [obj]
    except Exception as e:
        print(f"Fallback JSON parser failed: {e}")

    return []


def extract_json_object(text: str) -> dict:
    """Safely extracts a single JSON object from raw LLM output."""
    if not text:
        return {}

    clean_text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    if "<think>" in clean_text:
        clean_text = re.sub(r"^<think>.*?(?=\{)", "", clean_text, flags=re.DOTALL).strip()

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
        trimmed_content = (m.content[:300] + "...") if len(m.content) > 300 else m.content
        content_lines.append(f"- [{m.platform.upper()}] From: {m.sender} | Text: {trimmed_content}")
    formatted_input = "\n".join(content_lines)

    prompt = f"""
You are an executive AI assistant for Upskiller Academy. Analyze these incoming messages and provide a concise, highly structured briefing for the executive.

MESSAGES:
{formatted_input}

OUTPUT FORMAT:
🎯 **Executive Briefing**
- Group by lead inquiries, course questions, or urgent action items.
- Mention key points clearly with bold tags.
- Highlight any pending high-ticket leads, questions, or calls requested.
Keep it strictly factual, concise, and under 200 words.
"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a concise executive assistant. Never output thinking tags, <think> tags, or conversational preambles."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.2,
            max_tokens=400,
        )
        raw_text = chat_completion.choices[0].message.content.strip()
        clean_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
        clean_text = re.sub(r"^<think>.*?\n\n", "", clean_text, flags=re.DOTALL).strip()
        return clean_text
    except Exception as e:
        print(f"Error generating summary with Groq: {e}")
        return "⚠️ Failed to generate summary due to an API error."


async def generate_draft_replies(messages: list) -> list[dict]:
    """
    Upskiller Academy Lead Qualification & Direct Dispatch Classifier.
    Supports English, Hindi, and natural Hinglish auto-matching.
    """
    if not messages or not client:
        return []

    content_lines = []
    for m in messages:
        safe_content = (m.content[:250] + "...").replace('"', "'").replace("\n", " ")
        content_lines.append(
            f'{{"id": {m.id}, "platform": "{m.platform}", "sender": "{m.sender}", "content": "{safe_content}"}}'
        )
    formatted_input = "\n".join(content_lines)

    prompt = f"""
{UPSKILLER_KNOWLEDGE_BASE}

Classify incoming student/lead messages on WhatsApp or Email and draft high-converting, professional replies.

CRITICAL INSTRUCTION:
Do NOT think or reason before answering. Begin immediately with the `[` character.

LANGUAGE & TONE RULES:
1. Mirror the user's language naturally:
   - Hinglish lead -> warm, clean Hinglish.
   - Pure Hindi lead -> polite Hindi.
   - English lead -> professional English.
2. Keep replies concise, persuasive, and under 3-4 sentences.
3. Always end with an actionable next step (e.g. asking to book a demo or speak with a counselor).

RULES FOR `can_auto_reply`:
1. SET `can_auto_reply = true` FOR:
   - Course overview, 3-month duration, syllabus inquiries (SMC, ICT, Prop firm, FTMO, London & New York live trading sessions).
   - Routine fee structure overviews (mention ₹14,999 offer), batch timings (Mon–Fri 8:00 PM – 9:30 PM IST or weekends), and recordings access.
   - Routine greetings & interest checks ("Hi", "Hello", "Hyy", "Forex details bhejo", "Course details please").
   - Routine availability checks or demo booking inquiries.

2. SET `can_auto_reply = false` (FLAG FOR HUMAN APPROVAL) FOR:
   - Direct price negotiation or custom discounts below ₹14,999.
   - Bank transfers, scanner/QR codes, UPI ID sharing, and payment receipts.
   - Corporate training, placement tie-ups, or franchise inquiries.

MESSAGES:
{formatted_input}

TASK:
Output strictly a valid JSON array. No explanations, markdown tags, or thinking blocks.
[
  {{
    "platform": "whatsapp",
    "recipient": "sender",
    "proposed_reply": "Natural reply matching the lead's exact language (Hinglish/English/Hindi) based on Upskiller Academy details.",
    "can_auto_reply": true,
    "intent_reason": "Course inquiry / Lead greeting"
  }}
]
"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a JSON-only CRM counselor for Upskiller Academy. You must not generate reasoning or thinking tags. Start output directly with [ and end with ].",
                },
                {"role": "user", "content": prompt},
            ],
            model=MODEL_NAME,
            temperature=0.2,
            max_tokens=400,
        )
        raw_text = chat_completion.choices[0].message.content.strip()
        print(f"[DEBUG GROQ RAW]:\n{raw_text}")
        drafts = extract_json_array(raw_text)
        return drafts
    except Exception as e:
        print(f"Error classifying and drafting replies with Groq: {e}")
        return []


async def process_user_chat_command(user_text: str) -> dict:
    """Processes interactive commands from the Telegram dashboard."""
    if not client:
        return {"intent": "chat", "reply": "⚠️ GROQ_API_KEY configure nahi hai."}

    prompt = f"""
You are an intelligent executive AI assistant for Upskiller Academy. The user typed the following input in the control chat:
"{user_text}"

Analyze intent:
1. ACTION INTENT: If the user is asking you to compose, draft, or send an email or WhatsApp message to a lead or contact.
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
                {"role": "system", "content": "You are a JSON-only assistant. Never output thinking tags or <think> blocks. Output strictly a JSON object."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.2,
            max_tokens=400,
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
You are an executive assistant for Upskiller Academy. Review these recent emails and tell the user if there is anything urgent or important requiring attention (e.g. lead inquiries, work requests, meetings, deadlines, payments). 

Ignore newsletters, spam, or routine system notifications.

EMAILS:
{mails_text}

Respond in simple Hinglish or English:
- If important emails exist, highlight who sent them and what urgent action is required.
- If none are important, state that all recent emails are routine or non-urgent.
Keep it strictly under 3-4 concise bullet points.
"""

    try:
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a concise executive assistant. Do not use thinking tags."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.2,
            max_tokens=350,
        )
        raw = completion.choices[0].message.content.strip()
        clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        clean = re.sub(r"^<think>.*?\n\n", "", clean, flags=re.DOTALL).strip()
        return clean
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
You are an executive assistant for Upskiller Academy. Analyze these recent WhatsApp messages and report if there is anything urgent or important requiring immediate response (e.g. hot leads, fee payments, student doubts, admissions).

Ignore routine greetings, small talk, or casual chatter.

MESSAGES:
{chats_text}

Respond in clean Hinglish or English:
- If urgent items exist, mention the sender and what action is needed.
- If no urgent items exist, state that all recent WhatsApp messages are casual or routine.
Keep it strictly under 3-4 concise bullet points.
"""

    try:
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a concise executive assistant. Do not use thinking tags."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL_NAME,
            temperature=0.2,
            max_tokens=350,
        )
        raw = completion.choices[0].message.content.strip()
        clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        clean = re.sub(r"^<think>.*?\n\n", "", clean, flags=re.DOTALL).strip()
        return clean
    except Exception as e:
        return f"Error analyzing WhatsApp messages: {e}"