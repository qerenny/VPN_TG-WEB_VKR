from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Text
from sqlmodel import Field, SQLModel

from shared.product_constants import PRODUCT_SCOPE_STANDARD


class VpnControlPlane(SQLModel, table=True):
    __tablename__ = "vpn_control_planes"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    scope: str = Field(
        default=PRODUCT_SCOPE_STANDARD,
        sa_column=Column(Text, nullable=False),
    )
    server_name: str = Field(
        default="",
        sa_column=Column(Text, nullable=False),
    )
    provider: str = Field(sa_column=Column(Text, nullable=False))
    api_base_url: str = Field(sa_column=Column(Text, nullable=False))
    subscription_base_url: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    is_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False),
    )
    accepts_new_deployments: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False),
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
