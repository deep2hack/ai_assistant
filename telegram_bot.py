import os
import httpx
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def get_main_menu_keyboard() -> dict:
    """Chat box ke bottom par hamesha dikhne wale persistent buttons."""
    return {
        "keyboard": [
            [{"text": "📊 Today's Update"}, {"text": "🚀 Run Full Digest"}],
            [{"text": "✉️ Last 5 Emails"}, {"text": "💬 Last 5 WhatsApp"}],
            [{"text": "📋 All Recent Messages"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


async def send_telegram_message(
    chat_id: str | int,
    text: str,
    parse_mode: str = "Markdown",
    reply_markup: dict = None,
) -> bool:
    """Standard message ya updated preview bhejne ke liye."""
    if not TELEGRAM_BOT_TOKEN:
        print("Telegram bot token missing in .env")
        return False

    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(url, json=payload, timeout=10.0)
            if res.status_code != 200:
                # Agar Markdown formatting parse fail hoti hai toh fallback plain text bhejega
                payload.pop("parse_mode", None)
                fallback_res = await client.post(url, json=payload, timeout=10.0)
                return fallback_res.status_code == 200
            return True
        except Exception as e:
            print(f"Error sending Telegram message: {e}")
            return False


async def send_telegram_ack(callback_query_id: str, text: str = "") -> bool:
    """Button tap ka loading spinner hatane ke liye."""
    if not TELEGRAM_BOT_TOKEN:
        return False

    url = f"{BASE_URL}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": False,
    }

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(url, json=payload, timeout=5.0)
            return res.status_code == 200
        except Exception as e:
            print(f"Error acknowledging callback query: {e}")
            return False


async def send_action_card(
    chat_id: str | int,
    action_id: int,
    platform: str,
    recipient: str,
    proposed_text: str,
) -> bool:
    """Approve, Edit aur Dismiss inline buttons ke sath draft card bhejna."""
    card_text = (
        f"🤖 **Draft Reply Proposal (ID: {action_id})**\n\n"
        f"**Platform:** {platform.upper()}\n"
        f"**To:** `{recipient}`\n"
        f"**Proposed Text:**\n_{proposed_text}_\n\n"
        f"Kya aap ise approve karna chahte hain?"
    )

    markup = {
        "inline_keyboard": [
            [
                {"text": "🚀 Approve & Send", "callback_data": f"approve_{action_id}"},
                {"text": "✏️ Edit Draft", "callback_data": f"edit_{action_id}"},
            ],
            [
                {"text": "❌ Dismiss", "callback_data": f"dismiss_{action_id}"}
            ],
        ]
    }

    return await send_telegram_message(
        chat_id=chat_id,
        text=card_text,
        reply_markup=markup,
    )