from __future__ import annotations

import os

from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.vpn_topology_sync_service import VpnTopologySyncService
from shared.scripts.rollout_support import run_async


async def main() -> None:
    service = VpnTopologySyncService(RolloutFeatureFlags(db_dual_write_vpn_topology=True))
    raw_allow_destructive_sync = os.getenv(
        "APP_ALLOW_TOPOLOGY_DESTRUCTIVE_SYNC",
        os.getenv("NOWMEOW_ALLOW_TOPOLOGY_DESTRUCTIVE_SYNC", ""),
    )
    allow_destructive_sync = str(raw_allow_destructive_sync).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    result = await service.seed_topology(
        allow_destructive_sync=allow_destructive_sync
    )
    print(
        "Seed vpn topology completed: "
        f"control_planes_created={result.control_planes_created}, "
        f"locations_created={result.locations_created}, "
        f"access_points_created={result.access_points_created}, "
        f"allow_destructive_sync={allow_destructive_sync}."
    )


if __name__ == "__main__":
    run_async(main())
