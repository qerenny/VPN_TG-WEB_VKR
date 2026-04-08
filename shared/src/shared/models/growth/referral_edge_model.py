from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ReferralEdge(SQLModel, table=True):
    __tablename__ = "referral_edges"
    __table_args__ = (
        UniqueConstraint("referred_user_id", name="uq_referral_edges_referred_user"),
        UniqueConstraint(
            "referrer_user_id",
            "referred_user_id",
            name="uq_referral_edges_pair",
        ),
        CheckConstraint(
            "referrer_user_id <> referred_user_id",
            name="ck_referral_edges_distinct_users",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    referrer_user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    referred_user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    source: str = Field(sa_column=Column(Text, nullable=False))

