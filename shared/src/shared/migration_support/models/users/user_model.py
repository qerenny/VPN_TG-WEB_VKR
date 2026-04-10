import uuid
from typing import List, Optional

from sqlalchemy import BigInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Column, Field, Relationship, SQLModel

from shared.migration_support.models.payments.payment_model import Payment
from shared.migration_support.models.promos.promo_code_usage_model import PromoCodeUsage
from shared.migration_support.models.referrals.referral_model import Referral


class User(SQLModel, table=True):
    tg_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    uuid: str = Field(
        default_factory=lambda: str(uuid.uuid4()), sa_column=Column(UUID(as_uuid=False))
    )
    email: str
    expiration_date: Optional[int] = Field(default=None, sa_column=Column(BigInteger))
    login_date: int = Field(sa_column=Column(BigInteger))
    trial_date: Optional[int] = Field(default=None, sa_column=Column(BigInteger))
    info_channel_date: Optional[int] = Field(default=None, sa_column=Column(BigInteger))
    sub_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), sa_column=Column(Text)
    )

    referral: Optional["Referral"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "foreign_keys": lambda: [Referral.tg_id],
            "passive_deletes": True,
        },
    )

    referred_users: List["Referral"] = Relationship(
        back_populates="referrer",
        sa_relationship_kwargs={
            "foreign_keys": "Referral.referrer_tg_id",
            "passive_deletes": True,
        },
    )

    payments: Optional[List["Payment"]] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "foreign_keys": lambda: [Payment.tg_id],
            "passive_deletes": True,
        },
    )
    promo_code_usages: Optional[List["PromoCodeUsage"]] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "foreign_keys": "[PromoCodeUsage.tg_id]",
            "passive_deletes": True,
        },
    )
