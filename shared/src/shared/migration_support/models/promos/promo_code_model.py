from typing import Optional

from sqlalchemy import Column, Integer
from sqlmodel import Field, SQLModel


class PromoCode(SQLModel, table=True):
    code: str = Field(primary_key=True)
    duration: str
    remaining_uses: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
