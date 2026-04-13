from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clamp_limit(limit: int, *, minimum: int = 1, maximum: int) -> int:
    return max(minimum, min(int(limit), maximum))


def merge_metadata(
    existing: dict[str, Any] | None,
    updates: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        **dict(existing or {}),
        **dict(updates or {}),
    }


def normalize_text(value: Any, *, lowercase: bool = False) -> str:
    normalized = str(value or "").strip()
    return normalized.lower() if lowercase else normalized


def normalize_optional_text(value: Any, *, lowercase: bool = False) -> str | None:
    normalized = normalize_text(value, lowercase=lowercase)
    return normalized or None


def normalize_string_list(values: Iterable[Any]) -> list[str]:
    return [item for value in values if (item := normalize_text(value, lowercase=True))]
