import json
import logging
import re
import smtplib
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import settings
from encryption import encryptor
from database import AsyncSessionLocal
from models import GmailAccount

logger = logging.getLogger(__name__)


def html_to_text(html_content: str) -> str:
    """Best-effort HTML → plain-text for MIME fallback."""
    text = html_content
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


async def get_app_password(account_id: int) -> str:
    """Decrypts and returns the stored Gmail App Password for a given account ID."""
    async with AsyncSessionLocal() as session:
        acc = await session.get(GmailAccount, account_id)
        if not acc:
            raise ValueError(f"Gmail account ID {account_id} not found.")
        token_data = json.loads(encryptor.decrypt_token(acc.encrypted_credentials))
    return token_data["app_password"]


def build_mime_message(sender: str, recipient: str, subject: str, body: str) -> MIMEMultipart:
    """Builds a plain-text + HTML MIME message. No compliance headers added."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    msg.attach(MIMEText(html_to_text(body), "plain", "utf-8"))
    msg.attach(MIMEText(body, "html", "utf-8"))
    return msg


async def send_email(
    sender_email: str,
    app_password: str,
    recipient_email: str,
    subject: str,
    body: str,
) -> None:
    """Sends a single email via Gmail SMTP using an App Password. Runs in a thread pool."""

    message = build_mime_message(sender_email, recipient_email, subject, body)

    def _send_sync() -> None:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, app_password)
        server.send_message(message)
        server.quit()

    await asyncio.to_thread(_send_sync)


def test_smtp_credentials(email: str, password: str) -> bool:
    """Synchronously verifies that SMTP login succeeds. Used during account setup."""
    server = None
    try:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, 465, timeout=10)
        server.ehlo()
        server.login(email, password)
        server.quit()
        return True
    except Exception as exc:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass
        try:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(email, password)
            server.quit()
            return True
        except Exception as retry_exc:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass
            logger.error("SMTP auth check failed for %s: %s | fallback: %s", email, exc, retry_exc)
            return False
