from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer, Text
from sqlmodel import Field, SQLModel


class VpnLocation(SQLModel, table=True):
    __tablename__ = "vpn_locations"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    label: str = Field(sa_column=Column(Text, nullable=False))
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False),
    )
    sort_order: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False),
    )

