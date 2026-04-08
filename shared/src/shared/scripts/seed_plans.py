from __future__ import annotations

from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.payment_sync_service import PaymentSyncService
from shared.scripts.rollout_support import run_async


async def main() -> None:
    service = PaymentSyncService(
        RolloutFeatureFlags(db_dual_write_payments=True)
    )
    created = await service.seed_default_plans()
    print(f"Seed plans completed: created {created} plan rows.")


if __name__ == "__main__":
    run_async(main())
