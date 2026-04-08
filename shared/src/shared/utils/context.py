from contextvars import ContextVar
from typing import Optional

chat_id_var: ContextVar[Optional[int]] = ContextVar("chat_id", default=None)
user_id_var: ContextVar[Optional[int]] = ContextVar("user_id", default=None)
username_var: ContextVar[Optional[str]] = ContextVar("username", default=None)
