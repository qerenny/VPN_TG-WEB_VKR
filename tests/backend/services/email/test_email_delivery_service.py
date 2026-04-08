from unittest.mock import MagicMock, patch

import pytest

from backend.services.email.email_delivery_service import (
    NoopEmailDeliveryService,
    SmtpEmailDeliveryService,
    build_email_delivery_service,
)
from backend.services.email.email_types import OutgoingEmail
from shared.config.settings import MailSettings


def _smtp_settings(*, enabled: bool = True, provider: str = "smtp", smtp_ssl: bool = False) -> MailSettings:
    return MailSettings(
        enabled=enabled,
        provider=provider,
        from_email="noreply@example.com",
        from_name="Remote Access Service",
        reply_to="support@example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        smtp_starttls=True,
        smtp_ssl=smtp_ssl,
        timeout_seconds=10,
    )


@pytest.mark.asyncio
async def test_noop_email_delivery_service_keeps_message_in_memory():
    service = NoopEmailDeliveryService()
    message = OutgoingEmail(
        to_email="user@example.com",
        subject="Subject",
        text_body="Hello",
    )

    await service.send(message)

    assert service.sent_messages == [message]


@pytest.mark.asyncio
async def test_noop_email_delivery_service_logs_code_when_present():
    service = NoopEmailDeliveryService()
    message = OutgoingEmail(
        to_email="user@example.com",
        subject="Remote Access Service: код подтверждения email",
        text_body="Код подтверждения\n\nКод: 123456\nДействует 15 минут.",
    )

    with patch("backend.services.email.email_delivery_service.logger.info") as logger_info:
        await service.send(message)

    logger_info.assert_called_once()
    logged_args = logger_info.call_args.args
    assert "Skipping email delivery because noop mail provider is active" in logged_args[0]
    assert logged_args[1] == "user@example.com"
    assert logged_args[2] == "Remote Access Service: код подтверждения email"
    assert "123456" in logged_args[3]


def test_build_email_delivery_service_uses_noop_when_disabled():
    service = build_email_delivery_service(_smtp_settings(enabled=False))

    assert isinstance(service, NoopEmailDeliveryService)


@pytest.mark.asyncio
async def test_smtp_email_delivery_service_sends_message_via_smtp():
    service = SmtpEmailDeliveryService(_smtp_settings())
    smtp_client = MagicMock()
    smtp_context = MagicMock()
    smtp_context.__enter__.return_value = smtp_client
    smtp_context.__exit__.return_value = False

    with patch("backend.services.email.email_delivery_service.smtplib.SMTP", return_value=smtp_context) as smtp_class:
        await service.send(
            OutgoingEmail(
                to_email="user@example.com",
                subject="Test subject",
                text_body="Plain body",
                html_body="<p>Plain body</p>",
            )
        )

    smtp_class.assert_called_once_with(host="smtp.example.com", port=587, timeout=10)
    smtp_client.ehlo.assert_called()
    smtp_client.starttls.assert_called_once_with()
    smtp_client.login.assert_called_once_with("smtp-user", "smtp-password")
    smtp_client.send_message.assert_called_once()
    sent_message = smtp_client.send_message.call_args.args[0]
    assert sent_message["To"] == "user@example.com"
    assert sent_message["Subject"] == "Test subject"


@pytest.mark.asyncio
async def test_smtp_email_delivery_service_uses_ssl_transport_when_requested():
    service = SmtpEmailDeliveryService(_smtp_settings(smtp_ssl=True))
    smtp_client = MagicMock()
    smtp_context = MagicMock()
    smtp_context.__enter__.return_value = smtp_client
    smtp_context.__exit__.return_value = False

    with patch("backend.services.email.email_delivery_service.smtplib.SMTP_SSL", return_value=smtp_context) as smtp_ssl_class:
        await service.send(
            OutgoingEmail(
                to_email="user@example.com",
                subject="SSL subject",
                text_body="Plain body",
            )
        )

    smtp_ssl_class.assert_called_once_with(host="smtp.example.com", port=587, timeout=10)
    smtp_client.starttls.assert_not_called()
