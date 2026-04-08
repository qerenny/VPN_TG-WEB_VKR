from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlmodel import Field, SQLModel


class PaymentOrder(SQLModel, table=True):
    __tablename__ = "payment_orders"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    plan_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    status: str = Field(sa_column=Column(Text, nullable=False))
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    currency: str = Field(sa_column=Column(String(3), nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    paid_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    fulfilled_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    idempotency_key: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True, unique=True),
    )
    subscription_grant_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("subscription_grants.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
