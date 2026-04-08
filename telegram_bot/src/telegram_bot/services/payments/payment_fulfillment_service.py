import asyncio
import time
from typing import Any

from shared.config.config import PHOTO_menu
from shared.constants.payments import PROVIDER_STATUS_PAID
from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_legacy_payload
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
)
from shared.product_constants import (
    ENTITLEMENT_KIND_TIME,
    PRODUCT_SCOPE_STANDARD,
    PRODUCT_SCOPE_WHITELIST,
)
from shared.utils.logging_utils import logger, log_with_throttle
from telegram_bot.bot import bot
from telegram_bot.services.linking.telegram_link_service import TelegramLinkService
from telegram_bot.services.payments.payment_processing_service import PaymentProcessingService
from telegram_bot.services.payments.payment_queue_service import PaymentQueueService
from telegram_bot.services.subscriptions.subscription_provisioning_service import (
    SubscriptionProvisioningService,
)
from telegram_bot.shared.keyboards import build_main_menu_markup, build_profile_navigation_markup
from telegram_bot.shared.texts import messages

DEAD_LETTER_DEDUPE_TTL_SECONDS = 24 * 60 * 60


class PaymentFulfillmentService:
    WORKER_ERROR_LOG_COOLDOWN_SECONDS = 300.0

    def __init__(
        self,
        repo: PaymentRepository,
        payment_processing: PaymentProcessingService,
        queue_service: PaymentQueueService,
        subscription_service: SubscriptionProvisioningService,
        scan_interval_seconds: int,
        retry_base_seconds: int,
        max_retries: int,
        worker_pop_timeout_seconds: int,
        dedupe_ttl_seconds: int,
        telegram_link_service: TelegramLinkService | None = None,
        sync_service=None,
    ):
        self.repo = repo
        self.payment_processing = payment_processing
        self.queue_service = queue_service
        self.subscription_service = subscription_service
        self.scan_interval_seconds = scan_interval_seconds
        self.retry_base_seconds = retry_base_seconds
        self.max_retries = max_retries
        self.worker_pop_timeout_seconds = worker_pop_timeout_seconds
        self.dedupe_ttl_seconds = dedupe_ttl_seconds
        self.telegram_link_service = telegram_link_service

    async def enqueue_payment(self, payment_id: str) -> bool:
        payload = {
            "payment_id": str(payment_id),
            "attempt": 0,
            "queued_at": int(time.time()),
        }
        created = await self.queue_service.enqueue_if_new(
            payload,
            dedupe_ttl_seconds=self.dedupe_ttl_seconds,
        )
        if created:
            logger.info(f"Queued paid payment for processing: payment_id={payment_id}")
        return created

    async def enqueue_ready_payments(self) -> int:
        payments = await self.repo.get_unconfirmed_paid()
        enqueued_count = 0
        for payment in payments:
            if await self.enqueue_payment(str(payment.payment_id)):
                enqueued_count += 1

        if enqueued_count:
            logger.info(f"Queued {enqueued_count} paid payments for fulfillment.")
        return enqueued_count

    async def run_scheduler(self) -> None:
        logger.info(
            "Payment fulfillment scheduler started "
            f"(scan_interval={self.scan_interval_seconds}s)."
        )
        while True:
            try:
                await self.enqueue_ready_payments()
            except Exception as err:
                log_with_throttle(
                    "ERROR",
                    (
                        "payment-fulfillment-scheduler:"
                        f"{type(err).__name__}:{str(err)}"
                    ),
                    f"Failed to enqueue paid payment tasks: {err}",
                    cooldown_seconds=self.WORKER_ERROR_LOG_COOLDOWN_SECONDS,
                )
            await asyncio.sleep(self.scan_interval_seconds)

    async def process_queue_once(self) -> bool:
        await self.queue_service.promote_delayed()
        payload = await self.queue_service.pop_ready(
            timeout_seconds=self.worker_pop_timeout_seconds
        )
        if payload is None:
            return False

        payment_id = str(payload.get("payment_id", "")).strip()
        if not payment_id:
            logger.error("Payment task without payment_id. Dropping task.")
            return True

        try:
            await self.queue_service.refresh_dedupe(
                payload,
                ttl_seconds=self.dedupe_ttl_seconds,
            )
            payment = await self.repo.get_by_payment_id(payment_id)
            if payment is None:
                logger.warning(f"Payment {payment_id} not found. Dropping task.")
                return True

            if payment.confirmed:
                logger.info(f"Payment {payment_id} already confirmed. Skipping task.")
                return True

            if str(payment.status or "").strip().lower() not in PROVIDER_STATUS_PAID:
                logger.info(
                    f"Payment {payment_id} is not paid yet "
                    f"(status={payment.status}). Skipping task."
                )
                return True

            (
                subscription_updated_text,
                subscription_update_date_text,
                grant_tg_id_text,
                grant_referrer_id_text,
                referrer_tg_id,
            ) = await self.payment_processing.payment_processing(
                user_id=payment.user_id,
                tg_id=payment.tg_id,
                product=str(payment.payload),
                payment_id=str(payment.payment_id),
            )

            subscription_link_scope = self._subscription_link_scope(str(payment.payload))

            await self.repo.update_status(
                payment_id=payment_id,
                status=payment.status,
                confirmed=True,
            )
            payment.confirmed = True

            if payment.tg_id is not None:
                await self._notify_user(
                    tg_id=int(payment.tg_id),
                    subscription_updated_text=subscription_updated_text,
                    subscription_update_date_text=subscription_update_date_text,
                    grant_tg_id_text=grant_tg_id_text,
                    grant_referrer_id_text=grant_referrer_id_text,
                    referrer_tg_id=referrer_tg_id,
                    subscription_link_scope=subscription_link_scope,
                )
            logger.info(f"Payment fulfilled successfully: payment_id={payment_id}")
            return True
        except Exception as err:
            await self._retry_or_dead_letter(payload, str(err))
            return True

    async def run_worker(self) -> None:
        logger.info("Payment fulfillment worker started.")
        while True:
            try:
                await self.process_queue_once()
            except Exception as err:
                log_with_throttle(
                    "ERROR",
                    (
                        "payment-fulfillment-worker:"
                        f"{type(err).__name__}:{str(err)}"
                    ),
                    f"Payment fulfillment worker iteration failed: {err!r}",
                    cooldown_seconds=self.WORKER_ERROR_LOG_COOLDOWN_SECONDS,
                )
                await asyncio.sleep(1)

    async def shutdown(self) -> None:
        await self.queue_service.close()

    async def _retry_or_dead_letter(self, payload: dict[str, Any], error_message: str) -> None:
        attempt = int(payload.get("attempt", 0)) + 1
        payload["attempt"] = attempt
        payload["last_error"] = error_message

        payment_id = payload.get("payment_id")
        if attempt <= self.max_retries:
            delay = self.retry_base_seconds * (2 ** (attempt - 1))
            await self.queue_service.refresh_dedupe(
                payload,
                ttl_seconds=self._dedupe_ttl_for_retry(delay),
            )
            await self.queue_service.enqueue(payload, delay_seconds=delay)
            logger.warning(
                f"Payment retry scheduled for payment_id={payment_id} "
                f"(attempt={attempt}/{self.max_retries}, delay={delay}s)."
            )
            return

        await self.queue_service.refresh_dedupe(
            payload,
            ttl_seconds=max(self.dedupe_ttl_seconds, DEAD_LETTER_DEDUPE_TTL_SECONDS),
        )
        await self.queue_service.push_dead_letter(payload, error_message)
        logger.error(
            f"Payment moved to DLQ for payment_id={payment_id} "
            f"after {attempt - 1} retries: {error_message}"
        )

    async def _notify_user(
        self,
        tg_id: int,
        subscription_updated_text: str,
        subscription_update_date_text: str,
        grant_tg_id_text: str | None,
        grant_referrer_id_text: str | None,
        referrer_tg_id: int | None,
        subscription_link_scope: str | None = PRODUCT_SCOPE_STANDARD,
    ) -> None:
        try:
            cabinet_url = None
            if self.telegram_link_service is not None:
                cabinet_url = await self.telegram_link_service.create_web_link(tg_id=int(tg_id))
            message_lines = [
                "✅ Оплата подтверждена.",
                "Доступ обновлен в веб-кабинете.",
            ]
            if subscription_update_date_text:
                message_lines.append("")
                message_lines.append(subscription_update_date_text)
            await bot.send_message(
                chat_id=tg_id,
                text="\n".join(message_lines),
                parse_mode="Markdown",
                reply_markup=build_profile_navigation_markup(cabinet_url=cabinet_url),
            )
            if grant_tg_id_text:
                await bot.send_message(chat_id=tg_id, text=grant_tg_id_text, parse_mode="Markdown")
            if grant_referrer_id_text and referrer_tg_id:
                await bot.send_message(
                    chat_id=referrer_tg_id,
                    text=grant_referrer_id_text,
                    parse_mode="Markdown",
                )
            if self.telegram_link_service is not None:
                refreshed_cabinet_url = await self.telegram_link_service.create_web_link(tg_id=int(tg_id))
            else:
                refreshed_cabinet_url = None
            await bot.send_photo(
                chat_id=tg_id,
                photo=PHOTO_menu,
                caption=messages.get_random_message("start_welcome_message"),
                reply_markup=build_main_menu_markup(cabinet_url=refreshed_cabinet_url),
            )
        except Exception as err:
            logger.error(f"Failed to send payment fulfillment notification to tg_id={tg_id}: {err}")

    def _dedupe_ttl_for_retry(self, delay_seconds: int) -> int:
        return max(
            self.dedupe_ttl_seconds,
            int(delay_seconds) + self.dedupe_ttl_seconds,
        )

    @staticmethod
    def _subscription_link_scope(payload: str) -> str | None:
        seed = get_plan_seed_by_legacy_payload(str(payload))
        if seed is None:
            return PRODUCT_SCOPE_STANDARD
        if seed.scope == PRODUCT_SCOPE_STANDARD and seed.entitlement_kind == ENTITLEMENT_KIND_TIME:
            return PRODUCT_SCOPE_STANDARD
        if seed.scope == PRODUCT_SCOPE_WHITELIST:
            return PRODUCT_SCOPE_WHITELIST
        return None
