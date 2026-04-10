from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.access.access_issuance_service import AccessIssuanceService


@pytest.fixture
def service_and_mocks():
    access_grant_repository = AsyncMock()
    access_grant_repository.get_by_source.return_value = None
    subscription_flow_service = AsyncMock()
    traffic_limited_service = AsyncMock()
    standard_user_subscription_service = AsyncMock()
    service = AccessIssuanceService(
        access_grant_repository=access_grant_repository,
        subscription_flow_service=subscription_flow_service,
        traffic_limited_service=traffic_limited_service,
        standard_user_subscription_service=standard_user_subscription_service,
    )
    return (
        service,
        access_grant_repository,
        subscription_flow_service,
        traffic_limited_service,
        standard_user_subscription_service,
    )


@pytest.mark.asyncio
async def test_activate_from_payload_routes_standard_telegram_to_subscription_flow(service_and_mocks):
    service, access_grant_repository, subscription_flow_service, _, _ = service_and_mocks
    subscription_flow_service.activate_or_extend_subscription.return_value = ("updated", "details")
    service._resolve_target_user_id = AsyncMock(return_value=42)

    result = await service.activate_from_payload(
        payload="month1",
        source_type="request_approval",
        source_ref="request:1",
        tg_id=123,
    )

    assert result.activation_text == "updated"
    assert result.activation_details_text == "details"
    subscription_flow_service.activate_or_extend_subscription.assert_awaited_once_with(
        tg_id=123,
        period="month1",
    )
    access_grant_repository.record_grant.assert_awaited_once()
    _, kwargs = access_grant_repository.record_grant.await_args
    assert kwargs["user_id"] == 42


@pytest.mark.asyncio
async def test_activate_from_payload_routes_standard_web_payment_to_standard_service(service_and_mocks):
    service, access_grant_repository, _, _, standard_user_subscription_service = service_and_mocks
    standard_user_subscription_service.activate_payment.return_value = type(
        "Result",
        (),
        {
            "user_id": 42,
            "expires_at": datetime(2026, 4, 9, 15, 0, tzinfo=timezone.utc),
            "was_created": True,
        },
    )()

    result = await service.activate_from_payload(
        payload="month1",
        source_type="payment",
        source_ref="pay-1",
        user_id=42,
    )

    assert result.activation_text == "✅ Базовая конфигурация активирована"
    assert "Действует до:" in result.activation_details_text
    standard_user_subscription_service.activate_payment.assert_awaited_once_with(
        user_id=42,
        product="month1",
    )
    access_grant_repository.record_grant.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_from_payload_skips_reapplying_existing_source(service_and_mocks):
    service, access_grant_repository, subscription_flow_service, _, _ = service_and_mocks
    access_grant_repository.get_by_source.return_value = type("Grant", (), {"id": 1})()

    result = await service.activate_from_payload(
        payload="month1",
        source_type="payment",
        source_ref="pay-1",
        tg_id=123,
        user_id=42,
    )

    assert result.activation_text == "✅ Базовая конфигурация уже активирована"
    subscription_flow_service.activate_or_extend_subscription.assert_not_awaited()
    access_grant_repository.record_grant.assert_not_awaited()


@pytest.mark.asyncio
async def test_activate_from_payload_routes_traffic_limited_to_traffic_service(service_and_mocks):
    service, access_grant_repository, _, traffic_limited_service, _ = service_and_mocks
    traffic_limited_service.activate_source_for_user.return_value = type(
        "Result",
        (),
        {
            "user_id": 77,
            "granted_bytes": 15 * 1024 * 1024 * 1024,
            "remaining_bytes": 35 * 1024 * 1024 * 1024,
            "expires_at": None,
        },
    )()

    result = await service.activate_from_payload(
        payload="traffic_limited15gb",
        source_type="request_approval",
        source_ref="request:2",
        user_id=77,
    )

    assert result.activation_text == "✅ Конфигурация с лимитом трафика активирована: +15 GB"
    assert result.activation_details_text == "Остаток: 35 GB\nДействует до: без ограничения по сроку"
    traffic_limited_service.activate_source_for_user.assert_awaited_once_with(
        user_id=77,
        product="traffic_limited15gb",
        source_type="request_approval",
        source_ref="request:2",
        duration_days_override=None,
        quota_bytes_override=None,
    )
    access_grant_repository.record_grant.assert_awaited_once()
