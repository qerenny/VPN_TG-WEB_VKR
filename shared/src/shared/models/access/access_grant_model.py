from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class AccessGrant(SQLModel, table=True):
    __tablename__ = "access_grants"
    __table_args__ = (
        UniqueConstraint("source_type", "source_ref", name="uq_access_grants_source"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    granted_by_user_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
    template_code: str = Field(sa_column=Column(Text, nullable=False))
    scope: str = Field(sa_column=Column(Text, nullable=False))
    entitlement_kind: str = Field(sa_column=Column(Text, nullable=False))
    source_type: str = Field(sa_column=Column(Text, nullable=False))
    source_ref: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(sa_column=Column(Text, nullable=False))
    expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    quota_bytes: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    activated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
