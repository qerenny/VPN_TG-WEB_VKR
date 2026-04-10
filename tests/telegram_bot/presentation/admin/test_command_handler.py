from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.presentation.admin.command_handler import AdminCommandHandler


def make_message(chat_id: int) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id))


def make_call(chat_id: int, data: str, callback_id: str = "cb-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=callback_id,
        data=data,
        message=SimpleNamespace(chat=SimpleNamespace(id=chat_id)),
    )


@pytest.fixture
def handler():
    return AdminCommandHandler(
        repo=AsyncMock(),
        subscription_user_service=AsyncMock(),
        instruction=AsyncMock(),
        timestamp=MagicMock(),
        payment_queue_service=AsyncMock(),
        jwt_encoder=MagicMock(),
        access_request_service=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_show_user_management_includes_delete_button(handler):
    handler.repo.get.return_value = SimpleNamespace(
        tg_id=123,
        uuid="uuid-123",
        email="user@example.com",
        expiration_date=None,
        login_date=1,
        trial_date=None,
        sub_id="sub-123",
    )

    with patch(
        "telegram_bot.presentation.admin.command_handler.bot.send_message",
        new_callable=AsyncMock,
    ) as mock_send:
        await handler.show_user_management(6884511529, 123)

    _, kwargs = mock_send.call_args
    buttons = [button.callback_data for row in kwargs["reply_markup"].keyboard for button in row]
    assert "admin_sub_123" in buttons
    assert "admin_del_user_123" in buttons


@pytest.mark.asyncio
async def test_admin_delete_selected_user_confirms_with_target(handler):
    with (
        patch(
            "telegram_bot.presentation.admin.command_handler.BOT_ADMIN_IDS",
            [6884511529],
        ),
        patch(
            "telegram_bot.presentation.admin.command_handler.bot.answer_callback_query",
            new_callable=AsyncMock,
        ),
        patch(
            "telegram_bot.presentation.admin.command_handler.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await handler.handle_admin_callback(make_call(6884511529, "admin_del_user_123"))

    assert handler.sessions[6884511529]["target_tg_id"] == 123
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_confirm_delete_user_calls_delete_user(handler):
    handler.sessions[6884511529] = {
        "state": "confirm_delete_user",
        "target_tg_id": 123,
    }
    handler.subscription_user_service.delete_user.return_value = True

    with (
        patch(
            "telegram_bot.presentation.admin.command_handler.BOT_ADMIN_IDS",
            [6884511529],
        ),
        patch(
            "telegram_bot.presentation.admin.command_handler.bot.answer_callback_query",
            new_callable=AsyncMock,
        ),
        patch(
            "telegram_bot.presentation.admin.command_handler.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await handler.handle_admin_callback(
            make_call(6884511529, "admin_confirm_delete_user")
        )

    handler.subscription_user_service.delete_user.assert_awaited_once_with(123)
    mock_send.assert_awaited_once_with(6884511529, "User 123 deleted")


@pytest.mark.asyncio
async def test_show_admin_panel_sends_web_admin_link(handler):
    with (
        patch(
            "telegram_bot.presentation.admin.command_handler.BOT_ADMIN_IDS",
            [6884511529],
        ),
        patch(
            "telegram_bot.presentation.admin.command_handler.BACKEND_TELEGRAM_BASE_LINK",
            "https://api.example.com/test-api",
        ),
        patch(
            "telegram_bot.presentation.admin.command_handler.FRONTEND_ADMIN_PATH",
            "hidden-admin",
        ),
        patch(
            "telegram_bot.presentation.admin.command_handler.create_admin_bootstrap_token",
            new=AsyncMock(return_value="grant-token"),
        ),
        patch(
            "telegram_bot.presentation.admin.command_handler.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await handler.show_admin_panel(make_message(6884511529))

    _, kwargs = mock_send.call_args
    assert "временной ссылке" in kwargs["text"].lower()
    button = kwargs["reply_markup"].keyboard[0][0]
    assert button.url == "https://api.example.com/test-api/admin/session/bootstrap?grant=grant-token"


@pytest.mark.asyncio
async def test_admin_access_request_approve_reviews_request(handler):
    handler.access_request_service.review_request.return_value = SimpleNamespace(
        approved_template_label="1 месяц · Базовая конфигурация",
        requested_template_label="1 месяц · Базовая конфигурация",
    )
    call = make_call(6884511529, "admin_access_request_approve:12:month_1")
    call.message.message_id = 77

    with (
        patch("telegram_bot.presentation.admin.command_handler.BOT_ADMIN_IDS", [6884511529]),
        patch("telegram_bot.presentation.admin.command_handler.bot.answer_callback_query", new_callable=AsyncMock),
        patch("telegram_bot.presentation.admin.command_handler.bot.edit_message_text", new_callable=AsyncMock) as mock_edit_text,
        patch("telegram_bot.presentation.admin.command_handler.bot.edit_message_reply_markup", new_callable=AsyncMock) as mock_edit,
        patch("telegram_bot.presentation.admin.command_handler.bot.send_message", new_callable=AsyncMock) as mock_send,
    ):
        await handler.handle_admin_callback(call)

    handler.access_request_service.review_request.assert_awaited_once()
    mock_edit_text.assert_awaited_once()
    mock_edit.assert_not_awaited()
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_access_request_approve_marks_message_handled_when_already_reviewed(handler):
    from fastapi import HTTPException

    handler.access_request_service.review_request.side_effect = HTTPException(
        status_code=409,
        detail="Access request is already reviewed",
    )
    call = make_call(6884511529, "admin_access_request_approve:12:month_1")
    call.message.message_id = 77

    with (
        patch("telegram_bot.presentation.admin.command_handler.BOT_ADMIN_IDS", [6884511529]),
        patch("telegram_bot.presentation.admin.command_handler.bot.answer_callback_query", new_callable=AsyncMock),
        patch("telegram_bot.presentation.admin.command_handler.bot.edit_message_text", new_callable=AsyncMock) as mock_edit_text,
        patch("telegram_bot.presentation.admin.command_handler.bot.edit_message_reply_markup", new_callable=AsyncMock) as mock_edit_markup,
        patch("telegram_bot.presentation.admin.command_handler.bot.send_message", new_callable=AsyncMock) as mock_send,
    ):
        await handler.handle_admin_callback(call)

    mock_edit_text.assert_awaited_once()
    mock_edit_markup.assert_not_awaited()
    mock_send.assert_not_awaited()
