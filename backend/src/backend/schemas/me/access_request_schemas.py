from __future__ import annotations

from pydantic import BaseModel, Field


class WebAccessRequestCreateRequest(BaseModel):
    template_code: str | None = Field(default=None, min_length=1)
    request_kind: str = Field(default="new_access", min_length=1)
    comment: str | None = Field(default=None, max_length=1000)


class WebAccessRequestResponse(BaseModel):
    id: int
    user_id: int
    requested_template_code: str | None = None
    requested_template_label: str | None = None
    approved_template_label: str | None = None
    access_grant_id: int | None = None
    channel: str
    request_kind: str = "new_access"
    status: str
    comment: str | None = None
    review_note: str | None = None
    reviewed_by_actor: str | None = None
    requested_at: str
    reviewed_at: str | None = None
    expires_at: str | None = None
    metadata: dict = Field(default_factory=dict)


class WebAccessRequestListResponse(BaseModel):
    items: list[WebAccessRequestResponse]


class WebAccessRequestRepeatResponse(WebAccessRequestResponse):
    pass
