from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.referrals.referrals_stats_service import ReferralStatsService


@pytest.fixture
def service_and_repo():
    repo = AsyncMock()
    service = ReferralStatsService(repo=repo)
    return service, repo


@pytest.mark.asyncio
async def test_get_stats_returns_aggregated_values(service_and_repo):
    service, repo = service_and_repo
    repo.get_users_by_referrer.return_value = [1, 2, 3]
    repo.get.return_value = SimpleNamespace(paid_count=2, days_pending=5)

    result = await service.get_stats(123)

    repo.get_users_by_referrer.assert_awaited_once_with(123)
    repo.get.assert_awaited_once_with(123)
    assert result == {
        "invited": 3,
        "paid_count": 2,
        "pending_days": 5,
        "awaiting_paid_count": 1,
        "awaiting_bonus_days": 10,
    }


@pytest.mark.asyncio
async def test_get_stats_returns_zeroes_when_user_has_no_referrals(service_and_repo):
    service, repo = service_and_repo
    repo.get_users_by_referrer.return_value = []
    repo.get.return_value = SimpleNamespace(paid_count=0, days_pending=0)

    result = await service.get_stats(555)

    assert result == {
        "invited": 0,
        "paid_count": 0,
        "pending_days": 0,
        "awaiting_paid_count": 0,
        "awaiting_bonus_days": 0,
    }


@pytest.mark.asyncio
async def test_get_stats_projects_bonus_for_unpaid_invites(service_and_repo):
    service, repo = service_and_repo
    repo.get_users_by_referrer.return_value = [1, 2, 3]
    repo.get.return_value = SimpleNamespace(paid_count=1, days_pending=0)

    result = await service.get_stats(999)

    assert result["awaiting_paid_count"] == 2
    assert result["awaiting_bonus_days"] == 17


@pytest.mark.asyncio
async def test_get_stats_raises_when_user_missing(service_and_repo):
    service, repo = service_and_repo
    repo.get_users_by_referrer.return_value = []
    repo.get.return_value = None

    with pytest.raises(AttributeError):
        await service.get_stats(999)


@pytest.mark.asyncio
async def test_send_referral_link_uses_configured_base(service_and_repo):
    service, _repo = service_and_repo

    with (
        patch(
            "telegram_bot.services.referrals.referrals_stats_service.messages.get_random_message",
            return_value="link",
        ) as mock_message,
        patch(
            "telegram_bot.services.referrals.referrals_stats_service.BOT_REFERRAL_LINK",
            "https://ref/",
        ),
    ):
        result = await service.send_referral_link(456)

    assert result == "link\n```https://ref/456```"
    mock_message.assert_called_once_with("referral_link")


@pytest.mark.asyncio
async def test_send_rules_returns_message_text(service_and_repo):
    service, _repo = service_and_repo

    with patch(
        "telegram_bot.services.referrals.referrals_stats_service.messages.get_random_message",
        return_value="rules",
    ) as mock_message:
        result = await service.send_rules(789)

    assert result == "rules"
    mock_message.assert_called_once_with("referral_rules")
