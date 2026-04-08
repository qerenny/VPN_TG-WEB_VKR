from datetime import datetime, timezone
from typing import List

import sqlalchemy as sa
from sqlmodel import select

from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.base_repository import BaseRepository
from shared.infrastructure.growth_sync_service import (
    GrowthSyncService,
    ReferralRewardContext,
)
from shared.migration_support.models.referrals.referral_model import Referral
from shared.models.growth.referral_edge_model import ReferralEdge
from shared.models.growth.referral_reward_model import ReferralReward
from shared.models.users.telegram_account_model import TelegramAccount
from shared.utils.logging_utils import log_function_call, setup_logger

logger = setup_logger("migration_support.referral.repository", "database.log")


class ReferralRepository(BaseRepository[Referral]):
    def __init__(self, features: RolloutFeatureFlags | None = None):
        super().__init__(Referral)
        self.features = features or RolloutFeatureFlags()
        self.sync_service = GrowthSyncService(
            RolloutFeatureFlags(db_dual_write_growth=True)
        )

    @log_function_call(logger)
    async def get(self, id: int) -> Referral | None:
        async with self.get_session() as session:
            referral = await self._get_v2_referral(session, int(id))
            if referral is not None:
                return referral

            user_id = await self._resolve_user_id(session, int(id))
            if user_id is None:
                return None

            return Referral(tg_id=int(id))

    @log_function_call(logger)
    async def update_referrer(self, tg_id: int, referrer_tg_id: int) -> None:
        await self.sync_service.sync_referral_edge(
            referred_tg_id=int(tg_id),
            referrer_tg_id=int(referrer_tg_id),
            source="telegram_start",
        )

    @log_function_call(logger)
    async def get_users_by_referrer(self, referrer_tg_id: int) -> List[tuple[int]]:
        async with self.get_session() as session:
            user_id = await self._resolve_user_id(session, int(referrer_tg_id))
            if user_id is None:
                return []

            result = await session.execute(
                select(TelegramAccount.telegram_id)
                .join(
                    ReferralEdge,
                    ReferralEdge.referred_user_id == TelegramAccount.user_id,
                )
                .where(
                    ReferralEdge.referrer_user_id == user_id,
                    TelegramAccount.revoked_at.is_(None),
                )
                .order_by(TelegramAccount.telegram_id)
            )
            return [(int(tg_id),) for tg_id in result.scalars().all()]

    @log_function_call(logger)
    async def update_days_pending(self, tg_id: int, amount: int) -> None:
        if int(amount or 0) <= 0:
            return
        await self.sync_service.sync_referral_reward(
            beneficiary_tg_id=int(tg_id),
            reward_days=int(amount),
            context=ReferralRewardContext(
                referred_tg_id=int(tg_id),
                referrer_tg_id=None,
                trigger_type="manual_pending_bonus",
                trigger_ref=f"{tg_id}:{amount}:{int(datetime.now(timezone.utc).timestamp())}",
                source="referral_repository",
            ),
            applied=False,
        )

    async def reset_days_pending(self, tg_id: int) -> None:
        return None

    async def set_bonus_received(self, tg_id: int) -> None:
        return None

    async def increment_paid_count(self, tg_id: int) -> None:
        return None

    async def is_symmetrical_referral(self, tg_id: int, referrer_tg_id: int) -> bool:
        async with self.get_session() as session:
            source_user_id = await self._resolve_user_id(session, int(tg_id))
            target_user_id = await self._resolve_user_id(session, int(referrer_tg_id))
            if source_user_id is None or target_user_id is None:
                return False

            result = await session.execute(
                select(ReferralEdge.id).where(
                    ReferralEdge.referrer_user_id == source_user_id,
                    ReferralEdge.referred_user_id == target_user_id,
                )
            )
            return result.scalar_one_or_none() is not None

    async def _resolve_user_id(self, session, tg_id: int) -> int | None:
        return (
            await session.execute(
                select(TelegramAccount.user_id).where(
                    TelegramAccount.telegram_id == tg_id,
                    TelegramAccount.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def _get_v2_referral(self, session, tg_id: int) -> Referral | None:
        user_id = await self._resolve_user_id(session, tg_id)
        if user_id is None:
            return None

        referrer_tg_id = (
            await session.execute(
                select(TelegramAccount.telegram_id)
                .join(
                    ReferralEdge,
                    ReferralEdge.referrer_user_id == TelegramAccount.user_id,
                )
                .where(
                    ReferralEdge.referred_user_id == user_id,
                    TelegramAccount.revoked_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        invited_count = (
            await session.execute(
                select(sa.func.count(ReferralEdge.id)).where(
                    ReferralEdge.referrer_user_id == user_id
                )
            )
        ).scalar_one()
        days_pending = (
            await session.execute(
                select(sa.func.coalesce(sa.func.sum(ReferralReward.reward_days), 0)).where(
                    ReferralReward.beneficiary_user_id == user_id,
                    ReferralReward.applied_at.is_(None),
                    ReferralReward.canceled_at.is_(None),
                )
            )
        ).scalar_one()
        paid_count = (
            await session.execute(
                select(sa.func.count(ReferralReward.id)).where(
                    ReferralReward.beneficiary_user_id == user_id,
                    ReferralReward.trigger_type == "first_paid_order",
                    ReferralReward.canceled_at.is_(None),
                )
            )
        ).scalar_one()
        bonus_is_received = (
            await session.execute(
                select(ReferralReward.id).where(
                    ReferralReward.trigger_type == "first_paid_order",
                    ReferralReward.trigger_ref == str(tg_id),
                    ReferralReward.canceled_at.is_(None),
                ).limit(1)
            )
        ).scalar_one_or_none() is not None

        return Referral(
            tg_id=int(tg_id),
            referrer_tg_id=int(referrer_tg_id) if referrer_tg_id is not None else None,
            days_pending=int(days_pending or 0),
            invited_count=int(invited_count or 0),
            paid_count=int(paid_count or 0),
            bonus_is_received=bool(bonus_is_received),
        )
