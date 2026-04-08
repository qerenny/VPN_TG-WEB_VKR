from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.presentation.referrals.referral_menu_handler import ReferralMenuHandler
from telegram_bot.presentation.referrals.referrals_router import register_referrals_routes


class FakeCall:
    def __init__(self, chat_id=1, data="referrals_menu", cid="cbid"):
        self.id = cid
        self.data = data
        self.message = SimpleNamespace(chat=SimpleNamespace(id=chat_id))
        self.from_user = SimpleNamespace(username="user")


@pytest.mark.asyncio
async def test_referrals_menu_triggers_show():
    handler = AsyncMock(spec=ReferralMenuHandler)
    collected = {}

    def fake_cb_handler(*args, **kwargs):
        def decorator(func):
            collected["func"] = func
            return func

        return decorator

    with (
        patch(
            "telegram_bot.presentation.referrals.referrals_router.bot.callback_query_handler",
            fake_cb_handler,
        ),
        patch(
            "telegram_bot.presentation.referrals.referrals_router.bot.answer_callback_query",
            new_callable=AsyncMock,
        ) as mock_answer,
    ):
        register_referrals_routes(handler)
        cb = collected["func"]
        call = FakeCall(data="referrals_menu")
        await cb(call)

    mock_answer.assert_awaited_once_with("cbid")
    handler.show.assert_awaited_once_with(call)


@pytest.mark.asyncio
async def test_other_callbacks_do_not_call_show():
    handler = AsyncMock(spec=ReferralMenuHandler)
    collected = {}

    def fake_cb_handler(*args, **kwargs):
        def decorator(func):
            collected["func"] = func
            return func

        return decorator

    with (
        patch(
            "telegram_bot.presentation.referrals.referrals_router.bot.callback_query_handler",
            fake_cb_handler,
        ),
        patch(
            "telegram_bot.presentation.referrals.referrals_router.bot.answer_callback_query",
            new_callable=AsyncMock,
        ) as mock_answer,
    ):
        register_referrals_routes(handler)
        cb = collected["func"]
        call = FakeCall(data="referrals_rules")
        await cb(call)

    mock_answer.assert_awaited_once_with("cbid")
    handler.show.assert_not_awaited()
