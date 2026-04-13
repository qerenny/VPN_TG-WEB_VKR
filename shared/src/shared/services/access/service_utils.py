from __future__ import annotations

from typing import Any

from shared.utils.access_template_labels import format_access_template_label


def resolve_actor(principal: Any, *, fallback: str = "system") -> str:
    actor = str(getattr(principal, "actor", "") or "").strip()
    return actor or fallback
def format_template_label_or_none(template_code: str | None) -> str | None:
    if template_code is None:
        return None
    return format_access_template_label(template_code)
