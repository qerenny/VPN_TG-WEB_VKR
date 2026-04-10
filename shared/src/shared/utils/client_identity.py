from __future__ import annotations

import re

from shared.config.config import PRODUCT_REDIS_PREFIX
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_TRAFFIC_LIMITED

DEFAULT_CLIENT_IDENTITY_SEED = PRODUCT_REDIS_PREFIX


def normalize_client_identity_seed(
    value: str | None,
    *,
    fallback: str = DEFAULT_CLIENT_IDENTITY_SEED,
) -> str:
    raw = str(value or "").strip().lower()
    if "@" in raw:
        raw = raw.split("@", 1)[0]
    normalized = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-_")
    return normalized or fallback


def build_generated_client_label(
    *,
    seed: str | None,
    generated_value: str,
) -> str:
    normalized_generated = normalize_client_identity_seed(
        generated_value,
        fallback=DEFAULT_CLIENT_IDENTITY_SEED,
    )
    normalized_seed = normalize_client_identity_seed(seed, fallback="")
    if normalized_seed:
        return f"{normalized_seed}-{normalized_generated}"
    return normalized_generated


def build_vpn_client_email(
    *,
    seed: str | None,
    client_uuid: str,
    scope: str,
) -> str:
    normalized_seed = normalize_client_identity_seed(
        seed,
        fallback=DEFAULT_CLIENT_IDENTITY_SEED,
    )
    suffix = re.sub(r"[^a-z0-9]+", "", str(client_uuid or "").lower())[:8] or "client"
    if scope == PRODUCT_SCOPE_TRAFFIC_LIMITED:
        return f"wl-{normalized_seed}-{suffix}"
    if scope == PRODUCT_SCOPE_STANDARD:
        return f"{normalized_seed}-{suffix}"
    raise ValueError(f"Unsupported VPN scope: {scope}")


def resolve_user_identity_seed(
    *,
    web_email: str | None = None,
    telegram_username: str | None = None,
    telegram_id: int | None = None,
    user_id: int | None = None,
) -> str:
    if str(web_email or "").strip():
        return normalize_client_identity_seed(str(web_email), fallback=DEFAULT_CLIENT_IDENTITY_SEED)
    if str(telegram_username or "").strip():
        return normalize_client_identity_seed(str(telegram_username), fallback=DEFAULT_CLIENT_IDENTITY_SEED)
    if telegram_id is not None:
        return normalize_client_identity_seed(f"tg-{int(telegram_id)}", fallback=DEFAULT_CLIENT_IDENTITY_SEED)
    if user_id is not None:
        return normalize_client_identity_seed(f"user-{int(user_id)}", fallback=DEFAULT_CLIENT_IDENTITY_SEED)
    return DEFAULT_CLIENT_IDENTITY_SEED
