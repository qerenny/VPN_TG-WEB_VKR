from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared.services.access.access_request_service import AccessRequestService


@pytest.mark.asyncio
async def test_notify_reviewed_sends_single_user_message_for_approved_request():
    notification_service = AsyncMock()
    service = AccessRequestService(
        access_request_repository=AsyncMock(),
        access_grant_repository=AsyncMock(),
        access_issuance_service=AsyncMock(),
        notification_service=notification_service,
    )

    await service._notify_reviewed(
        SimpleNamespace(
            id=12,
            user_id=7,
            requested_template_code="month_1",
            request_kind="new_access",
            status="approved",
            review_note="Approved from Telegram admin panel",
            reviewed_by_actor="admin",
            metadata_json={"approved_template_code": "month_1"},
        )
    )

    notification_service.notify_user_request_reviewed.assert_awaited_once_with(
        user_id=7,
        request_id=12,
        status="approved",
        request_kind="new_access",
        template_code="month_1",
        review_note="Approved from Telegram admin panel",
        reviewed_by_actor="admin",
        auto_approved=False,
    )
    notification_service.notify_user_access_activated.assert_not_awaited()
