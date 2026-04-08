from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Integer, Text
from sqlmodel import Field, SQLModel


class SubscriptionGrant(SQLModel, table=True):
    __tablename__ = "subscription_grants"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    plan_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    source_type: str = Field(sa_column=Column(Text, nullable=False))
    source_ref: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(sa_column=Column(Text, nullable=False))
    duration_days: int = Field(sa_column=Column(Integer, nullable=False))
    expires_before: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    expires_after: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    applied_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
