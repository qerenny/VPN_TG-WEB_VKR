from __future__ import annotations

import asyncio
import re
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from email.utils import formataddr

from loguru import logger

from backend.services.email.email_types import OutgoingEmail
from shared.config.settings import MailSettings


class EmailDeliveryService(ABC):
    @abstractmethod
    async def send(self, message: OutgoingEmail) -> None: ...


class NoopEmailDeliveryService(EmailDeliveryService):
    def __init__(self) -> None:
        self.sent_messages: list[OutgoingEmail] = []

    async def send(self, message: OutgoingEmail) -> None:
        self.sent_messages.append(message)
        code_match = re.search(r"Код:\s*([0-9]{4,8})", str(message.text_body or ""))
        code_suffix = f", code={code_match.group(1)}" if code_match else ""
        logger.info(
            "Skipping email delivery because noop mail provider is active: to={}, subject={}{}",
            message.to_email,
            message.subject,
            code_suffix,
        )


class SmtpEmailDeliveryService(EmailDeliveryService):
    def __init__(self, settings: MailSettings) -> None:
        self.settings = settings

    async def send(self, message: OutgoingEmail) -> None:
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: OutgoingEmail) -> None:
        email = EmailMessage()
        email["From"] = formataddr((self.settings.from_name, self.settings.from_email))
        email["To"] = message.to_email
        email["Subject"] = message.subject

        reply_to = message.reply_to or self.settings.reply_to
        if reply_to:
            email["Reply-To"] = reply_to

        email.set_content(message.text_body)
        if message.html_body:
            email.add_alternative(message.html_body, subtype="html")

        client_factory = smtplib.SMTP_SSL if self.settings.smtp_ssl else smtplib.SMTP
        with client_factory(
            host=self.settings.smtp_host,
            port=self.settings.smtp_port,
            timeout=self.settings.timeout_seconds,
        ) as client:
            if not self.settings.smtp_ssl:
                client.ehlo()
                if self.settings.smtp_starttls:
                    client.starttls()
                    client.ehlo()
            if self.settings.smtp_username:
                client.login(
                    self.settings.smtp_username,
                    self.settings.smtp_password or "",
                )
            client.send_message(email)


def build_email_delivery_service(settings: MailSettings) -> EmailDeliveryService:
    if not settings.enabled or settings.provider == "noop":
        return NoopEmailDeliveryService()
    if settings.provider == "smtp":
        return SmtpEmailDeliveryService(settings)
    raise ValueError(f"Unsupported mail provider: {settings.provider}")
