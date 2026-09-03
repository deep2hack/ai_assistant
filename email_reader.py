import os
import imaplib
import email
from email.message import Message
from email.header import decode_header
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from database import save_message

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

IGNORED_SENDERS = [
    "noreply", "no-reply", "marketing", "notifications", "digest",
    "promotions", "newsletter", "suno.com", "zomato.com", "canva.com",
    "quora.com", "turboscribe.ai", "adobe.com", "google.com", 
    "fabricspa.com", "uber.com", "inshot.com"
]


def clean_header_text(header_value: str) -> str:
    if not header_value:
        return ""
    decoded_fragments = decode_header(header_value)
    text_parts = []
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            text_parts.append(fragment.decode(encoding or "utf-8", errors="ignore"))
        else:
            text_parts.append(str(fragment))
    return "".join(text_parts).strip()


def extract_body_from_email(msg: Message) -> str:
    """Extracts clean plain text and strictly trims it to prevent token explosion."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="ignore")
                    break
            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode("utf-8", errors="ignore")
                    # Remove HTML tags safely
                    soup = BeautifulSoup(html, "html.parser")
                    body = soup.get_text(separator=" ", strip=True)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="ignore")

    # Strict token safety: Trim body to first 800 characters
    body = " ".join(body.split())
    if len(body) > 800:
        body = body[:800] + "..."
    return body.strip()


async def check_new_emails(limit: int = 10) -> list[dict]:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Missing GMAIL_USER or GMAIL_APP_PASSWORD in .env")
        return []

    collected_emails = []

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("INBOX")

        status, response = mail.search(None, "UNSEEN")
        if status != "OK" or not response[0]:
            print("No new unread emails found.")
            mail.logout()
            return []

        mail_ids = response[0].split()[-limit:]

        for m_id in mail_ids:
            res_status, data = mail.fetch(m_id, "(RFC822)")
            if res_status != "OK":
                continue

            for part in data:
                if isinstance(part, tuple):
                    msg = email.message_from_bytes(part[1])

                    sender = msg.get("From", "Unknown")
                    if "<" in sender and ">" in sender:
                        sender_email = sender.split("<")[1].split(">")[0].strip()
                    else:
                        sender_email = sender.strip()

                    # Drop marketing mails
                    if any(ignored in sender_email.lower() for ignored in IGNORED_SENDERS):
                        print(f"⏩ Dropped promotional email from: {sender_email}")
                        continue

                    subject = clean_header_text(msg.get("Subject", "No Subject"))
                    body = extract_body_from_email(msg)
                    content = f"Subject: {subject}\n\nBody: {body}"

                    await save_message("email", sender_email, content)
                    collected_emails.append({"sender": sender_email, "subject": subject})
                    print(f"✅ Saved relevant email from: {sender_email} | Subject: {subject}")

        mail.logout()
    except Exception as e:
        print(f"Error fetching emails: {e}")

    return collected_emails