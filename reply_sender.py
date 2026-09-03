import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import httpx

load_dotenv()

# WhatsApp Node.js Bridge Endpoint (Port 3001)
WHATSAPP_BRIDGE_URL = os.getenv("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:3001/send-message")

# Gmail SMTP Credentials
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


async def send_whatsapp_reply(to_number: str, message_text: str) -> bool:
    """
    Dispatches a WhatsApp message directly via the local Node.js WhatsApp Web bridge.
    Completely bypasses Meta Cloud API, verified recipient lists, and template constraints.
    """
    payload = {
        "recipient": to_number,
        "message": message_text
    }

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(WHATSAPP_BRIDGE_URL, json=payload, timeout=15.0)
            if res.status_code == 200:
                print(f"WhatsApp message dispatched successfully to {to_number}")
                return True
            else:
                print(f"WhatsApp Bridge Error [{res.status_code}]: {res.text}")
                return False
        except Exception as e:
            print(f"Exception while connecting to WhatsApp bridge: {e}")
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