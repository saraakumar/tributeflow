"""Send the summary email over SMTP (e.g. Gmail with an app password)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .config import Config
from .retry import with_retries

log = logging.getLogger(__name__)


@with_retries(attempts=3, retry_on=(smtplib.SMTPException, OSError))
def send_email(cfg: Config, subject: str, body: str) -> bool:
    """Send the summary. Returns False (without raising) if email isn't configured."""
    if not (cfg.smtp_host and cfg.email.recipients):
        log.warning("email not configured (SMTP_HOST or recipients missing) — skipping send")
        return False

    msg = EmailMessage()
    msg["From"] = cfg.email.sender or cfg.smtp_user
    msg["To"] = ", ".join(cfg.email.recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
        if cfg.smtp_user:
            smtp.login(cfg.smtp_user, cfg.smtp_password)
        smtp.send_message(msg)
    log.info("summary email sent to %s", cfg.email.recipients)
    return True
