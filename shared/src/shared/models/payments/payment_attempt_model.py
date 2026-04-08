from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel


class PaymentAttempt(SQLModel, table=True):
    __tablename__ = "payment_attempts"

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("payment_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    provider: str = Field(sa_column=Column(Text, nullable=False))
    provider_payment_id: str = Field(sa_column=Column(Text, nullable=False))
    provider_status: str = Field(sa_column=Column(Text, nullable=False))
    provider_payload_json: dict = Field(
        default_factory=dict,
        sa_column=Column("provider_payload", JSON, nullable=False),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    paid_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
