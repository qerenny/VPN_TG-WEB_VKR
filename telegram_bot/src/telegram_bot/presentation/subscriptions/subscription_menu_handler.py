from telebot import types
from telebot.types import CallbackQuery

from shared.config.config import PHOTO_subscriptions
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.shared.config.navigation import (
    BACK_TO_SUBSCRIPTIONS,
    MAIN_MENU,
    WHITELIST_ACCESS,
    NEWS_CHANNEL_SUBSCRIBED
)
from telegram_bot.shared.config.subscription_products import (
    MONTH1,
    MONTH3,
    MONTH6,
    TRIAL,
    WHITELIST15GB,
    WHITELIST35GB,
    WHITELIST80GB,
    WHITELIST_TRIAL,
    YEAR1,
)
from telegram_bot.shared.texts import messages
from telegram_bot.shared.utils.menu_rendering import render_photo_menu
from telegram_bot.services.subscriptions.whitelist_traffic_service import WhiteListTrafficService


class SubscriptionMenuHandler:
    def __init__(
        self,
        repo: TelegramUserRepository,
        whitelist_traffic_service: WhiteListTrafficService | None = None,
        commerce_enabled: bool = True,
        traffic_limited_config_enabled: bool = True,
    ):
        self.repo = repo
        self.whitelist_traffic_service = whitelist_traffic_service
        self.commerce_enabled = commerce_enabled
        self.traffic_limited_config_enabled = traffic_limited_config_enabled

    async def show_subscription_menu(self, call: CallbackQuery) -> None:
        """
        Shows subscription options with trial button if user not registered.
        """
        tg_id = call.message.chat.id
        user = await self.repo.get(tg_id)
        user_expiry_date = user.expiration_date
        text = messages.get_random_message("subscription_info")
        text += f'\n\n{messages.get_random_message("subscription_select_subs")}'
        markup = types.InlineKeyboardMarkup()

        if not user_expiry_date:
            markup.add(types.InlineKeyboardButton(text=TRIAL, callback_data="sub_trial"))
        # if not user_news_channel_date:
        #     markup.add(types.InlineKeyboardButton(
        #         text=NEWS_CHANNEL_BONUS,
        #         callback_data="sub_news_channel_menu"
        #     ))

        if self.commerce_enabled:
            markup.add(types.InlineKeyboardButton(MONTH1["label"], callback_data="sub_month1"),
                       types.InlineKeyboardButton(MONTH3["label"], callback_data="sub_month3"))
            markup.add(types.InlineKeyboardButton(MONTH6["label"], callback_data="sub_month6"),
                       types.InlineKeyboardButton(YEAR1["label"], callback_data="sub_year1"))
        if self.traffic_limited_config_enabled:
            markup.add(types.InlineKeyboardButton(WHITELIST_ACCESS, callback_data="sub_whitelist_menu"))
        markup.add(types.InlineKeyboardButton(MAIN_MENU, callback_data="menu_start"))

        await render_photo_menu(
            target=call,
            photo=PHOTO_subscriptions,
            caption=text,
            reply_markup=markup,
            parse_mode="Markdown",
            bot_client=bot,
        )
        logger.info(f"Subscription menu displayed for tg_id={tg_id}")

    async def show_whitelist_menu(self, call: CallbackQuery) -> None:
        tg_id = call.message.chat.id
        text = self._build_whitelist_purchase_text()
        markup = types.InlineKeyboardMarkup()
        if not self.traffic_limited_config_enabled:
            await bot.answer_callback_query(
                call.id,
                "Конфигурации с лимитом трафика отключены.",
                show_alert=True,
            )
            return
        if await self._should_show_whitelist_trial(int(tg_id)):
            markup.add(
                types.InlineKeyboardButton(WHITELIST_TRIAL, callback_data="sub_whitelist_trial")
            )
        if self.commerce_enabled:
            markup.add(
                types.InlineKeyboardButton(WHITELIST15GB["label"], callback_data="sub_whitelist15gb"),
                types.InlineKeyboardButton(WHITELIST35GB["label"], callback_data="sub_whitelist35gb"),
            )
            markup.add(
                types.InlineKeyboardButton(WHITELIST80GB["label"], callback_data="sub_whitelist80gb")
            )
        markup.add(
            types.InlineKeyboardButton(BACK_TO_SUBSCRIPTIONS, callback_data="profile_subscriptions")
        )
        markup.add(types.InlineKeyboardButton(MAIN_MENU, callback_data="menu_start"))

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
    def _build_whitelist_purchase_text() -> str:
        return (
            f"{messages.get_random_message('subscription_whitelist_info')}\n\n"
            "*Условия трафика*\n"
            "Трафик у этой конфигурации считается отдельно от базовой конфигурации.\n"
            "При выдаче нового пакета трафик суммируется, а срок доступа продлевается от текущей активной даты.\n"
            "После окончания трафика или срока доступ по этому контуру останавливается до выдачи нового пакета.\n"
            "Если доступ не работает в вашей сети, сначала проверьте пробную конфигурацию `2 GB`, затем обратитесь в поддержку."
        )

    async def _should_show_whitelist_trial(self, tg_id: int) -> bool:
        if self.whitelist_traffic_service is None:
            return True
        return not await self.whitelist_traffic_service.has_used_trial(tg_id=int(tg_id))
