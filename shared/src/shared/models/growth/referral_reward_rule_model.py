from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer
from sqlmodel import Field, SQLModel


class ReferralRewardRule(SQLModel, table=True):
    __tablename__ = "referral_reward_rules"

    id: int | None = Field(default=None, primary_key=True)
    paid_referrals_threshold: int = Field(
        sa_column=Column(Integer, nullable=False, unique=True),
    )
    reward_days: int = Field(
        sa_column=Column(Integer, nullable=False),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False),
    )

