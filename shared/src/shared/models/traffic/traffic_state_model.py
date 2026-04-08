from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel


class TrafficState(SQLModel, table=True):
    __tablename__ = "traffic_state"

    vpn_client_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("vpn_clients.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    scope: str = Field(sa_column=Column(Text, nullable=False))
    allocated_bytes: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )
    used_bytes: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )
    remaining_bytes: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )
    expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    is_blocked: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False),
    )
    block_reason: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    last_provider_sync_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
