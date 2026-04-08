from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel


class PaymentWebhookEvent(SQLModel, table=True):
    __tablename__ = "payment_webhook_events"

    id: int | None = Field(default=None, primary_key=True)
    attempt_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("payment_attempts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    provider: str = Field(sa_column=Column(Text, nullable=False))
    provider_payment_id: str = Field(sa_column=Column(Text, nullable=False))
    provider_event_id: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    payload_hash: str = Field(sa_column=Column(Text, nullable=False))
    provider_status: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    payload_json: dict = Field(
        default_factory=dict,
        sa_column=Column("payload", JSON, nullable=False),
    )
    received_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    processed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
