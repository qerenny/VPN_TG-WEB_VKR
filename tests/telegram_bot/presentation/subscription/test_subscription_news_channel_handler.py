from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.presentation.subscriptions.subscription_news_channel_handler import (
    SubscriptionNewsChannelHandler,
)


class MockCall:
    def __init__(self, tg_id=1):
        self.message = SimpleNamespace(chat=SimpleNamespace(id=tg_id))
        self.id = 55


class Member:
    def __init__(self, status="member"):
        self.status = status


@pytest.fixture
def handler():
    repo = AsyncMock()
    flow = AsyncMock()
    menu = AsyncMock()
    return SubscriptionNewsChannelHandler(repo, flow, menu)


@pytest.fixture
def bot_mock(monkeypatch):
    bot = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_news_channel_handler.bot",
        bot,
    )
    return bot


@pytest.mark.asyncio
async def test_check_news_channel_subscription_calls_wrapped_handler_for_member(
    handler, bot_mock
):
    wrapped = AsyncMock()
    bot_mock.get_chat_member.return_value = Member()

    decorated = handler.check_news_channel_subscription(wrapped)
    call = MockCall(10)

    await decorated(call)

    wrapped.assert_awaited_once_with(call)


@pytest.mark.asyncio
async def test_check_news_channel_subscription_shows_menu_for_unsubscribed_user(
    handler, bot_mock
):
    wrapped = AsyncMock()
    handler.show_news_channel_menu = AsyncMock()
    bot_mock.get_chat_member.return_value = Member("left")

    decorated = handler.check_news_channel_subscription(wrapped)
    call = MockCall(7)

    await decorated(call)

    wrapped.assert_not_awaited()
    handler.show_news_channel_menu.assert_awaited_once_with(call)


@pytest.mark.asyncio
async def test_show_news_channel_menu_sends_link_and_confirm_button(handler, bot_mock):
    with patch(
        "telegram_bot.shared.texts.messages.get_random_message",
        return_value="join channel",
    ):
        await handler.show_news_channel_menu(MockCall(3))

    bot_mock.send_message.assert_awaited_once()
    markup = bot_mock.send_message.call_args.kwargs["reply_markup"]
    buttons = [button for row in markup.keyboard for button in row]
    assert [button.callback_data for button in buttons if button.callback_data] == [
        "sub_check_news_channel"
    ]


@pytest.mark.asyncio
async def test_handle_check_news_channel_alerts_when_user_is_not_subscribed(handler, bot_mock):
    bot_mock.get_chat_member.return_value = Member("left")
    call = MockCall(5)

    with patch(
        "telegram_bot.shared.texts.messages.get_random_message",
        return_value="not subscribed",
    ):
        await handler.handle_check_news_channel(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(
        callback_query_id=55,
        text="not subscribed",
        show_alert=True,
    )
    handler.subscription_menu_handler.show_subscription_menu.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_check_news_channel_returns_to_menu_for_subscribed_user(
    handler, bot_mock
):
    bot_mock.get_chat_member.return_value = Member()
    call = MockCall(11)

    await handler.handle_check_news_channel(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    handler.subscription_menu_handler.show_subscription_menu.assert_awaited_once_with(call)
