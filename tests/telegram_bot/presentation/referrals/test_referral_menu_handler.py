from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from telebot import types

from telegram_bot.presentation.referrals.referral_menu_handler import ReferralMenuHandler
from telegram_bot.shared.config.navigation import MAIN_MENU


@pytest.fixture
def stats_service():
    return AsyncMock()


@pytest.fixture
def handler(stats_service):
    return ReferralMenuHandler(stats_service)


class FakeCall:
    def __init__(self, chat_id, data="referrals_menu", call_id="1"):
        self.id = call_id
        self.data = data
        self.message = SimpleNamespace(chat=SimpleNamespace(id=chat_id))
        self.from_user = SimpleNamespace(username="user")


@pytest.mark.asyncio
async def test_show_displays_menu(handler, stats_service):
    call = FakeCall(chat_id=42)

    stats_service.get_stats.return_value = {
        "invited": 2,
        "paid_count": 1,
        "pending_days": 5,
        "awaiting_paid_count": 1,
        "awaiting_bonus_days": 7,
    }
    stats_service.send_referral_link.return_value = "link"
    stats_service.send_rules.return_value = "rules"

    with (
        patch(
            "telegram_bot.presentation.referrals.referral_menu_handler.messages.get_random_message",
            side_effect=[
                "info {num_of_users} {paid_count} {days} {awaiting_paid_count} {awaiting_bonus_days}",
                "welcome",
            ],
        ) as mock_msg,
        patch(
            "telegram_bot.presentation.referrals.referral_menu_handler.PHOTO_referral_program",
            "photo",
        ),
        patch(
            "telegram_bot.presentation.referrals.referral_menu_handler.bot.send_photo",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await handler.show(call)

    info_text = "info 2 1 5 1 7"
    expected_caption = f"welcome\n{info_text}\n\nrules\n\nlink"

    mock_msg.assert_any_call("referral_info")
    mock_msg.assert_any_call("referrals_welcome_message")

    mock_send.assert_awaited_once()
    args, kwargs = mock_send.call_args
    assert kwargs["chat_id"] == 42
    assert kwargs["photo"] == "photo"
    assert kwargs["caption"] == expected_caption
    assert kwargs["parse_mode"] == "Markdown"

    markup = kwargs["reply_markup"]
    assert isinstance(markup, types.InlineKeyboardMarkup)
    assert markup.keyboard[0][0].text == MAIN_MENU
    assert markup.keyboard[0][0].callback_data == "menu_start"

    stats_service.get_stats.assert_awaited_once_with(42)
    stats_service.send_referral_link.assert_awaited_once_with(42)
    stats_service.send_rules.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_show_propagates_errors(handler, stats_service):
    call = FakeCall(chat_id=1)
    stats_service.get_stats.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await handler.show(call)
