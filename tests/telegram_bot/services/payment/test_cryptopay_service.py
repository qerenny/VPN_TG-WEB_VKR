from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from telegram_bot.services.payments.cryptopay_service import CryptoPayService


@pytest.fixture
def service_and_client():
    with patch("telegram_bot.services.payments.cryptopay_service.CryptoPay") as CryptoMock:
        client_instance = AsyncMock()
        CryptoMock.return_value = client_instance
        service = CryptoPayService()
        yield service, client_instance, CryptoMock


def _invoice(invoice_id=1, status="paid", url="https://pay"):  # helper
    return SimpleNamespace(invoice_id=invoice_id, status=status, bot_invoice_url=url)


@pytest.mark.asyncio
async def test_service_initialization_is_lazy(service_and_client):
    _, _, crypto_cls = service_and_client
    crypto_cls.assert_not_called()


@pytest.mark.asyncio
async def test_create_payment_paid(service_and_client):
    service, client, _ = service_and_client
    client.create_invoice.return_value = _invoice(123, "paid", "url")
    result = await service.create_payment(1, "ret", {"description": "d", "payload": "p", "amount": 200})
    client.create_invoice.assert_awaited_once_with(
        amount=2,
        currency_type="fiat",
        fiat="RUB",
        description="d",
        payload="p",
        allow_anonymous=True,
        allow_comments=False,
        paid_btn_name="openBot",
        paid_btn_url="ret",
    )
    assert result == {"id": "123", "status": "paid", "url": "url", "confirmed": True}


@pytest.mark.asyncio
async def test_create_payment_unpaid(service_and_client):
    service, client, _ = service_and_client
    client.create_invoice.return_value = _invoice(5, "pending", "u")
    result = await service.create_payment(7, "r", {"description": "d2", "payload": "pl", "amount": 300})
    assert result == {"id": "5", "status": "pending", "url": "u", "confirmed": False}


@pytest.mark.asyncio
async def test_create_payment_initializes_client_once(service_and_client):
    service, client, crypto_cls = service_and_client
    client.create_invoice.return_value = _invoice(1, "pending", "u")

    await service.create_payment(1, "ret", {"description": "d", "payload": "p", "amount": 100})
    await service.create_payment(1, "ret", {"description": "d", "payload": "p", "amount": 100})

    crypto_cls.assert_called_once()


@pytest.mark.asyncio
async def test_create_payment_error_propagates(service_and_client):
    service, client, _ = service_and_client
    client.create_invoice.side_effect = Exception("boom")
    with pytest.raises(Exception, match="boom"):
        await service.create_payment(1, "ret", {"description": "d", "payload": "p", "amount": 100})


@pytest.mark.asyncio
async def test_find_payment_status_found(service_and_client):
    service, client, _ = service_and_client
    client.get_invoices.return_value = [_invoice(status="paid")]
    result = await service.find_payment_status(10)
    client.get_invoices.assert_awaited_once_with(invoice_ids=[10])
    assert result == "paid"


@pytest.mark.asyncio
async def test_find_payment_status_unknown(service_and_client):
    service, client, _ = service_and_client
    client.get_invoices.return_value = []
    result = await service.find_payment_status(99)
    assert result == "unknown"


@pytest.mark.asyncio
async def test_find_payment_status_error(service_and_client):
    service, client, _ = service_and_client
    client.get_invoices.side_effect = Exception("err")
    with pytest.raises(Exception, match="err"):
        await service.find_payment_status(1)


@pytest.mark.asyncio
async def test_find_payment_status_deserialize_error_uses_raw_fallback(service_and_client):
    service, client, _ = service_and_client
    client.get_invoices.side_effect = Exception("/getInvoices Failed to deserialize object")
    service._find_payment_status_via_raw_api = AsyncMock(return_value="paid")

    result = await service.find_payment_status(31619222)

    service._find_payment_status_via_raw_api.assert_awaited_once_with(31619222)
    assert result == "paid"


@pytest.mark.asyncio
async def test_raw_api_fallback_returns_unknown_on_http_error(service_and_client):
    service, _, _ = service_and_client
    request = httpx.Request("POST", "https://pay.crypt.bot/api/getInvoices")
    response = httpx.Response(502, request=request)

    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.post.return_value = response

    with patch("telegram_bot.services.payments.cryptopay_service.httpx.AsyncClient", return_value=async_client):
        result = await service._find_payment_status_via_raw_api(47623929)

    assert result == "unknown"


@pytest.mark.asyncio
async def test_raw_api_fallback_returns_unknown_on_invalid_json(service_and_client):
    service, _, _ = service_and_client

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("bad json")

    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.post.return_value = response

    with patch("telegram_bot.services.payments.cryptopay_service.httpx.AsyncClient", return_value=async_client):
        result = await service._find_payment_status_via_raw_api(47623929)

    assert result == "unknown"
