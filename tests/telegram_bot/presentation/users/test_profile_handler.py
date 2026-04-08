from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.presentation.users.profile_handler import ProfileHandler
from telegram_bot.shared.config.navigation import (
    OPEN_CABINET,
)


class MockCall:
    def __init__(self, tg_id=1):
        self.message = SimpleNamespace(chat=SimpleNamespace(id=tg_id))


@pytest.fixture
def handler():
    return ProfileHandler(
        repo=AsyncMock(),
        user_subscription_info_service=AsyncMock(),
        subscription_service=AsyncMock(),
        telegram_link_service=AsyncMock(),
    )


@pytest.fixture
def bot_mock(monkeypatch):
    bot = AsyncMock()
    monkeypatch.setattr("telegram_bot.presentation.users.profile_handler.bot", bot)
    monkeypatch.setattr("telegram_bot.presentation.users.profile_handler.PHOTO_my_subscription", "photo.png")
    return bot


@pytest.mark.asyncio
async def test_show_profile_sends_only_web_cabinet_button(handler, bot_mock):
    call = MockCall(42)
    handler.telegram_link_service.create_web_link.return_value = "https://example.com/app"

    await handler.show(call)

    bot_mock.send_photo.assert_awaited_once()

    kwargs = bot_mock.send_photo.call_args.kwargs
    assert "web-кабинете" in kwargs["caption"]
    texts = [btn.text for row in kwargs["reply_markup"].keyboard for btn in row]
    assert OPEN_CABINET in texts
    assert texts == [OPEN_CABINET]
    assert kwargs["reply_markup"].keyboard[0][0].url == "https://example.com/app"


@pytest.mark.asyncio
async def test_show_profile_without_cabinet_link_sends_no_markup(handler, bot_mock):
    call = MockCall(77)
    handler.telegram_link_service.create_web_link.return_value = None

    await handler.show(call)

    kwargs = bot_mock.send_photo.call_args.kwargs
    assert kwargs["reply_markup"] is None
