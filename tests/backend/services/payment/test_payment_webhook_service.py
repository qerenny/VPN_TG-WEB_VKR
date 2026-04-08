from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.payments.payment_webhook_service import PaymentWebhookService


@pytest.mark.asyncio
async def test_process_status_update_payment_not_found():
    repo = AsyncMock()
    redis_client = AsyncMock()
    repo.get_by_payment_id.return_value = None

    service = PaymentWebhookService(
        repo=repo,
        redis_client=redis_client,
        ready_queue_key="ready",
        dedupe_prefix="dedupe",
        dedupe_ttl_seconds=120,
    )

    result = await service.process_status_update(
        method="yookassa",
        payment_id="abc",
        status="succeeded",
    )

    assert result["accepted"] is True
    assert result["reason"] == "payment_not_found"
    repo.update_status.assert_not_awaited()
    redis_client.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_status_update_pending_only_updates_db():
    repo = AsyncMock()
    redis_client = AsyncMock()
    sync_service = AsyncMock()
    repo.get_by_payment_id.return_value = SimpleNamespace(
        payment_id="abc",
        method="cryptopay",
        status="new",
        confirmed=False,
    )

    service = PaymentWebhookService(
        repo=repo,
        redis_client=redis_client,
        ready_queue_key="ready",
        dedupe_prefix="dedupe",
        dedupe_ttl_seconds=120,
        sync_service=sync_service,
    )

    result = await service.process_status_update(
        method="cryptopay",
        payment_id="abc",
        status="pending",
        payload={"payload": {"invoice_id": "abc", "status": "pending"}},
    )

    assert result["accepted"] is True
    assert result["queued"] is False
    repo.update_status.assert_awaited_once_with(
        payment_id="abc",
        status="pending",
        confirmed=False,
    )
    sync_service.sync_legacy_payment.assert_not_awaited()
    redis_client.set.assert_not_awaited()
    redis_client.rpush.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_status_update_method_mismatch_is_ignored():
    repo = AsyncMock()
    redis_client = AsyncMock()
    repo.get_by_payment_id.return_value = SimpleNamespace(
        payment_id="abc",
        method="yookassa",
    )

    service = PaymentWebhookService(
        repo=repo,
        redis_client=redis_client,
        ready_queue_key="ready",
        dedupe_prefix="dedupe",
        dedupe_ttl_seconds=120,
    )

    result = await service.process_status_update(
        method="cryptopay",
        payment_id="abc",
        status="paid",
    )

    assert result["accepted"] is True
    assert result["reason"] == "payment_method_mismatch"
    repo.update_status.assert_not_awaited()
    redis_client.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_status_update_paid_enqueues_once():
    repo = AsyncMock()
    redis_client = AsyncMock()
    repo.get_by_payment_id.return_value = SimpleNamespace(
        payment_id="abc",
        method="cryptopay",
    )
    redis_client.set.return_value = True

    service = PaymentWebhookService(
        repo=repo,
        redis_client=redis_client,
        ready_queue_key="ready",
        dedupe_prefix="dedupe",
        dedupe_ttl_seconds=120,
    )

    result = await service.process_status_update(
        method="cryptopay",
        payment_id="abc",
        status="paid",
    )

    assert result["accepted"] is True
    assert result["queued"] is True
    redis_client.set.assert_awaited_once_with(
        "dedupe:abc",
        "1",
        ex=120,
        nx=True,
    )
    redis_client.rpush.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_status_update_paid_not_enqueued_when_duplicate():
    repo = AsyncMock()
    redis_client = AsyncMock()
    repo.get_by_payment_id.return_value = SimpleNamespace(
        payment_id="abc",
        method="yookassa",
    )
    redis_client.set.return_value = False

    service = PaymentWebhookService(
        repo=repo,
        redis_client=redis_client,
        ready_queue_key="ready",
        dedupe_prefix="dedupe",
        dedupe_ttl_seconds=120,
    )

    result = await service.process_status_update(
        method="yookassa",
        payment_id="abc",
        status="succeeded",
    )

    assert result["accepted"] is True
    assert result["queued"] is False
    redis_client.rpush.assert_not_awaited()
