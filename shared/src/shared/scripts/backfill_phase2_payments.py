from __future__ import annotations

from shared.config.database.session import get_db_session
from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.payment_sync_service import PaymentSyncService
from shared.migration_support.models.payments.payment_model import Payment as LegacyPayment
from shared.scripts.rollout_support import run_async
from sqlmodel import select


async def main() -> None:
    service = PaymentSyncService(
        RolloutFeatureFlags(db_dual_write_payments=True)
    )
    await service.seed_default_plans()

    async with get_db_session() as session:
        legacy_payments = (
            await session.execute(
                select(LegacyPayment).order_by(LegacyPayment.created_at, LegacyPayment.payment_id)
            )
        ).scalars().all()

    for payment in legacy_payments:
        await service.sync_legacy_payment(
            payment,
            provider=payment.method,
        )
        if payment.confirmed:
            await service.finalize_subscription_grant(
                payment,
                applied_at=service._legacy_ts_to_datetime(payment.created_at),
                legacy_backfill=True,
            )

    print(
        "Phase 2 backfill completed: "
        f"synced {len(legacy_payments)} legacy payments into current tables."
    )


if __name__ == "__main__":
    run_async(main())
