from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class AccessRegistryEntry(SQLModel, table=True):
    __tablename__ = "access_registry_entries"
    __table_args__ = (
        UniqueConstraint("identity_type", "identity_value", name="uq_access_registry_identity"),
    )

    id: int | None = Field(default=None, primary_key=True)
    identity_type: str = Field(sa_column=Column(Text, nullable=False))
    identity_value: str = Field(sa_column=Column(Text, nullable=False))
    template_code: str = Field(sa_column=Column(Text, nullable=False))
    priority: int = Field(
        default=100,
        sa_column=Column(Integer, nullable=False, server_default="100"),
    )
    auto_approve: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    allow_auto_renew: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_by_actor: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    updated_by_actor: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    valid_from: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    valid_until: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
