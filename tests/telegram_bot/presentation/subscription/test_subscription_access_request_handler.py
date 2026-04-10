from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.presentation.subscriptions.subscription_access_request_handler import (
    SubscriptionAccessRequestHandler,
)


class _Call:
    def __init__(self, callback_id: int = 1, chat_id: int = 42):
        self.id = callback_id
        self.message = SimpleNamespace(chat=SimpleNamespace(id=chat_id))


@pytest.mark.asyncio
async def test_show_status_shows_alert_and_returns_to_menu_when_no_requests(monkeypatch):
    bot_mock = SimpleNamespace(answer_callback_query=AsyncMock())
    render_mock = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_access_request_handler.bot",
        bot_mock,
    )
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_access_request_handler.render_photo_menu",
        render_mock,
    )

    service = SimpleNamespace(
        list_requests=AsyncMock(return_value=[]),
        is_registry_managed=AsyncMock(return_value=False),
        has_active_access=AsyncMock(return_value=False),
    )
    handler = SubscriptionAccessRequestHandler(service)

    await handler.show_status(_Call(), alert_on_empty=True)

    bot_mock.answer_callback_query.assert_awaited_once()
    _, kwargs = bot_mock.answer_callback_query.await_args
    assert kwargs["show_alert"] is True
    render_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_show_status_renders_history_when_requests_exist(monkeypatch):
    bot_mock = SimpleNamespace(answer_callback_query=AsyncMock())
    render_mock = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_access_request_handler.bot",
        bot_mock,
    )
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_access_request_handler.render_photo_menu",
        render_mock,
    )

    request = SimpleNamespace(
        id=10,
        status="pending",
        requested_at="2026-04-10T00:00:00+00:00",
        reviewed_at=None,
        review_note=None,
        reviewed_by_actor=None,
        requested_template_code="month_1",
        request_kind="new_access",
        expires_at="2026-04-12T00:00:00+00:00",
        metadata={},
    )
    service = SimpleNamespace(
        list_requests=AsyncMock(return_value=[request]),
    )
    handler = SubscriptionAccessRequestHandler(service)

    await handler.show_status(_Call(), alert_on_empty=True)

    bot_mock.answer_callback_query.assert_not_awaited()
    render_mock.assert_awaited_once()
    _, kwargs = render_mock.await_args
    caption = kwargs["caption"]
    buttons = kwargs["reply_markup"].keyboard
    assert "#10" not in caption
    assert "2026-04-10T00:00:00+00:00" not in caption
    assert "10.04.2026 03:00" in caption
    assert buttons[0][0].text == "⬅️ К запросу доступа"


@pytest.mark.asyncio
async def test_show_status_compacts_previous_requests(monkeypatch):
    bot_mock = SimpleNamespace(answer_callback_query=AsyncMock())
    render_mock = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_access_request_handler.bot",
        bot_mock,
    )
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_access_request_handler.render_photo_menu",
        render_mock,
    )

    latest_request = SimpleNamespace(
        id=10,
        status="pending",
        requested_at="2026-04-10T00:00:00+00:00",
        reviewed_at=None,
        review_note=None,
        reviewed_by_actor=None,
        requested_template_code="month_1",
        request_kind="new_access",
        expires_at="2026-04-12T00:00:00+00:00",
        metadata={},
    )
    previous_request = SimpleNamespace(
        id=9,
        status="approved",
        requested_at="2026-04-09T00:00:00+00:00",
        reviewed_at="2026-04-09T01:30:00+00:00",
        review_note="ok",
        reviewed_by_actor="admin",
        requested_template_code="month_1",
        request_kind="renewal",
        expires_at=None,
        metadata={},
    )
    service = SimpleNamespace(
        list_requests=AsyncMock(return_value=[latest_request, previous_request]),
    )
    handler = SubscriptionAccessRequestHandler(service)

    await handler.show_status(_Call(), alert_on_empty=True)

    _, kwargs = render_mock.await_args
    caption = kwargs["caption"]
    assert "*Предыдущие заявки*" in caption
    assert "• Одобрена · Продление · 09.04.2026 04:30" in caption
    assert "Комментарий: ok" not in caption


@pytest.mark.asyncio
async def test_show_request_menu_without_active_access_shows_only_initial_request(monkeypatch):
    render_mock = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_access_request_handler.render_photo_menu",
        render_mock,
    )

    service = SimpleNamespace(
        is_registry_managed=AsyncMock(return_value=False),
        has_active_access=AsyncMock(return_value=False),
    )
    handler = SubscriptionAccessRequestHandler(service)

    await handler.show_request_menu(_Call())

    _, kwargs = render_mock.await_args
    buttons = kwargs["reply_markup"].keyboard
    assert buttons[0][0].text == "🔐 Базовая конфигурация"
    assert len(buttons[0]) == 1
    assert buttons[1][0].text == "🛰 Конфигурация с лимитом трафика"
    all_buttons = [button.text for row in buttons for button in row]
    assert "📋 Статус заявки" not in all_buttons


@pytest.mark.asyncio
async def test_show_request_menu_with_active_access_shows_scope_choices_and_status(monkeypatch):
    render_mock = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_access_request_handler.render_photo_menu",
        render_mock,
    )

    service = SimpleNamespace(
        is_registry_managed=AsyncMock(return_value=False),
        has_active_access=AsyncMock(return_value=True),
    )
    handler = SubscriptionAccessRequestHandler(service)

    await handler.show_request_menu(_Call())

    _, kwargs = render_mock.await_args
    buttons = kwargs["reply_markup"].keyboard
    assert buttons[0][0].text == "🔐 Базовая конфигурация"
    assert buttons[1][0].text == "🛰 Конфигурация с лимитом трафика"
    all_buttons = [button.text for row in buttons for button in row]
    assert "📋 Статус заявки" not in all_buttons


@pytest.mark.asyncio
async def test_show_template_menu_marks_current_template(monkeypatch):
    render_mock = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_access_request_handler.render_photo_menu",
        render_mock,
    )

    service = SimpleNamespace(
        get_active_template_codes_by_scope=AsyncMock(return_value={"standard": "month_1"}),
    )
    handler = SubscriptionAccessRequestHandler(service)

    await handler.show_template_menu(_Call(), scope="standard")

    _, kwargs = render_mock.await_args
    buttons = kwargs["reply_markup"].keyboard
    assert buttons[0][0].text.startswith("✅ ")


@pytest.mark.asyncio
async def test_submit_template_request_uses_renewal_for_current_template(monkeypatch):
    service = SimpleNamespace(
        get_active_template_codes_by_scope=AsyncMock(return_value={"standard": "month_1"}),
    )
    handler = SubscriptionAccessRequestHandler(service)
    submit_mock = AsyncMock()
    monkeypatch.setattr(handler, "submit_request", submit_mock)
    call = _Call()

    await handler.submit_template_request(call, template_code="month_1")

    submit_mock.assert_awaited_once_with(
        call,
        request_kind="renewal",
        template_code="month_1",
    )


@pytest.mark.asyncio
async def test_submit_template_request_uses_new_access_for_other_template(monkeypatch):
    service = SimpleNamespace(
        get_active_template_codes_by_scope=AsyncMock(return_value={"standard": "month_1"}),
    )
    handler = SubscriptionAccessRequestHandler(service)
    submit_mock = AsyncMock()
    monkeypatch.setattr(handler, "submit_request", submit_mock)
    call = _Call()

    await handler.submit_template_request(call, template_code="month_3")

    submit_mock.assert_awaited_once_with(
        call,
        request_kind="new_access",
        template_code="month_3",
    )
