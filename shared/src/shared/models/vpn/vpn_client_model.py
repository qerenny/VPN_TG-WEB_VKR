from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel

from shared.product_constants import PRODUCT_SCOPE_STANDARD


class VpnClient(SQLModel, table=True):
    __tablename__ = "vpn_clients"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    )
    scope: str = Field(
        default=PRODUCT_SCOPE_STANDARD,
        sa_column=Column(Text, nullable=False),
    )
    provider: str = Field(sa_column=Column(Text, nullable=False))
    external_client_uuid: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    external_email: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    subscription_external_id: str = Field(
        sa_column=Column(Text, nullable=False, unique=True),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deactivated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
