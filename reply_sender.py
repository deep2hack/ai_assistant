import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import httpx

load_dotenv()

# WhatsApp Credentials
WA_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WA_PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

# Gmail SMTP Credentials
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


async def send_whatsapp_reply(to_number: str, message_text: str) -> bool:
    """Dispatches a direct WhatsApp reply using the official Meta Cloud API."""
    if not WA_TOKEN or not WA_PHONE_ID:
        print("Missing WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID in .env")
        return False

    url = f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text},
    }

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(url, json=payload, headers=headers, timeout=10.0)
            if res.status_code in [200, 201]:
                print(f"WhatsApp reply sent successfully to {to_number}")
                return True
            else:
                print(f"WhatsApp API Error [{res.status_code}]: {res.text}")
                return False
        except Exception as e:
            print(f"Exception while sending WhatsApp reply: {e}")
            return False


async def send_email_reply(to_email: str, subject: str, body: str) -> bool:
    """Dispatches an email reply via Gmail SMTP using SSL (Port 465)."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Missing GMAIL_USER or GMAIL_APP_PASSWORD in .env")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject if subject else "Re: Executive Assistant Follow-up"
        msg.attach(MIMEText(body, "plain"))

        # Gmail SSL Connection
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        print(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"Exception while sending email reply: {e}")
        return False
