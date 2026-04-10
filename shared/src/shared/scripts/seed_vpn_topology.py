from __future__ import annotations

import asyncio
import os

from shared.config.settings import RuntimeSyncFlags
from shared.infrastructure.vpn_topology_service import VpnTopologyService


async def main() -> None:
    service = VpnTopologyService(RuntimeSyncFlags(vpn_topology_sync_enabled=True))
    raw_allow_destructive_sync = os.getenv(
        "REMOTE_ACCESS_ALLOW_TOPOLOGY_DESTRUCTIVE_SYNC",
        "",
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
    asyncio.run(main())
