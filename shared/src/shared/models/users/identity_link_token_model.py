from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel


class IdentityLinkToken(SQLModel, table=True):
    __tablename__ = "identity_link_tokens"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    )
    purpose: str = Field(sa_column=Column(Text, nullable=False))
    token_hash: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    issued_by_channel: str = Field(sa_column=Column(Text, nullable=False))
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    used_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
