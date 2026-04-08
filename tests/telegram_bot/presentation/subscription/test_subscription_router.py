from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.presentation.subscriptions import subscription_router as router
from telegram_bot.shared.config.subscription_products import (
    MONTH1,
    MONTH3,
    MONTH6,
    WHITELIST15GB,
    WHITELIST35GB,
    WHITELIST80GB,
    YEAR1,
)


class MockCall:
    def __init__(self, tg_id=1, data=""):
        self.id = 77
        self.data = data
        self.message = SimpleNamespace(chat=SimpleNamespace(id=tg_id))


@pytest.fixture
def handlers():
    payment = AsyncMock()
    menu = AsyncMock()
    trial = AsyncMock()
    news = AsyncMock()
    news.check_news_channel_subscription = MagicMock(side_effect=lambda func: func)
    return payment, menu, trial, news


@pytest.fixture
def bot_mock(monkeypatch):
    class Bot:
        def __init__(self):
            self.answer_callback_query = AsyncMock()

        def callback_query_handler(self, *args, **kwargs):
            raise AssertionError("callback_query_handler should be patched")

    bot = Bot()
    monkeypatch.setattr(router, "bot", bot)
    return bot


@pytest.fixture
def register(bot_mock, handlers, monkeypatch):
    payment, menu, trial, news = handlers
    captured = []

    def fake_handler(*args, **kwargs):
        def decorator(func):
            captured.append(func)
            return func

        return decorator

    monkeypatch.setattr(router.bot, "callback_query_handler", fake_handler)
    router.register_subscription_routes(payment, menu, trial, news)
    return captured


@pytest.mark.asyncio
async def test_handle_show_subscriptions_answers_callback_and_opens_menu(
    register, handlers, bot_mock
):
    show_func, _ = register
    call = MockCall(3)

    await show_func(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    handlers[1].show_subscription_menu.assert_awaited_once_with(call)


@pytest.mark.asyncio
async def test_handle_subscription_choice_runs_trial_through_news_channel_guard(
    register, handlers, bot_mock
):
    _, choice_func = register
    payment, menu, trial, news = handlers
    call = MockCall(5, "sub_trial")

    await choice_func(call)

    news.check_news_channel_subscription.assert_called_once_with(trial.grant_trial)
    trial.grant_trial.assert_awaited_once_with(call)
    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    payment.ask_payment_method.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_subscription_choice_delegates_news_channel_check(register, handlers, bot_mock):
    _, choice_func = register
    call = MockCall(5, "sub_check_news_channel")

    await choice_func(call)

    handlers[3].handle_check_news_channel.assert_awaited_once_with(call)
    bot_mock.answer_callback_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_subscription_choice_opens_news_channel_menu(register, handlers, bot_mock):
    _, choice_func = register
    call = MockCall(5, "sub_news_channel_menu")

    await choice_func(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    handlers[3].show_news_channel_menu.assert_awaited_once_with(call)


@pytest.mark.asyncio
async def test_handle_subscription_choice_opens_whitelist_menu(register, handlers, bot_mock):
    _, choice_func = register
    call = MockCall(5, "sub_whitelist_menu")

    await choice_func(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    handlers[1].show_whitelist_menu.assert_awaited_once_with(call)


@pytest.mark.asyncio
async def test_handle_subscription_choice_runs_whitelist_trial_through_news_channel_guard(
    register, handlers, bot_mock
):
    _, choice_func = register
    payment, menu, trial, news = handlers
    call = MockCall(5, "sub_whitelist_trial")

    await choice_func(call)

    news.check_news_channel_subscription.assert_called_once_with(
        trial.grant_whitelist_trial
    )
    trial.grant_whitelist_trial.assert_awaited_once_with(call)
    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    payment.ask_payment_method.assert_not_awaited()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("sub_month1", MONTH1),
        ("sub_month3", MONTH3),
        ("sub_month6", MONTH6),
        ("sub_year1", YEAR1),
        ("sub_whitelist15gb", WHITELIST15GB),
        ("sub_whitelist35gb", WHITELIST35GB),
        ("sub_whitelist80gb", WHITELIST80GB),
    ],
)
@pytest.mark.asyncio
async def test_handle_subscription_choice_starts_payment_flow_for_paid_plans(
    register, handlers, bot_mock, data, expected
):
    _, choice_func = register
    payment, menu, trial, news = handlers
    call = MockCall(5, data)

    await choice_func(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    payment.ask_payment_method.assert_awaited_once_with(call, expected)
    news.check_news_channel_subscription.assert_called_once()
    trial.grant_trial.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_subscription_choice_skips_paid_plans_when_commerce_disabled(
    bot_mock,
    handlers,
    monkeypatch,
):
    payment, menu, trial, news = handlers
    captured = []

    def fake_handler(*args, **kwargs):
        def decorator(func):
            captured.append(func)
            return func

        return decorator

    monkeypatch.setattr(router.bot, "callback_query_handler", fake_handler)
    router.register_subscription_routes(
        payment,
        menu,
        trial,
        news,
        commerce_enabled=False,
    )
    _, choice_func = captured
    call = MockCall(5, "sub_month1")

    await choice_func(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(
        call.id,
        router.COMMERCE_DISABLED_CALLBACK_TEXT,
    )
    payment.ask_payment_method.assert_not_awaited()
    news.check_news_channel_subscription.assert_not_called()


@pytest.mark.asyncio
async def test_handle_subscription_choice_ignores_unknown_callbacks(register, handlers, bot_mock):
    _, choice_func = register

    await choice_func(MockCall(5, "unknown"))

    bot_mock.answer_callback_query.assert_not_awaited()
    handlers[0].ask_payment_method.assert_not_awaited()
    handlers[2].grant_trial.assert_not_awaited()
    handlers[3].handle_check_news_channel.assert_not_awaited()
