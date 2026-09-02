import json
import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response

app = FastAPI()

# Configuration
VERIFY_TOKEN = "my_bot_token_2026"

# Meta API Setup screen se copy karke yahan paste karo:
PHONE_NUMBER_ID = "YOUR_PHONE_NUMBER_ID"
ACCESS_TOKEN = "YOUR_TEMPORARY_ACCESS_TOKEN"


async def send_whatsapp_message(to_number: str, text: str):
    """WhatsApp Cloud API ke zariye user ko wapas message bhejta hai."""
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            print(f"Reply status: {response.status_code}, Response: {response.text}")
        except Exception as e:
            print(f"Error sending WhatsApp message: {e}")


@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """Meta Webhook handshake verification."""
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print("\n>>> Webhook successfully verified by Meta! <<<\n")
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Incoming WhatsApp events process karta hai."""
    try:
        body = await request.json()
    except Exception:
        return Response(content="Invalid JSON", status_code=400)

    # Pure payload ko terminal me print karega taaki structure check ho sake
    print("\n---------------- RAW PAYLOAD AAYA ----------------")
    print(json.dumps(body, indent=2))
    print("--------------------------------------------------\n")

    # Safe payload parsing
    try:
        entry_list = body.get("entry", [])
        if not entry_list:
            return Response(content="EVENT_RECEIVED", status_code=200)

        changes = entry_list[0].get("changes", [])
        if not changes:
            return Response(content="EVENT_RECEIVED", status_code=200)

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if messages:
            msg = messages[0]
            sender_id = msg.get("from")
            msg_type = msg.get("type")

            if msg_type == "text":
                text_content = msg.get("text", {}).get("body", "")

                print("=" * 45)
                print(f"📩 Naya Message Aaya: {sender_id}")
                print(f"💬 Text: {text_content}")
                print("=" * 45)

                # Automated test reply
                reply_text = f"Bot received your message: '{text_content}'"
                if PHONE_NUMBER_ID != 1207334012473009 and ACCESS_TOKEN != EAAcNDCBBGFYBSQmxGBDN3IYZBoAEDX8v3RzZBqBQvAJLNUKMKiFlPsg9jRq1Xa4YOcwvEmB0bvnrr8dRamJ0BpXw25A8LKYZADbtbq2bof4ZBsH7Hmo8BYBTtQ8ZBYZAhf8E8GeaB9HO9voE4lwJiLwhuXPLFIHY5FeRUqvXK1MdrjAOAoyqmHWQHWfKPBObVWwL8js5uGKkhZBSmGKY8UjGh0NcSQaqEi6vlP1ZBBbBhqcXewMVNj36O0LkZBMjJW9UNRgZCoDFz0WstcChsNvG46Lm2mXJLFLsDRdusH8QZDZD:
                    await send_whatsapp_message(sender_id, reply_text)

    except Exception as e:
        print(f"Parsing error: {e}")

    # Meta ko hamesha 200 OK return karna zaroori hota hai
    return Response(content="EVENT_RECEIVED", status_code=200)
