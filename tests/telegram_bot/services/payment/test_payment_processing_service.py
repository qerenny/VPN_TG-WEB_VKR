from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.payments.payment_processing_service import PaymentProcessingService


@pytest.fixture
def service_and_mocks():
    access_issuance_service = AsyncMock()
    bonuses = AsyncMock()
    service = PaymentProcessingService(
        access_issuance_service,
        bonuses,
    )
    return service, access_issuance_service, bonuses


@pytest.mark.asyncio
async def test_payment_processing_returns_subscription_and_bonus_messages(service_and_mocks):
    service, access_issuance_service, bonuses = service_and_mocks
    access_issuance_service.activate_from_payload.return_value = type(
        "AccessResult",
        (),
        {"activation_text": "updated", "activation_details_text": "date"},
    )()
    bonuses.grant_pending_and_referrer_bonus.return_value = (5, 999, 3)

    with patch(
        "telegram_bot.services.payments.payment_processing_service.messages.get_random_message",
        return_value="Bonus {days}",
    ) as get_message:
        result = await service.payment_processing(tg_id=1, product="month1")

    assert result == ("updated", "date", "Bonus 5", "Bonus 3", 999)
    access_issuance_service.activate_from_payload.assert_awaited_once_with(
        payload="month1",
        source_type="payment",
        source_ref="month1",
        tg_id=1,
        user_id=None,
    )
    bonuses.grant_pending_and_referrer_bonus.assert_awaited_once_with(1)
    assert get_message.call_count == 2


@pytest.mark.asyncio
async def test_payment_processing_omits_bonus_messages_when_nothing_granted(service_and_mocks):
    service, access_issuance_service, bonuses = service_and_mocks
    access_issuance_service.activate_from_payload.return_value = type(
        "AccessResult",
        (),
        {"activation_text": "u", "activation_details_text": "d"},
    )()
    bonuses.grant_pending_and_referrer_bonus.return_value = (0, None, None)

    with patch(
        "telegram_bot.services.payments.payment_processing_service.messages.get_random_message",
    ) as get_message:
        result = await service.payment_processing(tg_id=2, product="year1")

    assert result == ("u", "d", None, None, None)
    get_message.assert_not_called()


@pytest.mark.asyncio
async def test_payment_processing_continues_when_bonus_flow_fails(service_and_mocks):
    service, access_issuance_service, bonuses = service_and_mocks
    access_issuance_service.activate_from_payload.return_value = type(
        "AccessResult",
        (),
        {"activation_text": "updated", "activation_details_text": "date"},
    )()
    bonuses.grant_pending_and_referrer_bonus.side_effect = Exception("bonus failed")

    result = await service.payment_processing(tg_id=7, product="month3")

    assert result == ("updated", "date", None, None, None)


@pytest.mark.asyncio
async def test_payment_processing_skips_bonus_flow_when_referrals_disabled(service_and_mocks):
    service, access_issuance_service, bonuses = service_and_mocks
    service.referrals_enabled = False
    access_issuance_service.activate_from_payload.return_value = type(
        "AccessResult",
        (),
        {"activation_text": "updated", "activation_details_text": "date"},
    )()

    with patch(
        "telegram_bot.services.payments.payment_processing_service.messages.get_random_message",
    ) as get_message:
        result = await service.payment_processing(tg_id=7, product="month3")

    assert result == ("updated", "date", None, None, None)
    bonuses.grant_pending_and_referrer_bonus.assert_not_awaited()
    get_message.assert_not_called()


@pytest.mark.asyncio
async def test_payment_processing_propagates_subscription_errors(service_and_mocks):
    service, access_issuance_service, bonuses = service_and_mocks
    access_issuance_service.activate_from_payload.side_effect = Exception("boom")

    with pytest.raises(Exception, match="boom"):
        await service.payment_processing(tg_id=9, product="month6")

    bonuses.grant_pending_and_referrer_bonus.assert_not_awaited()


@pytest.mark.asyncio
async def test_payment_processing_routes_traffic_limited_products_to_traffic_service(service_and_mocks):
    service, access_issuance_service, bonuses = service_and_mocks
    access_issuance_service.activate_from_payload.return_value = type(
        "AccessResult",
        (),
        {
            "activation_text": "✅ Конфигурация с лимитом трафика активирована: +15 GB",
            "activation_details_text": "Остаток: 35 GB\nДействует до: без ограничения по сроку",
        },
    )()

    result = await service.payment_processing(
        tg_id=1,
        product="traffic_limited15gb",
        payment_id="pay-wl-1",
    )

    assert result == (
        "✅ Конфигурация с лимитом трафика активирована: +15 GB",
        "Остаток: 35 GB\nДействует до: без ограничения по сроку",
        None,
        None,
        None,
    )
    access_issuance_service.activate_from_payload.assert_awaited_once_with(
        payload="traffic_limited15gb",
        source_type="payment",
        source_ref="pay-wl-1",
        tg_id=1,
        user_id=None,
    )
    bonuses.grant_pending_and_referrer_bonus.assert_not_awaited()
