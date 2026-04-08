from telebot.types import CallbackQuery

from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.presentation.referrals.referral_menu_handler import ReferralMenuHandler


def register_referrals_routes(referral_menu_handler: ReferralMenuHandler):
    @bot.callback_query_handler(func=lambda call: call.data in ["referrals_menu", "referrals_link", "referrals_rules"])
    async def handle_referrals_callback(call: CallbackQuery):
        """
        Router for referral-related inline buttons.
        """
        await bot.answer_callback_query(call.id)

        if call.data == "referrals_menu":
            await referral_menu_handler.show(call)
