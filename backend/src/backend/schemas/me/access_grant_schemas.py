from __future__ import annotations

from pydantic import BaseModel


class WebAccessGrantResponse(BaseModel):
    id: int
    template_code: str
    template_label: str
    scope: str
    entitlement_kind: str
    source_type: str
    source_ref: str | None = None
    status: str
    expires_at: str | None = None
    quota_bytes: int | None = None
    granted_by_user_id: int | None = None
    created_at: str
    activated_at: str | None = None
    revoked_at: str | None = None
    metadata: dict


class WebAccessGrantListResponse(BaseModel):
    items: list[WebAccessGrantResponse]
