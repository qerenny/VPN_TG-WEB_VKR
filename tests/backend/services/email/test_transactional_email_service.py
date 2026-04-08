from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.email.transactional_email_service import TransactionalEmailService


@pytest.mark.asyncio
async def test_transactional_email_service_sends_verification_email():
    delivery_service = AsyncMock()
    template_service = MagicMock()
    template_service.build_verification_code_email.return_value = "message"
    service = TransactionalEmailService(
        delivery_service=delivery_service,
        template_service=template_service,
    )

    await service.send_verification_code(
        to_email="user@example.com",
        code="123456",
        expires_minutes=15,
    )

    template_service.build_verification_code_email.assert_called_once_with(
        to_email="user@example.com",
        code="123456",
        expires_minutes=15,
    )
    delivery_service.send.assert_awaited_once_with("message")


@pytest.mark.asyncio
async def test_transactional_email_service_sends_password_reset_email():
    delivery_service = AsyncMock()
    template_service = MagicMock()
    template_service.build_password_reset_code_email.return_value = "message"
    service = TransactionalEmailService(
        delivery_service=delivery_service,
        template_service=template_service,
    )

    await service.send_password_reset_code(
        to_email="user@example.com",
        code="654321",
        expires_minutes=20,
    )

    template_service.build_password_reset_code_email.assert_called_once_with(
        to_email="user@example.com",
        code="654321",
        expires_minutes=20,
    )
    delivery_service.send.assert_awaited_once_with("message")


@pytest.mark.asyncio
async def test_transactional_email_service_sends_linking_confirmation_email():
    delivery_service = AsyncMock()
    template_service = MagicMock()
    template_service.build_linking_confirmation_email.return_value = "message"
    service = TransactionalEmailService(
        delivery_service=delivery_service,
        template_service=template_service,
    )

    await service.send_linking_confirmation_code(
        to_email="user@example.com",
        code="111222",
        expires_minutes=10,
    )

    template_service.build_linking_confirmation_email.assert_called_once_with(
        to_email="user@example.com",
        code="111222",
        expires_minutes=10,
    )
    delivery_service.send.assert_awaited_once_with("message")
