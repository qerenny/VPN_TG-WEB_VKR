from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.routers.public_link import public_link_routes
from backend.services.linking.linking_service import (
    PublicLinkConsumeResult,
    PublicLinkPreviewResult,
)


@pytest.mark.asyncio
async def test_preview_web_link_returns_payload():
    linking_service = SimpleNamespace(
        preview_web_link=AsyncMock(
            return_value=PublicLinkPreviewResult(
                status="pending",
                purpose="link_web",
                expires_at="2026-04-03T12:30:00+00:00",
            )
        )
    )

    result = await public_link_routes.preview_web_link(
        token="abc",
        linking_service=linking_service,
    )

    assert result.status == "pending"
    assert result.purpose == "link_web"


@pytest.mark.asyncio
async def test_consume_public_link_uses_current_web_user():
    linking_service = SimpleNamespace(
        consume_web_link=AsyncMock(
            return_value=PublicLinkConsumeResult(
                status="linked",
                linked_user_id=7,
            )
        )
    )
    principal = SimpleNamespace(user_id=7)

    result = await public_link_routes.consume_public_link(
        payload=public_link_routes.PublicLinkConsumeRequest(token="abc"),
        principal=principal,
        linking_service=linking_service,
    )

    assert result.status == "linked"
    linking_service.consume_web_link.assert_awaited_once_with(
        raw_token="abc",
        current_user_id=7,
    )
