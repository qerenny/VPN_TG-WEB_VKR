from __future__ import annotations

from collections import defaultdict

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.growth_sync_service import (
    GrowthSyncService,
    ReferralRewardContext,
)
from shared.migration_support.models.promos.promo_code_model import PromoCode as LegacyPromoCode
from shared.migration_support.models.promos.promo_code_usage_model import PromoCodeUsage as LegacyPromoCodeUsage
from shared.migration_support.models.referrals.referral_model import Referral as LegacyReferral
from shared.migration_support.models.users.user_model import User as LegacyUser  # noqa: F401
from shared.scripts.rollout_support import run_async


async def main() -> None:
    service = GrowthSyncService(RolloutFeatureFlags(db_dual_write_growth=True))
    await service.seed_referral_reward_rules()

    async with get_db_session() as session:
        legacy_promo_codes = (
            await session.execute(select(LegacyPromoCode).order_by(LegacyPromoCode.code))
        ).scalars().all()
        legacy_promo_usages = (
            await session.execute(select(LegacyPromoCodeUsage).order_by(LegacyPromoCodeUsage.id))
        ).scalars().all()
        legacy_referrals = (
            await session.execute(select(LegacyReferral).order_by(LegacyReferral.tg_id))
        ).scalars().all()

    for promo in legacy_promo_codes:
        await service.sync_legacy_promo_code(promo_code=promo.code)

    for usage in legacy_promo_usages:
        await service.sync_promo_redemption(
            tg_id=int(usage.tg_id),
            promo_code=str(usage.code),
            legacy_usage_id=int(usage.id),
            legacy_backfill=True,
        )

    for referral in legacy_referrals:
        if referral.referrer_tg_id:
            await service.sync_referral_edge(
                referred_tg_id=int(referral.tg_id),
                referrer_tg_id=int(referral.referrer_tg_id),
                source="legacy_backfill",
            )

    for referral in legacy_referrals:
        pending_days = int(referral.days_pending or 0)
        if pending_days <= 0:
            continue
        await service.sync_referral_reward(
            beneficiary_tg_id=int(referral.tg_id),
            reward_days=pending_days,
            context=ReferralRewardContext(
                referred_tg_id=int(referral.tg_id),
                referrer_tg_id=int(referral.referrer_tg_id)
                if referral.referrer_tg_id is not None
                else None,
                trigger_type="legacy_pending_snapshot",
                trigger_ref=str(referral.tg_id),
                source="legacy_backfill",
                metadata={"legacy_snapshot": True},
            ),
            applied=False,
            legacy_backfill=True,
        )

    referrals_by_referrer: dict[int, list[LegacyReferral]] = defaultdict(list)
    referral_rows_by_tg_id = {int(referral.tg_id): referral for referral in legacy_referrals}
    for referral in legacy_referrals:
        if referral.referrer_tg_id and referral.bonus_is_received:
            referrals_by_referrer[int(referral.referrer_tg_id)].append(referral)

    for referrer_tg_id, referrals in referrals_by_referrer.items():
        ordered = sorted(referrals, key=lambda item: int(item.tg_id))
        for idx, referral in enumerate(ordered, start=1):
            await service.sync_referral_reward(
                beneficiary_tg_id=referrer_tg_id,
                reward_days=_calc_referrer_bonus(idx),
                context=ReferralRewardContext(
                    referred_tg_id=int(referral.tg_id),
                    referrer_tg_id=referrer_tg_id,
                    trigger_type="first_paid_order",
                    trigger_ref=str(referral.tg_id),
                    source="legacy_backfill",
                    metadata={
                        "legacy_snapshot": True,
                        "legacy_bonus_is_received": True,
                    },
                    paid_count_after_award=idx,
                ),
                applied=True,
                legacy_backfill=True,
            )

        referrer_row = referral_rows_by_tg_id.get(referrer_tg_id)
        target_paid_count = int(referrer_row.paid_count or 0) if referrer_row else len(ordered)
        for idx in range(len(ordered) + 1, target_paid_count + 1):
            await service.sync_referral_reward(
                beneficiary_tg_id=referrer_tg_id,
                reward_days=_calc_referrer_bonus(idx),
                context=ReferralRewardContext(
                    referred_tg_id=referrer_tg_id,
                    referrer_tg_id=None,
                    trigger_type="legacy_paid_count_snapshot",
                    trigger_ref=f"{referrer_tg_id}:{idx}",
                    source="legacy_backfill",
                    metadata={"legacy_snapshot": True},
                    paid_count_after_award=idx,
                ),
                applied=True,
                legacy_backfill=True,
            )

    print(
        "Phase 3 backfill completed: "
        f"synced {len(legacy_promo_codes)} promo codes, "
        f"{len(legacy_promo_usages)} promo usages and "
        f"{len(legacy_referrals)} referral rows into current tables."
    )


def _calc_referrer_bonus(count: int) -> int:
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


if __name__ == "__main__":
    run_async(main())
