from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

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


def test_serialize_traffic_limited_profile_returns_active_payload(service):
    now = datetime.now(timezone.utc)
    traffic_limited_client = SimpleNamespace(
        external_email="wl-user@example.com",
        external_client_uuid="wl-uuid-1",
        subscription_external_id="wl-sub-1",
    )
    traffic_limited_state = SimpleNamespace(
        allocated_bytes=1000,
        used_bytes=250,
        remaining_bytes=750,
        expires_at=now + timedelta(days=7),
        last_provider_sync_at=now,
        is_blocked=False,
    )

    payload = service._serialize_traffic_limited_profile(
        traffic_limited_client=traffic_limited_client,
        traffic_limited_state=traffic_limited_state,
        traffic_limited_subscription_link="https://frontend.example.com/subscription/traffic-limited/token",
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
async def test_execute_action_issues_access_override(monkeypatch, service):
    service.access_issuance_service = AsyncMock()
    service.access_issuance_service.activate_from_payload.return_value = SimpleNamespace(
        activation_text="granted",
        activation_details_text="details",
    )
    service._append_audit_log = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "backend.services.admin.admin_service.get_effective_product_feature_settings",
        lambda: SimpleNamespace(
            access_admin_override_enabled=True,
            standard_config_enabled=True,
            traffic_limited_config_enabled=True,
            commerce_enabled=True,
            referrals_enabled=True,
        ),
    )
    monkeypatch.setattr(
        service,
        "_load_active_plan",
        AsyncMock(return_value=SimpleNamespace(code="month_1", scope="standard", payload="month_1")),
    )

    result = await service.execute_action(
        principal=SimpleNamespace(actor="qa-admin", role="superadmin"),
        action_type="issue_access_override",
        target_user_id=7,
        target_tg_id=None,
        reason="manual recovery",
        dry_run=False,
        params={"template_code": "month_1"},
        redis_client=None,
    )

    service.access_issuance_service.activate_from_payload.assert_awaited_once()
    assert result["status"] == "success"
    assert result["summary"] == "granted"
    assert result["template_code"] == "month_1"


@pytest.mark.asyncio
async def test_safe_subscription_link_passes_scope(service):
    service.subscription_provisioning_service.get_subscription_link = AsyncMock(
        return_value="https://frontend.example.com/subscription/traffic-limited/token"
    )

    result = await service._safe_subscription_link(12345, scope="traffic_limited")

    assert result == "https://frontend.example.com/subscription/traffic-limited/token"
    service.subscription_provisioning_service.get_subscription_link.assert_awaited_once_with(
        12345,
        scope="traffic_limited",
    )


@pytest.mark.asyncio
async def test_execute_action_revokes_access(monkeypatch, service):
    service.standard_user_subscription_service = AsyncMock()
    service.standard_user_subscription_service.revoke_access.return_value = True
    service._append_audit_log = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "backend.services.admin.admin_service.get_effective_product_feature_settings",
        lambda: SimpleNamespace(
            access_admin_override_enabled=True,
            standard_config_enabled=True,
            traffic_limited_config_enabled=True,
            commerce_enabled=True,
            referrals_enabled=True,
        ),
    )
    monkeypatch.setattr(
        "backend.services.admin.admin_service.AccessGrantRepository",
        lambda: SimpleNamespace(revoke_user_scope_grants=AsyncMock()),
    )

    result = await service.execute_action(
        principal=SimpleNamespace(actor="qa-admin", role="superadmin"),
        action_type="revoke_access",
        target_user_id=7,
        target_tg_id=None,
        reason="cleanup",
        dry_run=False,
        params={"scope": "standard"},
        redis_client=None,
    )

    service.standard_user_subscription_service.revoke_access.assert_awaited_once_with(user_id=7)
    assert result["status"] == "success"
    assert result["scope"] == "standard"


@pytest.mark.asyncio
async def test_execute_action_rejects_extend_subscription_when_commerce_disabled(monkeypatch, service):
    monkeypatch.setattr(
        "backend.services.admin.admin_service.get_effective_product_feature_settings",
        lambda: SimpleNamespace(
            access_admin_override_enabled=True,
            standard_config_enabled=True,
            traffic_limited_config_enabled=True,
            commerce_enabled=False,
            referrals_enabled=False,
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_action(
            principal=SimpleNamespace(actor="qa-admin", role="superadmin"),
            action_type="extend_subscription",
            target_user_id=None,
            target_tg_id=404630971,
            reason="manual",
            dry_run=False,
            params={"period": "month1"},
            redis_client=None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Commerce module is disabled"


@pytest.mark.asyncio
async def test_execute_action_rejects_grant_compensation_days_when_commerce_disabled(monkeypatch, service):
    service._append_audit_log = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "backend.services.admin.admin_service.get_effective_product_feature_settings",
        lambda: SimpleNamespace(
            access_admin_override_enabled=True,
            standard_config_enabled=True,
            traffic_limited_config_enabled=True,
            commerce_enabled=False,
            referrals_enabled=False,
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_action(
            principal=SimpleNamespace(actor="qa-admin", role="superadmin"),
            action_type="grant_compensation_days",
            target_user_id=None,
            target_tg_id=404630971,
            reason="manual",
            dry_run=False,
            params={"days": 3},
            redis_client=None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Commerce module is disabled"
