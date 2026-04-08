from functools import wraps
from telebot import types
from telebot.types import CallbackQuery

from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.logging_utils import logger
from telegram_bot.services.subscriptions.subscription_flow_service import SubscriptionFlowService
# from telegram_bot.services.users.user_subscription_info_service import UserSubscriptionInfoService
# from telegram_bot.presentation.start.start_handler import StartHandler
from telegram_bot.bot import bot
from telegram_bot.shared.texts import messages
from telegram_bot.shared.config.navigation import (
    MAIN_MENU,
    NEWS_CHANNEL,
    NEWS_CHANNEL_SUBSCRIBED)
from telegram_bot.presentation.subscriptions.subscription_menu_handler import (
    SubscriptionMenuHandler,
)
from shared.config.config import BOT_NEWS_TG_LINK, BOT_NEWS_TG_ID

class SubscriptionNewsChannelHandler:
    def __init__(
        self,
        repo: TelegramUserRepository,
        subscription_flow_service: SubscriptionFlowService,
        subscription_menu_handler: SubscriptionMenuHandler,
    ):
        self.repo = repo
        self.subscription_flow_service = subscription_flow_service
        self.subscription_menu_handler = subscription_menu_handler


    def check_news_channel_subscription(self, func):
        """Decorator ensuring user subscribed to the news channel."""

        @wraps(func)
        async def wrapper(call: CallbackQuery, *args, **kwargs):
            tg_id = call.message.chat.id
            chat_member = await bot.get_chat_member(chat_id=BOT_NEWS_TG_ID, user_id=tg_id)
            if chat_member.status in {"left", "kicked"}:
                await self.show_news_channel_menu(call)
                return

            return await func(call, *args, **kwargs)

        return wrapper
        

            
        # bonus_added = await self.subscription_flow_service.activate_tg_news_channel_bonus(tg_id)

        # if bonus_added:
        #     expiration_key = (
        #         "subscription_updated_date_view" if user_expiry_date else "subscription_expiration"
        #     )
        #     expiration_text = await self.user_subscription_info_service.expiry_date_view(
        #         expiration_key, tg_id
        #     )
        #     bonus_message = messages.get_random_message("subscription_news_channel")
        #     result_text = f"{bonus_message}\n\n{expiration_text}"
        #     await bot.send_message(chat_id=tg_id, text=result_text, parse_mode="Markdown")
        #     await self.start_handler.send_main_menu(call.message)
        #     logger.info(f"User {tg_id} has been granted the news channel bonus.")
        # else:
        #     await bot.answer_callback_query(
        #         callback_query_id=call.id,
        #         text=messages.get_random_message(
        #             "subscription_news_channel_already_taken"
        #         ),
        #         show_alert=False,
        #     )
        #     logger.info(f"User {tg_id} already has the news channel bonus.")

        
    async def show_news_channel_menu(self, call: CallbackQuery) -> None:
        tg_id = call.message.chat.id
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        markup.add(types.InlineKeyboardButton(
            text=NEWS_CHANNEL,
            url=BOT_NEWS_TG_LINK
        ))
        
        markup.add(types.InlineKeyboardButton(
            text=NEWS_CHANNEL_SUBSCRIBED,
            callback_data="sub_check_news_channel"
        ))
        
        text = messages.get_random_message("subscription_news_channel_menu")
        await bot.send_message(
            chat_id=tg_id,
            text=text,
            reply_markup=markup,
            parse_mode="Markdown"        )

    async def handle_check_news_channel(self, call: CallbackQuery) -> None:
        """Checks subscription and shows appropriate menu or alert."""
        tg_id = call.message.chat.id
        chat_member = await bot.get_chat_member(chat_id=BOT_NEWS_TG_ID, user_id=tg_id)
        if chat_member.status in {"left", "kicked"}:
            await bot.answer_callback_query(
                callback_query_id=call.id,
                text=messages.get_random_message(
                    "subscription_news_channel_not_subscribed"
                ),
                show_alert=True,
            )
        else:
            await bot.answer_callback_query(call.id)
            await self.subscription_menu_handler.show_subscription_menu(call)
