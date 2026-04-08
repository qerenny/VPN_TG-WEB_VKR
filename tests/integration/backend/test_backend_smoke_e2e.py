from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.routers.subscription import subscription_routes
from shared.config.config import BACKEND_PREFIX, PAYMENT_WEBHOOK_TOKEN
from shared.migration_support.models.payments.payment_model import Payment
from shared.migration_support.models.users.user_model import User
from shared.migration_support.repositories.payments.payment_repository import PaymentRepository
from shared.migration_support.repositories.users.user_repository import UserRepository
from shared.utils.timestamp_utils import TimestampUtils


pytestmark = pytest.mark.integration


def make_uuid(seed: int) -> str:
    return str(uuid.UUID(int=seed))


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_encode_user_endpoint_returns_decodable_jwt(client):
    response = client.post(
        f"{BACKEND_PREFIX}/user/encode",
        params={"tg_id": 123, "email": "user@example.com"},
    )

    assert response.status_code == 200
    payload = client.app.state.deps.jwt_encoder.decode(response.json()["token"])
    assert payload["tg_id"] == 123
    assert payload["email"] == "user@example.com"


def test_public_config_endpoint_returns_frontend_runtime_config(client):
    response = client.get(f"{BACKEND_PREFIX}/user/public-config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["support_link"].startswith("https://t.me/")
    assert "telegram_proxy_url" in payload
    assert "subscription_add_links" in payload
    assert "app_links" in payload
    assert "instruction_links" in payload


def test_subscription_endpoint_reads_user_from_postgres_and_caches_in_redis(
    client,
    redis_client,
    run_async_fn,
):
    timestamp_utils = TimestampUtils()
    user = User(
        tg_id=321,
        uuid=make_uuid(321),
        email="sub@example.com",
        expiration_date=timestamp_utils.current_timestamp() + 86_400_000,
        login_date=timestamp_utils.current_timestamp(),
        trial_date=None,
        news_channel_date=None,
        sub_id="sub-321",
    )
    run_async_fn(UserRepository().create(user))

    token = client.app.state.deps.jwt_encoder.encode(
        {"tg_id": user.tg_id, "email": user.email}
    )

    response = client.get(f"{BACKEND_PREFIX}/subscription/{token}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sub_is_active"] is True
    assert payload["sub_link"].endswith("?uuid=sub-321")
    assert payload["support_link"].startswith("https://t.me/")

    cached_payload = run_async_fn(
        redis_client.get(f"{subscription_routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:info:v1:{token}")
    )
    assert cached_payload is not None
    assert json.loads(cached_payload.decode("utf-8"))["sub_link"] == payload["sub_link"]


def test_subscription_endpoint_reads_cached_redis_payload_without_reloading_service(
    client,
    run_async_fn,
):
    token = client.app.state.deps.jwt_encoder.encode(
        {"tg_id": 999, "email": "cached@example.com"}
    )
    redis_key = f"{subscription_routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:info:v1:{token}"

    client.app.state.deps.subscription_manager_service.get_subscription_formatted_info = AsyncMock(
        side_effect=AssertionError("service should not be called when Redis cache exists")
    )
    run_async_fn(
        client.app.state.redis_client.set(
            redis_key,
            json.dumps(
                {
                    "human_view_expiration_remaining": "1 day",
                    "human_view_expiration_date": "12:00:00 12-03-2026",
                    "sub_link": "https://cached.example.com/sub?uuid=cached-sub",
                    "sub_is_active": True,
                    "support_link": "https://t.me/cached_support",
                },
                ensure_ascii=False,
            ),
            ex=60,
        )
    )

    subscription_routes.subscription_info_cache.clear()

    response = client.get(f"{BACKEND_PREFIX}/subscription/{token}")

    assert response.status_code == 200
    assert response.json()["sub_link"] == "https://cached.example.com/sub?uuid=cached-sub"
    assert response.json()["sub_is_active"] is True


def test_subscription_build_endpoint_fetches_upstreams_and_then_serves_redis_cache(
    client,
    redis_client,
    run_async_fn,
    monkeypatch,
):
    http_client = AsyncMock()
    http_client.get.side_effect = [
        SimpleNamespace(
            status_code=200,
            content=b"cfg-a",
            text="ok",
            headers={
                "subscription-userinfo": "upload=1; download=2; total=10; expire=100"
            },
        ),
        SimpleNamespace(
            status_code=200,
            content=b"cfg-b",
            text="ok",
            headers={
                "subscription-userinfo": "upload=3; download=4; total=20; expire=200"
            },
        ),
    ]
    client.app.state.http_client = http_client

    monkeypatch.setattr(
        subscription_routes,
        "API_SERVERS",
        {"de": {"host": "de"}, "ee": {"host": "ee"}},
    )
    monkeypatch.setattr(
        subscription_routes,
        "build_subscription_url",
        lambda server: f"https://{server['host']}/sub/",
    )
    monkeypatch.setattr(
        subscription_routes,
        "process_subscription_content",
        lambda content, source_name=None, **kwargs: [f"{source_name}:{content.decode('utf-8')}"],
    )

    response = client.get(f"{BACKEND_PREFIX}/subscription/build", params={"uuid": "build-1"})

    assert response.status_code == 200
    assert response.text == "de:cfg-a\nee:cfg-b"
    assert (
        response.headers["profile-update-interval"]
        == subscription_routes.SUBSCRIPTION_PROFILE_UPDATE_INTERVAL
    )
    assert (
        response.headers["subscription-auto-update-open-enable"]
        == subscription_routes.SUBSCRIPTION_AUTO_UPDATE_OPEN_ENABLE
    )
    assert response.headers["profile-title"] == subscription_routes.SUBSCRIPTION_PROFILE_TITLE
    assert response.headers["support-url"].startswith("https://t.me/")
    assert response.headers["profile-web-page-url"]
    assert response.headers["announce"] == subscription_routes.SUBSCRIPTION_ANNOUNCE
    assert (
        response.headers["subscription-userinfo"]
        == "upload=4; download=6; total=20; expire=200"
    )
    assert http_client.get.await_count == 2

    cached_payload = run_async_fn(
        redis_client.get(f"{subscription_routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:build:build-1")
    )
    cached_result = subscription_routes._decode_subscription_build_cache(cached_payload)
    assert cached_result.body == "de:cfg-a\nee:cfg-b"
    assert cached_result.headers == {
        "subscription-userinfo": "upload=4; download=6; total=20; expire=200",
    }

    subscription_routes.subscription_cache.clear()
    subscription_routes.subscription_inflight.clear()

    cached_only_client = AsyncMock()
    cached_only_client.get.side_effect = AssertionError("upstream should not be called on Redis hit")
    client.app.state.http_client = cached_only_client

    second_response = client.get(f"{BACKEND_PREFIX}/subscription/build", params={"uuid": "build-1"})

    assert second_response.status_code == 200
    assert second_response.text == "de:cfg-a\nee:cfg-b"
    assert second_response.headers["profile-title"] == subscription_routes.SUBSCRIPTION_PROFILE_TITLE
    assert (
        second_response.headers["subscription-userinfo"]
        == "upload=4; download=6; total=20; expire=200"
    )
    assert cached_only_client.get.await_count == 0


def test_payment_webhook_updates_postgres_and_enqueues_ready_task(
    client,
    redis_client,
    run_async_fn,
):
    timestamp_utils = TimestampUtils()
    run_async_fn(
        UserRepository().create(
            User(
                tg_id=777,
                uuid=make_uuid(777),
                email="pay@example.com",
                expiration_date=None,
                login_date=timestamp_utils.current_timestamp(),
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-777",
            )
        )
    )
    run_async_fn(
        PaymentRepository().create(
            Payment(
                payment_id="payment-777",
                tg_id=777,
                status="pending",
                payload="month1",
                created_at=timestamp_utils.current_timestamp(),
                confirmed=False,
                method="yookassa",
            )
        )
    )

    response = client.post(
        f"{BACKEND_PREFIX}/payments/webhook/yookassa/{PAYMENT_WEBHOOK_TOKEN}",
        json={"object": {"id": "payment-777", "status": "succeeded"}},
    )

    assert response.status_code == 200
    assert response.json()["queued"] is True

    payment = run_async_fn(PaymentRepository().get_by_payment_id("payment-777"))
    assert payment is not None
    assert payment.status == "succeeded"
    assert payment.confirmed is False



def test_payment_webhook_deduplicates_repeat_notifications(
    client,
    redis_client,
    run_async_fn,
):
    timestamp_utils = TimestampUtils()
    run_async_fn(
        UserRepository().create(
            User(
                tg_id=888,
                uuid=make_uuid(888),
                email="dedupe@example.com",
                expiration_date=None,
                login_date=timestamp_utils.current_timestamp(),
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-888",
            )
        )
    )
    run_async_fn(
        PaymentRepository().create(
            Payment(
                payment_id="payment-dedupe",
                tg_id=888,
                status="pending",
                payload="month1",
                created_at=timestamp_utils.current_timestamp(),
                confirmed=False,
                method="yookassa",
            )
        )
    )

    first_response = client.post(
        f"{BACKEND_PREFIX}/payments/webhook/yookassa/{PAYMENT_WEBHOOK_TOKEN}",
        json={"object": {"id": "payment-dedupe", "status": "succeeded"}},
    )
    second_response = client.post(
        f"{BACKEND_PREFIX}/payments/webhook/yookassa/{PAYMENT_WEBHOOK_TOKEN}",
        json={"object": {"id": "payment-dedupe", "status": "succeeded"}},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["queued"] is True
    assert second_response.json()["queued"] is False



def test_cryptopay_webhook_updates_postgres_and_enqueues_ready_task(
    client,
    redis_client,
    run_async_fn,
):
    timestamp_utils = TimestampUtils()
    run_async_fn(
        UserRepository().create(
            User(
                tg_id=999,
                uuid=make_uuid(999),
                email="crypto@example.com",
                expiration_date=None,
                login_date=timestamp_utils.current_timestamp(),
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-999",
            )
        )
    )
    run_async_fn(
        PaymentRepository().create(
            Payment(
                payment_id="invoice-42",
                tg_id=999,
                status="pending",
                payload="month1",
                created_at=timestamp_utils.current_timestamp(),
                confirmed=False,
                method="cryptopay",
            )
        )
    )

    response = client.post(
        f"{BACKEND_PREFIX}/payments/webhook/cryptopay/{PAYMENT_WEBHOOK_TOKEN}",
        json={"update_type": "invoice_paid", "payload": {"invoice_id": "invoice-42"}},
    )

    assert response.status_code == 200
    assert response.json()["queued"] is True
    assert response.json()["status"] == "paid"

    payment = run_async_fn(PaymentRepository().get_by_payment_id("invoice-42"))
    assert payment is not None
    assert payment.status == "paid"
    assert payment.confirmed is False
