from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
import pytest

from backend.services.subscription.subscription_manager_service import (
    SubscriptionManagerService,
    TrafficLimitedSubscriptionSnapshot,
)


@pytest.mark.asyncio
async def test_get_subscription_formatted_info_includes_support_link():
    repo = AsyncMock()
    jwt_encoder = MagicMock()
    timestamp = MagicMock()

    jwt_encoder.decode.return_value = {"tg_id": 42, "email": "user@example.com"}
    repo.get.return_value = SimpleNamespace(
        email="user@example.com",
        expiration_date=1_800_000_000,
        sub_id="sub-42",
    )
    timestamp.current_timestamp.return_value = 1_700_000_000
    timestamp.calculate_time_difference.return_value = "10 дней"
    timestamp.timestamp_to_date.return_value = SimpleNamespace(
        replace=lambda **_: SimpleNamespace(strftime=lambda _fmt: "12:00:00 01-01-2027")
    )

    service = SubscriptionManagerService(
        repo=repo,
        jwt_encoder=jwt_encoder,
        timestamp=timestamp,
    )

    with (
        patch(
            "backend.services.subscription.subscription_manager_service.BACKEND_TELEGRAM_SUBSCRIPTION_LINK",
            "https://example.com/subscription/build",
        ),
        patch(
            "backend.services.subscription.subscription_manager_service.BOT_SUPPORT_TG_LINK",
            "https://t.me/remote_access_support",
        ),
    ):
        result = await service.get_subscription_formatted_info("jwt-token")

    assert result["sub_link"] == "https://example.com/subscription/build?uuid=sub-42"
    assert result["support_link"] == "https://t.me/remote_access_support"
    assert result["sub_is_active"] is True
    assert result["scope"] == "standard"
    assert result["traffic_remaining_bytes"] is None


@pytest.mark.asyncio
async def test_get_subscription_formatted_info_preserves_not_found_semantics():
    repo = AsyncMock()
    jwt_encoder = MagicMock()
    timestamp = MagicMock()

    jwt_encoder.decode.return_value = {"tg_id": 42, "email": "wrong@example.com"}
    repo.get.return_value = SimpleNamespace(
        email="user@example.com",
        expiration_date=1_800_000_000,
        sub_id="sub-42",
    )

    service = SubscriptionManagerService(
        repo=repo,
        jwt_encoder=jwt_encoder,
        timestamp=timestamp,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.get_subscription_formatted_info("jwt-token")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Email mismatch"


@pytest.mark.asyncio
async def test_get_subscription_formatted_info_builds_traffic_limited_link():
    repo = AsyncMock()
    jwt_encoder = MagicMock()
    timestamp = MagicMock()

    jwt_encoder.decode.return_value = {
        "tg_id": 42,
        "email": "wl@example.com",
        "scope": "traffic_limited",
    }
    timestamp.current_timestamp.return_value = 1_700_000_000_000
    timestamp.calculate_time_difference.return_value = "29 дней"
    timestamp.timestamp_to_date.return_value = SimpleNamespace(
        replace=lambda **_: SimpleNamespace(strftime=lambda _fmt: "12:00:00 01-01-2027")
    )

    service = SubscriptionManagerService(
        repo=repo,
        jwt_encoder=jwt_encoder,
        timestamp=timestamp,
    )

    with (
        patch.object(
            service,
            "_get_traffic_limited_snapshot",
            new=AsyncMock(
                return_value=TrafficLimitedSubscriptionSnapshot(
                    external_email="wl@example.com",
                    subscription_external_id="wl-sub-42",
                    expires_at_ms=1_800_000_000_000,
                    allocated_bytes=15 * 1024 * 1024 * 1024,
                    used_bytes=3 * 1024 * 1024 * 1024,
                    remaining_bytes=15 * 1024 * 1024,
                    is_blocked=False,
                )
            ),
        ),
        patch(
            "backend.services.subscription.subscription_manager_service.BACKEND_TELEGRAM_TRAFFIC_LIMITED_SUBSCRIPTION_LINK",
            "https://example.com/subscription/traffic-limited/build",
        ),
    ):
        result = await service.get_subscription_formatted_info(
            "jwt-token",
            scope="traffic_limited",
        )

    assert (
        result["sub_link"]
        == "https://example.com/subscription/traffic-limited/build?uuid=wl-sub-42"
    )
    assert result["sub_is_active"] is True
    assert result["scope"] == "traffic_limited"
    assert result["traffic_allocated_bytes"] == 15 * 1024 * 1024 * 1024
    assert result["traffic_used_bytes"] == 3 * 1024 * 1024 * 1024
    assert result["traffic_remaining_bytes"] == 15 * 1024 * 1024
    assert result["human_view_traffic_allocated"] == "15 GB"
    assert result["human_view_traffic_used"] == "3 GB"
    assert result["human_view_traffic_remaining"] == "15 MB"


@pytest.mark.asyncio
async def test_get_subscription_formatted_info_rejects_scope_mismatch():
    repo = AsyncMock()
    jwt_encoder = MagicMock()
    timestamp = MagicMock()

    jwt_encoder.decode.return_value = {
        "tg_id": 42,
        "email": "user@example.com",
        "scope": "traffic_limited",
    }

    service = SubscriptionManagerService(
        repo=repo,
        jwt_encoder=jwt_encoder,
        timestamp=timestamp,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.get_subscription_formatted_info("jwt-token", scope="standard")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Token scope mismatch"
