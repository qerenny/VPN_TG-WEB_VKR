from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, Text
from sqlmodel import Field, SQLModel


class AdminAuditLog(SQLModel, table=True):
    __tablename__ = "admin_audit_log"

    id: int | None = Field(default=None, primary_key=True)
    actor: str = Field(sa_column=Column(Text, nullable=False))
    actor_role: str = Field(sa_column=Column(Text, nullable=False))
    action_type: str = Field(sa_column=Column(Text, nullable=False))
    target_tg_id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True, index=True),
    )
    status: str = Field(sa_column=Column(Text, nullable=False))
    reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    dry_run: bool = Field(default=False)
    summary: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
