from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from shared.constants.payments import (
    ORDER_STATUS_CANCELED,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_FULFILLED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING_PAYMENT,
    PAYMENT_PROVIDER_UNKNOWN,
    PROVIDER_STATUS_CANCELED,
    PROVIDER_STATUS_FAILED,
    PROVIDER_STATUS_PAID,
)
from shared.config.database.session import get_db_session
from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.payment_plan_catalog import (
    PlanSeed,
    get_plan_seed_by_legacy_payload,
    iter_default_plan_seeds,
)
from shared.migration_support.models.payments.payment_model import Payment as LegacyPayment
from shared.migration_support.models.users.user_model import User as LegacyUser  # noqa: F401
from shared.models import register_models
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.payments.payment_webhook_event_model import PaymentWebhookEvent
from shared.models.payments.plan_model import Plan
from shared.models.subscriptions.subscription_grant_model import SubscriptionGrant
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.telegram_account_model import TelegramAccount
from shared.utils.logging_utils import setup_logger

logger = setup_logger("rollout.phase2.payments", "database.log")

register_models()

class PaymentSyncService:
    def __init__(self, features: RolloutFeatureFlags):
        self.features = features

    async def seed_default_plans(self) -> int:
        async with get_db_session() as session:
            created = await self._ensure_default_plans(session)
            await session.commit()
            return created

    async def sync_legacy_payment(
        self,
        legacy_payment: LegacyPayment,
        *,
        provider: str | None = None,
        provider_payload: dict[str, Any] | None = None,
        provider_event_id: str | None = None,
        create_webhook_event: bool = False,
        status_changed_at: datetime | None = None,
    ) -> int | None:
        if not self.features.db_dual_write_payments:
            return None

        async with get_db_session() as session:
            await self._ensure_default_plans(session)
            order, attempt = await self._upsert_from_legacy_payment(
                session,
                legacy_payment,
                provider=provider,
                provider_payload=provider_payload,
                status_changed_at=status_changed_at,
            )
            if create_webhook_event and provider_payload is not None:
                await self._record_webhook_event(
                    session,
                    attempt=attempt,
                    provider_event_id=provider_event_id,
                    provider_payload=provider_payload,
                    received_at=status_changed_at or datetime.now(timezone.utc),
                )
            await session.commit()
            return int(order.id)

    async def _ensure_default_plans(self, session) -> int:
        existing_plans = {
            plan.code: plan
            for plan in (
                await session.execute(select(Plan))
            ).scalars().all()
        }
        created = 0
        for seed in iter_default_plan_seeds():
            existing = existing_plans.get(seed.code)
            if existing is not None:
                self._sync_existing_plan(existing, seed)
                continue
            session.add(self._build_plan(seed))
            created += 1
        if created:
            await session.flush()
        return created

    async def _upsert_from_legacy_payment(
        self,
        session,
        legacy_payment: LegacyPayment,
        *,
        provider: str | None,
        provider_payload: dict[str, Any] | None,
        status_changed_at: datetime | None,
    ) -> tuple[PaymentOrder, PaymentAttempt]:
        provider_name = self._normalize_provider(provider or legacy_payment.method)
        created_at = self._legacy_ts_to_datetime(legacy_payment.created_at) or datetime.now(
            timezone.utc
        )
        status_timestamp = status_changed_at or created_at
        plan = await self._get_plan_for_legacy_payload(session, legacy_payment.payload)
        user_id = await self._resolve_user_id(session, int(legacy_payment.tg_id))

        order, attempt = await self._get_or_create_order_and_attempt(
            session,
            legacy_payment=legacy_payment,
            user_id=user_id,
            plan=plan,
            provider_name=provider_name,
            created_at=created_at,
        )

        order.user_id = user_id
        order.plan_id = int(plan.id)
        order.amount = plan.price_amount
        order.currency = str(plan.currency)
        order.metadata_json = {
            **(order.metadata_json or {}),
            "legacy_payload": str(legacy_payment.payload),
            "legacy_payment_id": str(legacy_payment.payment_id),
            "legacy_confirmed": bool(legacy_payment.confirmed),
        }

        attempt.order_id = int(order.id)
        attempt.provider = provider_name
        attempt.provider_payment_id = str(legacy_payment.payment_id)
        attempt.provider_payload_json = self._build_attempt_payload(
            legacy_payment=legacy_payment,
            provider_payload=provider_payload,
        )

        self._apply_payment_state(
            order=order,
            attempt=attempt,
            legacy_payment=legacy_payment,
            status_timestamp=status_timestamp,
        )

        return order, attempt

    async def _get_or_create_order_and_attempt(
        self,
        session,
        *,
        legacy_payment: LegacyPayment,
        user_id: int,
        plan: Plan,
        provider_name: str,
        created_at: datetime,
    ) -> tuple[PaymentOrder, PaymentAttempt]:
        attempt = await self._find_attempt(
            session,
            provider=provider_name,
            provider_payment_id=str(legacy_payment.payment_id),
        )
        order = None
        if attempt is not None:
            order = await session.get(PaymentOrder, attempt.order_id)

        idempotency_key = f"legacy_payment:{legacy_payment.payment_id}"
        if order is None:
            order = (
                await session.execute(
                    select(PaymentOrder).where(PaymentOrder.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()

        if order is None:
            order = PaymentOrder(
                user_id=user_id,
                plan_id=int(plan.id),
                status=ORDER_STATUS_PENDING_PAYMENT,
                amount=plan.price_amount,
                currency=str(plan.currency),
                created_at=created_at,
                paid_at=None,
                fulfilled_at=None,
                idempotency_key=idempotency_key,
                subscription_grant_id=None,
                metadata_json={
                    "legacy_payment_id": str(legacy_payment.payment_id),
                    "legacy_payload": str(legacy_payment.payload),
                    "legacy_backfill": True,
                },
            )
            session.add(order)
            await session.flush()

        if attempt is None:
            attempt = PaymentAttempt(
                order_id=int(order.id),
                provider=provider_name,
                provider_payment_id=str(legacy_payment.payment_id),
                provider_status=self._normalize_status(legacy_payment.status),
                provider_payload_json={},
                created_at=created_at,
                updated_at=created_at,
                paid_at=None,
            )
            session.add(attempt)
            await session.flush()

        return order, attempt

    async def _get_plan_for_legacy_payload(self, session, legacy_payload: str) -> Plan:
        seed = get_plan_seed_by_legacy_payload(str(legacy_payload))
        if seed is None:
            raise ValueError(f"Unsupported legacy payment payload: {legacy_payload!r}")

        plan = (
            await session.execute(select(Plan).where(Plan.code == seed.code))
        ).scalar_one_or_none()
        if plan is None:
            plan = self._build_plan(seed)
            session.add(plan)
            await session.flush()
        return plan

    async def _resolve_user_id(self, session, tg_id: int) -> int:
        telegram_account = (
            await session.execute(
                select(TelegramAccount).where(TelegramAccount.telegram_id == int(tg_id))
            )
        ).scalar_one_or_none()
        if telegram_account is None:
            raise ValueError(
                "Phase 2 payment sync requires Phase 1 identity rows. "
                f"Missing telegram_accounts row for tg_id={tg_id}."
            )
        return int(telegram_account.user_id)

    async def _find_attempt(
        self,
        session,
        *,
        provider: str,
        provider_payment_id: str,
    ) -> PaymentAttempt | None:
        attempt = (
            await session.execute(
                select(PaymentAttempt).where(
                    PaymentAttempt.provider == provider,
                    PaymentAttempt.provider_payment_id == provider_payment_id,
                )
            )
        ).scalar_one_or_none()
        if attempt is not None:
            return attempt

        return (
            await session.execute(
                select(PaymentAttempt).where(
                    PaymentAttempt.provider_payment_id == provider_payment_id
                )
            )
        ).scalar_one_or_none()

    async def _record_webhook_event(
        self,
        session,
        *,
        attempt: PaymentAttempt,
        provider_event_id: str | None,
        provider_payload: dict[str, Any],
        received_at: datetime,
    ) -> None:
        payload_hash = self._build_payload_hash(provider_payload)
        existing = (
            await session.execute(
                select(PaymentWebhookEvent).where(
                    PaymentWebhookEvent.provider == attempt.provider,
                    PaymentWebhookEvent.payload_hash == payload_hash,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.attempt_id = int(attempt.id)
            existing.processed_at = received_at
            return

        session.add(
            PaymentWebhookEvent(
                attempt_id=int(attempt.id),
                provider=attempt.provider,
                provider_payment_id=attempt.provider_payment_id,
                provider_event_id=provider_event_id,
                payload_hash=payload_hash,
                provider_status=self._extract_provider_status(provider_payload),
                payload_json=provider_payload,
                received_at=received_at,
                processed_at=received_at,
            )
        )

    def _apply_payment_state(
        self,
        *,
        order: PaymentOrder,
        attempt: PaymentAttempt,
        legacy_payment: LegacyPayment,
        status_timestamp: datetime,
    ) -> None:
        provider_status = self._normalize_status(legacy_payment.status)
        attempt.provider_status = provider_status
        attempt.updated_at = status_timestamp
        if provider_status in PROVIDER_STATUS_PAID and attempt.paid_at is None:
            attempt.paid_at = status_timestamp

        target_order_status = self._map_legacy_payment_to_order_status(legacy_payment)
        if order.status != ORDER_STATUS_FULFILLED or target_order_status == ORDER_STATUS_FULFILLED:
            order.status = target_order_status
        if target_order_status in {ORDER_STATUS_PAID, ORDER_STATUS_FULFILLED} and order.paid_at is None:
            order.paid_at = status_timestamp
        if target_order_status == ORDER_STATUS_FULFILLED and order.fulfilled_at is None:
            order.fulfilled_at = status_timestamp

        if legacy_payment.confirmed:
            self._attach_subscription_grant(order, legacy_payment, status_timestamp)

    def _attach_subscription_grant(
        self,
        order: PaymentOrder,
        legacy_payment: LegacyPayment,
        status_timestamp: datetime,
    ) -> None:
        # The actual grant row is created lazily by _finalize_subscription_grant.
        if order.fulfilled_at is None:
            order.fulfilled_at = status_timestamp
        order.status = ORDER_STATUS_FULFILLED

    @staticmethod
    def _normalize_provider(provider: str | None) -> str:
        normalized = str(provider or "").strip().lower()
        return normalized or PAYMENT_PROVIDER_UNKNOWN

    @staticmethod
    def _normalize_status(status: str | None) -> str:
        return str(status or "").strip().lower()

    def _map_legacy_payment_to_order_status(self, legacy_payment: LegacyPayment) -> str:
        if legacy_payment.confirmed:
            return ORDER_STATUS_FULFILLED

        provider_status = self._normalize_status(legacy_payment.status)
        if provider_status in PROVIDER_STATUS_PAID:
            return ORDER_STATUS_PAID
        if provider_status in PROVIDER_STATUS_CANCELED:
            return ORDER_STATUS_CANCELED
        if provider_status in PROVIDER_STATUS_FAILED:
            return ORDER_STATUS_FAILED
        return ORDER_STATUS_PENDING_PAYMENT

    def _build_plan(self, seed: PlanSeed) -> Plan:
        return Plan(
            code=seed.code,
            name=seed.name,
            kind=seed.kind,
            legacy_payload=seed.legacy_payload,
            scope=seed.scope,
            entitlement_kind=seed.entitlement_kind,
            duration_days=seed.duration_days,
            quota_bytes=seed.quota_bytes,
            price_amount=seed.price_amount,
            currency=seed.currency,
            is_active=seed.is_active,
            metadata_json={
                "legacy_payload": seed.legacy_payload,
                "scope": seed.scope,
                "entitlement_kind": seed.entitlement_kind,
                "quota_bytes": seed.quota_bytes,
            },
        )

    @staticmethod
    def _sync_existing_plan(plan: Plan, seed: PlanSeed) -> None:
        plan.name = seed.name
        plan.kind = seed.kind
        plan.legacy_payload = seed.legacy_payload
        plan.scope = seed.scope
        plan.entitlement_kind = seed.entitlement_kind
        plan.duration_days = seed.duration_days
        plan.quota_bytes = seed.quota_bytes
        plan.price_amount = seed.price_amount
        plan.currency = seed.currency
        plan.is_active = seed.is_active
        plan.metadata_json = {
            "legacy_payload": seed.legacy_payload,
            "scope": seed.scope,
            "entitlement_kind": seed.entitlement_kind,
            "quota_bytes": seed.quota_bytes,
        }

    async def finalize_subscription_grant(
        self,
        legacy_payment: LegacyPayment,
        *,
        applied_at: datetime | None = None,
        legacy_backfill: bool = False,
    ) -> int | None:
        if not self.features.db_dual_write_payments:
            return None

        async with get_db_session() as session:
            await self._ensure_default_plans(session)
            order, _attempt = await self._upsert_from_legacy_payment(
                session,
                legacy_payment,
                provider=None,
                provider_payload=None,
                status_changed_at=applied_at,
            )
            plan = await session.get(Plan, order.plan_id)
            if plan is None:
                raise ValueError(f"Plan {order.plan_id} not found for payment order {order.id}")

            grant = await self._get_or_create_subscription_grant(
                session,
                order=order,
                plan=plan,
                applied_at=applied_at or datetime.now(timezone.utc),
                created_at=self._legacy_ts_to_datetime(legacy_payment.created_at)
                or datetime.now(timezone.utc),
                legacy_payment_id=str(legacy_payment.payment_id),
                legacy_backfill=legacy_backfill,
            )
            order.subscription_grant_id = int(grant.id)
            order.status = ORDER_STATUS_FULFILLED
            if order.fulfilled_at is None:
                order.fulfilled_at = applied_at or datetime.now(timezone.utc)
            await session.commit()
            return int(grant.id)

    async def _get_or_create_subscription_grant(
        self,
        session,
        *,
        order: PaymentOrder,
        plan: Plan,
        applied_at: datetime,
        created_at: datetime,
        legacy_payment_id: str,
        legacy_backfill: bool,
    ) -> SubscriptionGrant:
        if order.subscription_grant_id is not None:
            grant = await session.get(SubscriptionGrant, order.subscription_grant_id)
            if grant is not None:
                return grant

        grant = (
            await session.execute(
                select(SubscriptionGrant).where(
                    SubscriptionGrant.source_type == "payment_order",
                    SubscriptionGrant.source_ref == str(order.id),
                )
            )
        ).scalar_one_or_none()
        if grant is not None:
            return grant

        subscription_state = await session.get(SubscriptionState, order.user_id)
        grant = SubscriptionGrant(
            user_id=order.user_id,
            plan_id=order.plan_id,
            source_type="payment_order",
            source_ref=str(order.id),
            status="applied",
            duration_days=plan.duration_days,
            expires_before=None,
            expires_after=getattr(subscription_state, "current_expires_at", None),
            created_at=created_at,
            applied_at=applied_at,
            metadata_json={
                "legacy_payment_id": legacy_payment_id,
                "legacy_backfill": legacy_backfill,
            },
        )
        session.add(grant)
        await session.flush()
        return grant

    def _build_attempt_payload(
        self,
        *,
        legacy_payment: LegacyPayment,
        provider_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = {
            "legacy_payment_id": str(legacy_payment.payment_id),
            "legacy_status": self._normalize_status(legacy_payment.status),
            "legacy_confirmed": bool(legacy_payment.confirmed),
            "legacy_payload": str(legacy_payment.payload),
        }
        if provider_payload is not None:
            payload["last_provider_payload"] = provider_payload
        return payload

    @staticmethod
    def _extract_provider_status(provider_payload: dict[str, Any]) -> str | None:
        if not isinstance(provider_payload, dict):
            return None
        if "status" in provider_payload:
            return str(provider_payload.get("status") or "").strip().lower() or None
        obj = provider_payload.get("object")
        if isinstance(obj, dict) and "status" in obj:
            return str(obj.get("status") or "").strip().lower() or None
        nested = provider_payload.get("payload")
        if isinstance(nested, dict) and "status" in nested:
            return str(nested.get("status") or "").strip().lower() or None
        return None

    @staticmethod
    def _build_payload_hash(provider_payload: dict[str, Any]) -> str:
        raw = json.dumps(provider_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _legacy_ts_to_datetime(timestamp_ms: int | None) -> datetime | None:
        if timestamp_ms is None:
            return None
        value = int(timestamp_ms)
        if value <= 0:
            return None
        if value < 1_000_000_000_000:
            value *= 1000
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
