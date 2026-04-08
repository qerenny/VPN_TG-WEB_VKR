from unittest.mock import MagicMock, patch

import pytest

from telegram_bot.services.payments.yookassa_service import YooKassaService


@pytest.fixture
def uuid_generator():
    generator = MagicMock()
    generator.generate_id.return_value = "uuid-123"
    return generator


@pytest.fixture
def service(uuid_generator):
    return YooKassaService(uuid=uuid_generator)


@pytest.fixture
def product():
    return {
        "label": "test_product",
        "amount": 3000,
        "description": "Test product description",
        "payload": "test_payload",
    }


@pytest.mark.asyncio
async def test_create_payment_success_builds_current_payload(service, uuid_generator, product):
    mock_payment = MagicMock()
    mock_payment.id = "payment-1"
    mock_payment.status = "pending"
    mock_payment.confirmation.confirmation_url = "https://pay.url"

    with patch(
        "telegram_bot.services.payments.yookassa_service.Payment.create",
        return_value=mock_payment,
    ) as create_payment:
        result = await service.create_payment(111, "https://return", product)

    payload, idempotence_key = create_payment.call_args.args
    assert payload == {
        "amount": {"value": "30.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://return"},
        "capture": True,
        "description": "Test product description",
        "metadata": {"tg_id": "111", "product": "test_payload"},
        "receipt": {
            "customer": {"email": "enderbrocreep2015@yandex.ru"},
            "items": [
                {
                    "description": "test_product",
                    "quantity": "1.00",
                    "amount": {"value": "30.00", "currency": "RUB"},
                    "vat_code": 1,
                }
            ],
        },
    }
    assert idempotence_key == "uuid-123"
    assert result == {
        "id": "payment-1",
        "status": "pending",
        "url": "https://pay.url",
        "confirmed": False,
    }
    uuid_generator.generate_id.assert_called_once()


@pytest.mark.asyncio
async def test_find_payment_status_success(service):
    with patch(
        "telegram_bot.services.payments.yookassa_service.Payment.find_one",
        return_value=MagicMock(status="succeeded"),
    ) as find_payment:
        status = await service.find_payment_status("pid")

    find_payment.assert_called_once_with("pid")
    assert status == "succeeded"


@pytest.mark.asyncio
async def test_find_payment_status_raises_when_provider_returns_none(service):
    with patch(
        "telegram_bot.services.payments.yookassa_service.Payment.find_one",
        return_value=None,
    ):
        with pytest.raises(RuntimeError, match="returned no payment object"):
            await service.find_payment_status("pid")


@pytest.mark.asyncio
async def test_find_payment_status_raises_when_provider_returns_empty_status(service):
    with patch(
        "telegram_bot.services.payments.yookassa_service.Payment.find_one",
        return_value=MagicMock(status=None),
    ):
        with pytest.raises(RuntimeError, match="without status"):
            await service.find_payment_status("pid")
