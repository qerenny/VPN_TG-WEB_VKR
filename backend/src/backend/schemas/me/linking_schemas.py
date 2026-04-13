from __future__ import annotations

from pydantic import BaseModel


class TelegramLinkStartResponse(BaseModel):
    status: str
    deep_link: str | None
    expires_at: str | None
    telegram_id: int | None
    telegram_username: str | None

class PublicLinkPreviewResponse(BaseModel):
    status: str
    purpose: str | None
    expires_at: str | None


class PublicLinkConsumeRequest(BaseModel):
    token: str


class PublicLinkConsumeResponse(BaseModel):
    status: str
    linked_user_id: int | None
