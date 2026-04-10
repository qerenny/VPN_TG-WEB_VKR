from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AdminActionRequest(BaseModel):
    action_type: str = Field(min_length=1)
    target_user_id: int | None = None
    target_tg_id: int | None = None
    reason: str | None = None
    dry_run: bool = False
    params: dict[str, Any] = Field(default_factory=dict)


class AdminLoginRequest(BaseModel):
    token: str = Field(min_length=1)
    actor: str | None = None


class AdminPromoCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    plan_id: int | None = None
    duration_days_override: int | None = None
    max_redemptions: int | None = None
    per_user_limit: int = 1
    valid_from: str | None = None
    valid_until: str | None = None


class AdminPromoToggleRequest(BaseModel):
    is_active: bool


class AdminAccessRequestReviewRequest(BaseModel):
    decision: str = Field(min_length=1)
    review_note: str | None = Field(default=None, max_length=1000)
    template_code: str | None = Field(default=None, min_length=1)


class AdminAccessRegistryUpsertRequest(BaseModel):
    identity_type: str = Field(min_length=1)
    identity_value: str = Field(min_length=1)
    auto_approve: bool = True
    allow_auto_renew: bool = False
    is_active: bool = True
    note: str | None = Field(default=None, max_length=1000)


class AdminAccessRegistryUpdateRequest(BaseModel):
    identity_type: str = Field(min_length=1)
    identity_value: str = Field(min_length=1)
    auto_approve: bool = True
    allow_auto_renew: bool = False
    is_active: bool = True
    note: str | None = Field(default=None, max_length=1000)


class AdminAccessRegistryBatchUpsertRequest(BaseModel):
    identities_text: str = Field(min_length=1)
    auto_approve: bool = True
    allow_auto_renew: bool = False
    is_active: bool = True
    note: str | None = Field(default=None, max_length=1000)
