from telebot.types import CallbackQuery

from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.presentation.payments.payment_command_handler import PaymentCommandHandler
from telegram_bot.presentation.subscriptions.subscription_menu_handler import SubscriptionMenuHandler
from telegram_bot.presentation.subscriptions.subscription_trial_handler import SubscriptionTrialHandler
from telegram_bot.presentation.subscriptions.subscription_news_channel_handler import SubscriptionNewsChannelHandler
from telegram_bot.shared.config.subscription_products import (
    MONTH1,
    MONTH3,
    MONTH6,
    WHITELIST15GB,
    WHITELIST35GB,
    WHITELIST80GB,
    YEAR1,
)


PAID_PRODUCTS = {
    "sub_month1": MONTH1,
    "sub_month3": MONTH3,
    "sub_month6": MONTH6,
    "sub_year1": YEAR1,
    "sub_whitelist15gb": WHITELIST15GB,
    "sub_whitelist35gb": WHITELIST35GB,
    "sub_whitelist80gb": WHITELIST80GB,
}
COMMERCE_DISABLED_CALLBACK_TEXT = "Оплата отключена"


def register_subscription_routes(
    payment_command_handler: PaymentCommandHandler,
    subscription_menu_handler: SubscriptionMenuHandler,
    subscription_trial_handler: SubscriptionTrialHandler,
    subscription_news_channel_handler: SubscriptionNewsChannelHandler,
    *,
    commerce_enabled: bool = True,
):
    @bot.callback_query_handler(func=lambda call: call.data == "profile_subscriptions")
    async def handle_show_subscriptions(call: CallbackQuery) -> None:
        await bot.answer_callback_query(call.id)
        await subscription_menu_handler.show_subscription_menu(call)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("sub_"))
    async def handle_subscription_choice(call: CallbackQuery) -> None:
        data = call.data

        if data == "sub_trial":
            await bot.answer_callback_query(call.id)
            decorated = subscription_news_channel_handler.check_news_channel_subscription(
                subscription_trial_handler.grant_trial
            )
            await decorated(call)
        elif data == "sub_check_news_channel":
            await subscription_news_channel_handler.handle_check_news_channel(call)
        elif data == "sub_news_channel_menu":
            await bot.answer_callback_query(call.id)
            await subscription_news_channel_handler.show_news_channel_menu(call)
        elif data == "sub_whitelist_menu":
            await bot.answer_callback_query(call.id)
            await subscription_menu_handler.show_whitelist_menu(call)
        elif data == "sub_whitelist_trial":
            await bot.answer_callback_query(call.id)
            decorated = subscription_news_channel_handler.check_news_channel_subscription(
                subscription_trial_handler.grant_whitelist_trial
            )
            await decorated(call)
        elif data in PAID_PRODUCTS:
            if not commerce_enabled:
                await bot.answer_callback_query(call.id, COMMERCE_DISABLED_CALLBACK_TEXT)
                return
            await bot.answer_callback_query(call.id)
            product = PAID_PRODUCTS[data]
            decorated = subscription_news_channel_handler.check_news_channel_subscription(
                lambda c: payment_command_handler.ask_payment_method(c, product)
            )
            await decorated(call)
