import os
import time
import asyncio
import logging
from types import SimpleNamespace
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, Query, BackgroundTasks

from database import (
    init_db,
    save_message,
    fetch_unsummarized_messages,
    mark_messages_summarized,
    save_pending_action,
    get_pending_action,
    update_pending_action_status,
    update_pending_action_text,
    set_action_status,
    get_editing_action,
    get_recent_messages_by_platform,
    get_latest_messages_all,
    get_todays_stats,
    create_pending_action,
)
from summarizer import (
    summarize_messages,
    generate_draft_replies,
    process_user_chat_command,
    check_important_emails_summary,
    check_important_whatsapp_summary,
)
from telegram_bot import (
    send_telegram_message,
    send_telegram_ack,
    send_action_card,
    get_main_menu_keyboard,
)
from reply_sender import send_whatsapp_reply, send_email_reply
from email_reader import check_new_emails, fetch_latest_emails

# Always reload environment freshly
load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
)
logger = logging.getLogger("ExecutiveAssistant")

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "my_secure_token")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "admin123")
SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT_SECONDS", "7200"))

# Stores chat_id -> last_activity_timestamp (Unix epoch)
authenticated_sessions: dict[int, float] = {}


def is_session_active(chat_id: int) -> bool:
    """Checks if chat session is verified and not expired."""
    if chat_id not in authenticated_sessions:
        return False

    last_active = authenticated_sessions[chat_id]
    if (time.time() - last_active) > SESSION_TIMEOUT_SECONDS:
        del authenticated_sessions[chat_id]
        return False

    authenticated_sessions[chat_id] = time.time()
    return True


# ==========================================
# LIFESPAN
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Shutdown complete.")


app = FastAPI(title="AI Executive Assistant", lifespan=lifespan)


# ==========================================
# 0. MANUAL TRIGGER ENDPOINTS
# ==========================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "AI Executive Assistant"}


@app.post("/digest/run")
async def trigger_digest(background_tasks: BackgroundTasks):
    background_tasks.add_task(dispatch_full_digest)
    return {"status": "accepted", "detail": "Pipeline dispatched in background"}


# ==========================================
# 1. WHATSAPP WEBHOOK (AUTONOMOUS PROCESSING)
# ==========================================

@app.get("/webhook/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified.")
        return Response(content=hub_challenge, media_type="text/plain", status_code=200)
    return Response(content="Verification failed", status_code=403)


@app.post("/webhook/whatsapp")
async def receive_whatsapp_message(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        entries = data.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    if msg.get("type") == "text":
                        sender_name = msg.get("from")
                        raw_id = msg.get("raw_id", sender_name)
                        body = msg.get("text", {}).get("body", "").strip()

                        if sender_name and body:
                            # 1. Database me Clean Display Name / Phone save karein
                            await save_message("whatsapp", sender_name, body)
                            logger.info(f"Saved WhatsApp from: {sender_name}")

                            # 2. Structured message object
                            msg_obj = SimpleNamespace(
                                id=None,
                                platform="whatsapp",
                                sender=sender_name,
                                content=body,
                            )

                            # 3. Background autonomous processor
                            background_tasks.add_task(
                                process_realtime_whatsapp,
                                msg_obj,
                                sender_name,
                                raw_id,
                                body,
                            )
    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}")

    return Response(content="EVENT_RECEIVED", status_code=200)


async def process_realtime_whatsapp(saved_msg, display_name: str, delivery_target: str, incoming_text: str):
    """
    Evaluates and automatically replies to incoming WhatsApp messages
    with zero-to-low human engagement.
    """
    try:
        drafts = await generate_draft_replies([saved_msg])
        if not drafts:
            logger.info("No draft generated for incoming WhatsApp message.")
            return

        draft = drafts[0]
        reply_text = draft.get("proposed_reply", "").strip()
        can_auto = draft.get("can_auto_reply", True)
        reason = draft.get("intent_reason", "Routine acknowledgment")

        if not reply_text:
            return

        # Case A: Autonomous Direct Send (Zero Action Required)
        if can_auto:
            logger.info(f"Auto-dispatching WhatsApp reply to destination: {delivery_target}")
            sent = await send_whatsapp_reply(delivery_target, reply_text)

            if sent:
                action_id = await save_pending_action("whatsapp", delivery_target, reply_text)
                await update_pending_action_status(action_id, "EXECUTED")
                if getattr(saved_msg, "id", None):
                    await mark_messages_summarized([saved_msg.id])

                if TELEGRAM_CHAT_ID:
                    auto_note = (
                        f"⚡ **Autonomous WhatsApp Reply Sent**\n\n"
                        f"**To:** `{display_name}`\n"
                        f"**Incoming:** _{incoming_text}_\n"
                        f"**Sent Reply:** _{reply_text}_\n"
                        f"**Reason:** {reason}"
                    )
                    await send_telegram_message(TELEGRAM_CHAT_ID, auto_note)
                return

        # Case B: Sensitive message fallback - Action Card sent to Telegram
        action_id = await save_pending_action("whatsapp", delivery_target, reply_text)
        if getattr(saved_msg, "id", None):
            await mark_messages_summarized([saved_msg.id])

        if TELEGRAM_CHAT_ID:
            await send_action_card(
                chat_id=TELEGRAM_CHAT_ID,
                action_id=action_id,
                platform="whatsapp",
                recipient=display_name,
                proposed_text=reply_text,
            )

    except Exception as e:
        logger.error(f"Error in process_realtime_whatsapp: {e}", exc_info=True)


# ==========================================
# 2. TELEGRAM WEBHOOK (Buttons, Actions & AI Chat)
# ==========================================

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return Response(content="BAD_REQUEST", status_code=400)

    # Case A: Inline action buttons (Approve, Edit, Dismiss)
    if "callback_query" in data:
        cb = data["callback_query"]
        cb_id = cb["id"]
        cb_data = cb.get("data", "")
        chat_id = cb.get("message", {}).get("chat", {}).get("id")

        if not is_session_active(chat_id):
            await send_telegram_ack(cb_id, "Session expired. Kripya pehle password enter karein.")
            return Response(status_code=200)

        try:
            if cb_data.startswith("approve_"):
                action_id = int(cb_data.split("_")[1])
                action = await get_pending_action(action_id)

                if not action:
                    await send_telegram_ack(cb_id, "Action not found.")
                    return Response(status_code=200)

                if action.status == "EXECUTED":
                    await send_telegram_ack(cb_id, "Already sent!")
                    return Response(status_code=200)

                await send_telegram_ack(cb_id, f"Dispatching {action.platform} reply...")

                success = False
                if action.platform.lower() == "whatsapp":
                    success = await send_whatsapp_reply(str(action.recipient).strip(), action.proposed_text)
                elif action.platform.lower() == "email":
                    success = await send_email_reply(
                        to_email=action.recipient,
                        subject=getattr(action, "subject", None) or "Re: Quick Update",
                        body=action.proposed_text,
                    )

                if success:
                    await update_pending_action_status(action_id, "EXECUTED")
                    await send_telegram_message(
                        chat_id,
                        f"✅ Reply successfully dispatched via {action.platform.upper()} to `{action.recipient}`.",
                    )
                else:
                    await send_telegram_message(
                        chat_id,
                        f"❌ Failed to dispatch reply to `{action.recipient}`.",
                    )

            elif cb_data.startswith("edit_"):
                action_id = int(cb_data.split("_")[1])
                await set_action_status(action_id, "EDITING")
                await send_telegram_ack(cb_id, "Edit mode activated.")
                await send_telegram_message(
                    chat_id,
                    f"✏️ **Edit Draft (ID: {action_id})**\n\nNiche apna modified reply likh kar send karein:",
                )

            elif cb_data.startswith("dismiss_"):
                action_id = int(cb_data.split("_")[1])
                await set_action_status(action_id, "DISMISSED")
                await send_telegram_ack(cb_id, "Dismissed.")
                await send_telegram_message(chat_id, f"❌ Draft ID {action_id} dismissed.")

        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            await send_telegram_ack(cb_id, "Action failed.")

        return Response(status_code=200)

    # Case B: Text message (Menu buttons, commands, or typed queries)
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"]["text"].strip()

        # Password authentication & Auto-lock Gate
        if not is_session_active(chat_id):
            if user_text == BOT_PASSWORD:
                authenticated_sessions[chat_id] = time.time()
                welcome = (
                    "🔓 **Access Granted!**\n\n"
                    f"Aapka session authenticate ho gaya hai (Auto-lock: {SESSION_TIMEOUT_SECONDS // 3600}h inactivity).\n"
                    "Niche diye gaye menu se control karein:"
                )
                await send_telegram_message(chat_id, welcome, reply_markup=get_main_menu_keyboard())
                return Response(status_code=200)
            else:
                lock_msg = (
                    "🔒 **Session Locked / Access Denied**\n\n"
                    "Aapka session lock ho chuka hai ya unauthorized access hai.\n"
                    "Use karne ke liye **password** type karke send karein."
                )
                await send_telegram_message(chat_id, lock_msg)
                return Response(status_code=200)

        # Manual Lock Command
        if user_text in ["/lock", "🔒 Lock"]:
            if chat_id in authenticated_sessions:
                del authenticated_sessions[chat_id]
            await send_telegram_message(chat_id, "🔒 Bot successfully lock kar diya gaya hai. Re-login ke liye password enter karein.")
            return Response(status_code=200)

        # 1. Check if user is currently editing a draft
        editing_action = await get_editing_action()
        if editing_action:
            updated = await update_pending_action_text(editing_action.id, user_text)
            markup = {
                "inline_keyboard": [
                    [
                        {"text": "🚀 Approve & Send", "callback_data": f"approve_{updated.id}"},
                        {"text": "✏️ Edit Again", "callback_data": f"edit_{updated.id}"},
                    ],
                    [{"text": "❌ Dismiss", "callback_data": f"dismiss_{updated.id}"}],
                ]
            }
            msg = (
                f"📝 **Updated Draft (ID: {updated.id})**\n\n"
                f"**To:** `{updated.recipient}`\n"
                f"**Reply:**\n_{updated.proposed_text}_"
            )
            await send_telegram_message(chat_id, msg, reply_markup=markup)
            return Response(status_code=200)

        # 2. Main Menu / Start command
        if user_text in ["/start", "/menu"]:
            welcome = (
                "👋 **Executive Assistant Control Panel**\n\n"
                "Niche diye gaye options par tap karein ya seedhe koi bhi message/instruction type karein:"
            )
            await send_telegram_message(chat_id, welcome, reply_markup=get_main_menu_keyboard())
            return Response(status_code=200)

        # 3. Today's Update
        elif user_text in ["📊 Today's Update", "/today"]:
            counts, pending = await get_todays_stats()
            stats_msg = "📈 **Today's Activity Overview**\n\n"
            if not counts:
                stats_msg += "• Aaj koi naya message log nahi hua.\n"
            else:
                for platform, count in counts:
                    stats_msg += f"• **{platform.upper()}:** {count} message(s)\n"
            stats_msg += f"\n⚠️ **Pending Approvals:** {pending}"
            await send_telegram_message(chat_id, stats_msg)
            return Response(status_code=200)

        # 4. Last 5 Emails (Read + Unread Live from Inbox)
        elif user_text in ["✉️ Last 5 Emails", "/mails"]:
            await send_telegram_message(chat_id, "🔍 Inbox se latest 5 emails fetch ho rahe hain...")
            emails = await fetch_latest_emails(limit=5)

            if not emails:
                await send_telegram_message(chat_id, "ℹ️ Inbox me koi relevant email nahi mila.")
                return Response(status_code=200)

            reply = "📬 **Latest 5 Emails (Read + Unread):**\n\n"
            for idx, mail in enumerate(emails, start=1):
                reply += (
                    f"{idx}. **From:** `{mail['sender']}`\n"
                    f"   **Subject:** *{mail['subject']}*\n"
                    f"   _{mail['snippet']}..._\n\n"
                )
            await send_telegram_message(chat_id, reply)
            return Response(status_code=200)

        # 5. Last 5 WhatsApp Messages
        elif user_text in ["💬 Last 5 WhatsApp", "/whatsapp"]:
            chats = await get_recent_messages_by_platform("whatsapp", limit=5)
            if not chats:
                await send_telegram_message(chat_id, "ℹ️ Database me koi WhatsApp message nahi mila.")
                return Response(status_code=200)

            reply = "💬 **Recent 5 WhatsApp Messages:**\n\n"
            for idx, c in enumerate(chats, start=1):
                clean_body = (c.content[:120] + "...").replace("\n", " ")
                reply += f"{idx}. **From:** `{c.sender}`\n   _{clean_body}_\n\n"
            await send_telegram_message(chat_id, reply)
            return Response(status_code=200)

        # 6. All Recent Messages
        elif user_text in ["📋 All Recent Messages", "/recent"]:
            all_msgs = await get_latest_messages_all(limit=5)
            if not all_msgs:
                await send_telegram_message(chat_id, "ℹ️ Koi messages available nahi hain.")
                return Response(status_code=200)

            reply = "📋 **Latest 5 Messages (All Channels):**\n\n"
            for idx, m in enumerate(all_msgs, start=1):
                clean_body = (m.content[:100] + "...").replace("\n", " ")
                reply += f"{idx}. [{m.platform.upper()}] `{m.sender}`: _{clean_body}_\n\n"
            await send_telegram_message(chat_id, reply)
            return Response(status_code=200)

        # 7. Run Full Digest On-Demand (Manual Trigger)
        elif user_text in ["🚀 Run Full Digest", "/digest"]:
            await send_telegram_message(chat_id, "⏳ Pipeline trigger ho rahi hai...")
            asyncio.create_task(dispatch_full_digest())
            return Response(status_code=200)

        # 8. Natural Language User Text / Custom Command Processing
        else:
            await send_telegram_message(chat_id, "🧠 Processing...")
            lower_query = user_text.lower()

            action_triggers = ["send", "bhej", "reply", "draft", "likh", "write"]
            is_action_command = any(word in lower_query for word in action_triggers)

            if not is_action_command:
                if any(k in lower_query for k in ["whatsapp", "wa ", "whats app"]):
                    chats = await get_recent_messages_by_platform("whatsapp", limit=7)
                    analysis = await check_important_whatsapp_summary(chats)
                    await send_telegram_message(chat_id, analysis)
                    return Response(status_code=200)

                email_check_keywords = [
                    "important mail", "koi mail", "check mail", "koi important",
                    "new email", "important email", "mails check", "mail check",
                    "aaj ka mail", "inbox", "mails",
                ]
                if any(k in lower_query for k in email_check_keywords):
                    emails = await fetch_latest_emails(limit=7)
                    analysis = await check_important_emails_summary(emails)
                    await send_telegram_message(chat_id, analysis)
                    return Response(status_code=200)

            result = await process_user_chat_command(user_text)

            if result.get("intent") == "chat":
                await send_telegram_message(chat_id, result.get("reply", "Done."))
                return Response(status_code=200)

            elif result.get("intent") == "action":
                platform = result.get("platform", "email").lower()
                recipient = result.get("recipient", "Unknown")
                draft = result.get("draft", "")
                subject = result.get("subject") or "Quick Update"

                action_id = await create_pending_action(
                    platform=platform,
                    recipient=recipient,
                    draft_body=draft,
                    subject=subject,
                )

                await send_action_card(
                    chat_id=chat_id,
                    action_id=action_id,
                    platform=platform,
                    recipient=recipient,
                    proposed_text=draft,
                )
                return Response(status_code=200)

    return Response(status_code=200)


# ==========================================
# 3. UNIFIED AI DIGEST PIPELINE (Manual Only)
# ==========================================

async def dispatch_full_digest():
    logger.info("Running unified executive digest pipeline...")

    try:
        await check_new_emails(limit=5)
        unsummarized = await fetch_unsummarized_messages()
        if not unsummarized:
            logger.info("No unsummarized messages.")
            return

        summary_text = await summarize_messages(unsummarized)
        if TELEGRAM_CHAT_ID:
            await send_telegram_message(TELEGRAM_CHAT_ID, summary_text)

        drafts = await generate_draft_replies(unsummarized)
        for draft in drafts:
            platform = draft.get("platform", "whatsapp").lower()
            recipient = draft.get("recipient")
            reply_text = draft.get("proposed_reply", "")
            can_auto = draft.get("can_auto_reply", False)
            reason = draft.get("intent_reason", "Routine acknowledgment")

            if can_auto:
                sent = False
                if platform == "whatsapp":
                    sent = await send_whatsapp_reply(recipient, reply_text)
                elif platform == "email":
                    sent = await send_email_reply(
                        to_email=recipient,
                        subject=draft.get("subject", "Re: Quick Update"),
                        body=reply_text,
                    )

                if sent:
                    action_id = await save_pending_action(platform, recipient, reply_text)
                    await update_pending_action_status(action_id, "EXECUTED")

                    if TELEGRAM_CHAT_ID:
                        auto_note = (
                            f"⚡ **Auto-Replied ({platform.upper()})**\n"
                            f"**To:** `{recipient}`\n"
                            f"**Reason:** {reason}\n"
                            f"**Message:** _{reply_text}_"
                        )
                        await send_telegram_message(TELEGRAM_CHAT_ID, auto_note)
                else:
                    can_auto = False

            if not can_auto:
                action_id = await save_pending_action(platform, recipient, reply_text)
                if TELEGRAM_CHAT_ID:
                    await send_action_card(
                        chat_id=TELEGRAM_CHAT_ID,
                        action_id=action_id,
                        platform=platform,
                        recipient=recipient,
                        proposed_text=reply_text,
                    )

        msg_ids = [m.id for m in unsummarized]
        await mark_messages_summarized(msg_ids)
        logger.info(f"Pipeline complete. Processed {len(msg_ids)} message(s).")

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)