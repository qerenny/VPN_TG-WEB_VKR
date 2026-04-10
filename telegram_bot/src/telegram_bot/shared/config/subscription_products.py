from __future__ import annotations

from decimal import Decimal

from shared.product_constants import (
    ENTITLEMENT_KIND_TIME,
    ENTITLEMENT_KIND_TRAFFIC,
    PRODUCT_SCOPE_STANDARD,
    PRODUCT_SCOPE_TRAFFIC_LIMITED,
)
from shared.constants.payments import (
    SUBSCRIPTION_PAYLOAD_INFO_CHANNEL_BONUS_4D,
    SUBSCRIPTION_PAYLOAD_TRIAL_3D,
)
from shared.infrastructure.payment_plan_catalog import PlanSeed, get_plan_seed_by_payload

TRIAL = "3 дня (пробный доступ)"
TRAFFIC_LIMITED_TRIAL = "2 GB (пробная конфигурация)"


def _amount_to_cents(amount: Decimal | None) -> int:
    if amount is None:
        return 0
    return int(amount * 100)


def _format_rub_price(amount: Decimal | None) -> str:
    if amount is None:
        return "0₽"
    return f"{int(amount)}₽"


def _quota_to_gb(quota_bytes: int | None) -> int:
    if quota_bytes is None:
        return 0
    return int(quota_bytes / (1024 * 1024 * 1024))


def _standard_label(seed: PlanSeed, *, icon: str, months: int) -> str:
    return f"{icon} {months} мес. - {_format_rub_price(seed.price_amount)}"


def _standard_description(months: int) -> str:
    return f"Базовая конфигурация на {months} {'месяц' if months == 1 else 'месяца' if months < 5 else 'месяцев'}."


def _traffic_limited_label(seed: PlanSeed, *, icon: str) -> str:
    return f"{icon} {_quota_to_gb(seed.quota_bytes)} GB - {_format_rub_price(seed.price_amount)}"


def _traffic_limited_description(seed: PlanSeed) -> str:
    return (
        f"Конфигурация с лимитом {_quota_to_gb(seed.quota_bytes)} GB трафика "
        f"на {seed.duration_days} дней."
    )


def _build_product(
    payload: str,
    *,
    label: str,
    description: str,
) -> dict[str, int | str]:
    seed = get_plan_seed_by_payload(payload)
    if seed is None:
        raise ValueError(f"Unknown payment payload: {payload}")
    return {
        "label": label,
        "amount": _amount_to_cents(seed.price_amount),
        "description": description,
        "payload": seed.payload,
    }


DAY_3_TIMESTAMP = SUBSCRIPTION_PAYLOAD_TRIAL_3D
INFO_CHANNEL_BONUS_TIMESTAMP = SUBSCRIPTION_PAYLOAD_INFO_CHANNEL_BONUS_4D

def _build_standard_product(payload: str, *, icon: str, months: int) -> dict[str, int | str]:
    seed = get_plan_seed_by_payload(payload)
    if seed is None or seed.scope != PRODUCT_SCOPE_STANDARD or seed.entitlement_kind != ENTITLEMENT_KIND_TIME:
        raise ValueError(f"Unexpected standard plan payload: {payload}")
    return _build_product(
        payload,
        label=_standard_label(seed, icon=icon, months=months),
        description=_standard_description(months),
    )


def _build_traffic_limited_product(payload: str, *, icon: str) -> dict[str, int | str]:
    seed = get_plan_seed_by_payload(payload)
    if seed is None or seed.scope != PRODUCT_SCOPE_TRAFFIC_LIMITED or seed.entitlement_kind != ENTITLEMENT_KIND_TRAFFIC:
        raise ValueError(f"Unexpected traffic-limited plan payload: {payload}")
    return _build_product(
        payload,
        label=_traffic_limited_label(seed, icon=icon),
        description=_traffic_limited_description(seed),
    )


MONTH1 = _build_standard_product("month1", icon="🔑", months=1)
MONTH3 = _build_standard_product("month3", icon="🛡️", months=3)
MONTH6 = _build_standard_product("month6", icon="⭐", months=6)
YEAR1 = _build_standard_product("year1", icon="👑", months=12)

TRAFFIC_LIMITED15GB = _build_traffic_limited_product("traffic_limited15gb", icon="📦")
TRAFFIC_LIMITED35GB = _build_traffic_limited_product("traffic_limited35gb", icon="📦")
TRAFFIC_LIMITED80GB = _build_traffic_limited_product("traffic_limited80gb", icon="📦")

SUBSCRIPTION_PRODUCTS = {
    "month1": MONTH1,
    "month3": MONTH3,
    "month6": MONTH6,
    "year1": YEAR1,
}

TRAFFIC_LIMITED_PRODUCTS = {
    "traffic_limited15gb": TRAFFIC_LIMITED15GB,
    "traffic_limited35gb": TRAFFIC_LIMITED35GB,
    "traffic_limited80gb": TRAFFIC_LIMITED80GB,
}

ALL_PAYMENT_PRODUCTS = {
    **SUBSCRIPTION_PRODUCTS,
    **TRAFFIC_LIMITED_PRODUCTS,
}
