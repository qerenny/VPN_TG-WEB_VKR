from telebot import types
from telebot.types import CallbackQuery

from shared.config.config import PHOTO_subscriptions
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.shared.config.navigation import (
    ACCESS_REQUEST,
    ACCESS_REQUEST_STATUS,
    TRAFFIC_LIMITED_ACCESS,
)
from telegram_bot.shared.keyboards import add_main_menu_button, add_subscription_navigation_buttons
from telegram_bot.shared.config.subscription_products import (
    MONTH1,
    MONTH3,
    MONTH6,
    TRIAL,
    TRAFFIC_LIMITED15GB,
    TRAFFIC_LIMITED35GB,
    TRAFFIC_LIMITED80GB,
    TRAFFIC_LIMITED_TRIAL,
    YEAR1,
)
from telegram_bot.shared.texts import messages
from telegram_bot.shared.utils.menu_rendering import render_photo_menu
from telegram_bot.services.subscriptions.traffic_limited_service import TrafficLimitedService


class SubscriptionMenuHandler:
    BLOCKED_ALERT_TEXT = "🚫 Аккаунт заблокирован."

    def __init__(
        self,
        repo: TelegramUserRepository,
        traffic_limited_service: TrafficLimitedService | None = None,
        commerce_enabled: bool = True,
        access_requests_enabled: bool = False,
        standard_config_enabled: bool = True,
        traffic_limited_config_enabled: bool = True,
    ):
        self.repo = repo
        self.traffic_limited_service = traffic_limited_service
        self.commerce_enabled = commerce_enabled
        self.access_requests_enabled = access_requests_enabled
        self.standard_config_enabled = standard_config_enabled
        self.traffic_limited_config_enabled = traffic_limited_config_enabled

    async def show_subscription_menu(self, call: CallbackQuery) -> None:
        """
        Shows subscription options with trial button if user not registered.
        """
        tg_id = call.message.chat.id
        if await self.repo.is_blocked(int(tg_id)):
            await bot.answer_callback_query(
                call.id,
                self.BLOCKED_ALERT_TEXT,
                show_alert=True,
            )
            return
        user = await self.repo.get(tg_id)
        user_expiry_date = user.expiration_date
        text = messages.get_random_message("subscription_info")
        text += f'\n\n{messages.get_random_message("subscription_select_subs")}'
        markup = types.InlineKeyboardMarkup()

        if self.standard_config_enabled and self.commerce_enabled and not user_expiry_date:
            markup.add(types.InlineKeyboardButton(text=TRIAL, callback_data="sub_trial"))

        if self.standard_config_enabled and self.commerce_enabled:
            markup.add(types.InlineKeyboardButton(MONTH1["label"], callback_data="sub_month1"),
                       types.InlineKeyboardButton(MONTH3["label"], callback_data="sub_month3"))
            markup.add(types.InlineKeyboardButton(MONTH6["label"], callback_data="sub_month6"),
                       types.InlineKeyboardButton(YEAR1["label"], callback_data="sub_year1"))
        if self.traffic_limited_config_enabled and self.commerce_enabled:
            markup.add(types.InlineKeyboardButton(TRAFFIC_LIMITED_ACCESS, callback_data="sub_traffic_limited_menu"))
        if self.access_requests_enabled:
            markup.add(
                types.InlineKeyboardButton(ACCESS_REQUEST, callback_data="sub_access_request"),
                types.InlineKeyboardButton(ACCESS_REQUEST_STATUS, callback_data="sub_access_request_status"),
            )
        add_main_menu_button(markup)

        await render_photo_menu(
            target=call,
            photo=PHOTO_subscriptions,
            caption=text,
            reply_markup=markup,
            parse_mode="Markdown",
            bot_client=bot,
        )
        logger.info(f"Subscription menu displayed for tg_id={tg_id}")

    async def show_traffic_limited_menu(self, call: CallbackQuery) -> None:
        tg_id = call.message.chat.id
        text = self._build_traffic_limited_purchase_text()
        markup = types.InlineKeyboardMarkup()
        if not self.traffic_limited_config_enabled:
            await bot.answer_callback_query(
                call.id,
                "Этот тип доступа сейчас недоступен.",
                show_alert=True,
            )
            return
        if self.commerce_enabled and await self._should_show_traffic_limited_trial(int(tg_id)):
            markup.add(
                types.InlineKeyboardButton(TRAFFIC_LIMITED_TRIAL, callback_data="sub_traffic_limited_trial")
            )
        if self.commerce_enabled:
            markup.add(
                types.InlineKeyboardButton(TRAFFIC_LIMITED15GB["label"], callback_data="sub_traffic_limited15gb"),
                types.InlineKeyboardButton(TRAFFIC_LIMITED35GB["label"], callback_data="sub_traffic_limited35gb"),
            )
            markup.add(
                types.InlineKeyboardButton(TRAFFIC_LIMITED80GB["label"], callback_data="sub_traffic_limited80gb")
            )
        add_subscription_navigation_buttons(markup)

        await render_photo_menu(
            target=call,
            photo=PHOTO_subscriptions,
            caption=text,
            reply_markup=markup,
            parse_mode="Markdown",
            bot_client=bot,
        )
        logger.info(f"Traffic-limited configuration menu displayed for tg_id={tg_id}")

    @staticmethod
    def _build_traffic_limited_purchase_text() -> str:
        return (
            f"{messages.get_random_message('subscription_traffic_limited_info')}\n\n"
            "*Как это работает*\n"
            "• Трафик считается отдельно от базовой конфигурации\n"
            "• Новый пакет добавляет трафик и продлевает срок\n"
            "• Когда трафик или срок закончится — нужен новый пакет\n\n"
            "💡 Не уверен, подойдёт ли? Попробуй пробную конфигурацию `2 GB`."
        )

    async def _should_show_traffic_limited_trial(self, tg_id: int) -> bool:
        if self.traffic_limited_service is None:
            return True
        return not await self.traffic_limited_service.has_used_trial(tg_id=int(tg_id))
