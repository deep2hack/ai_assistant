import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, Query

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
)
from summarizer import summarize_messages, generate_draft_replies
from telegram_bot import (
    send_telegram_message,
    send_telegram_ack,
    send_action_card,
)
from reply_sender import send_whatsapp_reply, send_email_reply

load_dotenv()

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "my_secure_token")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

app = FastAPI(title="AI Executive Assistant")


@app.on_event("startup")
async def startup_event():
    await init_db()
    print("Database initialized successfully.")


# ==========================================
# 1. WHATSAPP WEBHOOKS
# ==========================================

@app.get("/webhook/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        print("WhatsApp webhook verified successfully.")
        return Response(content=hub_challenge, media_type="text/plain", status_code=200)
    return Response(content="Verification failed", status_code=403)


@app.post("/webhook/whatsapp")
async def receive_whatsapp_message(request: Request):
    data = await request.json()
    print("Incoming WhatsApp Payload:", data)

    try:
        entries = data.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg in messages:
                    if msg.get("type") == "text":
                        sender = msg.get("from")
                        body = msg.get("text", {}).get("body", "").strip()
                        if sender and body:
                            await save_message(
                                platform="whatsapp",
                                sender=sender,
                                content=body,
                            )
                            print(f"Saved message from {sender}: {body}")
    except Exception as e:
        print(f"Error parsing WhatsApp webhook: {e}")

    return Response(content="EVENT_RECEIVED", status_code=200)


# ==========================================
# 2. TELEGRAM WEBHOOK (Approve, Edit, Dismiss)
# ==========================================

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()

    # Case A: User clicked an Inline Button
    if "callback_query" in data:
        cb = data["callback_query"]
        cb_id = cb["id"]
        cb_data = cb.get("data", "")
        chat_id = cb["message"]["chat"]["id"]

        # Action: Approve & Send
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
                success = await send_whatsapp_reply(action.recipient, action.proposed_text)
            elif action.platform.lower() == "email":
                success = await send_email_reply(
                    to_email=action.recipient,
                    subject=action.subject or "Re: Quick Update",
                    body=action.proposed_text,
                )

            if success:
                await update_pending_action_status(action_id, "EXECUTED")
                await send_telegram_message(
                    chat_id,
                    f"✅ Reply successfully dispatched via {action.platform.upper()} to `{action.recipient}`."
                )
            else:
                await send_telegram_message(chat_id, f"❌ Failed to dispatch reply to `{action.recipient}`.")

        # Action: Enter Edit Mode
        elif cb_data.startswith("edit_"):
            action_id = int(cb_data.split("_")[1])
            await set_action_status(action_id, "EDITING")
            await send_telegram_ack(cb_id, "Edit mode activated.")
            await send_telegram_message(
                chat_id,
                f"✏️ **Edit Draft (ID: {action_id})**\n\nNiche apna customized reply type karke send karein:"
            )

        # Action: Dismiss Draft
        elif cb_data.startswith("dismiss_"):
            action_id = int(cb_data.split("_")[1])
            await set_action_status(action_id, "DISMISSED")
            await send_telegram_ack(cb_id, "Dismissed.")
            await send_telegram_message(chat_id, f"❌ Draft ID {action_id} dismissed.")

        return Response(status_code=200)

    # Case B: User typed custom reply text for an EDITING action
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"]["text"].strip()

        editing_action = await get_editing_action()
        if editing_action:
            updated_action = await update_pending_action_text(editing_action.id, user_text)

            updated_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🚀 Approve & Send", "callback_data": f"approve_{updated_action.id}"},
                        {"text": "✏️ Edit Again", "callback_data": f"edit_{updated_action.id}"},
                    ],
                    [
                        {"text": "❌ Dismiss", "callback_data": f"dismiss_{updated_action.id}"}
                    ]
                ]
            }

            msg_text = (
                f"📝 **Updated Draft Proposal (ID: {updated_action.id})**\n\n"
                f"**Platform:** {updated_action.platform.upper()}\n"
                f"**To:** `{updated_action.recipient}`\n"
                f"**Updated Text:**\n_{updated_action.proposed_text}_"
            )
            await send_telegram_message(chat_id, msg_text, reply_markup=updated_markup)
            return Response(status_code=200)

    return Response(status_code=200)


# ==========================================
# 3. AI DIGEST & PIPELINE DISPATCHER
# ==========================================

async def dispatch_full_digest():
    print("Running executive digest pipeline...")
    unsummarized = await fetch_unsummarized_messages()
    if not unsummarized:
        print("No new messages found to summarize.")
        return

    # Generate Markdown Summary
    summary_text = await summarize_messages(unsummarized)
    await send_telegram_message(TELEGRAM_CHAT_ID, summary_text)

    # Generate AI Draft Replies
    drafts = await generate_draft_replies(unsummarized)
    for draft in drafts:
        action_id = await save_pending_action(
            platform=draft.get("platform", "whatsapp"),
            recipient=draft.get("recipient"),
            proposed_text=draft.get("proposed_reply", ""),
        )
        await send_action_card(
            chat_id=TELEGRAM_CHAT_ID,
            action_id=action_id,
            platform=draft.get("platform", "whatsapp"),
            recipient=draft.get("recipient"),
            proposed_text=draft.get("proposed_reply", ""),
        )

    # Mark all processed messages as summarized
    msg_ids = [m.id for m in unsummarized]
    await mark_messages_summarized(msg_ids)
    print(f"Digest complete. Processed {len(msg_ids)} messages.")
