import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.subscriptions.subscription_flow_service import (
    SubscriptionFlowService,
)
from telegram_bot.shared.config.subscription_products import DAY_3_TIMESTAMP


@pytest.fixture
def service_and_mocks():
    repo = AsyncMock()
    subscription_service = AsyncMock()
    instruction = MagicMock()
    user_info_service = AsyncMock()
    timestamp = MagicMock()
    sync_service = AsyncMock()
    service = SubscriptionFlowService(
        repo=repo,
        subscription_service=subscription_service,
        instruction=instruction,
        user_subscription_info_service=user_info_service,
        timestamp=timestamp,
        sync_service=sync_service,
    )
    return service, repo, subscription_service, user_info_service, timestamp, sync_service


@pytest.mark.asyncio
async def test_activate_or_extend_subscription_formats_existing_subscription_response(
    service_and_mocks,
):
    service, repo, subscription_service, user_info_service, timestamp, sync_service = service_and_mocks
    user = SimpleNamespace(expiration_date=1234567890)
    repo.get.return_value = user
    user_info_service.expiry_date_view.return_value = "Подписка активна до 01.01.2027"

    with patch(
        "telegram_bot.services.subscriptions.subscription_flow_service.messages.get_random_message",
        return_value="Подписка обновлена",
    ):
        result = await service.activate_or_extend_subscription(tg_id=12345, period="30d")

    assert result == ("✅ Подписка обновлена", "Подписка активна до 01.01.2027")
    subscription_service.create_or_update_user.assert_awaited_once_with(
        12345,
        "30d",
        user=user,
    )
    user_info_service.expiry_date_view.assert_awaited_once_with(
        "subscription_updated_date_view",
        12345,
    )


@pytest.mark.asyncio
async def test_activate_or_extend_subscription_formats_new_subscription_response(
    service_and_mocks,
):
    service, repo, subscription_service, user_info_service, timestamp, sync_service = service_and_mocks
    user = SimpleNamespace(expiration_date=None)
    repo.get.return_value = user
    user_info_service.expiry_date_view.return_value = "Подписка истекает 08.01.2027"

    with patch(
        "telegram_bot.services.subscriptions.subscription_flow_service.messages.get_random_message",
        return_value="Новый ключ активирован",
    ):
        result = await service.activate_or_extend_subscription(tg_id=67890, period="7d")

    assert result == ("Подписка истекает 08.01.2027", "Новый ключ активирован")
    subscription_service.create_or_update_user.assert_awaited_once_with(
        67890,
        "7d",
        user=user,
    )
    user_info_service.expiry_date_view.assert_awaited_once_with("subscription_expiration", 67890)


@pytest.mark.asyncio
async def test_activate_or_extend_subscription_raises_for_unknown_user(service_and_mocks):
    service, repo, subscription_service, user_info_service, timestamp, sync_service = service_and_mocks
    repo.get.return_value = None

    with pytest.raises(AttributeError, match="User not found"):
        await service.activate_or_extend_subscription(tg_id=1, period="30d")

    subscription_service.create_or_update_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_activate_trial_creates_trial_for_user_without_subscription(service_and_mocks):
    service, repo, subscription_service, user_info_service, timestamp, sync_service = service_and_mocks
    repo.get.return_value = SimpleNamespace(expiration_date=None, tg_id=99999, trial_date=None)
    timestamp.current_timestamp.return_value = 1640995200

    result = await service.activate_trial(99999)

    assert result is True
    subscription_service.create_or_update_user.assert_awaited_once_with(
        99999,
        DAY_3_TIMESTAMP,
        user=repo.get.return_value,
    )
    repo.set_trial_date.assert_awaited_once_with(tg_id=99999, trial_date=1640995200)
    assert repo.get.return_value.trial_date == 1640995200


@pytest.mark.asyncio
async def test_activate_trial_returns_none_for_existing_subscription(service_and_mocks):
    service, repo, subscription_service, user_info_service, timestamp, sync_service = service_and_mocks
    repo.get.return_value = SimpleNamespace(expiration_date=1234567890)

    result = await service.activate_trial(55555)

    assert result is None
    subscription_service.create_or_update_user.assert_not_awaited()
    repo.set_trial_date.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_tg_news_channel_date_only_sets_it_once(service_and_mocks):
    service, repo, subscription_service, user_info_service, timestamp, sync_service = service_and_mocks
    repo.get.side_effect = [
        SimpleNamespace(tg_id=77, news_channel_date=None),
        SimpleNamespace(news_channel_date=123),
    ]
    timestamp.current_timestamp.return_value = 1700000000

    first = await service.set_tg_news_channel_date(77)
    second = await service.set_tg_news_channel_date(77)

    assert first is True
    assert second is None
    repo.set_news_channel_date.assert_awaited_once_with(
        tg_id=77,
        news_channel_date=1700000000,
    )


@pytest.mark.asyncio
async def test_activate_trial_serializes_same_user_requests(service_and_mocks):
    service, repo, subscription_service, user_info_service, timestamp, sync_service = service_and_mocks
    state = {"active": False}

    async def get_user(_tg_id):
        return SimpleNamespace(
            expiration_date=1234567890 if state["active"] else None,
            tg_id=99999,
            trial_date=None,
        )

    async def create_or_update_user(*args, **kwargs):
        await asyncio.sleep(0.01)
        state["active"] = True

    repo.get.side_effect = get_user
    subscription_service.create_or_update_user.side_effect = create_or_update_user
    timestamp.current_timestamp.return_value = 1640995200

    first, second = await asyncio.gather(
        service.activate_trial(99999),
        service.activate_trial(99999),
    )

    assert sorted([first, second], key=lambda item: item is None) == [True, None]
    assert subscription_service.create_or_update_user.await_count == 1
    repo.set_trial_date.assert_awaited_once_with(
        tg_id=99999,
        trial_date=1640995200,
    )
