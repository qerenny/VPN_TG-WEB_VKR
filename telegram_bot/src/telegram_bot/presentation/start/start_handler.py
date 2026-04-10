### start/presentation/command_handler.py

from telebot.types import CallbackQuery, Message

from shared.config.config import PHOTO_menu
from shared.utils.logging_utils import logger
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from telegram_bot.bot import bot
from telegram_bot.presentation.referrals.referral_start_handler import ReferralStartHandler
from telegram_bot.services.linking.telegram_link_service import TelegramLinkService
from telegram_bot.services.users.user_registration_service import UserRegistrationService
from telegram_bot.services.subscriptions.subscription_provisioning_service import (
    SubscriptionProvisioningService,
)
from telegram_bot.shared.keyboards import build_main_menu_markup
from telegram_bot.shared.texts import messages
from telegram_bot.shared.utils.menu_rendering import render_photo_menu


class StartHandler:
    BLOCKED_TEXT = "🚫 Аккаунт заблокирован. Доступ временно закрыт."

    def __init__(
        self,
        referral_start: ReferralStartHandler,
        user_register: UserRegistrationService,
        repo: TelegramUserRepository,
        subscription_service: SubscriptionProvisioningService,
        telegram_link_service: TelegramLinkService,
        referrals_enabled: bool = True,
    ):
        self.repo = repo
        self.subscription_service = subscription_service
        self.referral_start = referral_start
        self.user_register = user_register
        self.telegram_link_service = telegram_link_service
        self.referrals_enabled = referrals_enabled
    async def process_start_command(self, message: Message) -> None:
        tg_id = message.chat.id
        referral_code = message.text.split()

        logger.info(f"Processing /start command with referral_code: {referral_code} for chat_id={tg_id}")

        start_arg = referral_code[1] if len(referral_code) > 1 else ""
        if start_arg.startswith("link_"):
            result = await self.telegram_link_service.consume_start_token(
                tg_id=int(tg_id),
                telegram_username=message.chat.username,
                raw_token=str(start_arg.removeprefix("link_")),
            )
            await bot.send_message(chat_id=tg_id, text=result.message)
            if result.status == "linked" and not await self.repo.is_blocked(int(tg_id)):
                await self.send_main_menu(message, force_new=True)
            return

        user_created = await self.user_register.register_user(message)
        if await self.repo.is_blocked(int(tg_id)):
            await bot.send_message(chat_id=tg_id, text=self.BLOCKED_TEXT)
            return
        if self.referrals_enabled:
            await self.referral_start.process_start_command(
                message,
                referral_code,
                user_created=user_created,
            )
            logger.info(f"Referral code processing complete for chat_id={tg_id}")

        await self.send_main_menu(message, force_new=True)
    async def send_main_menu(self, target: Message | CallbackQuery, *, force_new: bool = False) -> None:
        message = target.message if isinstance(target, CallbackQuery) else target
        tg_id = message.chat.id
        text = messages.get_random_message("start_welcome_message")
        cabinet_url = await self.telegram_link_service.create_web_link(tg_id=int(tg_id))
        markup = build_main_menu_markup(
            cabinet_url=cabinet_url,
            referrals_enabled=self.referrals_enabled,
        )
        await render_photo_menu(
            target=target,
            photo=PHOTO_menu,
            caption=text,
            reply_markup=markup,
            force_new=force_new,
            bot_client=bot,
        )
