from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, Text
from sqlmodel import Field, SQLModel


class WebAuthChallenge(SQLModel, table=True):
    __tablename__ = "web_auth_challenges"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(sa_column=Column(Text, nullable=False))
    purpose: str = Field(sa_column=Column(Text, nullable=False))
    code_hash: str = Field(sa_column=Column(Text, nullable=False))
    request_ip: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    request_user_agent: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    failed_attempts: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    last_sent_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    consumed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
