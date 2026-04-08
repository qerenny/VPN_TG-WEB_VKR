from __future__ import annotations

from pydantic import BaseModel, Field


class WebPromoApplyRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100)


class WebPromoApplyResponse(BaseModel):
    status: str
    granted_days: int
    message: str
