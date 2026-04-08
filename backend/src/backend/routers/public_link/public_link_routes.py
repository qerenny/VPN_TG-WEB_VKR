from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from backend.auth.web_auth import require_web_user
from backend.bootstrap import get_linking_service
from backend.schemas.me.linking_schemas import (
    PublicLinkConsumeRequest,
    PublicLinkConsumeResponse,
    PublicLinkPreviewResponse,
)
from backend.services.auth.auth_service import AuthenticatedWebUser
from backend.services.linking.linking_service import LinkingService

router = APIRouter(prefix="/public/link", tags=["public-link"])


@router.get("/telegram/{token}", response_model=PublicLinkPreviewResponse)
async def preview_web_link(
    token: str,
    linking_service: LinkingService = Depends(get_linking_service),
):
    result = await linking_service.preview_web_link(raw_token=token)
    return PublicLinkPreviewResponse(**asdict(result))


@router.post("/consume", response_model=PublicLinkConsumeResponse)
async def consume_public_link(
    payload: PublicLinkConsumeRequest,
    principal: AuthenticatedWebUser = Depends(require_web_user),
    linking_service: LinkingService = Depends(get_linking_service),
):
    result = await linking_service.consume_web_link(
        raw_token=payload.token,
        current_user_id=principal.user_id,
    )
    return PublicLinkConsumeResponse(**asdict(result))
