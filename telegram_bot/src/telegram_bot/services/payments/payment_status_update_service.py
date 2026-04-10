import asyncio
import time

from shared.config.config import PAYMENT_STATUS_SCAN_INTERVAL_SECONDS
from shared.constants.payments import (
    PROVIDER_STATUS_CANCELED,
    PROVIDER_STATUS_FAILED,
    PROVIDER_STATUS_PAID,
    RUNTIME_PAYMENT_STATUS_CANCELED,
)
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
    PaymentSnapshot,
)
from shared.utils.logging_utils import logger, log_with_throttle
from telegram_bot.services.payments.payment_fulfillment_service import (
    PaymentFulfillmentService,
)
from telegram_bot.services.payments.payment_gateway import PaymentGateway

PAID_STATUSES = PROVIDER_STATUS_PAID
TERMINAL_UNPAID_STATUSES = PROVIDER_STATUS_CANCELED | PROVIDER_STATUS_FAILED
SECONDS_IN_DAY = 24 * 60 * 60
MILLISECONDS_IN_SECOND = 1000
STALE_UNPAID_PAYMENT_DAYS = 7
STALE_UNPAID_PAYMENT_AGE_MS = (
    STALE_UNPAID_PAYMENT_DAYS * SECONDS_IN_DAY * MILLISECONDS_IN_SECOND
)
MILLISECONDS_EPOCH_THRESHOLD = 1_000_000_000_000


def _normalize_status(status: str) -> str:
    return str(status).strip().lower()


def _is_stale_unpaid_payment(created_at: int, now_ms: int) -> bool:
    created_at_int = int(created_at or 0)
    if created_at_int <= 0:
        return False
    if created_at_int < MILLISECONDS_EPOCH_THRESHOLD:
        created_at_int *= MILLISECONDS_IN_SECOND
    return (now_ms - created_at_int) >= STALE_UNPAID_PAYMENT_AGE_MS


class PaymentStatusChecker:
    ERROR_LOG_COOLDOWN_SECONDS = 300.0

    def __init__(
        self,
        repo: PaymentRepository,
        payment_fulfillment_service: PaymentFulfillmentService,
        gateways: dict[str, PaymentGateway] | None = None,
        scan_interval_seconds: int = PAYMENT_STATUS_SCAN_INTERVAL_SECONDS,
    ):
        self.repo = repo
        self.gateways: dict[str, PaymentGateway] = {
            str(key).strip().lower(): value
            for key, value in (gateways or {}).items()
        }
        self.payment_fulfillment_service = payment_fulfillment_service
        self.scan_interval_seconds = scan_interval_seconds

    async def run_scheduler(self):
        logger.info(
            "Payment status scheduler started "
            f"(scan_interval={self.scan_interval_seconds}s)."
        )
        while True:
            try:
                await self.check_and_update_payment_status()
            except Exception as err:
                log_with_throttle(
                    "ERROR",
                    f"payment-status-scheduler:{type(err).__name__}:{str(err)}",
                    f"Payment status check failed: {err!r}",
                    cooldown_seconds=self.ERROR_LOG_COOLDOWN_SECONDS,
                )
            await asyncio.sleep(self.scan_interval_seconds)

    async def check_and_update_payment_status(self):
        payments = await self.repo.get_unconfirmed()
        if not payments:
            return

        now_ms = int(time.time() * MILLISECONDS_IN_SECOND)
        tasks = []
        paid_payment_ids: list[str] = []
        updates = []
        valid_payments_for_check = []
        payments_to_sync = []

        for payment in payments:
            method = payment.method
            payment_id = payment.payment_id
            current_status = _normalize_status(payment.status)

            if current_status in PAID_STATUSES:
                paid_payment_ids.append(str(payment_id))
                payments_to_sync.append(payment)
                continue

            if current_status in TERMINAL_UNPAID_STATUSES:
                continue

            if _is_stale_unpaid_payment(payment.created_at, now_ms):
                payment.status = RUNTIME_PAYMENT_STATUS_CANCELED
                payment.confirmed = False
                updates.append((str(payment_id), RUNTIME_PAYMENT_STATUS_CANCELED, False))
                payments_to_sync.append(payment)
                logger.info(
                    "Marking unpaid payment as canceled due to age "
                    f"(payment_id={payment_id}, created_at={payment.created_at})"
                )
                continue

            try:
                method_key = str(method).strip().lower()
                gateway = self.gateways.get(method_key)
                if gateway is None:
                    logger.error(
                        f"Unsupported payment method: {method} for payment {payment_id}"
                    )
                    continue
                tasks.append(gateway.find_payment_status(str(payment_id)))
                valid_payments_for_check.append(payment)
            except Exception as e:
                logger.error(f"Error preparing task for payment {payment_id}: {e}")
                continue

        if not tasks:
            if updates:
                await self.repo.update_status_batch(updates)
            for payment_id in paid_payment_ids:
                await self.payment_fulfillment_service.enqueue_payment(payment_id)
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for payment, result in zip(valid_payments_for_check, results):
            if isinstance(result, Exception):
                log_with_throttle(
                    "ERROR",
                    (
                        "payment-status-check:"
                        f"{payment.payment_id}:{type(result).__name__}:{str(result)}"
                    ),
                    f"Error checking status for payment {payment.payment_id}: {result}",
                    cooldown_seconds=self.ERROR_LOG_COOLDOWN_SECONDS,
                )
                continue

            if result is None:
                log_with_throttle(
                    "ERROR",
                    f"payment-status-empty:{payment.payment_id}",
                    (
                        f"Payment provider returned empty status for "
                        f"payment {payment.payment_id}. Skipping update."
                    ),
                    cooldown_seconds=self.ERROR_LOG_COOLDOWN_SECONDS,
                )
                continue

            status = _normalize_status(result)
            if not status:
                log_with_throttle(
                    "ERROR",
                    f"payment-status-empty:{payment.payment_id}",
                    (
                        f"Payment provider returned empty status for "
                        f"payment {payment.payment_id}. Skipping update."
                    ),
                    cooldown_seconds=self.ERROR_LOG_COOLDOWN_SECONDS,
                )
                continue

            confirmed = status in PAID_STATUSES
            current_status = _normalize_status(payment.status)

            if status != current_status:
                # Confirmed flag is set only after successful fulfillment (3x-ui + DB sync).
                payment.status = status
                payment.confirmed = False
                updates.append((str(payment.payment_id), status, False))
                payments_to_sync.append(payment)

            if confirmed:
                paid_payment_ids.append(str(payment.payment_id))
                if payment not in payments_to_sync:
                    payment.status = status
                    payment.confirmed = False
                    payments_to_sync.append(payment)

        if updates:
            await self.repo.update_status_batch(updates)

        for payment_id in paid_payment_ids:
            await self.payment_fulfillment_service.enqueue_payment(payment_id)
