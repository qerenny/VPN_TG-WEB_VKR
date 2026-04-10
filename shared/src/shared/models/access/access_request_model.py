from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel


class AccessRequest(SQLModel, table=True):
    __tablename__ = "access_requests"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    requested_template_code: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    access_grant_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("access_grants.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    channel: str = Field(sa_column=Column(Text, nullable=False))
    request_kind: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(sa_column=Column(Text, nullable=False))
    comment: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    review_note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    reviewed_by_actor: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    requested_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    reviewed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
