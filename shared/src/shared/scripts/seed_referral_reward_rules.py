from __future__ import annotations

from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.growth_sync_service import GrowthSyncService
from shared.scripts.rollout_support import run_async


async def main() -> None:
    service = GrowthSyncService(RolloutFeatureFlags(db_dual_write_growth=True))
    created = await service.seed_referral_reward_rules()
    print(f"Seed referral reward rules completed: created {created} rule rows.")


if __name__ == "__main__":
    run_async(main())
