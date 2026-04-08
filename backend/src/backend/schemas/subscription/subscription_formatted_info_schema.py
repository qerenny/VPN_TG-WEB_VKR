from typing import Optional

from pydantic import BaseModel


class SubscriptionFormattedInfoSchema(BaseModel):
    scope: str
    human_view_expiration_remaining: Optional[str]
    human_view_expiration_date: Optional[str]
    sub_link: str
    sub_is_active: Optional[bool]
    support_link: Optional[str]
    traffic_allocated_bytes: Optional[int] = None
    traffic_used_bytes: Optional[int] = None
    traffic_remaining_bytes: Optional[int] = None
    human_view_traffic_allocated: Optional[str] = None
    human_view_traffic_used: Optional[str] = None
    human_view_traffic_remaining: Optional[str] = None
