from datetime import datetime
from zoneinfo import ZoneInfo

from telebot.types import CallbackQuery

from shared.product_constants import PRODUCT_SCOPE_WHITELIST
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.presentation.start.start_handler import StartHandler
from telegram_bot.services.linking.telegram_link_service import TelegramLinkService
from telegram_bot.services.subscriptions.subscription_provisioning_service import (
    SubscriptionProvisioningService,
)
from telegram_bot.services.subscriptions.subscription_flow_service import (
    SubscriptionFlowService,
)
from telegram_bot.services.subscriptions.whitelist_traffic_service import (
    WhiteListTrafficService,
)
from telegram_bot.services.users.user_subscription_info_service import UserSubscriptionInfoService
from telegram_bot.shared.keyboards import build_profile_navigation_markup
from telegram_bot.shared.texts import messages
from telegram_bot.shared.utils.menu_rendering import (
    dismiss_loading_message,
    send_loading_message,
)


class SubscriptionTrialHandler:
    def __init__(
        self,
        subscription_flow_service: SubscriptionFlowService,
        user_subscription_info_service: UserSubscriptionInfoService,
        start_handler: StartHandler,
        telegram_link_service: TelegramLinkService,
        whitelist_traffic_service: WhiteListTrafficService | None = None,
        subscription_service: SubscriptionProvisioningService | None = None,
    ):
        self.subscription_flow_service = subscription_flow_service
        self.user_subscription_info_service = user_subscription_info_service
        self.start_handler = start_handler
        self.telegram_link_service = telegram_link_service
        self.whitelist_traffic_service = whitelist_traffic_service
        self.subscription_service = subscription_service

    async def grant_trial(self, call: CallbackQuery) -> None:
        """
        Handles all callback queries starting with 'sub_':
        either activates trial or shows error if already used.
        """
        tg_id = call.message.chat.id
        loading_message_id = await send_loading_message(tg_id, bot_client=bot)
        try:
            subscription_activated = await self.subscription_flow_service.activate_trial(tg_id)
            if subscription_activated:
                trial_expiration = await self.user_subscription_info_service.expiry_date_view(
                    "subscription_trial_expiration", tg_id
                )
                trial_subscription = f"{messages.get_random_message('subscription_trial')}"
                result_text = f"{trial_subscription}\n\n{trial_expiration}"
                await bot.send_message(chat_id=tg_id, text=result_text, parse_mode="Markdown")
                await self.start_handler.send_main_menu(call.message)
            else:
                await bot.send_message(
                    chat_id=tg_id,
                    text=messages.get_random_message("subscription_trial_is_used"),
                )
        finally:
            await dismiss_loading_message(tg_id, loading_message_id, bot_client=bot)

    async def grant_whitelist_trial(self, call: CallbackQuery) -> None:
        if self.whitelist_traffic_service is None:
            raise RuntimeError("WhiteList trial flow is not configured")

        tg_id = int(call.message.chat.id)
        loading_message_id = await send_loading_message(tg_id, bot_client=bot)
        try:
            result = await self.whitelist_traffic_service.activate_trial(tg_id=tg_id)
            if result.was_created:
                granted_gb = int(result.granted_bytes // (1024 * 1024 * 1024))
                expires_at_view = self._format_datetime(result.expires_at)
                text = (
                    f"{messages.get_random_message('subscription_whitelist_trial')}\n\n"
                    f"*Трафик:* `{granted_gb} GB`\n"
                    f"*Действует до:* `{expires_at_view}`"
                )
                cabinet_url = await self.telegram_link_service.create_web_link(tg_id=tg_id)
                await bot.send_message(
                    chat_id=tg_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=build_profile_navigation_markup(cabinet_url=cabinet_url) if cabinet_url else None,
                )
                await self.start_handler.send_main_menu(call.message)
                logger.info(f"Granted whitelist trial for tg_id={tg_id}")
                return

            await bot.send_message(
                chat_id=tg_id,
                text=messages.get_random_message("subscription_whitelist_trial_is_used"),
            )
            logger.info(f"Whitelist trial already used for tg_id={tg_id}")
        finally:
            await dismiss_loading_message(tg_id, loading_message_id, bot_client=bot)

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "без срока"
        moscow_value = value.astimezone(ZoneInfo("Europe/Moscow"))
        return moscow_value.replace(microsecond=0).strftime("%H:%M:%S %d-%m-%Y")
