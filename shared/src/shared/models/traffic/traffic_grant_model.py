from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel


class TrafficGrant(SQLModel, table=True):
    __tablename__ = "traffic_grants"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    vpn_client_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("vpn_clients.id", ondelete="CASCADE"),
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
    scope: str = Field(sa_column=Column(Text, nullable=False))
    source_type: str = Field(sa_column=Column(Text, nullable=False))
    source_ref: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(sa_column=Column(Text, nullable=False))
    granted_bytes: int = Field(sa_column=Column(BigInteger, nullable=False))
    expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    is_trial: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False),
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
