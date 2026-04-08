from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

from shared.config.config import _as_bool, config
from shared.constants.payments import PLAN_KIND_BONUS, PLAN_KIND_PAID, PLAN_KIND_TRIAL
from shared.product_constants import (
    ENTITLEMENT_KIND_TIME,
    ENTITLEMENT_KIND_TRAFFIC,
    PRODUCT_SCOPE_STANDARD,
    PRODUCT_SCOPE_WHITELIST,
)


@dataclass(frozen=True, slots=True)
class PlanSeed:
    code: str
    legacy_payload: str
    name: str
    kind: str
    scope: str
    entitlement_kind: str
    duration_days: int
    quota_bytes: int | None
    price_amount: Decimal | None
    currency: str | None
    is_active: bool = True


DEFAULT_PLAN_SEEDS: tuple[PlanSeed, ...] = (
    PlanSeed(
        code="trial_3d",
        legacy_payload="day3",
        name="Trial 3 days",
        kind=PLAN_KIND_TRIAL,
        scope=PRODUCT_SCOPE_STANDARD,
        entitlement_kind=ENTITLEMENT_KIND_TIME,
        duration_days=3,
        quota_bytes=None,
        price_amount=None,
        currency=None,
    ),
    PlanSeed(
        code="news_bonus_4d",
        legacy_payload="day4",
        name="News bonus 4 days",
        kind=PLAN_KIND_BONUS,
        scope=PRODUCT_SCOPE_STANDARD,
        entitlement_kind=ENTITLEMENT_KIND_TIME,
        duration_days=4,
        quota_bytes=None,
        price_amount=None,
        currency=None,
    ),
    PlanSeed(
        code="month_1",
        legacy_payload="month1",
        name="1 month access",
        kind=PLAN_KIND_PAID,
        scope=PRODUCT_SCOPE_STANDARD,
        entitlement_kind=ENTITLEMENT_KIND_TIME,
        duration_days=30,
        quota_bytes=None,
        price_amount=Decimal("169.00"),
        currency="RUB",
    ),
    PlanSeed(
        code="month_3",
        legacy_payload="month3",
        name="3 months access",
        kind=PLAN_KIND_PAID,
        scope=PRODUCT_SCOPE_STANDARD,
        entitlement_kind=ENTITLEMENT_KIND_TIME,
        duration_days=90,
        quota_bytes=None,
        price_amount=Decimal("449.00"),
        currency="RUB",
    ),
    PlanSeed(
        code="month_6",
        legacy_payload="month6",
        name="6 months access",
        kind=PLAN_KIND_PAID,
        scope=PRODUCT_SCOPE_STANDARD,
        entitlement_kind=ENTITLEMENT_KIND_TIME,
        duration_days=180,
        quota_bytes=None,
        price_amount=Decimal("799.00"),
        currency="RUB",
    ),
    PlanSeed(
        code="year_1",
        legacy_payload="year1",
        name="12 months access",
        kind=PLAN_KIND_PAID,
        scope=PRODUCT_SCOPE_STANDARD,
        entitlement_kind=ENTITLEMENT_KIND_TIME,
        duration_days=365,
        quota_bytes=None,
        price_amount=Decimal("1490.00"),
        currency="RUB",
    ),
    PlanSeed(
        code="whitelist_trial_2gb",
        legacy_payload="whitelist_trial_2gb",
        name="Traffic-limited trial 2 GB",
        kind=PLAN_KIND_TRIAL,
        scope=PRODUCT_SCOPE_WHITELIST,
        entitlement_kind=ENTITLEMENT_KIND_TRAFFIC,
        duration_days=3,
        quota_bytes=2 * 1024 * 1024 * 1024,
        price_amount=None,
        currency=None,
        is_active=False,
    ),
    PlanSeed(
        code="whitelist_15gb",
        legacy_payload="whitelist15gb",
        name="Traffic-limited access 15 GB",
        kind=PLAN_KIND_PAID,
        scope=PRODUCT_SCOPE_WHITELIST,
        entitlement_kind=ENTITLEMENT_KIND_TRAFFIC,
        duration_days=30,
        quota_bytes=15 * 1024 * 1024 * 1024,
        price_amount=Decimal("99.00"),
        currency="RUB",
        is_active=True,
    ),
    PlanSeed(
        code="whitelist_35gb",
        legacy_payload="whitelist35gb",
        name="Traffic-limited access 35 GB",
        kind=PLAN_KIND_PAID,
        scope=PRODUCT_SCOPE_WHITELIST,
        entitlement_kind=ENTITLEMENT_KIND_TRAFFIC,
        duration_days=45,
        quota_bytes=35 * 1024 * 1024 * 1024,
        price_amount=Decimal("249.00"),
        currency="RUB",
        is_active=True,
    ),
    PlanSeed(
        code="whitelist_80gb",
        legacy_payload="whitelist80gb",
        name="Traffic-limited access 80 GB",
        kind=PLAN_KIND_PAID,
        scope=PRODUCT_SCOPE_WHITELIST,
        entitlement_kind=ENTITLEMENT_KIND_TRAFFIC,
        duration_days=60,
        quota_bytes=80 * 1024 * 1024 * 1024,
        price_amount=Decimal("499.00"),
        currency="RUB",
        is_active=True,
    ),
)


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _int_or_none(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _plan_seed_from_mapping(raw: dict) -> PlanSeed:
    return PlanSeed(
        code=str(raw["code"]).strip().lower(),
        legacy_payload=str(raw.get("legacy_payload", raw["code"])).strip().lower(),
        name=str(raw["name"]).strip(),
        kind=str(raw.get("kind", PLAN_KIND_PAID)).strip().lower(),
        scope=str(raw.get("scope", PRODUCT_SCOPE_STANDARD)).strip().lower(),
        entitlement_kind=str(raw.get("entitlement_kind", ENTITLEMENT_KIND_TIME)).strip().lower(),
        duration_days=int(raw.get("duration_days", 0)),
        quota_bytes=_int_or_none(raw.get("quota_bytes")),
        price_amount=_decimal_or_none(raw.get("price_amount")),
        currency=(
            str(raw.get("currency")).strip()
            if raw.get("currency") not in {None, ""}
            else None
        ),
        is_active=_as_bool(raw.get("is_active"), default=True),
    )


@lru_cache(maxsize=1)
def _load_plan_seeds() -> tuple[PlanSeed, ...]:
    raw_plans = config.get("plans", [])
    if not isinstance(raw_plans, list) or not raw_plans:
        return DEFAULT_PLAN_SEEDS

    seeds: list[PlanSeed] = []
    for raw in raw_plans:
        if isinstance(raw, dict):
            seeds.append(_plan_seed_from_mapping(raw))
    return tuple(seeds) or DEFAULT_PLAN_SEEDS


def get_plan_seed_by_legacy_payload(legacy_payload: str) -> PlanSeed | None:
    normalized = str(legacy_payload).strip().lower()
    return {
        seed.legacy_payload: seed
        for seed in _load_plan_seeds()
    }.get(normalized)


def get_plan_seed_by_code(code: str) -> PlanSeed | None:
    normalized = str(code).strip().lower()
    return {
        seed.code: seed
        for seed in _load_plan_seeds()
    }.get(normalized)


def iter_default_plan_seeds() -> tuple[PlanSeed, ...]:
    return _load_plan_seeds()
