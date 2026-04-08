from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.referrals.referral_registration_service import (
    ReferralRegistrationService,
)


@pytest.fixture
def service_and_mocks():
    repo = AsyncMock()
    user_repo = AsyncMock()
    payment_repo = AsyncMock()
    promo_usage_repo = AsyncMock()
    validator = AsyncMock()
    bonuses = AsyncMock()
    sync_service = AsyncMock()
    service = ReferralRegistrationService(
        repo=repo,
        user_repo=user_repo,
        payment_repo=payment_repo,
        promo_usage_repo=promo_usage_repo,
        validator=validator,
        bonuses=bonuses,
        sync_service=sync_service,
    )
    return service, repo, user_repo, payment_repo, promo_usage_repo, validator, bonuses, sync_service


@pytest.mark.asyncio
async def test_register_user_creates_referral_and_grants_bonus_for_new_valid_code(service_and_mocks):
    service, repo, user_repo, payment_repo, promo_usage_repo, validator, bonuses, sync_service = service_and_mocks
    repo.get.return_value = None
    validator.is_valid_referral.return_value = True
    validator.is_code_new.return_value = (True, "code_activated")

    with patch(
        "telegram_bot.services.referrals.referral_registration_service.BOT_BONUS_NEW_USER_INT",
        5,
    ):
        result = await service.register_user(
            tg_id=1,
            referral_code=["/start", "2"],
            user_created=True,
        )

    repo.update_referrer.assert_awaited_once_with(1, 2)
    bonuses.grant_bonus_to_user.assert_awaited_once()
    assert bonuses.grant_bonus_to_user.await_args.args == (1, 5)
    assert bonuses.grant_bonus_to_user.await_args.kwargs["reward_context"].trigger_type == "invite_registered"
    assert result == (True, "code_activated")


@pytest.mark.asyncio
async def test_register_user_updates_existing_code_without_bonus_when_not_new(service_and_mocks):
    service, repo, user_repo, payment_repo, promo_usage_repo, validator, bonuses, sync_service = service_and_mocks
    repo.get.return_value = object()
    validator.is_valid_referral.return_value = True
    validator.is_code_new.return_value = (False, "code_updated")
    user_repo.get.return_value = SimpleNamespace(
        expiration_date=None,
        trial_date=None,
        news_channel_date=None,
    )
    payment_repo.has_any_for_user.return_value = False
    promo_usage_repo.has_any_for_user.return_value = False

    result = await service.register_user(
        tg_id=2,
        referral_code=["/start", "3"],
        user_created=True,
    )

    repo.create.assert_not_awaited()
    repo.update_referrer.assert_awaited_once_with(2, 3)
    bonuses.grant_bonus_to_user.assert_not_awaited()
    assert result == (True, "code_updated")


@pytest.mark.asyncio
async def test_register_user_returns_invalid_code_for_bad_referral(service_and_mocks):
    service, repo, user_repo, payment_repo, promo_usage_repo, validator, bonuses, sync_service = service_and_mocks
    repo.get.return_value = None
    validator.is_valid_referral.return_value = False

    result = await service.register_user(
        tg_id=3,
        referral_code=["/start", "2"],
        user_created=True,
    )

    repo.update_referrer.assert_not_awaited()
    bonuses.grant_bonus_to_user.assert_not_awaited()
    assert result == (False, "invalid_code")


@pytest.mark.asyncio
async def test_register_user_without_code_only_ensures_referral_exists(service_and_mocks):
    service, repo, user_repo, payment_repo, promo_usage_repo, validator, bonuses, sync_service = service_and_mocks
    repo.get.return_value = None

    result = await service.register_user(
        tg_id=4,
        referral_code=["/start"],
        user_created=False,
    )

    repo.create.assert_not_awaited()
    repo.update_referrer.assert_not_awaited()
    validator.is_valid_referral.assert_not_awaited()
    bonuses.grant_bonus_to_user.assert_not_awaited()
    assert result == (True, "no_code")


@pytest.mark.asyncio
async def test_register_user_allows_late_referral_for_existing_unused_user(service_and_mocks):
    service, repo, user_repo, payment_repo, promo_usage_repo, validator, bonuses, sync_service = service_and_mocks
    repo.get.return_value = SimpleNamespace(referrer_tg_id=None)
    user_repo.get.return_value = SimpleNamespace(
        expiration_date=None,
        trial_date=None,
        news_channel_date=None,
    )
    payment_repo.has_any_for_user.return_value = False
    promo_usage_repo.has_any_for_user.return_value = False
    validator.is_valid_referral.return_value = True
    validator.is_code_new.return_value = (True, "code_activated")

    result = await service.register_user(
        tg_id=5,
        referral_code=["/start", "9"],
        user_created=False,
    )

    repo.update_referrer.assert_awaited_once_with(5, 9)
    bonuses.grant_bonus_to_user.assert_awaited_once()
    assert result == (True, "code_activated")


@pytest.mark.asyncio
async def test_register_user_rejects_late_referral_after_trial(service_and_mocks):
    service, repo, user_repo, payment_repo, promo_usage_repo, validator, bonuses, sync_service = service_and_mocks
    repo.get.return_value = SimpleNamespace(referrer_tg_id=None)
    user_repo.get.return_value = SimpleNamespace(
        expiration_date=None,
        trial_date=123,
        news_channel_date=None,
    )

    result = await service.register_user(
        tg_id=5,
        referral_code=["/start", "9"],
        user_created=False,
    )

    validator.is_valid_referral.assert_not_awaited()
    repo.update_referrer.assert_not_awaited()
    bonuses.grant_bonus_to_user.assert_not_awaited()
    assert result == (False, "existing_user")


@pytest.mark.asyncio
async def test_register_user_rejects_late_referral_after_payment(service_and_mocks):
    service, repo, user_repo, payment_repo, promo_usage_repo, validator, bonuses, sync_service = service_and_mocks
    repo.get.return_value = SimpleNamespace(referrer_tg_id=None)
    user_repo.get.return_value = SimpleNamespace(
        expiration_date=None,
        trial_date=None,
        news_channel_date=None,
    )
    payment_repo.has_any_for_user.return_value = True
    promo_usage_repo.has_any_for_user.return_value = False

    result = await service.register_user(
        tg_id=5,
        referral_code=["/start", "9"],
        user_created=False,
    )

    validator.is_valid_referral.assert_not_awaited()
    repo.update_referrer.assert_not_awaited()
    bonuses.grant_bonus_to_user.assert_not_awaited()
    assert result == (False, "existing_user")


@pytest.mark.asyncio
async def test_register_user_rejects_late_referral_after_promo(service_and_mocks):
    service, repo, user_repo, payment_repo, promo_usage_repo, validator, bonuses, sync_service = service_and_mocks
    repo.get.return_value = SimpleNamespace(referrer_tg_id=None)
    user_repo.get.return_value = SimpleNamespace(
        expiration_date=None,
        trial_date=None,
        news_channel_date=None,
    )
    payment_repo.has_any_for_user.return_value = False
    promo_usage_repo.has_any_for_user.return_value = True

    result = await service.register_user(
        tg_id=5,
        referral_code=["/start", "9"],
        user_created=False,
    )

    validator.is_valid_referral.assert_not_awaited()
    repo.update_referrer.assert_not_awaited()
    bonuses.grant_bonus_to_user.assert_not_awaited()
    assert result == (False, "existing_user")
