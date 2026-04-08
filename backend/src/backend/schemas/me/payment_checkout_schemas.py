from __future__ import annotations

from pydantic import BaseModel


class WebCheckoutRequest(BaseModel):
    plan_code: str
    method: str


class WebCheckoutResponse(BaseModel):
    payment_id: str
    status: str
    checkout_url: str
    provider: str
    plan_code: str
    plan_name: str
    scope: str
    amount: str
    currency: str
