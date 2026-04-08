from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlmodel import Field, SQLModel


class PromoCode(SQLModel, table=True):
    __tablename__ = "promo_codes"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    plan_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    duration_days_override: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    max_redemptions: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    per_user_limit: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False),
    )
    valid_from: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    valid_until: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

