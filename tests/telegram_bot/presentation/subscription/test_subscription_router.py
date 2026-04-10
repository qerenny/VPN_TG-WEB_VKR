from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.presentation.subscriptions import subscription_router as router
from telegram_bot.shared.config.subscription_products import (
    MONTH1,
    MONTH3,
    MONTH6,
    TRAFFIC_LIMITED15GB,
    TRAFFIC_LIMITED35GB,
    TRAFFIC_LIMITED80GB,
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
    access_request = AsyncMock()
    trial = AsyncMock()
    info_channel = AsyncMock()
    info_channel.check_info_channel_subscription = MagicMock(side_effect=lambda func: func)
    return payment, menu, access_request, trial, info_channel


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
    payment, menu, access_request, trial, info_channel = handlers
    captured = []

    def fake_handler(*args, **kwargs):
        def decorator(func):
            captured.append(func)
            return func

        return decorator

    monkeypatch.setattr(router.bot, "callback_query_handler", fake_handler)
    router.register_subscription_routes(payment, menu, access_request, trial, info_channel)
    return captured


def _register_with_flags(monkeypatch, handlers, **kwargs):
    payment, menu, access_request, trial, info_channel = handlers
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
        access_request,
        trial,
        info_channel,
        **kwargs,
    )
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
async def test_handle_subscription_choice_runs_trial_through_info_channel_guard(
    register, handlers, bot_mock
):
    _, choice_func = register
    payment, menu, access_request, trial, info_channel = handlers
    call = MockCall(5, "sub_trial")

    await choice_func(call)

    info_channel.check_info_channel_subscription.assert_called_once_with(trial.grant_trial)
    trial.grant_trial.assert_awaited_once_with(call)
    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    payment.ask_payment_method.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_subscription_choice_delegates_info_channel_check(register, handlers, bot_mock):
    _, choice_func = register
    call = MockCall(5, "sub_check_info_channel")

    await choice_func(call)

    handlers[4].handle_check_info_channel.assert_awaited_once_with(call)
    bot_mock.answer_callback_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_subscription_choice_opens_info_channel_menu(register, handlers, bot_mock):
    _, choice_func = register
    call = MockCall(5, "sub_info_channel_menu")

    await choice_func(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    handlers[4].show_info_channel_menu.assert_awaited_once_with(call)


@pytest.mark.asyncio
async def test_handle_subscription_choice_opens_traffic_limited_menu(register, handlers, bot_mock):
    _, choice_func = register
    call = MockCall(5, "sub_traffic_limited_menu")

    await choice_func(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    handlers[1].show_traffic_limited_menu.assert_awaited_once_with(call)


@pytest.mark.asyncio
async def test_handle_subscription_choice_runs_traffic_limited_trial_through_info_channel_guard(
    register, handlers, bot_mock
):
    _, choice_func = register
    payment, menu, access_request, trial, info_channel = handlers
    call = MockCall(5, "sub_traffic_limited_trial")

    await choice_func(call)

    info_channel.check_info_channel_subscription.assert_called_once_with(
        trial.grant_traffic_limited_trial
    )
    trial.grant_traffic_limited_trial.assert_awaited_once_with(call)
    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    payment.ask_payment_method.assert_not_awaited()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("sub_month1", MONTH1),
        ("sub_month3", MONTH3),
        ("sub_month6", MONTH6),
        ("sub_year1", YEAR1),
        ("sub_traffic_limited15gb", TRAFFIC_LIMITED15GB),
        ("sub_traffic_limited35gb", TRAFFIC_LIMITED35GB),
        ("sub_traffic_limited80gb", TRAFFIC_LIMITED80GB),
    ],
)
@pytest.mark.asyncio
async def test_handle_subscription_choice_starts_payment_flow_for_paid_plans(
    register, handlers, bot_mock, data, expected
):
    _, choice_func = register
    payment, menu, access_request, trial, info_channel = handlers
    call = MockCall(5, data)

    await choice_func(call)

    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)
    payment.ask_payment_method.assert_awaited_once_with(call, expected)
    info_channel.check_info_channel_subscription.assert_called_once()
    trial.grant_trial.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_subscription_choice_skips_paid_plans_when_commerce_disabled(
    bot_mock,
    handlers,
    monkeypatch,
):
    payment, menu, access_request, trial, info_channel = handlers
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
        access_request,
        trial,
        info_channel,
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
    info_channel.check_info_channel_subscription.assert_not_called()


@pytest.mark.asyncio
async def test_handle_subscription_choice_submits_access_request_when_enabled(
    bot_mock, handlers, monkeypatch
):
    _, choice_func = _register_with_flags(
        monkeypatch,
        handlers,
        access_requests_enabled=True,
    )
    call = MockCall(5, "sub_access_request")

    await choice_func(call)

    handlers[2].show_request_menu.assert_awaited_once_with(call)
    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)


@pytest.mark.asyncio
async def test_handle_subscription_choice_shows_access_request_template_menu(
    bot_mock, handlers, monkeypatch
):
    _, choice_func = _register_with_flags(
        monkeypatch,
        handlers,
        access_requests_enabled=True,
    )
    call = MockCall(5, "sub_access_request_scope:standard")

    await choice_func(call)

    handlers[2].show_template_menu.assert_awaited_once_with(call, scope="standard")
    bot_mock.answer_callback_query.assert_awaited_once_with(call.id)


@pytest.mark.asyncio
async def test_handle_subscription_choice_submits_access_request_with_selected_template(
    bot_mock, handlers, monkeypatch
):
    _, choice_func = _register_with_flags(
        monkeypatch,
        handlers,
        access_requests_enabled=True,
    )
    call = MockCall(5, "sub_access_request_submit:month_1")

    await choice_func(call)

    handlers[2].submit_template_request.assert_awaited_once_with(
        call,
        template_code="month_1",
    )
    bot_mock.answer_callback_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_subscription_choice_shows_access_request_status(
    bot_mock, handlers, monkeypatch
):
    _, choice_func = _register_with_flags(
        monkeypatch,
        handlers,
        access_requests_enabled=True,
    )
    call = MockCall(5, "sub_access_request_status")

    await choice_func(call)

    handlers[2].show_status.assert_awaited_once_with(call, alert_on_empty=True)
    bot_mock.answer_callback_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_subscription_choice_ignores_unknown_callbacks(register, handlers, bot_mock):
    _, choice_func = register

    await choice_func(MockCall(5, "unknown"))

    bot_mock.answer_callback_query.assert_not_awaited()
    handlers[0].ask_payment_method.assert_not_awaited()
    handlers[2].grant_trial.assert_not_awaited()
    handlers[4].handle_check_info_channel.assert_not_awaited()
