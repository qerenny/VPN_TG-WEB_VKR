from __future__ import annotations

from collections import defaultdict

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.migration_support.models.promos.promo_code_model import PromoCode as LegacyPromoCode
from shared.migration_support.models.promos.promo_code_usage_model import PromoCodeUsage as LegacyPromoCodeUsage
from shared.migration_support.models.referrals.referral_model import Referral as LegacyReferral
from shared.migration_support.models.users.user_model import User as LegacyUser  # noqa: F401
from shared.models import register_models
from shared.models.growth.promo_code_model import PromoCode
from shared.models.growth.promo_redemption_model import PromoRedemption
from shared.models.growth.referral_edge_model import ReferralEdge
from shared.models.growth.referral_reward_model import ReferralReward
from shared.models.growth.referral_reward_rule_model import ReferralRewardRule
from shared.models.users.telegram_account_model import TelegramAccount
from shared.scripts.rollout_support import RolloutCheck, print_checks, run_async

register_models()


async def main() -> None:
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
        promo_codes = (await session.execute(select(PromoCode))).scalars().all()
        promo_redemptions = (await session.execute(select(PromoRedemption))).scalars().all()
        referral_edges = (await session.execute(select(ReferralEdge))).scalars().all()
        referral_rewards = (await session.execute(select(ReferralReward))).scalars().all()
        referral_reward_rules = (
            await session.execute(select(ReferralRewardRule))
        ).scalars().all()
        telegram_accounts = (await session.execute(select(TelegramAccount))).scalars().all()

    user_id_by_tg_id = {
        int(account.telegram_id): int(account.user_id)
        for account in telegram_accounts
    }
    tg_id_by_user_id = {
        int(account.user_id): int(account.telegram_id)
        for account in telegram_accounts
    }
    promo_by_code = {promo.code: promo for promo in promo_codes}
    promo_code_by_id = {int(promo.id): promo.code for promo in promo_codes}
    redemptions_by_key = {
        (int(redemption.user_id), promo_code_by_id.get(int(redemption.promo_code_id))): redemption
        for redemption in promo_redemptions
    }
    redemption_count_by_promo_code = defaultdict(int)
    for redemption in promo_redemptions:
        promo_code = promo_code_by_id.get(int(redemption.promo_code_id))
        if promo_code is not None:
            redemption_count_by_promo_code[promo_code] += 1

    edges_by_referred_tg = {}
    for edge in referral_edges:
        referred_tg_id = tg_id_by_user_id.get(int(edge.referred_user_id))
        referrer_tg_id = tg_id_by_user_id.get(int(edge.referrer_user_id))
        if referred_tg_id is not None:
            edges_by_referred_tg[referred_tg_id] = referrer_tg_id

    pending_days_by_tg = defaultdict(int)
    paid_reward_count_by_tg = defaultdict(int)
    first_paid_reward_exists = set()
    for reward in referral_rewards:
        beneficiary_tg_id = tg_id_by_user_id.get(int(reward.beneficiary_user_id))
        if beneficiary_tg_id is None or reward.canceled_at is not None:
            continue
        if reward.applied_at is None:
            pending_days_by_tg[beneficiary_tg_id] += int(reward.reward_days)
        if reward.applied_at is not None and reward.trigger_type in {
            "first_paid_order",
            "legacy_paid_count_snapshot",
        }:
            paid_reward_count_by_tg[beneficiary_tg_id] += 1
        if reward.applied_at is not None and reward.trigger_type == "first_paid_order":
            first_paid_reward_exists.add((beneficiary_tg_id, str(reward.trigger_ref)))

    missing_promo_codes = 0
    promo_remaining_uses_mismatches = 0
    for legacy_promo in legacy_promo_codes:
        promo = promo_by_code.get(str(legacy_promo.code))
        if promo is None:
            missing_promo_codes += 1
            continue
        if legacy_promo.remaining_uses is None:
            if promo.max_redemptions is not None:
                promo_remaining_uses_mismatches += 1
            continue
        remaining = int(promo.max_redemptions or 0) - redemption_count_by_promo_code.get(
            str(legacy_promo.code),
            0,
        )
        if remaining != int(legacy_promo.remaining_uses):
            promo_remaining_uses_mismatches += 1

    missing_redemptions = 0
    for legacy_usage in legacy_promo_usages:
        user_id = user_id_by_tg_id.get(int(legacy_usage.tg_id))
        if user_id is None or (user_id, str(legacy_usage.code)) not in redemptions_by_key:
            missing_redemptions += 1

    missing_edges = 0
    pending_days_mismatches = 0
    paid_count_mismatches = 0
    bonus_flag_mismatches = 0
    for legacy_referral in legacy_referrals:
        tg_id = int(legacy_referral.tg_id)
        referrer_tg_id = (
            int(legacy_referral.referrer_tg_id)
            if legacy_referral.referrer_tg_id is not None
            else None
        )
        if referrer_tg_id is not None and edges_by_referred_tg.get(tg_id) != referrer_tg_id:
            missing_edges += 1

        if pending_days_by_tg.get(tg_id, 0) != int(legacy_referral.days_pending or 0):
            pending_days_mismatches += 1

        if paid_reward_count_by_tg.get(tg_id, 0) != int(legacy_referral.paid_count or 0):
            paid_count_mismatches += 1

        expected_bonus_received = bool(legacy_referral.bonus_is_received)
        actual_bonus_received = (
            referrer_tg_id is not None
            and (referrer_tg_id, str(tg_id)) in first_paid_reward_exists
        )
        if expected_bonus_received != actual_bonus_received:
            bonus_flag_mismatches += 1

    rules_by_threshold = {
        int(rule.paid_referrals_threshold): int(rule.reward_days)
        for rule in referral_reward_rules
        if rule.is_active
    }
    expected_rules = {1: 7, 3: 10, 5: 15, 10: 31, 15: 62}

    checks = [
        RolloutCheck(
            name="legacy promo codes mapped to promo_codes",
            ok=missing_promo_codes == 0,
            details=f"missing={missing_promo_codes}",
        ),
        RolloutCheck(
            name="legacy promo usages mapped to promo_redemptions",
            ok=missing_redemptions == 0,
            details=f"missing={missing_redemptions}",
        ),
        RolloutCheck(
            name="promo remaining_uses parity",
            ok=promo_remaining_uses_mismatches == 0,
            details=f"mismatches={promo_remaining_uses_mismatches}",
        ),
        RolloutCheck(
            name="referral reward rules seeded",
            ok=rules_by_threshold == expected_rules,
            details=f"present={rules_by_threshold}",
        ),
        RolloutCheck(
            name="legacy referral links mapped to referral_edges",
            ok=missing_edges == 0,
            details=f"missing={missing_edges}",
        ),
        RolloutCheck(
            name="legacy referral pending days parity",
            ok=pending_days_mismatches == 0,
            details=f"mismatches={pending_days_mismatches}",
        ),
        RolloutCheck(
            name="legacy referral paid_count parity",
            ok=paid_count_mismatches == 0,
            details=f"mismatches={paid_count_mismatches}",
        ),
        RolloutCheck(
            name="legacy referral bonus_is_received parity",
            ok=bonus_flag_mismatches == 0,
            details=f"mismatches={bonus_flag_mismatches}",
        ),
    ]
    print_checks(checks)
    if not all(check.ok for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    run_async(main())
