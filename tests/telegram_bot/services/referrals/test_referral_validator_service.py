from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.referrals.referral_validator_service import ReferralValidatorService


@pytest.fixture
def service_and_repo():
    repo = AsyncMock()
    service = ReferralValidatorService(repo=repo)
    return service, repo


@pytest.mark.asyncio
async def test_is_valid_referral_rejects_invalid_format(service_and_repo):
    service, repo = service_and_repo

    result = await service.is_valid_referral(123, "abc")

    assert result is False
    repo.get.assert_not_called()
    repo.is_symmetrical_referral.assert_not_called()


@pytest.mark.asyncio
async def test_is_valid_referral_rejects_self_referral(service_and_repo):
    service, repo = service_and_repo

    result = await service.is_valid_referral(123, "123")

    assert result is False
    repo.get.assert_not_called()
    repo.is_symmetrical_referral.assert_not_called()


@pytest.mark.asyncio
async def test_is_valid_referral_requires_existing_referrer(service_and_repo):
    service, repo = service_and_repo
    repo.get.return_value = None

    result = await service.is_valid_referral(123, "456")

    assert result is False
    repo.get.assert_awaited_once_with(456)
    repo.is_symmetrical_referral.assert_not_called()


@pytest.mark.asyncio
async def test_is_valid_referral_rejects_symmetrical_referral(service_and_repo):
    service, repo = service_and_repo
    repo.get.return_value = SimpleNamespace()
    repo.is_symmetrical_referral.return_value = True

    result = await service.is_valid_referral(1, "2")

    assert result is False
    repo.get.assert_awaited_once_with(2)
    repo.is_symmetrical_referral.assert_awaited_once_with(tg_id=1, referrer_tg_id=2)


@pytest.mark.asyncio
async def test_is_valid_referral_accepts_normal_referral(service_and_repo):
    service, repo = service_and_repo
    repo.get.return_value = SimpleNamespace()
    repo.is_symmetrical_referral.return_value = False

    result = await service.is_valid_referral(1, "002")

    assert result is True
    repo.get.assert_awaited_once_with(2)
    repo.is_symmetrical_referral.assert_awaited_once_with(tg_id=1, referrer_tg_id=2)


@pytest.mark.asyncio
async def test_is_code_new_returns_activation_for_fresh_code(service_and_repo):
    service, repo = service_and_repo
    repo.get.return_value = SimpleNamespace(referrer_tg_id=None)

    result = await service.is_code_new(123, 456)

    assert result == (True, "code_activated")
    repo.get.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_is_code_new_returns_updated_for_existing_code(service_and_repo):
    service, repo = service_and_repo
    repo.get.return_value = SimpleNamespace(referrer_tg_id=111)

    result = await service.is_code_new(123, 456)

    assert result == (False, "code_updated")
    repo.get.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_is_code_new_raises_when_user_missing(service_and_repo):
    service, repo = service_and_repo
    repo.get.return_value = None

    with pytest.raises(AttributeError):
        await service.is_code_new(123, 456)

    repo.get.assert_awaited_once_with(123)
