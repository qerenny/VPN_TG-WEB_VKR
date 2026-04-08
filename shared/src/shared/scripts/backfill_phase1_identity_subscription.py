from __future__ import annotations

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.identity_subscription_sync_service import (
    IdentitySubscriptionSyncService,
)
from shared.migration_support.models.users.user_model import User as LegacyUser
from shared.scripts.rollout_support import run_async


async def main() -> None:
    service = IdentitySubscriptionSyncService(
        RolloutFeatureFlags(
            db_dual_write_identity=True,
            db_dual_write_subscription=True,
        )
    )

    async with get_db_session() as session:
        result = await session.execute(select(LegacyUser))
        legacy_users = result.scalars().all()

    for user in legacy_users:
        await service.sync_legacy_user(user)

    print(
        f"Phase 1 backfill completed: synced {len(legacy_users)} legacy users into current tables."
    )


if __name__ == "__main__":
    run_async(main())
