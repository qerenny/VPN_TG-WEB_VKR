from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.migration_support.models.users.user_model import User
from telegram_bot.services.users.user_subscription_info_service import (
    UserSubscriptionInfoService,
)
from telegram_bot.shared.config.navigation import EXPIRED, LESS_THAN_HOUR


@pytest.fixture
def service_and_mocks():
    repo = AsyncMock()
    timestamp = MagicMock()
    service = UserSubscriptionInfoService(repo=repo, timestamp=timestamp)
    return service, repo, timestamp


@pytest.fixture
def user_with_expiration():
    return User(
        tg_id=12345,
        uuid="uid",
        email="user@example.com",
        expiration_date=1700000000,
        sub_id="sub-1",
    )


@pytest.mark.asyncio
async def test_get_expiration_ts_returns_user_timestamp(service_and_mocks, user_with_expiration):
    service, repo, timestamp = service_and_mocks
    repo.get.return_value = user_with_expiration

    assert await service.get_expiration_ts(12345) == 1700000000
    repo.get.assert_awaited_once_with(12345)


@pytest.mark.asyncio
async def test_get_expiration_str_formats_timestamp(service_and_mocks, user_with_expiration):
    service, repo, timestamp = service_and_mocks
    repo.get.return_value = user_with_expiration
    timestamp.timestamp_to_date.return_value = datetime(2023, 11, 15, 10, 13, 20)

    assert await service.get_expiration_str(12345) == "10:13:20 15-11-2023"


@pytest.mark.asyncio
async def test_get_expiration_pretty_returns_message_for_expired_subscription(
    service_and_mocks, user_with_expiration
):
    service, repo, timestamp = service_and_mocks
    repo.get.return_value = user_with_expiration
    timestamp.calculate_time_difference.return_value = EXPIRED

    with patch("telegram_bot.services.users.user_subscription_info_service.messages.get_random_message") as get_message:
        get_message.return_value = "Subscription expired"
        result = await service.get_expiration_pretty(12345)

    assert result == "Subscription expired"
    get_message.assert_called_once_with("users_subs_ended")


@pytest.mark.asyncio
async def test_get_expiration_pretty_returns_message_for_less_than_hour(
    service_and_mocks, user_with_expiration
):
    service, repo, timestamp = service_and_mocks
    repo.get.return_value = user_with_expiration
    timestamp.calculate_time_difference.return_value = LESS_THAN_HOUR

    with patch("telegram_bot.services.users.user_subscription_info_service.messages.get_random_message") as get_message:
        get_message.return_value = "Less than an hour left"
        result = await service.get_expiration_pretty(12345)

    assert result == "Less than an hour left"
    get_message.assert_called_once_with("users_subs_less_than_hour")


@pytest.mark.asyncio
async def test_expiry_date_view_combines_template_and_formatted_values(
    service_and_mocks, user_with_expiration
):
    service, repo, timestamp = service_and_mocks
    repo.get.return_value = user_with_expiration
    timestamp.timestamp_to_date.return_value = datetime(2023, 11, 15, 10, 13, 20)
    timestamp.calculate_time_difference.return_value = "5 days"

    with patch("telegram_bot.services.users.user_subscription_info_service.messages.get_random_message") as get_message:
        get_message.side_effect = [
            "Welcome message",
            "Expires in {remaining} at {expiration_date}",
        ]

        result = await service.expiry_date_view("welcome", 12345)

    assert result == "Welcome message\nExpires in 5 days at 10:13:20 15-11-2023"
