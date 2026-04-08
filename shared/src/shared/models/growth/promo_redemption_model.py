from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel


class PromoRedemption(SQLModel, table=True):
    __tablename__ = "promo_redemptions"
    __table_args__ = (
        UniqueConstraint("promo_code_id", "user_id", name="uq_promo_redemptions_code_user"),
        UniqueConstraint("subscription_grant_id", name="uq_promo_redemptions_grant"),
    )

    id: int | None = Field(default=None, primary_key=True)
    promo_code_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("promo_codes.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    redeemed_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    subscription_grant_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("subscription_grants.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

