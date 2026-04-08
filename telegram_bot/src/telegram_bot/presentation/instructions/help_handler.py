from telebot import types
from telebot.types import CallbackQuery, Message, WebAppInfo

from shared.config.config import PHOTO_instructions
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.shared.config.navigation import (
    FAQ,
    FAQ_LINK,
    INSTRUCTIONS_DEVICES,
    INSTRUCTIONS_DEVICES_LINK,
    MAIN_MENU,
)
from telegram_bot.shared.texts import messages
from telegram_bot.shared.utils.menu_rendering import render_photo_menu


class HelpHandler:
    async def show(self, target: Message | CallbackQuery) -> None:
        """
        Sends user platform instructions with inline buttons.
        """
        message = target.message if isinstance(target, CallbackQuery) else target
        chat_id = message.chat.id
        logger.info(f"User requested instructions. chat_id={chat_id}")

        text = messages.get_random_message("instructions_welcome_message")
        markup = types.InlineKeyboardMarkup()

        markup.row(types.InlineKeyboardButton(f"{FAQ}", web_app=WebAppInfo(FAQ_LINK)))
        markup.row(types.InlineKeyboardButton(f"{INSTRUCTIONS_DEVICES}", web_app=WebAppInfo(INSTRUCTIONS_DEVICES_LINK)))
        markup.add(types.InlineKeyboardButton(MAIN_MENU, callback_data="menu_start"))

        await render_photo_menu(
            target=target,
            photo=PHOTO_instructions,
            caption=text,
            reply_markup=markup,
            bot_client=bot,
        )
        logger.info(f"Instructions sent to user chat_id={chat_id}")  # <-- Added logging
