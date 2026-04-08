from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel


class TelegramAccount(SQLModel, table=True):
    __tablename__ = "telegram_accounts"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
    )
    telegram_id: int = Field(
        sa_column=Column(BigInteger, nullable=False, unique=True),
    )
    username: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    linked_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    first_seen_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_seen_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
