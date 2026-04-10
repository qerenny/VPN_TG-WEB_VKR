from unittest.mock import AsyncMock

import pytest
from telebot.types import Chat
from telebot.types import User as TelebotUser

from telegram_bot.presentation.instructions.help_handler import HelpHandler


class MockMessage:
    def __init__(self, chat_id: int):
        self.chat = Chat(id=chat_id, type="private")
        self.message_id = 1
        self.from_user = TelebotUser(id=chat_id, is_bot=False, first_name="Test")


@pytest.mark.asyncio
async def test_show_renders_only_main_menu_when_docs_links_missing(monkeypatch):
    render_photo_menu = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.instructions.help_handler.render_photo_menu",
        render_photo_menu,
    )
    monkeypatch.setattr(
        "telegram_bot.presentation.instructions.help_handler.messages.get_random_message",
        lambda _: "help",
    )
    monkeypatch.setattr("telegram_bot.presentation.instructions.help_handler.FAQ_LINK", "")
    monkeypatch.setattr(
        "telegram_bot.presentation.instructions.help_handler.INSTRUCTIONS_DEVICES_LINK",
        "",
    )

    await HelpHandler().show(MockMessage(chat_id=42))

    render_photo_menu.assert_awaited_once()
    kwargs = render_photo_menu.await_args.kwargs
    assert "Дополнительные справочные материалы не настроены." in kwargs["caption"]
    rows = kwargs["reply_markup"].keyboard
    assert len(rows) == 1
    assert [button.callback_data for button in rows[0]] == ["menu_start"]


@pytest.mark.asyncio
async def test_show_renders_configured_docs_links(monkeypatch):
    render_photo_menu = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.instructions.help_handler.render_photo_menu",
        render_photo_menu,
    )
    monkeypatch.setattr(
        "telegram_bot.presentation.instructions.help_handler.messages.get_random_message",
        lambda _: "help",
    )
    monkeypatch.setattr(
        "telegram_bot.presentation.instructions.help_handler.FAQ_LINK",
        "https://example.com/faq",
    )
    monkeypatch.setattr(
        "telegram_bot.presentation.instructions.help_handler.INSTRUCTIONS_DEVICES_LINK",
        "https://example.com/devices",
    )

    await HelpHandler().show(MockMessage(chat_id=42))

    kwargs = render_photo_menu.await_args.kwargs
    rows = kwargs["reply_markup"].keyboard
    assert rows[0][0].web_app.url == "https://example.com/faq"
    assert rows[1][0].web_app.url == "https://example.com/devices"
    assert [button.callback_data for button in rows[2]] == ["menu_start"]
