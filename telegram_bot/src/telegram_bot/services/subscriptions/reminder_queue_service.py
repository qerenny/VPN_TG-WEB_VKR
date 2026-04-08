import json
import time
from typing import Any

from shared.utils.async_redis_client import AsyncRedisClient
from shared.utils.logging_utils import logger


class ReminderQueueService:
    def __init__(
        self,
        redis_client: AsyncRedisClient,
        ready_queue_key: str,
        retry_queue_key: str,
        dead_letter_queue_key: str,
        dedupe_prefix: str,
        delayed_batch_size: int = 100,
    ):
        self.redis_client = redis_client
        self.ready_queue_key = ready_queue_key
        self.retry_queue_key = retry_queue_key
        self.dead_letter_queue_key = dead_letter_queue_key
        self.dedupe_prefix = dedupe_prefix
        self.delayed_batch_size = delayed_batch_size

    async def enqueue_if_new(self, payload: dict[str, Any], dedupe_ttl_seconds: int) -> bool:
        dedupe_key = self._build_dedupe_key(payload)
        created = await self.redis_client.set(dedupe_key, "1", ex=dedupe_ttl_seconds, nx=True)
        if not created:
            return False
        await self.enqueue(payload)
        return True

    async def enqueue(self, payload: dict[str, Any], delay_seconds: int = 0) -> None:
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        if delay_seconds <= 0:
            await self.redis_client.rpush(self.ready_queue_key, data)
            return

        due_ts = int(time.time()) + delay_seconds
        await self.redis_client.zadd(self.retry_queue_key, due_ts, data)

    async def promote_delayed(self) -> int:
        now_ts = int(time.time())
        delayed = await self.redis_client.zrangebyscore(
            self.retry_queue_key,
            "-inf",
            now_ts,
            limit=self.delayed_batch_size,
        )
        moved = 0

        for raw_task in delayed:
            removed = await self.redis_client.zrem(self.retry_queue_key, raw_task)
            if removed:
                await self.redis_client.rpush(self.ready_queue_key, raw_task)
                moved += 1

        if moved:
            logger.info(f"Moved {moved} delayed reminder tasks to ready queue.")
        return moved

    async def pop_ready(self, timeout_seconds: int) -> dict[str, Any] | None:
        result = await self.redis_client.blpop(self.ready_queue_key, timeout_seconds=timeout_seconds)
        if result is None:
            return None

        _, raw_payload = result
        try:
            payload = json.loads(raw_payload)
            if not isinstance(payload, dict):
                logger.error("Invalid reminder payload type in queue. Dropping task.")
                return None
            return payload
        except json.JSONDecodeError:
            logger.error("Failed to decode reminder payload from queue. Dropping task.")
            return None

    async def push_dead_letter(self, payload: dict[str, Any], error_message: str) -> None:
        dead_task = {
            "payload": payload,
            "error": error_message,
            "failed_at": int(time.time()),
        }
        data = json.dumps(dead_task, separators=(",", ":"), ensure_ascii=False)
        await self.redis_client.rpush(self.dead_letter_queue_key, data)

    async def close(self) -> None:
        await self.redis_client.aclose()

    def _build_dedupe_key(self, payload: dict[str, Any]) -> str:
        tg_id = payload.get("tg_id")
        expiration_date = payload.get("expiration_date")
        return f"{self.dedupe_prefix}:{tg_id}:{expiration_date}"
