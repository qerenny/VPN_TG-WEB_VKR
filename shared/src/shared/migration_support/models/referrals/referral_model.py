from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean
from sqlmodel import Column, Field, ForeignKey, Relationship, SQLModel

if TYPE_CHECKING:
    from shared.migration_support.models.users.user_model import User


class Referral(SQLModel, table=True):
    tg_id: int = Field(
        sa_column=Column(
            BigInteger, ForeignKey("user.tg_id", ondelete="CASCADE"), primary_key=True
        )
    )

    referrer_tg_id: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, ForeignKey("user.tg_id"), nullable=True),
    )

    days_pending: Optional[int] = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=True),
    )

    invited_count: Optional[int] = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=True),
    )

    paid_count: Optional[int] = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=True),
    )

    bonus_is_received: Optional[bool] = Field(
        default=False,
        sa_column=Column(Boolean, nullable=True),
    )

    user: Optional["User"] = Relationship(
        back_populates="referral",
        sa_relationship_kwargs={
            "foreign_keys": "[Referral.tg_id]",
            "passive_deletes": True,
        },
    )

    referrer: Optional["User"] = Relationship(
        back_populates="referred_users",
        sa_relationship_kwargs={
            "foreign_keys": "[Referral.referrer_tg_id]",
            "passive_deletes": True,
        },
    )
