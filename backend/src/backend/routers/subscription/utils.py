import base64
import re

from shared.config.config import (
    LOCATION_LABELS,
    KEY_PROFILE_TAG,
    INBOUND_ID_MAP,
)
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_WHITELIST


def _extract_inbound_id(remark: str) -> int | None:
    """Extract inbound id from remark suffix (e.g. user_2 or weathered-silence2)."""
    match = re.search(r"_(\d+)$", remark)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None

    # Fallback for remarks without underscore suffix (e.g. "...silence1").
    match = re.search(r"(\d+)$", remark)
    if match:
        try:
            inbound_id = int(match.group(1))
        except ValueError:
            return None
        if inbound_id in INBOUND_ID_MAP:
            return inbound_id

    return None


def _strip_whitelist_decoration(label: str) -> str:
    cleaned = str(label).strip()

    while cleaned:
        original = cleaned
        for token in ("🏳️", "🏳", KEY_PROFILE_TAG, "\U0001f638"):
            if token and cleaned.startswith(token):
                cleaned = cleaned[len(token):].strip()
            if token and cleaned.endswith(token):
                cleaned = cleaned[: -len(token)].strip()
        if cleaned == original:
            break

    return cleaned


def _format_subscription_label(label: str, *, scope: str) -> str:
    if scope == PRODUCT_SCOPE_WHITELIST:
        return f"{_strip_whitelist_decoration(label)}{KEY_PROFILE_TAG}🏳️"
    return f"{label}{KEY_PROFILE_TAG}"


def process_subscription_content(
    content: bytes,
    source_name: str | None = None,
    *,
    scope: str = PRODUCT_SCOPE_STANDARD,
    inbound_labels: dict[int, str] | None = None,
) -> list[str]:
    """
    Decodes subscription content (Base64 or raw) and adds location labels
    based on inbound ID suffix (e.g. _1).
    """
    try:
        # Try decode base64
        decoded = base64.b64decode(content, validate=True).decode("utf-8")
    except Exception:
        # Use raw content if not valid base64
        decoded = content.decode("utf-8", errors="ignore")

    configs = []
    for line in decoded.strip().splitlines():
        if not line.strip():
            continue

        label = LOCATION_LABELS.get(
            source_name,
            LOCATION_LABELS.get("default", "🌍VPN"),
        )

        remark = line.split("#", 1)[1] if "#" in line else line
        remark = remark.strip()

        inbound_id = _extract_inbound_id(remark)
        if inbound_id is not None and inbound_labels and inbound_id in inbound_labels:
            label = str(inbound_labels[inbound_id])
        elif inbound_id in INBOUND_ID_MAP:
            country_key = INBOUND_ID_MAP[inbound_id]
            label = LOCATION_LABELS.get(country_key, label)

        formatted_label = _format_subscription_label(label, scope=scope)

        if "#" in line:
            base, _tail = line.split("#", 1)
            line = f"{base}#{formatted_label}"
        else:
            line = f"{line}#{formatted_label}"

        configs.append(line)

    return configs
