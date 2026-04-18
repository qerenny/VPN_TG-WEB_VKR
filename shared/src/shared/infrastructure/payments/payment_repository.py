from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlmodel import select

from shared.constants.payments import (
    ORDER_STATUS_CANCELED,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_FULFILLED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING_PAYMENT,
    PAID_PROVIDER_STATUSES,
    RUNTIME_PAYMENT_STATUS_CANCELED,
    RUNTIME_PAYMENT_STATUS_FAILED,
    RUNTIME_PAYMENT_STATUS_PAID,
    RUNTIME_PAYMENT_STATUS_PENDING,
)
from shared.infrastructure.base_repository import BaseRepository
from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_payload
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.payments.plan_model import Plan
from shared.models.subscriptions.subscription_grant_model import SubscriptionGrant
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.telegram_account_model import TelegramAccount
from shared.product_constants import ENTITLEMENT_KIND_TIME
from shared.utils.logging_utils import log_function_call, setup_logger
from shared.utils.timestamp_utils import datetime_to_legacy_ms

logger = setup_logger("payment.repository", "database.log")

@dataclass(slots=True)
class PaymentSnapshot:
    payment_id: str
    user_id: int | None
    tg_id: int | None
    status: str
    payload: str
    created_at: int
    confirmed: bool = False
    method: str | None = None


class PaymentRepository(BaseRepository[PaymentSnapshot]):
    def __init__(self):
        super().__init__(PaymentSnapshot)

    @log_function_call(logger)
    async def create(self, obj: PaymentSnapshot) -> PaymentSnapshot:
        async with self.get_session() as session:
            normalized = PaymentSnapshot(
                payment_id=str(obj.payment_id),
                user_id=getattr(obj, "user_id", None),
                tg_id=getattr(obj, "tg_id", None),
                status=str(obj.status),
                payload=str(obj.payload),
                created_at=int(obj.created_at),
                confirmed=bool(obj.confirmed),
                method=obj.method,
            )
            if normalized.user_id is None:
                normalized.user_id = await self._resolve_user_id_by_tg_id(
                    session,
                    tg_id=normalized.tg_id,
                )
            await self._create_current_payment(session, normalized)
        created = await self.get_by_payment_id(str(obj.payment_id))
        return created or obj

    @log_function_call(logger)
    async def get_by_payment_id(self, payment_id: str) -> Optional[PaymentSnapshot]:
        async with self.get_session() as session:
            return await self._get_v2_payment_by_id(session, payment_id)

    @log_function_call(logger)
    async def update_status(self, payment_id: str, status: str, confirmed: bool) -> None:
        payment = await self.get_by_payment_id(payment_id)
        if payment is None:
            return

        payment.status = status
        payment.confirmed = confirmed
        async with self.get_session() as session:
            await self._update_current_payment_state(
                session,
                payment_id=str(payment_id),
                status=str(status),
                confirmed=bool(confirmed),
            )
    @log_function_call(logger)
    async def update_status_batch(self, updates: List[Tuple[str, str, bool]]) -> None:
        if not updates:
            return
        for payment_id, status, confirmed in updates:
            await self.update_status(str(payment_id), str(status), bool(confirmed))

    @log_function_call(logger)
    async def get_all(self) -> List[PaymentSnapshot]:
        async with self.get_session() as session:
            return await self._get_v2_payments(session)

    @log_function_call(logger)
    async def get_unconfirmed(self) -> List[PaymentSnapshot]:
        payments = await self.get_all()
        return [payment for payment in payments if not bool(payment.confirmed)]

    @log_function_call(logger)
    async def get_unconfirmed_paid(self) -> List[PaymentSnapshot]:
        payments = await self.get_all()
        return [
            payment
            for payment in payments
            if not bool(payment.confirmed)
            and str(payment.status).strip().lower() in PAID_PROVIDER_STATUSES
        ]

    @log_function_call(logger)
    async def has_any_for_user(self, tg_id: int) -> bool:
        async with self.get_session() as session:
            result = await session.execute(
                select(PaymentOrder.id)
                .join(
                    TelegramAccount,
                    (TelegramAccount.user_id == PaymentOrder.user_id)
                    & TelegramAccount.revoked_at.is_(None),
                )
                .where(TelegramAccount.telegram_id == int(tg_id))
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def _get_v2_payment_by_id(self, session, payment_id: str) -> PaymentSnapshot | None:
        payments = await self._get_v2_payments(session, payment_ids=[payment_id])
        return payments[0] if payments else None

    async def _get_v2_payments(
        self,
        session,
        payment_ids: list[str] | None = None,
    ) -> list[PaymentSnapshot]:
        stmt = (
            select(
                PaymentAttempt.provider_payment_id,
                PaymentAttempt.provider,
                PaymentAttempt.provider_status,
                PaymentAttempt.created_at.label("attempt_created_at"),
                PaymentOrder.user_id,
                PaymentOrder.status.label("order_status"),
                PaymentOrder.created_at.label("order_created_at"),
                PaymentOrder.fulfilled_at,
                PaymentOrder.subscription_grant_id,
                PaymentOrder.metadata_json,
                Plan.payload.label("plan_payload"),
                Plan.metadata_json.label("plan_metadata_json"),
                TelegramAccount.telegram_id,
            )
            .join(PaymentOrder, PaymentOrder.id == PaymentAttempt.order_id)
            .join(Plan, Plan.id == PaymentOrder.plan_id)
            .outerjoin(
                TelegramAccount,
                (TelegramAccount.user_id == PaymentOrder.user_id)
                & TelegramAccount.revoked_at.is_(None),
            )
        )
        if payment_ids:
            stmt = stmt.where(PaymentAttempt.provider_payment_id.in_(payment_ids))

        rows = (await session.execute(stmt)).all()
        return [self._build_snapshot_from_v2_row(row) for row in rows]

    def _build_snapshot_from_v2_row(self, row) -> PaymentSnapshot:
        order_metadata = row.metadata_json or {}
        plan_metadata = row.plan_metadata_json or {}

        payload = (
            str(order_metadata.get("plan_payload") or "").strip()
            or str(getattr(row, "plan_payload", "") or "").strip()
            or str(plan_metadata.get("plan_payload") or "").strip()
            or ""
        )
        status = self._map_v2_status_to_runtime(
            order_status=row.order_status,
            provider_status=row.provider_status,
        )
        confirmed = bool(
            row.fulfilled_at is not None
            or row.subscription_grant_id is not None
            or str(row.order_status).strip().lower() == ORDER_STATUS_FULFILLED
        )
        created_at = datetime_to_legacy_ms(
            row.order_created_at or row.attempt_created_at
        ) or 0

        return PaymentSnapshot(
            payment_id=str(row.provider_payment_id),
            user_id=int(row.user_id),
            tg_id=int(row.telegram_id) if row.telegram_id is not None else None,
            status=status,
            payload=payload,
            created_at=created_at,
            confirmed=confirmed,
            method=str(row.provider or "").strip().lower() or None,
        )

    async def _create_current_payment(self, session, obj: PaymentSnapshot) -> None:
        existing_attempt = await self._find_attempt(
            session,
            provider=self._normalize_provider_name(obj.method),
            provider_payment_id=str(obj.payment_id),
        )
        if existing_attempt is not None:
            return

        plan = await self._get_plan_for_payload(session, str(obj.payload))
        created_at = self._legacy_ts_to_datetime(obj.created_at) or datetime.now(timezone.utc)
        order_status = self._runtime_status_to_order_status(
            str(obj.status),
            confirmed=bool(obj.confirmed),
        )
        order = PaymentOrder(
            user_id=int(obj.user_id),
            plan_id=int(plan.id),
            status=order_status,
            amount=plan.price_amount,
            currency=str(plan.currency),
            created_at=created_at,
            paid_at=created_at if order_status in {ORDER_STATUS_PAID, ORDER_STATUS_FULFILLED} else None,
            fulfilled_at=created_at if order_status == ORDER_STATUS_FULFILLED else None,
            idempotency_key=f"runtime_payment:{obj.payment_id}",
            subscription_grant_id=None,
            metadata_json={
                "plan_payload": str(obj.payload),
                "legacy_payment_id": str(obj.payment_id),
                "initiated_via": "telegram" if obj.tg_id is not None else "web",
            },
        )
        session.add(order)
        await session.flush()

        attempt = PaymentAttempt(
            order_id=int(order.id),
            provider=self._normalize_provider_name(obj.method),
            provider_payment_id=str(obj.payment_id),
            provider_status=str(obj.status or "").strip().lower(),
            provider_payload_json={},
            created_at=created_at,
            updated_at=created_at,
            paid_at=created_at if str(obj.status or "").strip().lower() in PAID_PROVIDER_STATUSES else None,
        )
        session.add(attempt)
        await session.commit()

    async def _update_current_payment_state(
        self,
        session,
        *,
        payment_id: str,
        status: str,
        confirmed: bool,
    ) -> None:
        attempt = await self._find_attempt(
            session,
            provider="",
            provider_payment_id=str(payment_id),
        )
        if attempt is None:
            return

        order = await session.get(PaymentOrder, int(attempt.order_id))
        if order is None:
            return

        now = datetime.now(timezone.utc)
        normalized_status = str(status or "").strip().lower()
        attempt.provider_status = normalized_status
        attempt.updated_at = now
        if normalized_status in PAID_PROVIDER_STATUSES and attempt.paid_at is None:
            attempt.paid_at = now

        target_order_status = self._runtime_status_to_order_status(
            normalized_status,
            confirmed=confirmed,
        )
        if order.status != ORDER_STATUS_FULFILLED or target_order_status == ORDER_STATUS_FULFILLED:
            order.status = target_order_status
        if target_order_status in {ORDER_STATUS_PAID, ORDER_STATUS_FULFILLED} and order.paid_at is None:
            order.paid_at = now
        if target_order_status == ORDER_STATUS_FULFILLED and order.fulfilled_at is None:
            order.fulfilled_at = now
        if confirmed and order.subscription_grant_id is None:
            plan = await session.get(Plan, int(order.plan_id))
            if plan is None:
                raise ValueError(f"Plan {order.plan_id} not found for payment order {order.id}")
            if self._should_finalize_subscription_grant(plan):
                grant = await self._get_or_create_subscription_grant(
                    session,
                    order=order,
                    plan=plan,
                    created_at=order.created_at or now,
                    applied_at=now,
                    payment_id=str(payment_id),
                )
                order.subscription_grant_id = int(grant.id)
                order.status = ORDER_STATUS_FULFILLED

        await session.commit()

    async def _get_plan_for_payload(self, session, payload: str) -> Plan:
        seed = get_plan_seed_by_payload(str(payload))
        if seed is None:
            raise ValueError(f"Unsupported payment payload: {payload!r}")
        plan = (
            await session.execute(select(Plan).where(Plan.code == seed.code))
        ).scalar_one_or_none()
        if plan is None:
            raise ValueError(f"Plan {seed.code} not found for payload {payload!r}")
        return plan

    async def _resolve_user_id_by_tg_id(self, session, *, tg_id: int | None) -> int:
        if tg_id is None:
            raise ValueError("Payment requires either user_id or tg_id")
        telegram_account = (
            await session.execute(
                select(TelegramAccount).where(
                    TelegramAccount.telegram_id == int(tg_id),
                    TelegramAccount.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if telegram_account is None:
            raise ValueError(f"Telegram account not found for tg_id={tg_id}")
        return int(telegram_account.user_id)

    async def _get_or_create_subscription_grant(
        self,
        session,
        *,
        order: PaymentOrder,
        plan: Plan,
        created_at: datetime,
        applied_at: datetime,
        payment_id: str,
    ) -> SubscriptionGrant:
        if order.subscription_grant_id is not None:
            grant = await session.get(SubscriptionGrant, int(order.subscription_grant_id))
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

        subscription_state = await session.get(SubscriptionState, int(order.user_id))
        grant = SubscriptionGrant(
            user_id=int(order.user_id),
            plan_id=int(order.plan_id),
            source_type="payment_order",
            source_ref=str(order.id),
            status="applied",
            duration_days=plan.duration_days,
            expires_before=None,
            expires_after=getattr(subscription_state, "current_expires_at", None),
            created_at=created_at,
            applied_at=applied_at,
            metadata_json={
                "payment_id": str(payment_id),
            },
        )
        session.add(grant)
        await session.flush()
        return grant

    async def _find_attempt(
        self,
        session,
        *,
        provider: str,
        provider_payment_id: str,
    ) -> PaymentAttempt | None:
        normalized_provider = self._normalize_provider_name(provider)
        attempt = (
            await session.execute(
                select(PaymentAttempt).where(
                    PaymentAttempt.provider == normalized_provider,
                    PaymentAttempt.provider_payment_id == str(provider_payment_id),
                )
            )
        ).scalar_one_or_none()
        if attempt is not None:
            return attempt

        return (
            await session.execute(
                select(PaymentAttempt).where(
                    PaymentAttempt.provider_payment_id == str(provider_payment_id)
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _normalize_provider_name(value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        return normalized or "unknown"

    @staticmethod
    def _runtime_status_to_order_status(status: str | None, *, confirmed: bool) -> str:
        if confirmed:
            return ORDER_STATUS_FULFILLED

        normalized = str(status or "").strip().lower()
        if normalized in PAID_PROVIDER_STATUSES:
            return ORDER_STATUS_PAID
        if normalized == RUNTIME_PAYMENT_STATUS_CANCELED:
            return ORDER_STATUS_CANCELED
        if normalized == RUNTIME_PAYMENT_STATUS_FAILED:
            return ORDER_STATUS_FAILED
        return ORDER_STATUS_PENDING_PAYMENT

    def _map_v2_status_to_runtime(
        self,
        *,
        order_status: str | None,
        provider_status: str | None,
    ) -> str:
        normalized_provider = str(provider_status or "").strip().lower()
        normalized_order = str(order_status or "").strip().lower()

        if normalized_order == ORDER_STATUS_FULFILLED:
            return normalized_provider or RUNTIME_PAYMENT_STATUS_PAID
        if normalized_provider:
            return normalized_provider
        if normalized_order == ORDER_STATUS_PAID:
            return RUNTIME_PAYMENT_STATUS_PAID
        if normalized_order == ORDER_STATUS_CANCELED:
            return RUNTIME_PAYMENT_STATUS_CANCELED
        if normalized_order == ORDER_STATUS_FAILED:
            return RUNTIME_PAYMENT_STATUS_FAILED
        if normalized_order == ORDER_STATUS_PENDING_PAYMENT:
            return RUNTIME_PAYMENT_STATUS_PENDING
        return normalized_order or RUNTIME_PAYMENT_STATUS_PENDING

    @staticmethod
    def _should_finalize_subscription_grant(plan: Plan) -> bool:
        return str(getattr(plan, "entitlement_kind", "") or "").strip().lower() == ENTITLEMENT_KIND_TIME

    @staticmethod
    def _legacy_ts_to_datetime(timestamp_ms: int | None) -> datetime | None:
        if timestamp_ms is None:
            return None
        return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
