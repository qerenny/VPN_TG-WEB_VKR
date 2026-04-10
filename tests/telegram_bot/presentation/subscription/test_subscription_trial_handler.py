from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

import pytest

from telegram_bot.presentation.subscriptions.subscription_trial_handler import SubscriptionTrialHandler


class MockCall:
    def __init__(self, tg_id=1):
        self.message = SimpleNamespace(chat=SimpleNamespace(id=tg_id))
        self.id = 55


@pytest.fixture
def handler():
    flow = AsyncMock()
    info = AsyncMock()
    start_handler = AsyncMock()
    telegram_link_service = AsyncMock()
    traffic_limited_service = AsyncMock()
    subscription_service = AsyncMock()
    return SubscriptionTrialHandler(
        flow,
        info,
        start_handler,
        telegram_link_service=telegram_link_service,
        traffic_limited_service=traffic_limited_service,
        subscription_service=subscription_service,
    )


@pytest.fixture
def flow(handler):
    return handler.subscription_flow_service


@pytest.fixture
def info(handler):
    return handler.user_subscription_info_service


@pytest.fixture
def start_handler(handler):
    return handler.start_handler


@pytest.fixture
def traffic_limited_service(handler):
    return handler.traffic_limited_service


@pytest.fixture
def telegram_link_service(handler):
    return handler.telegram_link_service


@pytest.fixture
def subscription_service(handler):
    return handler.subscription_service


@pytest.fixture
def bot_mock(monkeypatch):
    bot = AsyncMock()
    bot.send_message.return_value = SimpleNamespace(message_id=501)
    monkeypatch.setattr("telegram_bot.presentation.subscriptions.subscription_trial_handler.bot", bot)
    return bot


@pytest.mark.asyncio
async def test_grant_trial_success(handler, flow, info, start_handler, bot_mock):
    flow.activate_trial.return_value = "key"
    info.expiry_date_view.return_value = "expires"
    with patch("telegram_bot.shared.texts.messages.get_random_message", return_value="trial"):
        call = MockCall(10)
        await handler.grant_trial(call)
    assert bot_mock.send_message.await_count == 2
    text = bot_mock.send_message.await_args_list[1].kwargs["text"]
    assert "expires" in text and "trial" in text
    bot_mock.delete_message.assert_awaited_once_with(chat_id=10, message_id=501)
    start_handler.send_main_menu.assert_awaited_once_with(call.message)


@pytest.mark.asyncio
async def test_grant_trial_already_used(handler, flow, bot_mock):
    flow.activate_trial.return_value = None
    with patch("telegram_bot.shared.texts.messages.get_random_message", return_value="used"):
        await handler.grant_trial(MockCall(8))
    assert bot_mock.send_message.await_args_list[1].kwargs == {"chat_id": 8, "text": "used"}
    bot_mock.delete_message.assert_awaited_once_with(chat_id=8, message_id=501)


@pytest.mark.asyncio
async def test_grant_trial_error(handler, flow, bot_mock):
    flow.activate_trial.side_effect = Exception("boom")
    with patch("telegram_bot.shared.texts.messages.get_random_message", return_value="msg"):
        with pytest.raises(Exception, match="boom"):
            await handler.grant_trial(MockCall(1))


@pytest.mark.asyncio
async def test_grant_traffic_limited_trial_success(
    handler,
    traffic_limited_service,
    telegram_link_service,
    start_handler,
    bot_mock,
):
    traffic_limited_service.activate_trial.return_value = SimpleNamespace(
        granted_bytes=2 * 1024 * 1024 * 1024,
        expires_at=datetime(2026, 4, 2, 12, 0, 0, tzinfo=timezone.utc),
        was_created=True,
    )
    telegram_link_service.create_web_link.return_value = "https://example.com/app"

    with patch(
        "telegram_bot.shared.texts.messages.get_random_message",
        return_value="trial ok",
    ):
        call = MockCall(10)
        await handler.grant_traffic_limited_trial(call)

    traffic_limited_service.activate_trial.assert_awaited_once_with(tg_id=10)
    telegram_link_service.create_web_link.assert_awaited_once_with(tg_id=10)
    assert bot_mock.send_message.await_count == 2
    kwargs = bot_mock.send_message.await_args_list[1].kwargs
    assert "trial ok" in kwargs["text"]
    assert "2 GB" in kwargs["text"]
    assert kwargs["reply_markup"] is not None
    bot_mock.delete_message.assert_awaited_once_with(chat_id=10, message_id=501)
    start_handler.send_main_menu.assert_awaited_once_with(call.message)


@pytest.mark.asyncio
async def test_grant_traffic_limited_trial_already_used(
    handler,
    traffic_limited_service,
    bot_mock,
):
    traffic_limited_service.activate_trial.return_value = SimpleNamespace(
        was_created=False,
    )
    with patch(
        "telegram_bot.shared.texts.messages.get_random_message",
        return_value="wl used",
    ):
        await handler.grant_traffic_limited_trial(MockCall(8))

    assert bot_mock.send_message.await_args_list[1].kwargs == {"chat_id": 8, "text": "wl used"}
    bot_mock.delete_message.assert_awaited_once_with(chat_id=8, message_id=501)
