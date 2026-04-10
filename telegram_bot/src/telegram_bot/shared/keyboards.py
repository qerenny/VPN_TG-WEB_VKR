from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from shared.config.config import BOT_INFO_CHANNEL_ENABLED, BOT_INFO_CHANNEL_TG_LINK
from shared.config.settings import get_effective_product_feature_settings
from telegram_bot.shared.config.navigation import (
    DOCS_MENU_ENABLED,
    FRONT_PROFILE,
    HELP,
    INSTRUCTIONS,
    MAIN_MENU,
    INFO_CHANNEL,
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


def build_main_menu_markup(
    *,
    cabinet_url: str | None = None,
    referrals_enabled: bool | None = None,
) -> InlineKeyboardMarkup:
    if referrals_enabled is None:
        referrals_enabled = get_effective_product_feature_settings().referrals_enabled

    markup = InlineKeyboardMarkup()
    if cabinet_url:
        markup.add(_build_cabinet_button(text=FRONT_PROFILE, cabinet_url=cabinet_url))
    markup.add(InlineKeyboardButton(SUBSCRIPTIONS, callback_data="profile_subscriptions"))
    if referrals_enabled:
        markup.add(InlineKeyboardButton(REFERRALS, callback_data="referrals_menu"))

    info_links: list[InlineKeyboardButton] = []
    if WHO_WE_ARE_LINK:
        info_links.append(InlineKeyboardButton(WHO_WE_ARE, url=WHO_WE_ARE_LINK))
    if BOT_INFO_CHANNEL_ENABLED:
        info_links.append(InlineKeyboardButton(INFO_CHANNEL, url=BOT_INFO_CHANNEL_TG_LINK))
    if info_links:
        markup.add(*info_links)

    action_buttons = [InlineKeyboardButton(HELP, callback_data="menu_help")]
    if DOCS_MENU_ENABLED:
        action_buttons.append(InlineKeyboardButton(INSTRUCTIONS, callback_data="menu_instructions"))
    markup.add(*action_buttons)
    return markup
