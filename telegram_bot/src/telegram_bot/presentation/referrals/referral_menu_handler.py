from telebot import types

from shared.config.config import PHOTO_referral_program
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.services.referrals.referrals_stats_service import ReferralStatsService
from telegram_bot.shared.config.navigation import MAIN_MENU
from telegram_bot.shared.texts import messages
from telegram_bot.shared.utils.menu_rendering import render_photo_menu


class ReferralMenuHandler:
    def __init__(self, stats_service: ReferralStatsService):
        self.stats = stats_service
    async def show(self, call: types.CallbackQuery):
        """
        Displays the referral program menu with user's stats and buttons.
        """
        tg_id = call.message.chat.id

        stats = await self.stats.get_stats(tg_id)

        info_text = messages.get_random_message("referral_info").format(
            num_of_users=stats["invited"],
            paid_count=stats["paid_count"],
            days=stats["pending_days"],
            awaiting_paid_count=stats["awaiting_paid_count"],
            awaiting_bonus_days=stats["awaiting_bonus_days"],
        )

        welcome_text = messages.get_random_message("referrals_welcome_message") + "\n" + info_text
        referral_link_text = await self.stats.send_referral_link(tg_id)
        rules_text = await self.stats.send_rules(tg_id)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text=MAIN_MENU, callback_data="menu_start"))

        result = f"{welcome_text}\n\n{rules_text}\n\n{referral_link_text}"
        await render_photo_menu(
            target=call,
            photo=PHOTO_referral_program,
            caption=result,
            reply_markup=markup,
            parse_mode="Markdown",
            bot_client=bot,
        )
        logger.info(f"Referral menu displayed to tg_id={tg_id} with stats={stats}")
