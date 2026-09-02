import email
from email.header import decode_header
import imaplib
import os
from bs4 import BeautifulSoup
from database import save_message
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def clean_html(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator=" ", strip=True)


async def check_new_emails(limit: int = 5):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Gmail credentials missing in .env")
        return 0

    print(f"Connecting to Gmail for {GMAIL_USER}...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    mail.select("INBOX")

    # Sirf Unread (UNSEEN) emails search karega
    status, messages = mail.search(None, "UNSEEN")
    mail_ids = messages[0].split()

    if not mail_ids:
        print("Koi naya unread email nahi mila.")
        mail.logout()
        return 0

    print(f"Total {len(mail_ids)} unread emails mile. Processing latest {limit}...")

    # Sirf latest 'limit' emails process karega
    for mail_id in mail_ids[-limit:]:
        _, msg_data = mail.fetch(mail_id, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])

                # Decode Subject
                subject_header = decode_header(msg.get("Subject", "No Subject"))[0]
                subject = subject_header[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(
                        subject_header[1] or "utf-8", errors="ignore"
                    )

                sender = msg.get("From", "Unknown Sender")

                # Extract Body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            body = part.get_payload(decode=True).decode(
                                errors="ignore"
                            )
                            break
                        elif content_type == "text/html" and not body:
                            raw_html = part.get_payload(decode=True).decode(
                                errors="ignore"
                            )
                            body = clean_html(raw_html)
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")

                # Database me format karke save
                content_payload = f"Subject: {subject}\nSnippet: {body[:350].strip()}"
                await save_message(
                    platform="email", sender=sender, content=content_payload
                )
                print(f"Saved Email: {subject[:40]}... from {sender}")

    mail.logout()
    return len(mail_ids)