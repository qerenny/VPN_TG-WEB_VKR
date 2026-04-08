from __future__ import annotations

from decimal import Decimal

from sqlalchemy import BigInteger, JSON, Boolean, Column, Integer, Numeric, String, Text
from sqlmodel import Field, SQLModel

from shared.product_constants import ENTITLEMENT_KIND_TIME, PRODUCT_SCOPE_STANDARD


class Plan(SQLModel, table=True):
    __tablename__ = "plans"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    name: str = Field(sa_column=Column(Text, nullable=False))
    kind: str = Field(sa_column=Column(Text, nullable=False))
    legacy_payload: str = Field(
        default="",
        sa_column=Column(Text, nullable=False),
    )
    scope: str = Field(
        default=PRODUCT_SCOPE_STANDARD,
        sa_column=Column(Text, nullable=False),
    )
    entitlement_kind: str = Field(
        default=ENTITLEMENT_KIND_TIME,
        sa_column=Column(Text, nullable=False),
    )
    duration_days: int = Field(sa_column=Column(Integer, nullable=False))
    quota_bytes: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    price_amount: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(12, 2), nullable=True),
    )
    currency: str | None = Field(
        default=None,
        sa_column=Column(String(3), nullable=True),
    )
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
