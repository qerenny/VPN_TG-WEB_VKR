from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean
from sqlmodel import Column, Field, ForeignKey, Relationship, SQLModel

if TYPE_CHECKING:
    from shared.migration_support.models.users.user_model import User


class Payment(SQLModel, table=True):
    payment_id: str = Field(primary_key=True)
    tg_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("user.tg_id", ondelete="CASCADE"))
    )
    status: str
    payload: str
    created_at: int = Field(sa_column=Column(BigInteger))
    confirmed: bool = Field(default=False, sa_column=Column(Boolean))
    method: str | None = Field(default=None)

    user: Optional["User"] = Relationship(
        back_populates="payments",
        sa_relationship_kwargs={
            "foreign_keys": "[Payment.tg_id]",
            "passive_deletes": True,
        },
    )
