from telebot.types import CallbackQuery

from telegram_bot.bot import bot
from telegram_bot.presentation.payments.payment_command_handler import PaymentCommandHandler
from telegram_bot.shared.config.subscription_products import ALL_PAYMENT_PRODUCTS
from telegram_bot.shared.utils.menu_rendering import (
    dismiss_loading_message,
    send_loading_message,
)

PRODUCTS = ALL_PAYMENT_PRODUCTS


def register_payments_routes(
    payment_command_handler: PaymentCommandHandler,
):
    @bot.callback_query_handler(func=lambda call: call.data.startswith("pay_method:"))
    async def callback_choose_payment_method(call: CallbackQuery):
        await bot.answer_callback_query(call.id)
        parts = call.data.split(":")
        if len(parts) != 3:
            await bot.send_message(call.message.chat.id, "Неверный формат выбора оплаты.")
            return

        _, method, payload = parts
        product = ALL_PAYMENT_PRODUCTS.get(payload)
        if product is None:
            await bot.send_message(call.message.chat.id, "Ошибка: продукт не найден.")
            return

        loading_message_id = await send_loading_message(call.message.chat.id, bot_client=bot)
        try:
            await payment_command_handler.initiate_payment(call.message, product, method)
        finally:
            await dismiss_loading_message(call.message.chat.id, loading_message_id, bot_client=bot)
