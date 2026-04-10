from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.access.telegram_access_request_service import TelegramAccessRequestService


@pytest.mark.asyncio
async def test_create_or_get_pending_request_delegates_to_backend_service():
    user_repository = AsyncMock()
    user_repository.get_app_user_id.return_value = 7
    access_request_service = AsyncMock()
    access_request_service.list_user_requests.return_value = []
    access_request_service.create_request.return_value = SimpleNamespace(
        id=12,
        user_id=7,
        requested_template_code="month_1",
        status="pending",
        channel="telegram",
        request_kind="new_access",
        comment="need access",
        review_note=None,
        reviewed_by_actor=None,
        requested_at="2026-04-09T21:01:00+00:00",
        reviewed_at=None,
        expires_at="2026-04-12T21:01:00+00:00",
        metadata={},
    )
    service = TelegramAccessRequestService(
        user_repository=user_repository,
        access_request_service=access_request_service,
        access_grant_repository=AsyncMock(),
    )

    snapshot, created = await service.create_or_get_pending_request(
        tg_id=42,
        template_code="month_1",
        request_kind="new_access",
    )

    assert created is True
    assert snapshot.id == 12
    assert snapshot.requested_template_code == "month_1"
    assert snapshot.request_kind == "new_access"
    access_request_service.create_request.assert_awaited_once_with(
        user_id=7,
        template_code="month_1",
        request_kind="new_access",
        comment=None,
        channel="telegram",
    )


@pytest.mark.asyncio
async def test_create_or_get_pending_request_returns_existing_when_latest_request_matches():
    user_repository = AsyncMock()
    user_repository.get_app_user_id.return_value = 7
    existing = SimpleNamespace(
        id=11,
        user_id=7,
        requested_template_code=None,
        status="pending",
        channel="telegram",
        request_kind="renewal",
        comment=None,
        review_note=None,
        reviewed_by_actor=None,
        requested_at="2026-04-09T21:00:00+00:00",
        reviewed_at=None,
        expires_at="2026-04-12T21:00:00+00:00",
        metadata={},
    )
    access_request_service = AsyncMock()
    access_request_service.list_user_requests.return_value = [existing]
    access_request_service.create_request.return_value = existing
    service = TelegramAccessRequestService(
        user_repository=user_repository,
        access_request_service=access_request_service,
        access_grant_repository=AsyncMock(),
    )

    snapshot, created = await service.create_or_get_pending_request(tg_id=42, request_kind="renewal")

    assert created is False
    assert snapshot.id == 11
    assert snapshot.request_kind == "renewal"


@pytest.mark.asyncio
async def test_create_or_get_pending_request_preserves_auto_approved_metadata():
    user_repository = AsyncMock()
    user_repository.get_app_user_id.return_value = 7
    access_request_service = AsyncMock()
    access_request_service.list_user_requests.return_value = []
    access_request_service.create_request.return_value = SimpleNamespace(
        id=13,
        user_id=7,
        requested_template_code="month_1",
        status="approved",
        channel="telegram",
        request_kind="new_access",
        comment=None,
        review_note="Auto-approved by access registry",
        reviewed_by_actor="access_registry",
        requested_at="2026-04-09T21:02:00+00:00",
        reviewed_at="2026-04-09T21:02:01+00:00",
        expires_at=None,
        metadata={"auto_approved": True, "approved_template_code": "month_1"},
    )
    service = TelegramAccessRequestService(
        user_repository=user_repository,
        access_request_service=access_request_service,
        access_grant_repository=AsyncMock(),
    )

    snapshot, created = await service.create_or_get_pending_request(tg_id=42)

    assert created is True
    assert snapshot.status == "approved"
    assert snapshot.reviewed_by_actor == "access_registry"
    assert snapshot.metadata["auto_approved"] is True
    assert snapshot.metadata["approved_template_code"] == "month_1"


@pytest.mark.asyncio
async def test_has_active_access_checks_active_grants():
    user_repository = AsyncMock()
    user_repository.get_app_user_id.return_value = 7
    access_grant_repository = AsyncMock()
    access_grant_repository.list_active_user_grants.return_value = [SimpleNamespace(id=1)]
    service = TelegramAccessRequestService(
        user_repository=user_repository,
        access_request_service=AsyncMock(),
        access_grant_repository=access_grant_repository,
    )

    assert await service.has_active_access(tg_id=42) is True
    access_grant_repository.list_active_user_grants.assert_awaited_once_with(user_id=7, limit=1)
