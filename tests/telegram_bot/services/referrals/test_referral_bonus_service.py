from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.infrastructure.growth_service import ReferralRewardContext
from telegram_bot.services.referrals.referral_bonus_service import ReferralBonusService


@pytest.fixture
def service_and_mocks():
    repo_referrals = AsyncMock()
    repo_user = AsyncMock()
    timestamp = MagicMock()
    client = AsyncMock()
    growth_service = AsyncMock()
    growth_service.sync_flags = SimpleNamespace(growth_sync_enabled=False)
    service = ReferralBonusService(
        repo_referrals=repo_referrals,
        repo_user=repo_user,
        timestamp=timestamp,
        client=client,
        growth_service=growth_service,
    )
    service.default_referrer_bonus_days = 7
    service.referrer_bonus_rules = {3: 10, 5: 15, 10: 31, 15: 62}
    return service, repo_referrals, repo_user, timestamp, client, growth_service


@pytest.mark.asyncio
async def test_grant_bonus_to_user_stores_pending_days_for_inactive_user(service_and_mocks):
    service, repo_referrals, repo_user, timestamp, client, growth_service = service_and_mocks
    repo_user.get.return_value = SimpleNamespace(tg_id=1, email="a@b.com", expiration_date=None)
    timestamp.current_timestamp.return_value = 100

    await service.grant_bonus_to_user(1, 7)

    repo_referrals.update_days_pending.assert_awaited_once_with(1, 7)
    client.update_client.assert_not_awaited()
    growth_service.sync_referral_reward.assert_not_awaited()


@pytest.mark.asyncio
async def test_grant_bonus_to_user_updates_active_subscription(service_and_mocks):
    service, repo_referrals, repo_user, timestamp, client, growth_service = service_and_mocks
    active_user = SimpleNamespace(tg_id=1, email="a@b.com", expiration_date=200)
    repo_user.get.return_value = active_user
    timestamp.current_timestamp.return_value = 100

    await service.grant_bonus_to_user(1, 5)

    client.update_client.assert_awaited_once_with(1, "day5", user=active_user)
    repo_referrals.update_days_pending.assert_not_awaited()
    growth_service.sync_referral_reward.assert_not_awaited()


@pytest.mark.asyncio
async def test_grant_pending_and_referrer_bonus_returns_zero_without_pending_days(service_and_mocks):
    service, repo_referrals, repo_user, timestamp, client, _growth_service = service_and_mocks
    repo_referrals.get.return_value = SimpleNamespace(
        tg_id=1,
        referrer_tg_id=None,
        days_pending=0,
    )

    with patch.object(service, "_grant_bonus_to_referrer", wraps=service._grant_bonus_to_referrer) as grant_referrer:
        result = await service.grant_pending_and_referrer_bonus(1)

    assert result == (0, None, None)
    grant_referrer.assert_not_called()


@pytest.mark.asyncio
async def test_grant_pending_and_referrer_bonus_executes_full_flow(service_and_mocks):
    service, repo_referrals, repo_user, timestamp, client, growth_service = service_and_mocks
    referral_user = SimpleNamespace(
        tg_id=10,
        referrer_tg_id=20,
        days_pending=5,
        bonus_is_received=False,
    )
    referral_referrer = SimpleNamespace(
        tg_id=20,
        referrer_tg_id=None,
        paid_count=4,
    )
    repo_referrals.get.side_effect = [referral_user, referral_user, referral_referrer]

    with patch.object(service, "grant_bonus_to_user", new=AsyncMock()) as grant_bonus:
        result = await service.grant_pending_and_referrer_bonus(10)

    assert result == (5, 20, 15)
    growth_service.apply_pending_referral_rewards.assert_awaited_once_with(beneficiary_tg_id=10)
    grant_bonus.assert_any_await(10, 5)
    assert grant_bonus.await_args_list[1].args == (20, 15)
    assert grant_bonus.await_args_list[1].kwargs["reward_context"].trigger_type == "first_paid_order"


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (3, 10),
        (5, 15),
        (10, 31),
        (15, 62),
        (1, 7),
    ],
)
def test_calc_referrer_bonus_uses_current_thresholds(service_and_mocks, count, expected):
    service, *_ = service_and_mocks
    assert service._calc_referrer_bonus(count) == expected


@pytest.mark.asyncio
async def test_grant_bonus_to_user_syncs_reward_context(service_and_mocks):
    service, repo_referrals, repo_user, timestamp, client, growth_service = service_and_mocks
    growth_service.sync_flags = SimpleNamespace(growth_sync_enabled=True)
    active_user = SimpleNamespace(tg_id=2, email="b@c.com", expiration_date=300)
    repo_user.get.return_value = active_user
    timestamp.current_timestamp.return_value = 100

    context = ReferralRewardContext(
        referred_tg_id=2,
        referrer_tg_id=9,
        trigger_type="invite_registered",
        trigger_ref="2",
    )
    await service.grant_bonus_to_user(2, 4, reward_context=context)

    growth_service.sync_referral_reward.assert_awaited_once_with(
        beneficiary_tg_id=2,
        reward_days=4,
        context=context,
        applied=True,
    )


@pytest.mark.asyncio
async def test_grant_bonus_to_user_uses_growth_sync_for_inactive_user_when_enabled(service_and_mocks):
    service, repo_referrals, repo_user, timestamp, client, growth_service = service_and_mocks
    growth_service.sync_flags = SimpleNamespace(growth_sync_enabled=True)
    repo_user.get.return_value = SimpleNamespace(tg_id=3, email="c@d.com", expiration_date=None)
    timestamp.current_timestamp.return_value = 100

    context = ReferralRewardContext(
        referred_tg_id=3,
        referrer_tg_id=8,
        trigger_type="invite_registered",
        trigger_ref="3",
    )

    await service.grant_bonus_to_user(3, 5, reward_context=context)

    repo_referrals.update_days_pending.assert_not_awaited()
    growth_service.sync_referral_reward.assert_awaited_once_with(
        beneficiary_tg_id=3,
        reward_days=5,
        context=context,
        applied=False,
    )
