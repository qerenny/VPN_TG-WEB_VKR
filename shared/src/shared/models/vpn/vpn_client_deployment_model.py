from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Text
from sqlmodel import Field, SQLModel


class VpnClientDeployment(SQLModel, table=True):
    __tablename__ = "vpn_client_deployments"

    id: int | None = Field(default=None, primary_key=True)
    vpn_client_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("vpn_clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    access_point_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("vpn_access_points.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    external_client_id: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    external_remark: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    status: str = Field(sa_column=Column(Text, nullable=False))
    last_synced_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_error: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    removed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
