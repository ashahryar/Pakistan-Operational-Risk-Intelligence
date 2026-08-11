"""
pipeline/helpers/email_helper.py

Reusable Email Helper

Supports

✓ Task Success
✓ Task Failure
✓ DAG Success
✓ DAG Failure

Future

✓ HTML Email
✓ Multiple Recipients
✓ Attachments
"""

import os
import smtplib
import logging

from pathlib import Path

from dotenv import load_dotenv

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger(__name__)


# ==========================================================
# LOAD ENV
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")

SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

SMTP_EMAIL = os.getenv("SMTP_EMAIL")

SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

ALERT_EMAIL = os.getenv("ALERT_EMAIL")


# ==========================================================
# HTML TEMPLATE
# ==========================================================

def build_html(subject: str, body: str):

    return f"""
    <html>

    <body style="font-family:Arial;">

        <h2>{subject}</h2>

        <hr>

        <pre style="font-size:14px;">
{body}
        </pre>

        <hr>

        <p>
        Pakistan Operational Risk Intelligence Platform
        </p>

    </body>

    </html>
    """
# ==========================================================
# SEND EMAIL
# ==========================================================

def send_email(subject: str, body: str):

    if not SMTP_EMAIL or not SMTP_PASSWORD or not ALERT_EMAIL:

        logger.warning("Email configuration is missing.")

        return False

    try:

        message = MIMEMultipart("alternative")

        message["From"] = SMTP_EMAIL
        message["To"] = ALERT_EMAIL
        message["Subject"] = subject

        # Plain Text
        plain = MIMEText(body, "plain")

        # HTML Version
        html = MIMEText(
            build_html(subject, body),
            "html",
        )

        message.attach(plain)
        message.attach(html)

        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
        ) as server:

            server.ehlo()

            server.starttls()

            server.ehlo()

            server.login(
                SMTP_EMAIL,
                SMTP_PASSWORD,
            )

            server.sendmail(
                SMTP_EMAIL,
                [ALERT_EMAIL],
                message.as_string(),
            )

        logger.info("=" * 60)
        logger.info("EMAIL SENT SUCCESSFULLY")
        logger.info("=" * 60)

        return True

    except Exception as e:

        logger.exception("EMAIL FAILED")

        return False
    
# ==========================================================
# FUTURE HELPERS
# ==========================================================

def send_email_with_attachment(
    subject: str,
    body: str,
    attachment=None,
):
    """
    Future implementation

    Supports:

    • PDF Reports
    • CSV Files
    • Log Files
    """

    logger.info(
        "Attachment email feature coming soon."
    )


def send_multiple(
    subject: str,
    body: str,
    recipients: list,
):
    """
    Send email to multiple recipients.
    """

    if not recipients:
        return False

    success = True

    for recipient in recipients:

        try:

            global ALERT_EMAIL

            ALERT_EMAIL = recipient

            send_email(
                subject,
                body,
            )

        except Exception:

            success = False

    return success


# ==========================================================
# EXPORTS
# ==========================================================

__all__ = [

    "send_email",

    "send_multiple",

    "send_email_with_attachment",

]