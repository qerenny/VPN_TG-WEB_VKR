import json
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.subscriptions.reminder_queue_service import (
    ReminderQueueService,
)


@pytest.fixture
def service_and_redis():
    redis_client = AsyncMock()
    service = ReminderQueueService(
        redis_client=redis_client,
        ready_queue_key="ready",
        retry_queue_key="retry",
        dead_letter_queue_key="dead",
        dedupe_prefix="dedupe",
        delayed_batch_size=10,
    )
    return service, redis_client


@pytest.mark.asyncio
async def test_enqueue_if_new_pushes_to_ready_queue_for_new_payload(service_and_redis):
    service, redis_client = service_and_redis
    redis_client.set.return_value = True

    created = await service.enqueue_if_new(
        {"tg_id": 1, "expiration_date": 2_000},
        dedupe_ttl_seconds=60,
    )

    assert created is True
    redis_client.set.assert_awaited_once_with(
        "dedupe:1:2000",
        "1",
        ex=60,
        nx=True,
    )
    redis_client.rpush.assert_awaited_once()


@pytest.mark.asyncio
async def test_pop_ready_drops_non_dict_payload(service_and_redis):
    service, redis_client = service_and_redis
    redis_client.blpop.return_value = ("ready", json.dumps(["not", "a", "dict"]))

    payload = await service.pop_ready(timeout_seconds=5)

    assert payload is None


@pytest.mark.asyncio
async def test_promote_delayed_moves_only_removed_tasks(service_and_redis):
    service, redis_client = service_and_redis
    redis_client.zrangebyscore.return_value = ["task-1", "task-2"]
    redis_client.zrem.side_effect = [1, 0]

    with patch(
        "telegram_bot.services.subscriptions.reminder_queue_service.time.time",
        return_value=100,
    ):
        moved = await service.promote_delayed()

    assert moved == 1
    redis_client.rpush.assert_awaited_once_with("ready", "task-1")


@pytest.mark.asyncio
async def test_push_dead_letter_serializes_failure_payload(service_and_redis):
    service, redis_client = service_and_redis

    with patch(
        "telegram_bot.services.subscriptions.reminder_queue_service.time.time",
        return_value=321,
    ):
        await service.push_dead_letter({"tg_id": 7}, "boom")

    redis_client.rpush.assert_awaited_once()
    pushed_payload = json.loads(redis_client.rpush.await_args.args[1])
    assert pushed_payload == {
        "payload": {"tg_id": 7},
        "error": "boom",
        "failed_at": 321,
    }
