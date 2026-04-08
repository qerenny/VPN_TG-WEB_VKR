from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from shared.config.config import BOT_NEWS_TG_LINK
from telegram_bot.shared.config.navigation import (
    FRONT_PROFILE,
    HELP,
    INSTRUCTIONS,
    MAIN_MENU,
    NEWS_CHANNEL,
    OPEN_CABINET,
    REFERRALS,
    SUBSCRIPTIONS,
    WHO_WE_ARE,
    WHO_WE_ARE_LINK,
)


def _build_cabinet_button(*, text: str, cabinet_url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, url=cabinet_url)


def build_profile_navigation_markup(*, cabinet_url: str | None = None) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    if cabinet_url:
        markup.add(_build_cabinet_button(text=OPEN_CABINET, cabinet_url=cabinet_url))
        return markup
    markup.add(InlineKeyboardButton(MAIN_MENU, callback_data="menu_start"))
    return markup


def build_main_menu_markup(*, cabinet_url: str | None = None) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    if cabinet_url:
        markup.add(_build_cabinet_button(text=FRONT_PROFILE, cabinet_url=cabinet_url))
    markup.add(InlineKeyboardButton(SUBSCRIPTIONS, callback_data="profile_subscriptions"))
    markup.add(InlineKeyboardButton(REFERRALS, callback_data="referrals_menu"))
    markup.add(
        InlineKeyboardButton(WHO_WE_ARE, url=WHO_WE_ARE_LINK),
        InlineKeyboardButton(NEWS_CHANNEL, url=BOT_NEWS_TG_LINK),
    )
    markup.add(
        InlineKeyboardButton(HELP, callback_data="menu_help"),
        InlineKeyboardButton(INSTRUCTIONS, callback_data="menu_instructions"),
    )
    return markup
