import asyncio
from typing import Any

from telebot import types

from shared.config.config import (
    REDIS_REMINDER_DEDUPE_TTL_SECONDS,
    REDIS_REMINDER_LOOKAHEAD_HOURS,
    REDIS_REMINDER_MAX_RETRIES,
    REDIS_REMINDER_RETRY_BASE_SECONDS,
    REDIS_REMINDER_SCAN_INTERVAL_SECONDS,
    REDIS_REMINDER_WORKER_POP_TIMEOUT_SECONDS,
)
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.logging_utils import logger, log_with_throttle
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.bot import bot
from telegram_bot.services.subscriptions.reminder_queue_service import (
    ReminderQueueService,
)
from telegram_bot.services.users.user_subscription_info_service import UserSubscriptionInfoService
from telegram_bot.shared.texts import messages


class SubscriptionReminderService:
    WORKER_ERROR_LOG_COOLDOWN_SECONDS = 300.0

    def __init__(
        self,
        repo: TelegramUserRepository,
        user_subscription_info_service: UserSubscriptionInfoService,
        timestamp: TimestampUtils,
        reminder_queue_service: ReminderQueueService,
        scan_interval_seconds: int = REDIS_REMINDER_SCAN_INTERVAL_SECONDS,
        lookahead_hours: int = REDIS_REMINDER_LOOKAHEAD_HOURS,
        retry_base_seconds: int = REDIS_REMINDER_RETRY_BASE_SECONDS,
        max_retries: int = REDIS_REMINDER_MAX_RETRIES,
        worker_pop_timeout_seconds: int = REDIS_REMINDER_WORKER_POP_TIMEOUT_SECONDS,
        dedupe_ttl_seconds: int = REDIS_REMINDER_DEDUPE_TTL_SECONDS,
    ):
        self.repo = repo
        self.user_subscription_info_service = user_subscription_info_service
        self.timestamp = timestamp
        self.reminder_queue_service = reminder_queue_service
        self.scan_interval_seconds = scan_interval_seconds
        self.lookahead_hours = lookahead_hours
        self.retry_base_seconds = retry_base_seconds
        self.max_retries = max_retries
        self.worker_pop_timeout_seconds = worker_pop_timeout_seconds
        self.dedupe_ttl_seconds = dedupe_ttl_seconds

    async def send_renewal_reminder(self, tg_id: int) -> None:
        """
        Sends a renewal reminder message with a subscription button.
        """
        text = await self.user_subscription_info_service.expiry_date_view("renewal_reminder", tg_id)

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                text=messages.get_random_message("renewal_update_sub_message"),
                callback_data="profile_subscriptions",
            )
        )

        await bot.send_message(chat_id=tg_id, text=text, parse_mode="Markdown", reply_markup=markup)

        logger.info(f"Sent renewal reminder to tg_id={tg_id}.")

    async def enqueue_expiring_users(self) -> int:
        now_ts = self.timestamp.current_timestamp()
        lookahead_ms = self.lookahead_hours * 60 * 60 * 1000
        max_expiry_ts = now_ts + lookahead_ms
        users = await self.repo.get_users_expiring_between(now_ts, max_expiry_ts)

        enqueued_count = 0
        for user in users:
            if user.expiration_date is None:
                continue

            payload = {
                "tg_id": user.tg_id,
                "expiration_date": user.expiration_date,
                "attempt": 0,
                "queued_at": now_ts,
            }
            created = await self.reminder_queue_service.enqueue_if_new(
                payload,
                dedupe_ttl_seconds=self.dedupe_ttl_seconds,
            )
            if created:
                enqueued_count += 1

        if enqueued_count:
            logger.info(f"Queued {enqueued_count} subscription reminders.")
        return enqueued_count

    async def run_scheduler(self) -> None:
        logger.info(
            "Subscription reminder scheduler started "
            f"(scan_interval={self.scan_interval_seconds}s, lookahead={self.lookahead_hours}h)."
        )
        while True:
            try:
                await self.enqueue_expiring_users()
            except Exception as err:
                log_with_throttle(
                    "ERROR",
                    f"subscription-reminder-scheduler:{type(err).__name__}:{str(err)}",
                    f"Failed to enqueue reminder tasks: {err}",
                    cooldown_seconds=self.WORKER_ERROR_LOG_COOLDOWN_SECONDS,
                )

            await asyncio.sleep(self.scan_interval_seconds)

    async def process_queue_once(self) -> bool:
        await self.reminder_queue_service.promote_delayed()
        payload = await self.reminder_queue_service.pop_ready(
            timeout_seconds=self.worker_pop_timeout_seconds
        )
        if payload is None:
            return False

        try:
            if await self._is_payload_stale(payload):
                logger.info(
                    "Skipping stale reminder task "
                    f"for tg_id={payload.get('tg_id')}, expiration={payload.get('expiration_date')}"
                )
                return True

            tg_id = int(payload["tg_id"])
            await self.send_renewal_reminder(tg_id)
            return True
        except Exception as err:
            await self._retry_or_dead_letter(payload, str(err))
            return True

    async def run_worker(self) -> None:
        logger.info("Subscription reminder worker started.")
        while True:
            try:
                await self.process_queue_once()
            except Exception as err:
                log_with_throttle(
                    "ERROR",
                    f"subscription-reminder-worker:{type(err).__name__}:{str(err)}",
                    f"Subscription reminder worker iteration failed: {err!r}",
                    cooldown_seconds=self.WORKER_ERROR_LOG_COOLDOWN_SECONDS,
                )
                await asyncio.sleep(1)

    async def shutdown(self) -> None:
        await self.reminder_queue_service.close()

    async def _is_payload_stale(self, payload: dict[str, Any]) -> bool:
        tg_id = payload.get("tg_id")
        expected_expiration = payload.get("expiration_date")
        if tg_id is None or expected_expiration is None:
            return True

        user = await self.repo.get(int(tg_id))
        if user is None or user.expiration_date is None:
            return True

        if int(user.expiration_date) != int(expected_expiration):
            return True

        now_ts = self.timestamp.current_timestamp()
        return int(user.expiration_date) <= now_ts

    async def _retry_or_dead_letter(self, payload: dict[str, Any], error_message: str) -> None:
        attempt = int(payload.get("attempt", 0)) + 1
        payload["attempt"] = attempt
        payload["last_error"] = error_message

        if attempt <= self.max_retries:
            delay = self.retry_base_seconds * (2 ** (attempt - 1))
            await self.reminder_queue_service.enqueue(payload, delay_seconds=delay)
            logger.warning(
                f"Reminder retry scheduled for tg_id={payload.get('tg_id')} "
                f"(attempt={attempt}/{self.max_retries}, delay={delay}s)."
            )
            return

        await self.reminder_queue_service.push_dead_letter(payload, error_message)
        logger.error(
            f"Reminder moved to DLQ for tg_id={payload.get('tg_id')} "
            f"after {attempt - 1} retries: {error_message}"
        )

    async def check_expiring_users(self):
        """
        Legacy single-run checker retained for compatibility/tests.
        """
        await asyncio.sleep(3540)  # Wait ~59 minutes between checks

        boundary_ts_minus_hour, boundary_ts = self.timestamp.get_timestamp_with_reminder_time()
        users = await self.repo.get_all()

        for user in users:
            try:
                tg_id = user.tg_id
                expiry_ts = user.expiration_date

                if expiry_ts is not None and boundary_ts_minus_hour < expiry_ts <= boundary_ts:
                    await self.send_renewal_reminder(tg_id)
            except Exception as e:
                logger.error(f"Failed to send reminder to user {user.tg_id}: {e}")
                continue
