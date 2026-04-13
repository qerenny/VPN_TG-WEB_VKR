from telebot.types import Message

from telegram_bot.bot import bot
from telegram_bot.presentation.subscriptions.subscription_promo_handler import SubscriptionPromoHandler


def register_promo_routes(promo_handler: SubscriptionPromoHandler):
    @bot.message_handler(commands=["promo"])
    async def handle_promo_command(message: Message) -> None:
        await promo_handler.activate_promo(message)
