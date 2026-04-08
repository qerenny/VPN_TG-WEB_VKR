from typing import Optional

from shared.infrastructure.referrals.referral_repository import (
    ReferralRepository,
)
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.infrastructure.growth_sync_service import (
    GrowthSyncService,
    ReferralRewardContext,
)
from shared.constants.referrals import (
    REFERRAL_REWARD_SOURCE_PAYMENT_FULFILLMENT,
    REFERRAL_TRIGGER_FIRST_PAID_ORDER,
)
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.infrastructure.api.client_manager import ClientManager


class ReferralBonusService:
    def __init__(
        self,
        repo_referrals: ReferralRepository,
        repo_user: TelegramUserRepository,
        timestamp: TimestampUtils,
        client: ClientManager,
        sync_service: GrowthSyncService | None = None,
    ):
        self.repo_referrals = repo_referrals
        self.timestamp = timestamp
        self.repo_user = repo_user
        self.client = client
        self.sync_service = sync_service

    async def grant_bonus_to_user(
        self,
        tg_id: int,
        days_amount: int,
        *,
        reward_context: ReferralRewardContext | None = None,
    ) -> None:
        """
        Grants bonus days to a user or stores them as pending if the user is inactive.
        """
        logger.info(f"Granting bonus: tg_id={tg_id}, days_amount={days_amount}")

        if days_amount is None or days_amount <= 0:
            logger.info(
                f"Invalid days_amount={days_amount} for tg_id={tg_id}, skipping bonus grant"
            )
            return

        user = await self.repo_user.get(tg_id)
        if user is None:
            logger.info(f"User {tg_id} not found while granting referral bonus")
            return

        now = self.timestamp.current_timestamp()
        expiration_date = user.expiration_date
        reward_applied = False

        if not expiration_date or expiration_date <= now:
            logger.info(f"User {tg_id} not active; keeping referral bonus pending")
            if not self._is_growth_sync_enabled():
                await self.repo_referrals.update_days_pending(tg_id, days_amount)
        else:
            logger.info(f"User {tg_id} has active subscription; updating via client")
            await self.client.update_client(tg_id, f"day{days_amount}", user=user)
            reward_applied = True

        await self._sync_referral_reward(
            beneficiary_tg_id=tg_id,
            reward_days=days_amount,
            reward_context=reward_context,
            applied=reward_applied,
        )

    async def grant_pending_and_referrer_bonus(
        self,
        tg_id: int,
    ) -> tuple[int, int | None, int | None]:
        logger.info(f"Starting pending bonus distribution for tg_id={tg_id}")

        pending_days = await self._grant_pending_days(tg_id)
        if pending_days is None or pending_days == 0:
            return 0, None, None

        referrer_info = await self._grant_bonus_to_referrer(tg_id)
        return pending_days, *referrer_info

    async def _grant_pending_days(self, tg_id: int) -> int:
        referral = await self.repo_referrals.get(tg_id)
        if not referral:
            logger.info(f"No referral record found for tg_id={tg_id}")
            return 0

        days_pending = referral.days_pending
        if days_pending is None or days_pending <= 0:
            logger.info(f"No pending days for tg_id={tg_id}")
            return 0

        await self.grant_bonus_to_user(tg_id, days_pending)
        await self._apply_pending_rewards(tg_id)
        logger.info(f"Granted and reset {days_pending} pending days for tg_id={tg_id}")
        return days_pending

    async def _grant_bonus_to_referrer(
        self,
        tg_id: int,
    ) -> tuple[Optional[int], Optional[int]]:
        referral = await self.repo_referrals.get(tg_id)
        if not referral or referral.bonus_is_received or not referral.referrer_tg_id:
            logger.info(f"No bonus to referrer needed for tg_id={tg_id}")
            return None, None

        referrer_tg_id = referral.referrer_tg_id
        referrer_referral = await self.repo_referrals.get(referrer_tg_id)
        paid_count = int(getattr(referrer_referral, "paid_count", 0) or 0) + 1
        bonus_days = self._calc_referrer_bonus(paid_count)

        await self.grant_bonus_to_user(
            referrer_tg_id,
            bonus_days,
            reward_context=ReferralRewardContext(
                referred_tg_id=tg_id,
                referrer_tg_id=referrer_tg_id,
                trigger_type=REFERRAL_TRIGGER_FIRST_PAID_ORDER,
                trigger_ref=str(tg_id),
                source=REFERRAL_REWARD_SOURCE_PAYMENT_FULFILLMENT,
                metadata={"legacy_bonus_is_received": True},
                paid_count_after_award=paid_count,
            ),
        )
        logger.info(
            f"Granted {bonus_days} bonus days to referrer {referrer_tg_id} "
            f"after {paid_count} paid invites"
        )
        return referrer_tg_id, bonus_days

    def _calc_referrer_bonus(self, count: int) -> int:
        """
        Bonus days for the number of paid invited friends.
        """
        match count:
            case 3:
                return 10
            case 5:
                return 15
            case 10:
                return 31
            case 15:
                return 62
            case _:
                return 7

    async def _sync_referral_reward(
        self,
        *,
        beneficiary_tg_id: int,
        reward_days: int,
        reward_context: ReferralRewardContext | None,
        applied: bool,
    ) -> None:
        if self.sync_service is None or reward_context is None:
            return
        try:
            await self.sync_service.sync_referral_reward(
                beneficiary_tg_id=beneficiary_tg_id,
                reward_days=reward_days,
                context=reward_context,
                applied=applied,
            )
        except Exception as err:
            logger.error(
                "Phase 3 dual write failed for referral reward "
                f"beneficiary_tg_id={beneficiary_tg_id}, "
                f"trigger_type={reward_context.trigger_type}, "
                f"trigger_ref={reward_context.trigger_ref}: {err!r}"
            )

    def _is_growth_sync_enabled(self) -> bool:
        if self.sync_service is None:
            return False
        features = getattr(self.sync_service, "features", None)
        return bool(getattr(features, "db_dual_write_growth", False))

    async def _apply_pending_rewards(self, beneficiary_tg_id: int) -> None:
        if self.sync_service is None:
            return
        try:
            await self.sync_service.apply_pending_referral_rewards(
                beneficiary_tg_id=beneficiary_tg_id,
            )
        except Exception as err:
            logger.error(
                "Phase 3 dual write failed while applying pending referral rewards "
                f"beneficiary_tg_id={beneficiary_tg_id}: {err!r}"
            )
