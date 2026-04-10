from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.presentation.subscriptions.subscription_promo_handler import (
    SubscriptionPromoHandler,
)


@pytest.fixture
def handler():
    subscription_flow_service = AsyncMock()
    start_handler = AsyncMock()
    promo_repo = AsyncMock()
    promo_code_repo = AsyncMock()
    return SubscriptionPromoHandler(
        subscription_flow_service=subscription_flow_service,
        start_handler=start_handler,
        promo_repo=promo_repo,
        promo_code_repo=promo_code_repo,
    )


@pytest.fixture
def bot_mock(monkeypatch):
    bot = AsyncMock()
    monkeypatch.setattr(
        "telegram_bot.presentation.subscriptions.subscription_promo_handler.bot",
        bot,
    )
    return bot


@pytest.mark.asyncio
async def test_activate_promo_marks_usage(handler, bot_mock):
    message = SimpleNamespace(
        chat=SimpleNamespace(id=42),
        text="/promo PROMO7",
    )
    handler.promo_repo.is_used.return_value = False
    handler.promo_code_repo.get_by_code.return_value = SimpleNamespace(
        remaining_uses=2,
        duration="day7",
    )
    handler.subscription_flow_service.activate_or_extend_subscription.return_value = (
        "subscription text",
        "key text",
    )

    with patch(
        "telegram_bot.presentation.subscriptions.subscription_promo_handler.messages.get_random_message",
        return_value="promo {promo_code}",
    ):
        await handler.activate_promo(message)

    handler.promo_repo.mark_used.assert_awaited_once_with(42, "PROMO7")
    handler.start_handler.send_main_menu.assert_awaited_once_with(message)
    assert bot_mock.send_message.await_count == 2
