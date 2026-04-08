from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.admin.admin_service import AdminService
from shared.config.settings import get_backend_settings


@pytest.fixture
def service():
    return AdminService(
        settings=get_backend_settings(),
        user_repository=AsyncMock(),
        payment_repository=AsyncMock(),
        referral_repository=AsyncMock(),
        promo_code_repository=AsyncMock(),
        jwt_encoder=AsyncMock(),
        timestamp=SimpleNamespace(current_timestamp=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)),
    )


def test_serialize_whitelist_profile_returns_active_payload(service):
    now = datetime.now(timezone.utc)
    whitelist_client = SimpleNamespace(
        external_email="wl-user@example.com",
        external_client_uuid="wl-uuid-1",
        subscription_external_id="wl-sub-1",
    )
    whitelist_state = SimpleNamespace(
        allocated_bytes=1000,
        used_bytes=250,
        remaining_bytes=750,
        expires_at=now + timedelta(days=7),
        last_provider_sync_at=now,
        is_blocked=False,
    )

    payload = service._serialize_whitelist_profile(
        whitelist_client=whitelist_client,
        whitelist_state=whitelist_state,
        whitelist_subscription_link="https://frontend.example.com/subscription/whitelist/token",
    )

    assert payload["is_enabled"] is True
    assert payload["email"] == "wl-user@example.com"
    assert payload["uuid"] == "wl-uuid-1"
    assert payload["sub_id"] == "wl-sub-1"
    assert payload["allocated_bytes"] == 1000
    assert payload["used_bytes"] == 250
    assert payload["remaining_bytes"] == 750
    assert payload["subscription_link"].endswith("/token")
    assert payload["raw_build_link"].endswith("?uuid=wl-sub-1")
    assert payload["is_active"] is True
    assert payload["is_blocked"] is False


@pytest.mark.asyncio
async def test_safe_subscription_link_passes_scope(service):
    service.subscription_provisioning_service.get_subscription_link = AsyncMock(
        return_value="https://frontend.example.com/subscription/whitelist/token"
    )

    result = await service._safe_subscription_link(12345, scope="whitelist")

    assert result == "https://frontend.example.com/subscription/whitelist/token"
    service.subscription_provisioning_service.get_subscription_link.assert_awaited_once_with(
        12345,
        scope="whitelist",
    )
