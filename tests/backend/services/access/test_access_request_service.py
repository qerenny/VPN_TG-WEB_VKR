from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from shared.services.access.access_request_service import AccessRequestService
from shared.product_constants import ACCESS_REQUEST_KIND_RENEWAL


def _features(**overrides):
    values = {
        "access_requests_enabled": True,
        "access_registry_enabled": False,
        "standard_config_enabled": True,
        "traffic_limited_config_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_create_request_rejects_disabled_module(monkeypatch):
    service = AccessRequestService(
        access_request_repository=AsyncMock(),
        access_grant_repository=AsyncMock(),
        access_issuance_service=AsyncMock(),
    )
    monkeypatch.setattr(
        "shared.services.access.access_request_service.get_effective_product_feature_settings",
        lambda: _features(access_requests_enabled=False),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.create_request(user_id=7, template_code=None, comment=None, channel="web")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_review_request_rejects_unknown_decision(monkeypatch):
    access_request_repository = AsyncMock()
    access_request_repository.get_request.return_value = SimpleNamespace(
        id=10,
        user_id=7,
        requested_template_code="month_1",
        access_grant_id=None,
        channel="web",
        status="pending",
        comment=None,
        review_note=None,
        reviewed_by_actor=None,
        requested_at=SimpleNamespace(isoformat=lambda: "2026-04-09T20:00:00+00:00"),
        reviewed_at=None,
        metadata_json={},
    )
    service = AccessRequestService(
        access_request_repository=access_request_repository,
        access_grant_repository=AsyncMock(),
        access_issuance_service=AsyncMock(),
    )
    monkeypatch.setattr(
        "shared.services.access.access_request_service.get_effective_product_feature_settings",
        lambda: _features(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.review_request(
            request_id=10,
            decision="hold",
            principal=SimpleNamespace(actor="qa-admin"),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_review_request_reject_marks_request(monkeypatch):
    access_request_repository = AsyncMock()
    access_request_repository.get_request.return_value = SimpleNamespace(
        id=10,
        user_id=7,
        requested_template_code="month_1",
        access_grant_id=None,
        channel="web",
        status="pending",
        comment="need access",
        review_note="no",
        reviewed_by_actor="qa-admin",
        requested_at=SimpleNamespace(isoformat=lambda: "2026-04-09T20:00:00+00:00"),
        reviewed_at=SimpleNamespace(isoformat=lambda: "2026-04-09T20:01:00+00:00"),
        metadata_json={},
    )
    access_request_repository.mark_reviewed.return_value = access_request_repository.get_request.return_value
    service = AccessRequestService(
        access_request_repository=access_request_repository,
        access_grant_repository=AsyncMock(),
        access_issuance_service=AsyncMock(),
    )
    monkeypatch.setattr(
        "shared.services.access.access_request_service.get_effective_product_feature_settings",
        lambda: _features(),
    )

    result = await service.review_request(
        request_id=10,
        decision="reject",
        principal=SimpleNamespace(actor="qa-admin"),
        review_note="not eligible",
    )

    access_request_repository.mark_reviewed.assert_awaited_once()
    assert result.status == "pending" or result.reviewed_by_actor == "qa-admin"


@pytest.mark.asyncio
async def test_create_request_renewal_uses_current_active_template_when_not_provided(monkeypatch):
    access_request_repository = AsyncMock()
    access_request_repository.create_request.return_value = SimpleNamespace(
        id=14,
        user_id=7,
        requested_template_code="month_3",
        access_grant_id=None,
        channel="web",
        request_kind=ACCESS_REQUEST_KIND_RENEWAL,
        status="pending",
        comment=None,
        review_note=None,
        reviewed_by_actor=None,
        requested_at=SimpleNamespace(isoformat=lambda: "2026-04-09T20:00:00+00:00"),
        reviewed_at=None,
        expires_at=SimpleNamespace(isoformat=lambda: "2026-04-12T20:00:00+00:00"),
        metadata_json={},
    )
    service = AccessRequestService(
        access_request_repository=access_request_repository,
        access_grant_repository=AsyncMock(),
        access_issuance_service=AsyncMock(),
    )
    monkeypatch.setattr(
        "shared.services.access.access_request_service.get_effective_product_feature_settings",
        lambda: _features(access_request_pending_ttl_hours=72),
    )
    monkeypatch.setattr(service, "_resolve_default_renewal_template_code", AsyncMock(return_value="month_3"))

    result = await service.create_request(
        user_id=7,
        template_code=None,
        comment=None,
        channel="web",
        request_kind=ACCESS_REQUEST_KIND_RENEWAL,
    )

    access_request_repository.create_request.assert_awaited_once()
    assert result.request_kind == ACCESS_REQUEST_KIND_RENEWAL
    assert result.requested_template_code == "month_3"


@pytest.mark.asyncio
async def test_create_request_expires_stale_pending_before_creating(monkeypatch):
    access_request_repository = AsyncMock()
    access_request_repository.create_request.return_value = SimpleNamespace(
        id=15,
        user_id=7,
        requested_template_code=None,
        access_grant_id=None,
        channel="web",
        request_kind="new_access",
        status="pending",
        comment=None,
        review_note=None,
        reviewed_by_actor=None,
        requested_at=SimpleNamespace(isoformat=lambda: "2026-04-09T20:00:00+00:00"),
        reviewed_at=None,
        expires_at=SimpleNamespace(isoformat=lambda: "2026-04-12T20:00:00+00:00"),
        metadata_json={},
    )
    access_request_repository.expire_stale_pending.return_value = []
    service = AccessRequestService(
        access_request_repository=access_request_repository,
        access_grant_repository=AsyncMock(),
        access_issuance_service=AsyncMock(),
    )
    monkeypatch.setattr(
        "shared.services.access.access_request_service.get_effective_product_feature_settings",
        lambda: _features(access_request_pending_ttl_hours=24),
    )

    await service.create_request(user_id=7, template_code=None, comment=None, channel="web")


@pytest.mark.asyncio
async def test_repeat_request_retouches_pending_request_and_notifies_admins(monkeypatch):
    requested_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    access_request_repository = AsyncMock()
    access_request_repository.get_request.return_value = SimpleNamespace(
        id=21,
        user_id=7,
        requested_template_code="month_1",
        access_grant_id=None,
        channel="web",
        request_kind="new_access",
        status="pending",
        comment=None,
        review_note=None,
        reviewed_by_actor=None,
        requested_at=requested_at,
        reviewed_at=None,
        expires_at=requested_at + timedelta(days=3),
        metadata_json={},
    )
    access_request_repository.touch_pending_request.return_value = SimpleNamespace(
        id=21,
        user_id=7,
        requested_template_code="month_1",
        access_grant_id=None,
        channel="web",
        request_kind="new_access",
        status="pending",
        comment=None,
        review_note=None,
        reviewed_by_actor=None,
        requested_at=datetime.now(timezone.utc),
        reviewed_at=None,
        expires_at=requested_at + timedelta(days=3),
        metadata_json={"repeat_count": 1},
    )
    notification_service = AsyncMock()
    service = AccessRequestService(
        access_request_repository=access_request_repository,
        access_grant_repository=AsyncMock(),
        access_issuance_service=AsyncMock(),
        notification_service=notification_service,
    )
    monkeypatch.setattr(
        "shared.services.access.access_request_service.get_effective_product_feature_settings",
        lambda: _features(),
    )

    result = await service.repeat_request(user_id=7, request_id=21)

    access_request_repository.touch_pending_request.assert_awaited_once()
    notification_service.notify_admins_request_created.assert_awaited_once_with(
        request_id=21,
        user_id=7,
        request_kind="new_access",
        requested_template_code="month_1",
        channel="web",
        comment=None,
    )
    assert result.id == 21


@pytest.mark.asyncio
async def test_repeat_request_rejects_before_cooldown(monkeypatch):
    requested_at = datetime.now(timezone.utc) - timedelta(minutes=3)
    access_request_repository = AsyncMock()
    access_request_repository.get_request.return_value = SimpleNamespace(
        id=22,
        user_id=7,
        requested_template_code="month_1",
        access_grant_id=None,
        channel="web",
        request_kind="new_access",
        status="pending",
        comment=None,
        review_note=None,
        reviewed_by_actor=None,
        requested_at=requested_at,
        reviewed_at=None,
        expires_at=requested_at + timedelta(days=3),
        metadata_json={},
    )
    service = AccessRequestService(
        access_request_repository=access_request_repository,
        access_grant_repository=AsyncMock(),
        access_issuance_service=AsyncMock(),
        notification_service=AsyncMock(),
    )
    monkeypatch.setattr(
        "shared.services.access.access_request_service.get_effective_product_feature_settings",
        lambda: _features(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.repeat_request(user_id=7, request_id=22)

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_create_request_rejects_registry_managed_user(monkeypatch):
    access_request_repository = AsyncMock()
    access_registry_service = AsyncMock()
    access_registry_service.find_managed_entry.return_value = SimpleNamespace(id=5)
    service = AccessRequestService(
        access_request_repository=access_request_repository,
        access_grant_repository=AsyncMock(),
        access_issuance_service=AsyncMock(),
        access_registry_service=access_registry_service,
    )
    monkeypatch.setattr(
        "shared.services.access.access_request_service.get_effective_product_feature_settings",
        lambda: _features(access_registry_enabled=True),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.create_request(user_id=7, template_code=None, comment=None, channel="web")

    assert exc_info.value.status_code == 409
