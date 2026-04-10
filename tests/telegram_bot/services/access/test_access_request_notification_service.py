from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.access.access_request_notification_service import (
    AccessRequestNotificationService,
)


@pytest.mark.asyncio
async def test_notify_admins_request_created_sends_inline_review_buttons():
    service = AccessRequestNotificationService()

    with (
        patch(
            "telegram_bot.services.access.access_request_notification_service.BOT_ADMIN_IDS",
            [123],
        ),
        patch.object(
            AccessRequestNotificationService,
            "_telegram_runtime_enabled",
            return_value=True,
        ),
        patch.object(
            AccessRequestNotificationService,
            "_resolve_requester_identity_line",
            new=AsyncMock(return_value="Telegram: `@alice`"),
        ),
        patch(
            "telegram_bot.services.access.access_request_notification_service.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await service.notify_admins_request_created(
            request_id=15,
            user_id=7,
            request_kind="new_access",
            requested_template_code="month_1",
            channel="telegram",
            comment="need access",
        )

    _, kwargs = mock_send.await_args
    assert "Telegram: `@alice`" in kwargs["text"]
    buttons = kwargs["reply_markup"].keyboard[0]
    assert buttons[0].callback_data == "admin_access_request_approve:15:month_1"
    assert buttons[1].callback_data == "admin_access_request_reject:15"


@pytest.mark.asyncio
async def test_notify_user_request_reviewed_attaches_profile_navigation_markup():
    telegram_link_service = AsyncMock()
    telegram_link_service.create_web_link = AsyncMock(return_value="https://frontend.example.com/auth/login?link_token=abc")
    service = AccessRequestNotificationService(telegram_link_service=telegram_link_service)

    with (
        patch.object(
            AccessRequestNotificationService,
            "_telegram_runtime_enabled",
            return_value=True,
        ),
        patch.object(
            AccessRequestNotificationService,
            "_resolve_user_tg_id",
            new=AsyncMock(return_value=123),
        ),
        patch(
            "telegram_bot.services.access.access_request_notification_service.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await service.notify_user_request_reviewed(
            user_id=7,
            request_id=15,
            status="approved",
            request_kind="new_access",
            template_code="month_1",
            review_note="Approved",
            reviewed_by_actor="admin",
            auto_approved=False,
        )

    _, kwargs = mock_send.await_args
    button = kwargs["reply_markup"].keyboard[0][0]
    assert button.url == "https://frontend.example.com/auth/login?link_token=abc"


@pytest.mark.asyncio
async def test_notify_user_access_activated_falls_back_to_main_menu_button_without_cabinet_url():
    telegram_link_service = AsyncMock()
    telegram_link_service.create_web_link = AsyncMock(return_value=None)
    service = AccessRequestNotificationService(telegram_link_service=telegram_link_service)

    with (
        patch.object(
            AccessRequestNotificationService,
            "_telegram_runtime_enabled",
            return_value=True,
        ),
        patch.object(
            AccessRequestNotificationService,
            "_resolve_user_tg_id",
            new=AsyncMock(return_value=123),
        ),
        patch(
            "telegram_bot.services.access.access_request_notification_service.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await service.notify_user_access_activated(
            user_id=7,
            source_type="request_approval",
            template_code="month_1",
        )

    _, kwargs = mock_send.await_args
    button = kwargs["reply_markup"].keyboard[0][0]
    assert button.callback_data == "menu_start"


@pytest.mark.asyncio
async def test_resolve_requester_identity_line_falls_back_to_telegram_for_web_channel_without_email():
    service = AccessRequestNotificationService()

    class _ScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    session = AsyncMock()
    session.execute.side_effect = [
        _ScalarResult(SimpleNamespace(username="alice", telegram_id=123456)),
        _ScalarResult(SimpleNamespace(email=None)),
    ]

    @asynccontextmanager
    async def _fake_session():
        yield session

    with patch(
        "telegram_bot.services.access.access_request_notification_service.get_db_session",
        _fake_session,
    ):
        line = await service._resolve_requester_identity_line(user_id=7, channel="web")

    assert line == "Telegram: `@alice`"
