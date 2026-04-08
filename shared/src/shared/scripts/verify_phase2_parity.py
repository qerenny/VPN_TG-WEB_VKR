from __future__ import annotations

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_legacy_payload
from shared.migration_support.models.payments.payment_model import Payment as LegacyPayment
from shared.migration_support.models.users.user_model import User as LegacyUser  # noqa: F401
from shared.models import register_models
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.payments.plan_model import Plan
from shared.models.subscriptions.subscription_grant_model import SubscriptionGrant
from shared.scripts.rollout_support import RolloutCheck, print_checks, run_async

register_models()

PAID_STATUSES = {"paid", "succeeded"}
CANCELED_STATUSES = {"canceled", "cancelled", "expired"}
FAILED_STATUSES = {"failed", "refunded", "rejected"}


async def main() -> None:
    async with get_db_session() as session:
        legacy_payments = (
            await session.execute(select(LegacyPayment).order_by(LegacyPayment.payment_id))
        ).scalars().all()
        attempts = (await session.execute(select(PaymentAttempt))).scalars().all()
        orders = (await session.execute(select(PaymentOrder))).scalars().all()
        plans = (await session.execute(select(Plan))).scalars().all()
        grants = (await session.execute(select(SubscriptionGrant))).scalars().all()

    attempts_by_provider_id = {
        (attempt.provider, attempt.provider_payment_id): attempt
        for attempt in attempts
    }
    attempts_by_payment_id = {}
    for attempt in attempts:
        attempts_by_payment_id.setdefault(attempt.provider_payment_id, attempt)

    orders_by_id = {order.id: order for order in orders}
    plans_by_id = {plan.id: plan for plan in plans}
    grants_by_id = {grant.id: grant for grant in grants}
    grants_by_source_ref = {
        (grant.source_type, grant.source_ref): grant
        for grant in grants
    }

    missing_attempts = 0
    missing_orders = 0
    plan_mismatches = 0
    status_mismatches = 0
    provider_status_mismatches = 0
    missing_grants = 0
    unsupported_payloads = 0

    for legacy_payment in legacy_payments:
        provider = str(legacy_payment.method or "").strip().lower()
        attempt = attempts_by_provider_id.get((provider or "unknown", legacy_payment.payment_id))
        if attempt is None:
            attempt = attempts_by_payment_id.get(str(legacy_payment.payment_id))
        if attempt is None:
            missing_attempts += 1
            continue

        order = orders_by_id.get(attempt.order_id)
        if order is None:
            missing_orders += 1
            continue

        seed = get_plan_seed_by_legacy_payload(str(legacy_payment.payload))
        if seed is None:
            unsupported_payloads += 1
            continue

        plan = plans_by_id.get(order.plan_id)
        if plan is None or plan.code != seed.code:
            plan_mismatches += 1

        if _normalize_status(attempt.provider_status) != _normalize_status(legacy_payment.status):
            provider_status_mismatches += 1

        if order.status not in _expected_order_statuses(legacy_payment):
            status_mismatches += 1

        if legacy_payment.confirmed:
            grant = None
            if order.subscription_grant_id is not None:
                grant = grants_by_id.get(order.subscription_grant_id)
            if grant is None:
                grant = grants_by_source_ref.get(("payment_order", str(order.id)))
            if grant is None:
                missing_grants += 1

    paid_plan_codes = {plan.code for plan in plans if plan.kind == "paid"}
    required_paid_plan_codes = {"month_1", "month_3", "month_6", "year_1"}

    checks = [
        RolloutCheck(
            name="required paid plans exist",
            ok=required_paid_plan_codes.issubset(paid_plan_codes),
            details=f"present={sorted(paid_plan_codes)}",
        ),
        RolloutCheck(
            name="legacy payments mapped to payment_attempts",
            ok=missing_attempts == 0,
            details=f"missing={missing_attempts}",
        ),
        RolloutCheck(
            name="legacy payments mapped to payment_orders",
            ok=missing_orders == 0,
            details=f"missing={missing_orders}",
        ),
        RolloutCheck(
            name="legacy payment payload mapped to plans",
            ok=plan_mismatches == 0 and unsupported_payloads == 0,
            details=f"mismatches={plan_mismatches}, unsupported={unsupported_payloads}",
        ),
        RolloutCheck(
            name="payment_attempt provider_status parity",
            ok=provider_status_mismatches == 0,
            details=f"mismatches={provider_status_mismatches}",
        ),
        RolloutCheck(
            name="payment_orders normalized status parity",
            ok=status_mismatches == 0,
            details=f"mismatches={status_mismatches}",
        ),
        RolloutCheck(
            name="confirmed legacy payments mapped to subscription_grants",
            ok=missing_grants == 0,
            details=f"missing={missing_grants}",
        ),
    ]
    print_checks(checks)
    if not all(check.ok for check in checks):
        raise SystemExit(1)


def _normalize_status(status: str | None) -> str:
    return str(status or "").strip().lower()


def _expected_order_statuses(legacy_payment: LegacyPayment) -> set[str]:
    if legacy_payment.confirmed:
        return {"fulfilled"}

    status = _normalize_status(legacy_payment.status)
    if status in PAID_STATUSES:
        return {"paid", "fulfilled"}
    if status in CANCELED_STATUSES:
        return {"canceled"}
    if status in FAILED_STATUSES:
        return {"failed"}
    return {"pending_payment"}


if __name__ == "__main__":
    run_async(main())
