from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.routers.payments import payment_webhook_routes as routes


def _features(**overrides):
    values = {
        "commerce_enabled": True,
        "referrals_enabled": True,
        "promos_enabled": True,
        "web_purchase_enabled": True,
        "telegram_bot_enabled": True,
        "telegram_proxy_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_request(payload=None, *, json_side_effect=None, redis_client=None):
    async def json_func():
        if json_side_effect is not None:
            raise json_side_effect
        return payload

    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis_client=redis_client)),
        json=json_func,
    )


def test_assert_webhook_auth_requires_configured_token():
    with patch.object(routes, "PAYMENT_WEBHOOK_TOKEN", ""):
        with pytest.raises(routes.HTTPException) as exc_info:
            routes._assert_webhook_auth("token")

    assert exc_info.value.status_code == 503


def test_assert_webhook_auth_rejects_invalid_token():
    with patch.object(routes, "PAYMENT_WEBHOOK_TOKEN", "secret"):
        with pytest.raises(routes.HTTPException) as exc_info:
            routes._assert_webhook_auth("wrong")

    assert exc_info.value.status_code == 403


def test_assert_webhook_auth_rejects_disabled_commerce():
    with (
        patch.object(routes, "PAYMENT_WEBHOOK_TOKEN", "secret"),
        patch.object(
            routes,
            "get_product_feature_settings",
            return_value=_features(commerce_enabled=False),
        ),
    ):
        with pytest.raises(routes.HTTPException) as exc_info:
            routes._assert_webhook_auth("secret")

    assert exc_info.value.status_code == 404


def test_extract_yookassa_update_reads_object_payload():
    payment_id, status = routes._extract_yookassa_update(
        {"object": {"id": " payment-1 ", "status": "SUCCEEDED"}}
    )

    assert payment_id == "payment-1"
    assert status == "succeeded"


def test_extract_cryptopay_update_supports_invoice_paid_update_type():
    payment_id, status = routes._extract_cryptopay_update(
        {"update_type": "invoice_paid", "payload": {"invoice_id": 42}}
    )

    assert payment_id == "42"
    assert status == "paid"


@pytest.mark.asyncio
async def test_yookassa_webhook_processes_status_update():
    service = AsyncMock()
    service.process_status_update.return_value = {"accepted": True, "queued": True}
    request = make_request({"object": {"id": "pay-1", "status": "succeeded"}})

    with (
        patch.object(routes, "_assert_webhook_auth") as assert_auth,
        patch.object(routes, "_build_service", return_value=service),
    ):
        result = await routes.yookassa_webhook("secret", request)

    assert_auth.assert_called_once_with("secret")
    service.process_status_update.assert_awaited_once_with(
        method="yookassa",
        payment_id="pay-1",
        status="succeeded",
        payload={"object": {"id": "pay-1", "status": "succeeded"}},
    )
    assert result == {"ok": True, "accepted": True, "queued": True}


@pytest.mark.asyncio
async def test_cryptopay_webhook_rejects_invalid_json():
    request = make_request(json_side_effect=ValueError("boom"))

    with patch.object(routes, "_assert_webhook_auth"):
        with pytest.raises(routes.HTTPException) as exc_info:
            await routes.cryptopay_webhook("secret", request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid JSON payload"
