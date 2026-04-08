from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.shared.config.navigation import EXPIRED, LESS_THAN_HOUR
from telegram_bot.shared.texts import messages


class UserSubscriptionInfoService:
    def __init__(self, repo: TelegramUserRepository, timestamp: TimestampUtils):
        self.repo = repo
        self.timestamp = timestamp
    async def get_expiration_ts(self, tg_id: int) -> int:
        """
        Retrieves the expiration timestamp for a user's subscription.
        """
        ts = await self.repo.get(tg_id)
        ts = ts.expiration_date
        logger.info(f"Expiration timestamp for tg_id={tg_id}: {ts}.")
        return ts
    async def get_expiration_str(self, tg_id: int, expiration_ts: int | None = None) -> str:
        """
        Converts the expiration timestamp to a formatted date string.
        """
        ts = expiration_ts if expiration_ts is not None else await self.get_expiration_ts(tg_id)
        date_str = (
            self.timestamp.timestamp_to_date(ts).replace(microsecond=0, tzinfo=None).strftime("%H:%M:%S %d-%m-%Y")
        )
        logger.info(f"Formatted expiration date for tg_id={tg_id}: {date_str}.")
        return date_str
    async def get_expiration_pretty(self, tg_id: int, expiration_ts: int | None = None) -> str:
        """
        Converts the expiration date to a human-readable format.
        """
        date_ts = expiration_ts if expiration_ts is not None else await self.get_expiration_ts(tg_id)
        date_diff = self.timestamp.calculate_time_difference(date_ts)
        if date_diff == EXPIRED:
            logger.info(f"User subscription expired for tg_id={tg_id}.")
            return messages.get_random_message("users_subs_ended")
        if date_diff == LESS_THAN_HOUR:
            logger.info(f"User subscription less than an hour for tg_id={tg_id}.")
            return messages.get_random_message("users_subs_less_than_hour")
        logger.info(f"User subscription valid for tg_id={tg_id}: {date_diff}.")
        return date_diff
    async def expiry_date_view(self, type_of_message: str, tg_id: int) -> str:
        """
        Builds a message showing the user's subscription expiration status.
        Includes time left and exact expiration date.
        """
        expiration_ts = await self.get_expiration_ts(tg_id)
        expiration_date = await self.get_expiration_str(tg_id, expiration_ts=expiration_ts)
        remaining = await self.get_expiration_pretty(tg_id, expiration_ts=expiration_ts)

        logger.info(
            f"Generating expiry date view for tg_id={tg_id}, type_of_message={type_of_message}, remains={remaining}, expires={expiration_date}"
        )

        return f"{messages.get_random_message(type_of_message)}\n" + messages.get_random_message(
            "expiry_date_view"
        ).format(remaining=remaining, expiration_date=expiration_date)
