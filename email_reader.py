import os
import imaplib
import email
from email.message import Message
from email.header import decode_header
from dotenv import load_dotenv
from database import save_message

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def clean_header_text(header_value: str) -> str:
    """Decodes MIME encoded header strings safely into readable text."""
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
    """Extracts plain text body from single-part or multipart emails."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="ignore")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="ignore")
    return body.strip()


async def check_new_emails(limit: int = 5) -> list[dict]:
    """
    Connects to Gmail via IMAP SSL, fetches the latest unread emails (default 5),
    saves them to SQLite, and returns a list of processed items.
    """
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
            print("No new unread emails found in inbox.")
            mail.logout()
            return []

        # Sirf aakhiri latest N emails pick karein
        mail_ids = response[0].split()[-limit:]
        print(f"Fetching latest {len(mail_ids)} unread email(s)...")

        for m_id in mail_ids:
            res_status, data = mail.fetch(m_id, "(RFC822)")
            if res_status != "OK":
                continue

            for part in data:
                if isinstance(part, tuple):
                    msg = email.message_from_bytes(part[1])

                    subject = clean_header_text(msg.get("Subject", "No Subject"))

                    sender = msg.get("From", "Unknown")
                    if "<" in sender and ">" in sender:
                        sender_email = sender.split("<")[1].split(">")[0].strip()
                    else:
                        sender_email = sender.strip()

                    body = extract_body_from_email(msg)
                    content = f"Subject: {subject}\n\n{body}"

                    await save_message(
                        platform="email",
                        sender=sender_email,
                        content=content
                    )

                    collected_emails.append({
                        "sender": sender_email,
                        "subject": subject,
                        "body": body
                    })
                    print(f"✅ Saved unread email from: {sender_email} | Subject: {subject}")

        mail.logout()
    except Exception as e:
        print(f"Error fetching emails via IMAP: {e}")

    return collected_emails