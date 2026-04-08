import json
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.payments.payment_queue_service import PaymentQueueService


@pytest.fixture
def service_and_redis():
    redis_client = AsyncMock()
    service = PaymentQueueService(
        redis_client=redis_client,
        ready_queue_key="ready",
        retry_queue_key="retry",
        dead_letter_queue_key="dead",
        dedupe_prefix="dedupe",
        delayed_batch_size=10,
    )
    return service, redis_client


@pytest.mark.asyncio
async def test_enqueue_if_new_skips_duplicate_payload(service_and_redis):
    service, redis_client = service_and_redis
    redis_client.set.return_value = False

    created = await service.enqueue_if_new({"payment_id": "pay-1"}, dedupe_ttl_seconds=120)

    assert created is False
    redis_client.rpush.assert_not_awaited()
    redis_client.zadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_dedupe_updates_existing_key_ttl(service_and_redis):
    service, redis_client = service_and_redis

    await service.refresh_dedupe({"payment_id": "pay-1"}, ttl_seconds=180)

    redis_client.set.assert_awaited_once_with("dedupe:pay-1", "1", ex=180)


@pytest.mark.asyncio
async def test_pop_ready_drops_invalid_json(service_and_redis):
    service, redis_client = service_and_redis
    redis_client.blpop.return_value = ("ready", "{invalid")

    payload = await service.pop_ready(timeout_seconds=5)

    assert payload is None


@pytest.mark.asyncio
async def test_requeue_dead_letters_resets_attempt_and_last_error(service_and_redis):
    service, redis_client = service_and_redis
    dead_task = json.dumps(
        {
            "payload": {
                "payment_id": "pay-1",
                "attempt": 3,
                "last_error": "boom",
            }
        }
    )
    redis_client.blpop.side_effect = [("dead", dead_task), None]

    requeued, skipped = await service.requeue_dead_letters(limit=2, delay_seconds=30)

    assert (requeued, skipped) == (1, 0)
    redis_client.zadd.assert_awaited_once()
    queued_payload = json.loads(redis_client.zadd.await_args.args[2])
    assert queued_payload == {"payment_id": "pay-1", "attempt": 0}


@pytest.mark.asyncio
async def test_promote_delayed_moves_only_removed_tasks(service_and_redis):
    service, redis_client = service_and_redis
    redis_client.zrangebyscore.return_value = ["a", "b"]
    redis_client.zrem.side_effect = [1, 0]

    with patch(
        "telegram_bot.services.payments.payment_queue_service.time.time",
        return_value=100,
    ):
        moved = await service.promote_delayed()

    assert moved == 1
    redis_client.rpush.assert_awaited_once_with("ready", "a")
