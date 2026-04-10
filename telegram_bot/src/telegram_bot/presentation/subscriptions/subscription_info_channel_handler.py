from functools import wraps
from telebot import types
from telebot.types import CallbackQuery

from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.logging_utils import logger
from telegram_bot.services.subscriptions.subscription_flow_service import SubscriptionFlowService
from telegram_bot.bot import bot
from telegram_bot.shared.texts import messages
from telegram_bot.shared.config.navigation import (
    INFO_CHANNEL,
    INFO_CHANNEL_CONFIRMED,
)
from telegram_bot.presentation.subscriptions.subscription_menu_handler import (
    SubscriptionMenuHandler,
)
from shared.config.config import BOT_INFO_CHANNEL_ENABLED, BOT_INFO_CHANNEL_TG_LINK, BOT_INFO_CHANNEL_TG_ID


class SubscriptionInfoChannelHandler:
    def __init__(
        self,
        repo: TelegramUserRepository,
        subscription_flow_service: SubscriptionFlowService,
        subscription_menu_handler: SubscriptionMenuHandler,
    ):
        self.repo = repo
        self.subscription_flow_service = subscription_flow_service
        self.subscription_menu_handler = subscription_menu_handler

    @staticmethod
    def is_enabled() -> bool:
        return BOT_INFO_CHANNEL_ENABLED

    def check_info_channel_subscription(self, func):
        """Decorator ensuring user subscribed to the informational channel."""

        @wraps(func)
        async def wrapper(call: CallbackQuery, *args, **kwargs):
            if not self.is_enabled():
                return await func(call, *args, **kwargs)
            tg_id = call.message.chat.id
            chat_member = await bot.get_chat_member(chat_id=BOT_INFO_CHANNEL_TG_ID, user_id=tg_id)
            if chat_member.status in {"left", "kicked"}:
                await self.show_info_channel_menu(call)
                return

            return await func(call, *args, **kwargs)

        return wrapper

    async def show_info_channel_menu(self, call: CallbackQuery) -> None:
        if not self.is_enabled():
            await bot.answer_callback_query(call.id)
            await self.subscription_menu_handler.show_subscription_menu(call)
            return

        tg_id = call.message.chat.id

        markup = types.InlineKeyboardMarkup(row_width=1)

        markup.add(types.InlineKeyboardButton(
            text=INFO_CHANNEL,
            url=BOT_INFO_CHANNEL_TG_LINK
        ))

        markup.add(types.InlineKeyboardButton(
            text=INFO_CHANNEL_CONFIRMED,
            callback_data="sub_check_info_channel"
        ))

        text = messages.get_random_message("subscription_info_channel_menu")
        await bot.send_message(
            chat_id=tg_id,
            text=text,
            reply_markup=markup,
            parse_mode="Markdown",
        )

    async def handle_check_info_channel(self, call: CallbackQuery) -> None:
        """Checks subscription and shows appropriate menu or alert."""
        if not self.is_enabled():
            await bot.answer_callback_query(call.id)
            await self.subscription_menu_handler.show_subscription_menu(call)
            return
        tg_id = call.message.chat.id
        chat_member = await bot.get_chat_member(chat_id=BOT_INFO_CHANNEL_TG_ID, user_id=tg_id)
        if chat_member.status in {"left", "kicked"}:
            await bot.answer_callback_query(
                callback_query_id=call.id,
                text=messages.get_random_message(
                    "subscription_info_channel_not_subscribed"
                ),
                show_alert=True,
            )
        else:
            await bot.answer_callback_query(call.id)
            await self.subscription_menu_handler.show_subscription_menu(call)
