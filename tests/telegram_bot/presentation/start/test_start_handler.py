from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from telebot.types import Chat
from telebot.types import User as TelebotUser

from telegram_bot.presentation.start.start_handler import StartHandler
from telegram_bot.shared.config.navigation import FRONT_PROFILE


class MockMessage:
    def __init__(self, chat_id: int, text: str = "/start"):
        self.chat = Chat(id=chat_id, type="private")
        self.message_id = 1
        self.from_user = TelebotUser(id=chat_id, is_bot=False, first_name="Test")
        self.text = text


def make_handler() -> StartHandler:
    return StartHandler(
        referral_start=AsyncMock(),
        user_register=AsyncMock(),
        repo=AsyncMock(),
        subscription_service=AsyncMock(),
        telegram_link_service=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_process_start_command_calls_dependencies(monkeypatch):
    message = MockMessage(chat_id=42, text="/start ref")
    handler = make_handler()
    handler.user_register.register_user.return_value = True

    send_main_menu = AsyncMock()
    monkeypatch.setattr(handler, "send_main_menu", send_main_menu)

    await handler.process_start_command(message)

    handler.user_register.register_user.assert_called_once_with(message)
    handler.referral_start.process_start_command.assert_called_once_with(
        message,
        ["/start", "ref"],
        user_created=True,
    )
    send_main_menu.assert_called_once_with(message)


@pytest.mark.asyncio
async def test_send_main_menu_builds_markup_without_subscription_link(monkeypatch):
    message = MockMessage(chat_id=100)

    with patch(
        "telegram_bot.presentation.start.start_handler.messages.get_random_message",
        return_value="hi",
    ):
        bot_mock = AsyncMock()
        monkeypatch.setattr("telegram_bot.presentation.start.start_handler.bot", bot_mock)
        handler = make_handler()
        handler.telegram_link_service.create_web_link.return_value = "https://example.com/app"

        await handler.send_main_menu(message)

    bot_mock.send_photo.assert_awaited_once()
    _, kwargs = bot_mock.send_photo.call_args
    assert kwargs["chat_id"] == 100
    assert kwargs["photo"]
    assert kwargs["caption"] == "hi"

    markup = kwargs["reply_markup"]
    rows = markup.keyboard
    assert rows[0][0].text == FRONT_PROFILE
    assert rows[0][0].url == "https://example.com/app"
    assert [button.callback_data for button in rows[1]] == ["profile_subscriptions"]
    assert [button.callback_data for button in rows[2]] == ["referrals_menu"]
    assert rows[3][0].text
    assert rows[3][1].url
    assert [button.callback_data for button in rows[4]] == ["menu_help", "menu_instructions"]


@pytest.mark.asyncio
async def test_send_main_menu_always_shows_profile_entrypoint(monkeypatch):
    message = MockMessage(chat_id=100)

    with patch(
        "telegram_bot.presentation.start.start_handler.messages.get_random_message",
        return_value="hi",
    ):
        bot_mock = AsyncMock()
        monkeypatch.setattr("telegram_bot.presentation.start.start_handler.bot", bot_mock)
        handler = make_handler()
        handler.telegram_link_service.create_web_link.return_value = "https://example.com/app"

        await handler.send_main_menu(message)

    _, kwargs = bot_mock.send_photo.call_args
    first_row = kwargs["reply_markup"].keyboard[0]
    assert first_row[0].text == FRONT_PROFILE
    assert first_row[0].url == "https://example.com/app"


@pytest.mark.asyncio
async def test_send_main_menu_can_render_without_cabinet_link(monkeypatch):
    message = MockMessage(chat_id=100)

    with patch(
        "telegram_bot.presentation.start.start_handler.messages.get_random_message",
        return_value="hi",
    ):
        bot_mock = AsyncMock()
        monkeypatch.setattr("telegram_bot.presentation.start.start_handler.bot", bot_mock)
        handler = make_handler()
        handler.telegram_link_service.create_web_link.return_value = None

        await handler.send_main_menu(message)

    _, kwargs = bot_mock.send_photo.call_args
    rows = kwargs["reply_markup"].keyboard
    assert [button.callback_data for button in rows[0]] == ["profile_subscriptions"]


@pytest.mark.asyncio
async def test_process_start_command_consumes_link_token_without_registration(monkeypatch):
    message = MockMessage(chat_id=42, text="/start link_token123")
    handler = make_handler()
    handler.telegram_link_service.consume_start_token.return_value = SimpleNamespace(
        status="linked",
        message="linked ok",
    )

    send_main_menu = AsyncMock()
    bot_mock = AsyncMock()
    monkeypatch.setattr(handler, "send_main_menu", send_main_menu)
    monkeypatch.setattr("telegram_bot.presentation.start.start_handler.bot", bot_mock)

    await handler.process_start_command(message)

    handler.telegram_link_service.consume_start_token.assert_awaited_once_with(
        tg_id=42,
        telegram_username=None,
        raw_token="token123",
    )
    handler.user_register.register_user.assert_not_called()
    handler.referral_start.process_start_command.assert_not_called()
    bot_mock.send_message.assert_awaited_once()
    send_main_menu.assert_awaited_once_with(message)
