import asyncio

from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.presentation.instructions.help_handler import HelpHandler
from telegram_bot.services.subscriptions.subscription_provisioning_service import (
    SubscriptionProvisioningService,
)
from telegram_bot.services.users.user_subscription_info_service import UserSubscriptionInfoService
from telegram_bot.shared.config.subscription_products import DAY_3_TIMESTAMP
from telegram_bot.shared.texts import messages


class SubscriptionFlowService:
    _user_locks: dict[int, asyncio.Lock] = {}

    def __init__(
        self,
        repo: TelegramUserRepository,
        subscription_service: SubscriptionProvisioningService,
        instruction: HelpHandler,
        user_subscription_info_service: UserSubscriptionInfoService,
        timestamp: TimestampUtils,
    ):
        self.subscription_service = subscription_service
        self.repo = repo
        self.instruction = instruction
        self.user_subscription_info_service = user_subscription_info_service
        self.timestamp = timestamp

    @classmethod
    def _get_user_lock(cls, tg_id: int) -> asyncio.Lock:
        lock = cls._user_locks.get(tg_id)
        if lock is None:
            lock = asyncio.Lock()
            cls._user_locks[tg_id] = lock
        return lock

    async def set_tg_info_channel_date(self, tg_id: int) -> bool:
        """
        Marks informational channel confirmation for a user.
        If the user doesn't exist, creates one with the bonus.
        """
        user = await self.repo.get(tg_id)
        if not user:
            return None
        user_info_channel_date = user.info_channel_date

        if not user_info_channel_date:
            current_ts = self.timestamp.current_timestamp()
            await self.repo.set_info_channel_date(tg_id=tg_id, info_channel_date=current_ts)
            user.info_channel_date = current_ts
            return True
        return None
    async def activate_or_extend_subscription(self, tg_id: int, period: str) -> tuple[str, str]:
        async with self._get_user_lock(tg_id):
            user = await self.repo.get(tg_id)
            if not user:
                raise AttributeError("User not found")
            user_expiry_date = user.expiration_date

            await self.subscription_service.create_or_update_user(tg_id, period, user=user)

        if user_expiry_date:
            logger.info(f"Updating subscription for tg_id={tg_id}")
            subscription_updated_text = f"✅ {messages.get_random_message('subscription_updated')}"
            subscription_update_date_text = await self.user_subscription_info_service.expiry_date_view(
                "subscription_updated_date_view", tg_id
            )
            return subscription_updated_text, subscription_update_date_text
        else:
            logger.info(f"Creating new subscription for tg_id={tg_id}")
            subscription_updated_text = await self.user_subscription_info_service.expiry_date_view(
                "subscription_expiration", tg_id
            )
            subscription_update_date_text = messages.get_random_message("subscription_new_key")
            return subscription_updated_text, subscription_update_date_text
    async def activate_trial(self, tg_id: int) -> bool:
        """
        Starts a 3-day trial period for a user.
        If user doesn't exist, creates one with trial.
        """
        async with self._get_user_lock(tg_id):
            user = await self.repo.get(tg_id)
            if not user:
                raise AttributeError("User not found")
            user_expiry_date = user.expiration_date

            if not user_expiry_date:
                await self.subscription_service.create_or_update_user(
                    tg_id, DAY_3_TIMESTAMP, user=user
                )
                current_ts = self.timestamp.current_timestamp()
                await self.repo.set_trial_date(tg_id=tg_id, trial_date=current_ts)
                user.trial_date = current_ts
                return True
            return None
