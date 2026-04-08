from telebot.types import Message

from telegram_bot.bot import bot
from telegram_bot.presentation.admin.command_handler import AdminCommandHandler


def register_admin_routes(admin_command_handler: AdminCommandHandler):
    @bot.message_handler(commands=["admin_panel"])
    async def handle_admin_panel(message: Message):
        await admin_command_handler.show_admin_panel(message)

    @bot.message_handler(commands=["upload_photos"])
    async def handle_upload_photos(message: Message):
        await admin_command_handler.upload_photos(message)

    @bot.message_handler(commands=["show_photos"])
    async def handle_show_photos(message: Message):
        await admin_command_handler.show_photos(message)

    @bot.message_handler(commands=["retry_payment_dlq"])
    async def handle_retry_payment_dlq(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 2:
            try:
                limit = int(parts[1])
            except ValueError:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text="Использование: /retry_payment_dlq [limit]",
                )
                return
        else:
            limit = 100

        await admin_command_handler.retry_payment_dlq(
            chat_id=message.chat.id,
            limit=limit,
        )

    # @bot_fun.message_handler(commands=['message'])
    # async def handle_broadcast(message: Message):
    #     await admin.broadcast_to_all(message)
