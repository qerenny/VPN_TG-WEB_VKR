from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.presentation.subscriptions.subscription_menu_handler import SubscriptionMenuHandler
from telegram_bot.shared.config.navigation import ACCESS_REQUEST, ACCESS_REQUEST_STATUS, TRAFFIC_LIMITED_ACCESS
from telegram_bot.shared.config.subscription_products import TRIAL, TRAFFIC_LIMITED15GB, TRAFFIC_LIMITED_TRIAL
from telegram_bot.shared.utils import menu_rendering


class MockCall:
    def __init__(self, tg_id=1):
        self.id = f"cb-{tg_id}"
        menu_rendering._CHAT_MENU_MESSAGE_IDS.pop(tg_id, None)
        self.message = SimpleNamespace(chat=SimpleNamespace(id=tg_id))


@pytest.fixture
def handler():
    repo = AsyncMock()
    repo.is_blocked = AsyncMock(return_value=False)
    traffic_limited_service = AsyncMock()
    return SubscriptionMenuHandler(repo, traffic_limited_service=traffic_limited_service)


@pytest.fixture
def repo(handler):
    return handler.repo


@pytest.fixture
def traffic_limited_service(handler):
    return handler.traffic_limited_service


@pytest.fixture
def bot_mock(monkeypatch):
    bot = AsyncMock()
    monkeypatch.setattr("telegram_bot.presentation.subscriptions.subscription_menu_handler.bot", bot)
    return bot


@pytest.mark.asyncio
async def test_show_subscription_menu_with_trial(handler, repo, bot_mock):
    repo.get.return_value = SimpleNamespace(expiration_date=None, info_channel_date=None)
    call = MockCall(42)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="text"),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_subscription_menu(call)
    repo.get.assert_awaited_once_with(42)
    bot_mock.send_photo.assert_awaited_once()
    kwargs = bot_mock.send_photo.call_args.kwargs
    markup = kwargs["reply_markup"]
    texts = [btn.text for row in markup.keyboard for btn in row]
    assert TRIAL in texts
    assert TRAFFIC_LIMITED_ACCESS in texts


@pytest.mark.asyncio
async def test_show_subscription_menu_hides_trial_when_commerce_disabled(repo, bot_mock):
    repo.is_blocked = AsyncMock(return_value=False)
    handler = SubscriptionMenuHandler(
        repo,
        traffic_limited_service=AsyncMock(),
        commerce_enabled=False,
        access_requests_enabled=True,
    )
    repo.get.return_value = SimpleNamespace(expiration_date=None, info_channel_date=None)
    call = MockCall(42)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="text"),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_subscription_menu(call)
    texts = [btn.text for row in bot_mock.send_photo.call_args.kwargs["reply_markup"].keyboard for btn in row]
    assert TRIAL not in texts
    assert ACCESS_REQUEST in texts
    assert TRAFFIC_LIMITED_ACCESS not in texts


@pytest.mark.asyncio
async def test_show_subscription_menu_without_trial(handler, repo, bot_mock):
    repo.get.return_value = SimpleNamespace(expiration_date=123, info_channel_date=None)
    call = MockCall(7)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="text"),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_subscription_menu(call)
    texts = [btn.text for row in bot_mock.send_photo.call_args.kwargs["reply_markup"].keyboard for btn in row]
    assert TRIAL not in texts
    assert TRAFFIC_LIMITED_ACCESS in texts


@pytest.mark.asyncio
async def test_show_subscription_menu_hides_standard_actions_when_standard_module_disabled(repo, bot_mock):
    repo.is_blocked = AsyncMock(return_value=False)
    handler = SubscriptionMenuHandler(
        repo,
        traffic_limited_service=AsyncMock(),
        standard_config_enabled=False,
        traffic_limited_config_enabled=True,
    )
    repo.get.return_value = SimpleNamespace(expiration_date=None, info_channel_date=None)
    call = MockCall(7)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="text"),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_subscription_menu(call)
    texts = [btn.text for row in bot_mock.send_photo.call_args.kwargs["reply_markup"].keyboard for btn in row]
    assert TRIAL not in texts
    assert TRAFFIC_LIMITED_ACCESS in texts


@pytest.mark.asyncio
async def test_show_subscription_menu_hides_traffic_limited_actions_when_module_disabled(repo, bot_mock):
    repo.is_blocked = AsyncMock(return_value=False)
    handler = SubscriptionMenuHandler(
        repo,
        traffic_limited_service=AsyncMock(),
        standard_config_enabled=True,
        traffic_limited_config_enabled=False,
    )
    repo.get.return_value = SimpleNamespace(expiration_date=None, info_channel_date=None)
    call = MockCall(7)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="text"),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_subscription_menu(call)
    texts = [btn.text for row in bot_mock.send_photo.call_args.kwargs["reply_markup"].keyboard for btn in row]
    assert TRIAL in texts
    assert TRAFFIC_LIMITED_ACCESS not in texts


@pytest.mark.asyncio
async def test_show_subscription_menu_displays_access_request_buttons_when_enabled(repo, bot_mock):
    repo.is_blocked = AsyncMock(return_value=False)
    handler = SubscriptionMenuHandler(
        repo,
        traffic_limited_service=AsyncMock(),
        access_requests_enabled=True,
    )
    repo.get.return_value = SimpleNamespace(expiration_date=None, info_channel_date=None)
    call = MockCall(7)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", side_effect=lambda key, **_: key),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_subscription_menu(call)
    texts = [btn.text for row in bot_mock.send_photo.call_args.kwargs["reply_markup"].keyboard for btn in row]
    assert ACCESS_REQUEST in texts
    assert ACCESS_REQUEST_STATUS in texts


@pytest.mark.asyncio
async def test_show_traffic_limited_menu_displays_traffic_limited_products(handler, traffic_limited_service, bot_mock):
    traffic_limited_service.has_used_trial.return_value = False
    call = MockCall(9)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="wl text"),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_traffic_limited_menu(call)

    kwargs = bot_mock.send_photo.call_args.kwargs
    assert "Условия трафика" in kwargs["caption"]
    assert "Трафик у этой конфигурации считается отдельно" in kwargs["caption"]
    assert "трафик суммируется" in kwargs["caption"]
    texts = [btn.text for row in kwargs["reply_markup"].keyboard for btn in row]
    assert TRAFFIC_LIMITED_TRIAL in texts
    assert TRAFFIC_LIMITED15GB["label"] in texts


@pytest.mark.asyncio
async def test_show_traffic_limited_menu_hides_trial_after_use(handler, traffic_limited_service, bot_mock):
    traffic_limited_service.has_used_trial.return_value = True

    call = MockCall(9)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="wl text"),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_traffic_limited_menu(call)

    texts = [
        btn.text
        for row in bot_mock.send_photo.call_args.kwargs["reply_markup"].keyboard
        for btn in row
    ]
    assert TRAFFIC_LIMITED_TRIAL not in texts
    assert TRAFFIC_LIMITED15GB["label"] in texts


@pytest.mark.asyncio
async def test_show_traffic_limited_menu_hides_trial_when_commerce_disabled(traffic_limited_service, bot_mock):
    repo = AsyncMock()
    repo.is_blocked = AsyncMock(return_value=False)
    handler = SubscriptionMenuHandler(
        repo,
        traffic_limited_service=traffic_limited_service,
        commerce_enabled=False,
        traffic_limited_config_enabled=True,
    )
    traffic_limited_service.has_used_trial.return_value = False

    call = MockCall(9)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="wl text"),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        await handler.show_traffic_limited_menu(call)

    texts = [
        btn.text
        for row in bot_mock.send_photo.call_args.kwargs["reply_markup"].keyboard
        for btn in row
    ]
    assert TRAFFIC_LIMITED_TRIAL not in texts
    assert TRAFFIC_LIMITED15GB["label"] not in texts


@pytest.mark.asyncio
async def test_show_subscription_menu_repo_error(handler, repo, bot_mock):
    repo.get.side_effect = Exception("fail")
    call = MockCall(1)
    with (
        patch("telegram_bot.shared.texts.messages.get_random_message", return_value="text"),
        patch("telegram_bot.presentation.subscriptions.subscription_menu_handler.PHOTO_subscriptions", "photo.png"),
    ):
        with pytest.raises(Exception, match="fail"):
            await handler.show_subscription_menu(call)
    repo.get.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_show_subscription_menu_shows_blocked_alert(repo, bot_mock):
    repo.is_blocked = AsyncMock(return_value=True)
    handler = SubscriptionMenuHandler(
        repo,
        traffic_limited_service=AsyncMock(),
    )
    call = MockCall(42)

    await handler.show_subscription_menu(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(
        call.id,
        handler.BLOCKED_ALERT_TEXT,
        show_alert=True,
    )
    bot_mock.send_photo.assert_not_awaited()
