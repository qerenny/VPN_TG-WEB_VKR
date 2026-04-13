from __future__ import annotations

from pydantic import BaseModel, Field


class WebLoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    device_name: str | None = None


class WebEmailRequest(BaseModel):
    email: str = Field(min_length=3)


class WebPublicLinkLoginRequest(BaseModel):
    token: str = Field(min_length=8)
    device_name: str | None = None


class WebRegisterVerifyRequest(BaseModel):
    email: str = Field(min_length=3)
    code: str = Field(default="", min_length=0)
    password: str = Field(min_length=1)
    device_name: str | None = None


class WebPasswordResetRequest(BaseModel):
    email: str = Field(min_length=3)
    code: str = Field(min_length=4)
    new_password: str = Field(min_length=1)


class WebMeResponse(BaseModel):
    user_id: int
    email: str | None = None
    email_verified: bool
    telegram_linked: bool
    telegram_id: int | None = None
    telegram_username: str | None = None
    display_name: str | None = None
    timezone: str | None = None
    locale: str | None = None
    marketing_opt_in: bool = False
    preferred_contact_email: str | None = None
    created_at: str
    last_login_at: str | None = None
