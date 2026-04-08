from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.payments.payment_processing_service import PaymentProcessingService


@pytest.fixture
def service_and_mocks():
    subscription_manager = AsyncMock()
    bonuses = AsyncMock()
    whitelist_traffic_service = AsyncMock()
    service = PaymentProcessingService(
        subscription_manager,
        bonuses,
        whitelist_traffic_service=whitelist_traffic_service,
    )
    return service, subscription_manager, bonuses, whitelist_traffic_service


@pytest.mark.asyncio
async def test_payment_processing_returns_subscription_and_bonus_messages(service_and_mocks):
    service, subscription_manager, bonuses, _ = service_and_mocks
    subscription_manager.activate_or_extend_subscription.return_value = ("updated", "date")
    bonuses.grant_pending_and_referrer_bonus.return_value = (5, 999, 3)

    with patch(
        "telegram_bot.services.payments.payment_processing_service.messages.get_random_message",
        return_value="Bonus {days}",
    ) as get_message:
        result = await service.payment_processing(tg_id=1, product="month1")

    assert result == ("updated", "date", "Bonus 5", "Bonus 3", 999)
    subscription_manager.activate_or_extend_subscription.assert_awaited_once_with(
        tg_id=1,
        period="month1",
    )
    bonuses.grant_pending_and_referrer_bonus.assert_awaited_once_with(1)
    assert get_message.call_count == 2


@pytest.mark.asyncio
async def test_payment_processing_omits_bonus_messages_when_nothing_granted(service_and_mocks):
    service, subscription_manager, bonuses, _ = service_and_mocks
    subscription_manager.activate_or_extend_subscription.return_value = ("u", "d")
    bonuses.grant_pending_and_referrer_bonus.return_value = (0, None, None)

    with patch(
        "telegram_bot.services.payments.payment_processing_service.messages.get_random_message",
    ) as get_message:
        result = await service.payment_processing(tg_id=2, product="year1")

    assert result == ("u", "d", None, None, None)
    get_message.assert_not_called()


@pytest.mark.asyncio
async def test_payment_processing_continues_when_bonus_flow_fails(service_and_mocks):
    service, subscription_manager, bonuses, _ = service_and_mocks
    subscription_manager.activate_or_extend_subscription.return_value = ("updated", "date")
    bonuses.grant_pending_and_referrer_bonus.side_effect = Exception("bonus failed")

    result = await service.payment_processing(tg_id=7, product="month3")

    assert result == ("updated", "date", None, None, None)


@pytest.mark.asyncio
async def test_payment_processing_skips_bonus_flow_when_referrals_disabled(service_and_mocks):
    service, subscription_manager, bonuses, _ = service_and_mocks
    service.referrals_enabled = False
    subscription_manager.activate_or_extend_subscription.return_value = ("updated", "date")

    with patch(
        "telegram_bot.services.payments.payment_processing_service.messages.get_random_message",
    ) as get_message:
        result = await service.payment_processing(tg_id=7, product="month3")

    assert result == ("updated", "date", None, None, None)
    bonuses.grant_pending_and_referrer_bonus.assert_not_awaited()
    get_message.assert_not_called()


@pytest.mark.asyncio
async def test_payment_processing_propagates_subscription_errors(service_and_mocks):
    service, subscription_manager, bonuses, _ = service_and_mocks
    subscription_manager.activate_or_extend_subscription.side_effect = Exception("boom")

    with pytest.raises(Exception, match="boom"):
        await service.payment_processing(tg_id=9, product="month6")

    bonuses.grant_pending_and_referrer_bonus.assert_not_awaited()


@pytest.mark.asyncio
async def test_payment_processing_routes_whitelist_products_to_traffic_service(service_and_mocks):
    service, subscription_manager, bonuses, whitelist_traffic_service = service_and_mocks
    whitelist_traffic_service.activate_payment.return_value = type(
        "Result",
        (),
        {
            "granted_bytes": 15 * 1024 * 1024 * 1024,
            "remaining_bytes": 35 * 1024 * 1024 * 1024,
            "expires_at": None,
        },
    )()

    result = await service.payment_processing(
        tg_id=1,
        product="whitelist15gb",
        payment_id="pay-wl-1",
    )

    assert result == (
        "✅ Конфигурация с лимитом трафика активирована: +15 GB",
        "Остаток: 35 GB\nДействует до: без ограничения по сроку",
        None,
        None,
        None,
    )
    whitelist_traffic_service.activate_payment.assert_awaited_once_with(
        tg_id=1,
        product="whitelist15gb",
        payment_id="pay-wl-1",
    )
    subscription_manager.activate_or_extend_subscription.assert_not_awaited()
    bonuses.grant_pending_and_referrer_bonus.assert_not_awaited()
