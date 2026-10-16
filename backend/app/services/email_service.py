"""Email dispatch service supporting SMTP delivery with development console fallback."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from app.config import get_settings

logger = logging.getLogger("berthmark.email")

DEMO_DOMAINS = (
    "pacific-shipping.com",
    "rotterdam-logistics.nl",
    "globalmaritime.org",
    "example.com",
    "test.com",
    "maritime.com",
)


def is_demo_account(email: str) -> bool:
    """Check if recipient email belongs to a demo or simulated account."""
    if not email:
        return False
    clean = email.strip().lower()
    if any(clean.endswith(f"@{domain}") for domain in DEMO_DOMAINS):
        return True
    if clean.startswith("demo@") or clean.startswith("test@") or clean == "mock-user":
        return True
    return False


class EmailService:
    """Dispatches operational alerts and subscription emails."""

    def __init__(self):
        self._sent_emails = []

    async def send_email(
        self,
        to_email: str,
        subject: str,
        plain_text: str,
        html_content: Optional[str] = None,
    ) -> bool:
        """Send an email to the recipient.

        If recipient is a demo account, real SMTP delivery is suppressed to prevent bounces.
        If SMTP server is configured in settings/env and recipient is non-demo, dispatches via SMTP.
        Always logs a formatted email preview to stdout/logger for local development and testing.
        """
        is_demo = is_demo_account(to_email)
        record = {
            "to": to_email,
            "subject": subject,
            "body": plain_text,
            "is_demo": is_demo,
            "smtp_dispatched": False,
        }
        self._sent_emails.append(record)

        # Output formatted email preview box to console/logs
        tag = " [DEMO ACCOUNT - REAL SMTP SUPPRESSED]" if is_demo else ""
        preview = (
            f"\n==================== [OUTBOUND EMAIL DISPATCH{tag}] ====================\n"
            f"To: {to_email}\n"
            f"From: alerts@berthmark.com\n"
            f"Subject: {subject}\n"
            f"--------------------------------------------------------------------\n"
            f"{plain_text.strip()}\n"
            f"===================================================================="
        )
        print(preview, flush=True)
        logger.info(preview)

        # Do not send real emails for demo accounts to prevent bounces
        if is_demo:
            logger.info(
                "Demo account detected for '%s'. Real SMTP delivery suppressed to prevent bounces.",
                to_email,
            )
            return True

        settings = get_settings()
        smtp_host = getattr(settings, "SMTP_HOST", None)
        smtp_port = getattr(settings, "SMTP_PORT", 587)
        smtp_user = getattr(settings, "SMTP_USER", None)
        smtp_pass = getattr(settings, "SMTP_PASSWORD", None)

        if smtp_host:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = getattr(settings, "SMTP_FROM", "alerts@berthmark.com")
                msg["To"] = to_email
                msg.attach(MIMEText(plain_text, "plain"))
                if html_content:
                    msg.attach(MIMEText(html_content, "html"))

                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    server.starttls()
                    if smtp_user and smtp_pass:
                        server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                record["smtp_dispatched"] = True
                return True
            except Exception as e:
                logger.warning(f"Failed to dispatch email via SMTP ({smtp_host}:{smtp_port}): {e}")
                return False

        return True


email_service = EmailService()
