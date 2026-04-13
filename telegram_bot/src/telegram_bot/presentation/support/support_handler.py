from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from shared.config.config import PHOTO_help
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from shared.config.config import BOT_SUPPORT_TG_LINK
from telegram_bot.shared.keyboards import add_main_menu_button
from telegram_bot.shared.texts import messages
from telegram_bot.shared.utils.menu_rendering import render_photo_menu


class SupportHandler:
    async def show(self, call: CallbackQuery) -> None:
        """
        Sends a support message to the user with a return to main menu option.
        """
        chat_id = call.message.chat.id

        text = messages.get_random_message("support_welcome_message")
        user_code_text = messages.get_random_message("support_user_info").format(user_code=chat_id)
        
        text += f"\n\n{user_code_text}"
        markup = InlineKeyboardMarkup()
        if BOT_SUPPORT_TG_LINK:
            markup.add(
                InlineKeyboardButton(
                    text=messages.get_random_message("support_chat_link"),
                    url=BOT_SUPPORT_TG_LINK,
                )
            )
        add_main_menu_button(markup)

        await render_photo_menu(
            target=call,
            photo=PHOTO_help,
            caption=text,
            reply_markup=markup,
            parse_mode="Markdown",
            bot_client=bot,
        )
        logger.info(f"Support message sent to user tg_id={chat_id}.")
