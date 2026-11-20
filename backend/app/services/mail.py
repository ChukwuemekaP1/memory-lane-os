"""Email delivery: memory (tests) / file (dev) / SMTP (prod) backends."""

from __future__ import annotations

import asyncio
import json
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    to: str
    subject: str
    text_body: str
    html_body: str = ""
    template: str = ""
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Mailer(Protocol):
    async def send(self, message: Message) -> str | None:
        """Deliver (or record) a message. Returns a provider message id, if any."""
        ...


class MemoryMailer:
    """In-process outbox for tests. Not thread-safe; tests are single-threaded."""

    def __init__(self) -> None:
        self.outbox: list[Message] = []

    async def send(self, message: Message) -> str | None:
        self.outbox.append(message)
        return f"memory-{len(self.outbox)}"

    def last_to(self, email: str) -> Message | None:
        lowered = email.lower()
        for msg in reversed(self.outbox):
            if msg.to.lower() == lowered:
                return msg
        return None

    def clear(self) -> None:
        self.outbox.clear()


class FileMailer:
    """Dev backend: writes one JSON file per message for inspection."""

    def __init__(self, mail_dir: str) -> None:
        self._dir = Path(mail_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    async def send(self, message: Message) -> str | None:
        stamp = message.queued_at.strftime("%Y%m%dT%H%M%S%f")
        safe_to = "".join(c if c.isalnum() or c in "@._-" else "_" for c in message.to)
        path = self._dir / f"{stamp}-{safe_to}.json"
        payload = {
            "to": message.to, "subject": message.subject, "template": message.template,
            "text_body": message.text_body, "html_body": message.html_body,
        }
        await asyncio.to_thread(path.write_text, json.dumps(payload, indent=2), "utf-8")
        logger.info("mail written to %s", path.name)
        return None


class SmtpMailer:
    """Production backend: plain SMTP (works with Mailpit/SES-compatible relays)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _deliver(self, message: Message) -> None:
        mail = EmailMessage()
        mail["From"] = self._settings.mail_from
        mail["To"] = message.to
        mail["Subject"] = message.subject
        mail.set_content(message.text_body)
        if message.html_body:
            mail.add_alternative(message.html_body, subtype="html")
        with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=15) as smtp:
            if self._settings.smtp_use_tls:
                smtp.starttls()
            if self._settings.smtp_username:
                smtp.login(self._settings.smtp_username, self._settings.smtp_password)
            smtp.send_message(mail)

    async def send(self, message: Message) -> str | None:
        await asyncio.to_thread(self._deliver, message)
        logger.info("mail sent", extra={})
        return None


_mailer: Mailer | None = None


def get_mailer(settings: Settings | None = None) -> Mailer:
    global _mailer
    if _mailer is not None:
        return _mailer
    from app.config import get_settings

    resolved = settings or get_settings()
    if resolved.mail_driver == "memory":
        _mailer = MemoryMailer()
    elif resolved.mail_driver == "file":
        _mailer = FileMailer(resolved.mail_dir)
    else:
        _mailer = SmtpMailer(resolved)
    return _mailer


def reset_mailer() -> None:
    global _mailer
    _mailer = None
