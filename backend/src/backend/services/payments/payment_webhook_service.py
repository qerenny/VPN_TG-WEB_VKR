import json
import time
from typing import Any

from backend.utils.async_redis_client import AsyncRedisClient, RedisClientError
from shared.constants.payments import PROVIDER_STATUS_PAID
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
)
from shared.utils.logging_utils import logger


class PaymentWebhookService:
    def __init__(
        self,
        repo: PaymentRepository,
        redis_client: AsyncRedisClient | None,
        ready_queue_key: str,
        dedupe_prefix: str,
        dedupe_ttl_seconds: int,
    ):
        self.repo = repo
        self.redis_client = redis_client
        self.ready_queue_key = ready_queue_key
        self.dedupe_prefix = dedupe_prefix
        self.dedupe_ttl_seconds = dedupe_ttl_seconds

    async def process_status_update(
        self,
        *,
        method: str,
        payment_id: str,
        status: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payment_id = str(payment_id).strip()
        status = str(status).strip().lower()
        method = str(method).strip().lower()

        if not payment_id or not status:
            return {"accepted": False, "reason": "missing_payment_id_or_status"}

        payment = await self.repo.get_by_payment_id(payment_id)
        if payment is None:
            logger.warning(
                "Webhook payment not found: "
                f"method={method}, payment_id={payment_id}, status={status}"
            )
            return {"accepted": True, "reason": "payment_not_found"}

        payment_method = str(payment.method or "").strip().lower()
        if payment_method and payment_method != method:
            logger.warning(
                "Webhook payment method mismatch: "
                f"payment_id={payment_id}, expected={payment_method}, got={method}"
            )
            return {"accepted": True, "reason": "payment_method_mismatch"}

        await self.repo.update_status(
            payment_id=payment_id,
            status=status,
            # confirmed=True only after full fulfillment pipeline.
            confirmed=False,
        )

        queued = False
        if status in PROVIDER_STATUS_PAID:
            queued = await self._enqueue_for_fulfillment(payment_id)

        return {"accepted": True, "status": status, "queued": queued}

    async def _enqueue_for_fulfillment(self, payment_id: str) -> bool:
        if self.redis_client is None:
            logger.warning(
                f"Webhook paid event for {payment_id} arrived, but Redis is unavailable."
            )
            return False

        dedupe_key = f"{self.dedupe_prefix}:{payment_id}"
        try:
            created = await self.redis_client.set(
                dedupe_key,
                "1",
                ex=self.dedupe_ttl_seconds,
                nx=True,
            )
            if not created:
                return False

            payload = {
                "payment_id": str(payment_id),
                "attempt": 0,
                "queued_at": int(time.time()),
            }
            data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            await self.redis_client.rpush(self.ready_queue_key, data)
            return True
        except RedisClientError as err:
            logger.error(
                f"Failed to enqueue paid payment from webhook: payment_id={payment_id}, err={err}"
            )
            return False
