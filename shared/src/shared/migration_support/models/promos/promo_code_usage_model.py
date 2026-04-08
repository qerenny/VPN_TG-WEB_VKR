from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from shared.migration_support.models.users.user_model import User


class PromoCodeUsage(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("tg_id", "code"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tg_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("user.tg_id", ondelete="CASCADE"))
    )
    code: str

    user: Optional["User"] = Relationship(
        back_populates="promo_code_usages",
        sa_relationship_kwargs={
            "foreign_keys": "[PromoCodeUsage.tg_id]",
            "passive_deletes": True,
        },
    )
