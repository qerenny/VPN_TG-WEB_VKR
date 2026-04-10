from __future__ import annotations

import asyncio

from shared.config.settings import RuntimeSyncFlags
from shared.infrastructure.growth_service import GrowthService


async def main() -> None:
    service = GrowthService(RuntimeSyncFlags(growth_sync_enabled=True))
    created = await service.seed_referral_reward_rules()
    print(f"Seed referral reward rules completed: created {created} rule rows.")


if __name__ == "__main__":
    asyncio.run(main())
