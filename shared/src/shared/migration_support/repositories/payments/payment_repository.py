from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlmodel import select

from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.base_repository import BaseRepository
from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_legacy_payload
from shared.infrastructure.payment_sync_service import PaymentSyncService
from shared.migration_support.models.payments.payment_model import Payment
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.payments.plan_model import Plan
from shared.models.users.telegram_account_model import TelegramAccount
from shared.product_constants import ENTITLEMENT_KIND_TIME
from shared.utils.logging_utils import log_function_call, setup_logger

logger = setup_logger("migration_support.payments.repository", "database.log")

PAID_STATUSES = {"paid", "succeeded"}
CANCELED_STATUSES = {"canceled", "cancelled", "expired"}
FAILED_STATUSES = {"failed", "refunded", "rejected"}


class PaymentRepository(BaseRepository[Payment]):
    def __init__(self, features: RolloutFeatureFlags | None = None):
        super().__init__(Payment)
        self.features = features or RolloutFeatureFlags()
        self.sync_service = PaymentSyncService(
            RolloutFeatureFlags(db_dual_write_payments=True)
        )

    @log_function_call(logger)
    async def create(self, obj: Payment) -> Payment:
        await self.sync_service.sync_legacy_payment(
            obj,
            provider=obj.method,
            status_changed_at=self._legacy_ts_to_datetime(obj.created_at)
            or datetime.now(timezone.utc),
        )
        return obj

    @log_function_call(logger)
    async def get_by_payment_id(self, payment_id: str) -> Optional[Payment]:
        async with self.get_session() as session:
            return await self._get_v2_payment_by_id(session, payment_id)

    @log_function_call(logger)
    async def update_status(self, payment_id: str, status: str, confirmed: bool) -> None:
        payment = await self.get_by_payment_id(payment_id)
        if payment is None:
            return

        payment.status = status
        payment.confirmed = confirmed
        await self.sync_service.sync_legacy_payment(
            payment,
            provider=payment.method,
        )
        if confirmed and self._should_finalize_subscription_grant(payment.payload):
            await self.sync_service.finalize_subscription_grant(payment)

    @log_function_call(logger)
    async def update_status_batch(self, updates: List[Tuple[str, str, bool]]) -> None:
        if not updates:
            return

        for payment_id, status, confirmed in updates:
            await self.update_status(str(payment_id), str(status), bool(confirmed))

    @log_function_call(logger)
    async def get_all(self) -> List[Payment]:
        async with self.get_session() as session:
            return await self._get_v2_payments(session)

    @log_function_call(logger)
    async def get_unconfirmed(self) -> List[Payment]:
        payments = await self.get_all()
        return [payment for payment in payments if not bool(payment.confirmed)]

    @log_function_call(logger)
    async def get_unconfirmed_paid(self) -> List[Payment]:
        payments = await self.get_all()
        return [
            payment
            for payment in payments
            if not bool(payment.confirmed)
            and str(payment.status).strip().lower() in PAID_STATUSES
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

    async def _get_v2_payment_by_id(self, session, payment_id: str) -> Payment | None:
        payments = await self._get_v2_payments(session, payment_ids=[payment_id])
        return payments[0] if payments else None

    async def _get_v2_payments(
        self,
        session,
        payment_ids: list[str] | None = None,
    ) -> list[Payment]:
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
                Plan.legacy_payload.label("plan_legacy_payload"),
                Plan.metadata_json.label("plan_metadata_json"),
                TelegramAccount.telegram_id,
            )
            .join(PaymentOrder, PaymentOrder.id == PaymentAttempt.order_id)
            .join(Plan, Plan.id == PaymentOrder.plan_id)
            .join(
                TelegramAccount,
                (TelegramAccount.user_id == PaymentOrder.user_id)
                & TelegramAccount.revoked_at.is_(None),
            )
        )
        if payment_ids:
            stmt = stmt.where(PaymentAttempt.provider_payment_id.in_(payment_ids))

        rows = (await session.execute(stmt)).all()
        return [self._build_legacy_payment_from_v2_row(row) for row in rows]

    def _build_legacy_payment_from_v2_row(self, row) -> Payment:
        order_metadata = row.metadata_json or {}
        plan_metadata = row.plan_metadata_json or {}

        payload = (
            str(order_metadata.get("legacy_payload") or "").strip()
            or str(getattr(row, "plan_legacy_payload", "") or "").strip()
            or str(plan_metadata.get("legacy_payload") or "").strip()
            or ""
        )
        status = self._map_v2_status_to_legacy(
            order_status=row.order_status,
            provider_status=row.provider_status,
        )
        confirmed = bool(
            row.fulfilled_at is not None
            or row.subscription_grant_id is not None
            or str(row.order_status).strip().lower() == "fulfilled"
        )
        created_at = self._datetime_to_legacy_ms(
            row.order_created_at or row.attempt_created_at
        ) or 0

        return Payment(
            payment_id=str(row.provider_payment_id),
            tg_id=int(row.telegram_id),
            status=status,
            payload=payload,
            created_at=created_at,
            confirmed=confirmed,
            method=str(row.provider or "").strip().lower() or None,
        )

    def _map_v2_status_to_legacy(
        self,
        *,
        order_status: str | None,
        provider_status: str | None,
    ) -> str:
        normalized_provider = str(provider_status or "").strip().lower()
        normalized_order = str(order_status or "").strip().lower()

        if normalized_order == "fulfilled":
            return normalized_provider or "paid"
        if normalized_provider:
            return normalized_provider
        if normalized_order == "paid":
            return "paid"
        if normalized_order == "canceled":
            return "canceled"
        if normalized_order == "failed":
            return "failed"
        if normalized_order == "pending_payment":
            return "pending"
        return normalized_order or "pending"

    @staticmethod
    def _should_finalize_subscription_grant(payload: str) -> bool:
        seed = get_plan_seed_by_legacy_payload(str(payload))
        if seed is None:
            return True
        return seed.entitlement_kind == ENTITLEMENT_KIND_TIME

    @staticmethod
    def _datetime_to_legacy_ms(value: datetime | None) -> int | None:
        normalized = PaymentRepository._ensure_utc(value)
        if normalized is None:
            return None
        return int(normalized.timestamp() * 1000)

    @staticmethod
    def _legacy_ts_to_datetime(timestamp_ms: int | None) -> datetime | None:
        if timestamp_ms is None:
            return None
        return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)

    @staticmethod
    def _ensure_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
