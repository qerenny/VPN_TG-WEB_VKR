from telebot.types import Message

from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.services.referrals.referral_registration_service import (
    ReferralRegistrationService,
)
from telegram_bot.shared.texts import messages


class ReferralStartHandler:
    def __init__(self, registration_service: ReferralRegistrationService):
        self.registration_service = registration_service
    async def process_start_command(
        self,
        message: Message,
        referral_code: list[str],
        *,
        user_created: bool,
    ):
        """
        Processes /start with or without referral code and handles user registration.
        """
        tg_id = message.chat.id

        logger.info(f"Processing start command from user {tg_id}, referral_code={referral_code}")

        registered, status = await self.registration_service.register_user(
            tg_id,
            referral_code,
            user_created=user_created,
        )

        if status == "invalid_code":
            text = messages.get_random_message("referral_invalid_code")
            await bot.send_message(chat_id=tg_id, text=text)
            logger.info(f"Invalid referral code used: {referral_code}")

        elif status == "existing_user":
            text = messages.get_random_message("referral_existing_user")
            await bot.send_message(chat_id=tg_id, text=text)
            logger.info(f"Referral code rejected for existing user tg_id={tg_id}")

        elif status == "code_activated":
            text = messages.get_random_message("referral_code_activated")
            referrer_id = int(referral_code[1])
            ref_text = messages.get_random_message("referral_code_used")
            await bot.send_message(chat_id=tg_id, text=text, parse_mode="Markdown")
            await bot.send_message(chat_id=referrer_id, text=ref_text, parse_mode="Markdown")
            logger.info(f"Activated referral code for tg_id={tg_id}, referrer_id={referrer_id}")

        elif status == "code_updated":
            text = messages.get_random_message("referral_code_changed")
            await bot.send_message(chat_id=tg_id, text=text, parse_mode="Markdown")
            logger.info(f"Updated referral code for tg_id={tg_id}")

        logger.info(f"Referral start processed: tg_id={tg_id}, status={status}")
