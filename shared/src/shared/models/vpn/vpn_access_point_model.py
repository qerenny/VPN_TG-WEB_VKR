from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlmodel import Field, SQLModel

from shared.product_constants import PRODUCT_SCOPE_STANDARD


class VpnAccessPoint(SQLModel, table=True):
    __tablename__ = "vpn_access_points"

    id: int | None = Field(default=None, primary_key=True)
    control_plane_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("vpn_control_planes.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    location_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("vpn_locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    code: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    scope: str = Field(
        default=PRODUCT_SCOPE_STANDARD,
        sa_column=Column(Text, nullable=False),
    )
    kind: str = Field(sa_column=Column(Text, nullable=False))
    external_id: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    is_enabled: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False),
    )
    priority: int = Field(
        default=100,
        sa_column=Column(Integer, nullable=False),
    )
    capacity_limit: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
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
