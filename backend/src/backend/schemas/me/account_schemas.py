from __future__ import annotations

from pydantic import BaseModel, Field


class WebProfileResponse(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    locale: str | None = None
    marketing_opt_in: bool
    preferred_contact_email: str | None = None
    auth_email: str | None = None
    email_verified: bool


class WebProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    locale: str | None = None
    marketing_opt_in: bool | None = None
    preferred_contact_email: str | None = Field(default=None, min_length=0)


class WebLinksResponse(BaseModel):
    web: dict
    telegram: dict


class WebSubscriptionsResponse(BaseModel):
    standard: dict
    traffic_limited: dict
    access_policy: dict | None = None


class WebPaymentsResponse(BaseModel):
    items: list[dict]


class WebPlanCatalogResponse(BaseModel):
    standard: list[dict]
    traffic_limited: list[dict]


class WebReferralStatsResponse(BaseModel):
    invited_count: int
    paid_count: int
    pending_days: int
    referral_link: str | None = None
    telegram_linked: bool
