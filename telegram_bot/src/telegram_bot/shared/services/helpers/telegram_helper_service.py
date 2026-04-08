from shared.utils.logging_utils import logger
from telegram_bot.bot import bot


class TelegramHelperService:
    async def remove_message(self, tg_id: int, msg_id: int) -> None:
        """
        Deletes a specific message in a Telegram chat.
        """
        logger.info(f"Removing message with ID {msg_id} for user {tg_id}.")
        await bot.delete_message(tg_id, msg_id)
