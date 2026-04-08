from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.presentation.subscriptions.subscription_menu_handler import SubscriptionMenuHandler
from telegram_bot.shared.config.navigation import WHITELIST_ACCESS
from telegram_bot.shared.config.subscription_products import TRIAL, WHITELIST15GB, WHITELIST_TRIAL


class MockCall:
    def __init__(self, tg_id=1):
        self.message = SimpleNamespace(chat=SimpleNamespace(id=tg_id))


@pytest.fixture
def handler():
    repo = AsyncMock()
    whitelist_traffic_service = AsyncMock()
    return SubscriptionMenuHandler(repo, whitelist_traffic_service=whitelist_traffic_service)


@pytest.fixture
def repo(handler):
    return handler.repo


@pytest.fixture
def whitelist_traffic_service(handler):
    return handler.whitelist_traffic_service


@pytest.fixture
def bot_mock(monkeypatch):
    bot = AsyncMock()
    monkeypatch.setattr("telegram_bot.presentation.subscriptions.subscription_menu_handler.bot", bot)
    return bot


@pytest.mark.asyncio
async def test_show_subscription_menu_with_trial(handler, repo, bot_mock):
    repo.get.return_value = SimpleNamespace(expiration_date=None, news_channel_date=None)
    call = MockCall(42)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="text"),
        patch("shared.config.config.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_subscription_menu(call)
    repo.get.assert_awaited_once_with(42)
    bot_mock.send_photo.assert_awaited_once()
    kwargs = bot_mock.send_photo.call_args.kwargs
    markup = kwargs["reply_markup"]
    texts = [btn.text for row in markup.keyboard for btn in row]
    assert TRIAL in texts
    assert WHITELIST_ACCESS in texts


@pytest.mark.asyncio
async def test_show_subscription_menu_without_trial(handler, repo, bot_mock):
    repo.get.return_value = SimpleNamespace(expiration_date=123, news_channel_date=None)
    call = MockCall(7)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="text"),
        patch("shared.config.config.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_subscription_menu(call)
    texts = [btn.text for row in bot_mock.send_photo.call_args.kwargs["reply_markup"].keyboard for btn in row]
    assert TRIAL not in texts
    assert WHITELIST_ACCESS in texts


@pytest.mark.asyncio
async def test_show_whitelist_menu_displays_whitelist_products(handler, whitelist_traffic_service, bot_mock):
    whitelist_traffic_service.has_used_trial.return_value = False
    call = MockCall(9)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="wl text"),
        patch("shared.config.config.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_whitelist_menu(call)

    kwargs = bot_mock.send_photo.call_args.kwargs
    assert "Условия трафика" in kwargs["caption"]
    assert "Трафик у `Белых списков` считается отдельно" in kwargs["caption"]
    assert "трафик суммируется" in kwargs["caption"]
    texts = [btn.text for row in kwargs["reply_markup"].keyboard for btn in row]
    assert WHITELIST_TRIAL in texts
    assert WHITELIST15GB["label"] in texts


@pytest.mark.asyncio
async def test_show_whitelist_menu_hides_trial_after_use(handler, whitelist_traffic_service, bot_mock):
    whitelist_traffic_service.has_used_trial.return_value = True

    call = MockCall(9)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="wl text"),
        patch("shared.config.config.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_whitelist_menu(call)

    texts = [
        btn.text
        for row in bot_mock.send_photo.call_args.kwargs["reply_markup"].keyboard
        for btn in row
    ]
    assert WHITELIST_TRIAL not in texts
    assert WHITELIST15GB["label"] in texts


@pytest.mark.asyncio
async def test_show_subscription_menu_repo_error(handler, repo, bot_mock):
    repo.get.side_effect = Exception("fail")
    call = MockCall(1)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="text"),
        patch("shared.config.config.PHOTO_subscriptions", "photo.png"),
    ):
        with pytest.raises(Exception, match="fail"):
            await handler.show_subscription_menu(call)
    repo.get.assert_awaited_once_with(1)
