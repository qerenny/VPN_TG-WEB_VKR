from telebot.types import CallbackQuery, Message

from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.presentation.instructions.help_handler import HelpHandler
from telegram_bot.presentation.start.start_handler import StartHandler
from telegram_bot.presentation.support.support_handler import SupportHandler
from telegram_bot.presentation.users.profile_handler import ProfileHandler


def register_start_routes(
    start: StartHandler, profile: ProfileHandler, support: SupportHandler, instructions: HelpHandler
):
    @bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
    async def handle_menu_callback(call: CallbackQuery) -> None:
        await bot.answer_callback_query(call.id)
        data = call.data

        match data:
            case "menu_profile":
                await profile.show(call)
            case "menu_help":
                await support.show(call)
            case "menu_instructions":
                await instructions.show(call)
            case "menu_start":
                await start.send_main_menu(call)

    @bot.message_handler(commands=["start"])
    async def handle_start(message: Message) -> None:
        await start.process_start_command(message)
