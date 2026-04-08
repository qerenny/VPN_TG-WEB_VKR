from typing import Optional

from pydantic import BaseModel


class UserInfoSchema(BaseModel):
    tg_id: int
    email: str
    sub_id: str
    login_date: int
    expiration_date: Optional[int]
