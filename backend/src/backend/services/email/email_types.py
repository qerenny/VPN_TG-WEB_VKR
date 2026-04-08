from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    to_email: str
    subject: str
    text_body: str
    html_body: str | None = None
    reply_to: str | None = None
