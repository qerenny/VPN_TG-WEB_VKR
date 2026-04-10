from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.access.access_lifecycle_service import AccessLifecycleService


@pytest.mark.asyncio
async def test_run_once_revokes_runtime_when_expired_grant_has_no_replacement(monkeypatch):
    access_grant_repository = AsyncMock()
    access_grant_repository.reconcile_expired_grants.return_value = [
        SimpleNamespace(id=10, user_id=7, scope="standard", template_code="month_1", metadata_json={}),
    ]
    access_grant_repository.has_active_scope_grant.return_value = False
    access_grant_repository.list_expiring_active_grants.return_value = []
    access_grant_repository.list_active_grants_by_source_types.return_value = []
    access_registry_repository = AsyncMock()
    access_registry_repository.list_active_entries.return_value = []
    access_issuance_service = AsyncMock()
    standard_service = AsyncMock()
    standard_service.revoke_access.return_value = True
    traffic_limited_service = AsyncMock()
    service = AccessLifecycleService(
        access_grant_repository=access_grant_repository,
        access_registry_repository=access_registry_repository,
        access_issuance_service=access_issuance_service,
        standard_user_subscription_service=standard_service,
        traffic_limited_service=traffic_limited_service,
    )
    monkeypatch.setattr(
        "telegram_bot.services.access.access_lifecycle_service.get_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=False, access_auto_renew_window_hours=24),
    )

    result = await service.run_once()

    standard_service.revoke_access.assert_awaited_once_with(user_id=7)
    assert result.expired_grants == 1
    assert result.runtime_revocations == 1
    assert result.registry_issued_grants == 0
    assert result.registry_revoked_grants == 0
    assert result.auto_renewed_grants == 0


@pytest.mark.asyncio
async def test_run_once_auto_renews_expiring_grant_when_registry_policy_allows(monkeypatch):
    access_grant_repository = AsyncMock()
    access_grant_repository.reconcile_expired_grants.return_value = []
    access_grant_repository.list_expiring_active_grants.return_value = [
        SimpleNamespace(
            id=22,
            user_id=7,
            scope="standard",
            template_code="month_1",
            metadata_json={"plan_payload": "month1"},
        ),
    ]
    access_grant_repository.get_by_source.return_value = None
    access_grant_repository.list_active_grants_by_source_types.return_value = []
    access_registry_repository = AsyncMock()
    access_registry_repository.find_auto_approve_match.return_value = SimpleNamespace(id=3)
    access_registry_repository.list_active_entries.return_value = []
    access_issuance_service = AsyncMock()
    service = AccessLifecycleService(
        access_grant_repository=access_grant_repository,
        access_registry_repository=access_registry_repository,
        access_issuance_service=access_issuance_service,
        standard_user_subscription_service=AsyncMock(),
        traffic_limited_service=AsyncMock(),
    )
    monkeypatch.setattr(
        "telegram_bot.services.access.access_lifecycle_service.get_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=True, access_auto_renew_window_hours=24),
    )

    result = await service.run_once()

    access_issuance_service.activate_from_payload.assert_awaited_once_with(
        payload="month1",
        source_type="access_registry_auto_renew",
        source_ref="access_auto_renew:22",
        user_id=7,
        channel_override="system",
        extra_metadata={
            "auto_renew": True,
            "renewed_from_grant_id": 22,
            "access_registry_entry_id": 3,
        },
    )
    assert result.auto_renewed_grants == 1
    assert result.registry_issued_grants == 0
    assert result.registry_revoked_grants == 0


@pytest.mark.asyncio
async def test_run_once_bootstraps_registry_managed_access_when_missing(monkeypatch):
    access_grant_repository = AsyncMock()
    access_grant_repository.reconcile_expired_grants.return_value = []
    access_grant_repository.list_expiring_active_grants.return_value = []
    access_grant_repository.list_active_grants_by_source_types.return_value = []
    access_grant_repository.has_active_scope_grant.return_value = False
    access_registry_repository = AsyncMock()
    access_registry_repository.list_active_entries.return_value = [
        SimpleNamespace(id=5, auto_approve=True),
    ]
    access_registry_repository.resolve_user_ids_for_entry.return_value = [7]
    access_issuance_service = AsyncMock()
    service = AccessLifecycleService(
        access_grant_repository=access_grant_repository,
        access_registry_repository=access_registry_repository,
        access_issuance_service=access_issuance_service,
        standard_user_subscription_service=AsyncMock(),
        traffic_limited_service=AsyncMock(),
    )
    monkeypatch.setattr(
        "telegram_bot.services.access.access_lifecycle_service.get_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=True, access_auto_renew_window_hours=24),
    )

    result = await service.run_once()

    access_issuance_service.activate_from_payload.assert_awaited_once()
    _, kwargs = access_issuance_service.activate_from_payload.await_args
    assert kwargs["source_type"] == "access_registry"
    assert kwargs["user_id"] == 7
    assert kwargs["extra_metadata"]["registry_bootstrap"] is True
    assert result.registry_issued_grants == 1


@pytest.mark.asyncio
async def test_run_once_revokes_registry_managed_access_when_entry_missing(monkeypatch):
    access_grant_repository = AsyncMock()
    access_grant_repository.reconcile_expired_grants.return_value = []
    access_grant_repository.list_expiring_active_grants.return_value = []
    access_grant_repository.list_active_grants_by_source_types.return_value = [
        SimpleNamespace(user_id=7, scope="standard"),
    ]
    access_grant_repository.has_active_scope_grant.return_value = False
    access_grant_repository.revoke_scope_grants_by_source_types.return_value = [SimpleNamespace(id=10)]
    access_registry_repository = AsyncMock()
    access_registry_repository.list_active_entries.return_value = []
    access_registry_repository.find_matching_entry_for_user.return_value = None
    standard_service = AsyncMock()
    standard_service.revoke_access.return_value = True
    service = AccessLifecycleService(
        access_grant_repository=access_grant_repository,
        access_registry_repository=access_registry_repository,
        access_issuance_service=AsyncMock(),
        standard_user_subscription_service=standard_service,
        traffic_limited_service=AsyncMock(),
    )
    monkeypatch.setattr(
        "telegram_bot.services.access.access_lifecycle_service.get_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=True, access_auto_renew_window_hours=24),
    )

    result = await service.run_once()

    access_grant_repository.revoke_scope_grants_by_source_types.assert_awaited_once()
    standard_service.revoke_access.assert_awaited_once_with(user_id=7)
    assert result.registry_revoked_grants == 1
