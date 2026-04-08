from __future__ import annotations

import re

from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_WHITELIST

DEFAULT_CLIENT_IDENTITY_SEED = "remote_access"


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
    if scope == PRODUCT_SCOPE_WHITELIST:
        return f"wl-{normalized_seed}-{suffix}"
    if scope == PRODUCT_SCOPE_STANDARD:
        return f"{normalized_seed}-{suffix}"
    raise ValueError(f"Unsupported VPN scope: {scope}")
