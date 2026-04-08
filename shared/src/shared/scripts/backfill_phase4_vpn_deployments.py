from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.vpn_topology_sync_service import VpnTopologySyncService
from shared.migration_support.models.users.user_model import User as LegacyUser
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
    await service.seed_topology(allow_destructive_sync=allow_destructive_sync)

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    async with get_db_session() as session:
        legacy_users = (
            await session.execute(select(LegacyUser).order_by(LegacyUser.tg_id))
        ).scalars().all()

    active_users = [
        user
        for user in legacy_users
        if user.expiration_date is not None and int(user.expiration_date) > now_ms
    ]
    for user in active_users:
        await service.sync_legacy_user_deployments(
            user,
            allow_destructive_sync=allow_destructive_sync,
        )

    print(
        "Phase 4 backfill completed: "
        f"synced {len(active_users)} active legacy users into vpn_client_deployments "
        f"(allow_destructive_sync={allow_destructive_sync})."
    )


if __name__ == "__main__":
    run_async(main())
