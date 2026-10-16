"""Email dispatch service supporting SMTP delivery with development console fallback."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from app.config import get_settings

logger = logging.getLogger("berthmark.email")


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

        If SMTP server is configured in settings/env, dispatches via SMTP.
        Always logs a formatted email preview to stdout/logger for local development and testing.
        """
        record = {
            "to": to_email,
            "subject": subject,
            "body": plain_text,
        }
        self._sent_emails.append(record)

        # Always output formatted email preview box to console/logs
        preview = (
            f"\n==================== [OUTBOUND EMAIL DISPATCH] ====================\n"
            f"To: {to_email}\n"
            f"From: alerts@berthmark.com\n"
            f"Subject: {subject}\n"
            f"--------------------------------------------------------------------\n"
            f"{plain_text.strip()}\n"
            f"===================================================================="
        )
        print(preview, flush=True)
        logger.info(preview)

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
                return True
            except Exception as e:
                logger.warning(f"Failed to dispatch email via SMTP ({smtp_host}:{smtp_port}): {e}")
                return False

        return True


email_service = EmailService()
