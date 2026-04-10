# users/presentation/profile_handler.py

from telebot.types import CallbackQuery

from shared.config.config import PHOTO_my_subscription
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.services.linking.telegram_link_service import TelegramLinkService
from telegram_bot.services.subscriptions.subscription_provisioning_service import SubscriptionProvisioningService
from telegram_bot.services.users.user_subscription_info_service import UserSubscriptionInfoService
from telegram_bot.shared.keyboards import build_profile_navigation_markup
from telegram_bot.shared.utils.menu_rendering import render_photo_menu


class ProfileHandler:
    def __init__(
        self,
        repo: TelegramUserRepository,
        user_subscription_info_service: UserSubscriptionInfoService,
        subscription_service: SubscriptionProvisioningService,
        telegram_link_service: TelegramLinkService,
    ):
        self.repo = repo
        self.user_subscription_info_service = user_subscription_info_service
        self.subscription_service = subscription_service
        self.telegram_link_service = telegram_link_service

    async def show(self, call: CallbackQuery) -> None:
        chat_id = call.message.chat.id
        cabinet_url = await self.telegram_link_service.create_web_link(tg_id=chat_id)

        caption = self._build_caption(cabinet_available=bool(cabinet_url))
        markup = build_profile_navigation_markup(cabinet_url=cabinet_url) if cabinet_url else None

        await render_photo_menu(
            target=call,
            photo=PHOTO_my_subscription,
            caption=caption,
            reply_markup=markup,
            parse_mode="Markdown",
            bot_client=bot,
        )
        logger.info(f"Profile menu shown for tg_id={chat_id}.")

    def _build_caption(self, *, cabinet_available: bool) -> str:
        if not cabinet_available:
            return (
                "*👤 Профиль*\n\n"
                "Кабинет готовится — скоро появится ссылка для входа."
            )
        return (
            "*👤 Профиль*\n\n"
            "Управляй доступом, заявками и настройками в кабинете."
        )
