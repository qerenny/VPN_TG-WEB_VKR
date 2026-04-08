from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_legacy_payload
from shared.migration_support.models.promos.promo_code_model import PromoCode as LegacyPromoCode
from shared.migration_support.models.promos.promo_code_usage_model import PromoCodeUsage as LegacyPromoCodeUsage
from shared.migration_support.models.users.user_model import User as LegacyUser  # noqa: F401
from shared.models import register_models
from shared.models.growth.promo_code_model import PromoCode
from shared.models.growth.promo_redemption_model import PromoRedemption
from shared.models.growth.referral_edge_model import ReferralEdge
from shared.models.growth.referral_reward_model import ReferralReward
from shared.models.growth.referral_reward_rule_model import ReferralRewardRule
from shared.models.payments.plan_model import Plan
from shared.models.subscriptions.subscription_grant_model import SubscriptionGrant
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.telegram_account_model import TelegramAccount
from shared.utils.logging_utils import setup_logger

logger = setup_logger("rollout.phase3.growth", "database.log")

register_models()


@dataclass(frozen=True, slots=True)
class ReferralRewardRuleSeed:
    paid_referrals_threshold: int
    reward_days: int


@dataclass(frozen=True, slots=True)
class ReferralRewardContext:
    referred_tg_id: int
    referrer_tg_id: int | None
    trigger_type: str
    trigger_ref: str
    source: str = "telegram_bot"
    metadata: dict[str, Any] | None = None
    paid_count_after_award: int | None = None


DEFAULT_REFERRAL_REWARD_RULE_SEEDS: tuple[ReferralRewardRuleSeed, ...] = (
    ReferralRewardRuleSeed(1, 7),
    ReferralRewardRuleSeed(3, 10),
    ReferralRewardRuleSeed(5, 15),
    ReferralRewardRuleSeed(10, 31),
    ReferralRewardRuleSeed(15, 62),
)


class GrowthSyncService:
    def __init__(self, features: RolloutFeatureFlags):
        self.features = features

    async def seed_referral_reward_rules(self) -> int:
        async with get_db_session() as session:
            created = await self._ensure_referral_reward_rules(session)
            await session.commit()
            return created

    async def sync_legacy_promo_code(
        self,
        *,
        promo_code: str,
        synced_at: datetime | None = None,
    ) -> int | None:
        if not self.features.db_dual_write_growth:
            return None

        promo_code = str(promo_code or "").strip()
        if not promo_code:
            raise ValueError("promo_code is required")

        async with get_db_session() as session:
            legacy_promo = await self._get_legacy_promo(session, promo_code)
            if legacy_promo is None:
                raise ValueError(f"Legacy promo code not found: {promo_code!r}")
            promo = await self._upsert_promo_code_from_legacy(
                session,
                legacy_promo=legacy_promo,
                now=synced_at or datetime.now(timezone.utc),
            )
            await session.commit()
            return int(promo.id)

    async def sync_promo_redemption(
        self,
        *,
        tg_id: int,
        promo_code: str,
        redeemed_at: datetime | None = None,
        legacy_usage_id: int | None = None,
        legacy_backfill: bool = False,
    ) -> int | None:
        if not self.features.db_dual_write_growth:
            return None

        promo_code = str(promo_code or "").strip()
        if not promo_code:
            raise ValueError("promo_code is required")

        async with get_db_session() as session:
            await self._ensure_referral_reward_rules(session)
            legacy_promo = await self._get_legacy_promo(session, promo_code)
            if legacy_promo is None:
                raise ValueError(f"Legacy promo code not found: {promo_code!r}")

            user_id = await self._resolve_user_id(session, int(tg_id))
            now = redeemed_at or datetime.now(timezone.utc)
            promo = await self._upsert_promo_code_from_legacy(
                session,
                legacy_promo=legacy_promo,
                now=now,
            )
            redemption = await self._get_or_create_promo_redemption(
                session,
                promo_code_id=int(promo.id),
                user_id=user_id,
                redeemed_at=now,
            )
            await self._ensure_promo_grant(
                session,
                redemption=redemption,
                promo=promo,
                legacy_promo=legacy_promo,
                tg_id=int(tg_id),
                granted_at=now,
                legacy_usage_id=legacy_usage_id,
                legacy_backfill=legacy_backfill,
            )
            await session.commit()
            return int(redemption.id)

    async def sync_referral_edge(
        self,
        *,
        referred_tg_id: int,
        referrer_tg_id: int,
        source: str,
        created_at: datetime | None = None,
    ) -> int | None:
        if not self.features.db_dual_write_growth:
            return None

        async with get_db_session() as session:
            edge = await self._upsert_referral_edge(
                session,
                referred_tg_id=int(referred_tg_id),
                referrer_tg_id=int(referrer_tg_id),
                source=source,
                created_at=created_at or datetime.now(timezone.utc),
            )
            await session.commit()
            return int(edge.id)

    async def sync_referral_reward(
        self,
        *,
        beneficiary_tg_id: int,
        reward_days: int,
        context: ReferralRewardContext,
        applied: bool,
        created_at: datetime | None = None,
        applied_at: datetime | None = None,
        legacy_backfill: bool = False,
    ) -> int | None:
        if not self.features.db_dual_write_growth:
            return None

        if reward_days <= 0:
            return None

        async with get_db_session() as session:
            await self._ensure_referral_reward_rules(session)
            beneficiary_user_id = await self._resolve_user_id(session, int(beneficiary_tg_id))
            edge = None
            if context.referrer_tg_id is not None:
                edge = await self._upsert_referral_edge(
                    session,
                    referred_tg_id=int(context.referred_tg_id),
                    referrer_tg_id=int(context.referrer_tg_id),
                    source=context.source,
                    created_at=created_at or datetime.now(timezone.utc),
                )

            reward = await self._get_or_create_referral_reward(
                session,
                edge_id=int(edge.id) if edge is not None else None,
                beneficiary_user_id=beneficiary_user_id,
                reward_days=int(reward_days),
                context=context,
                created_at=created_at or datetime.now(timezone.utc),
            )
            if applied:
                await self._apply_single_referral_reward(
                    session,
                    reward=reward,
                    beneficiary_tg_id=int(beneficiary_tg_id),
                    applied_at=applied_at or created_at or datetime.now(timezone.utc),
                    legacy_backfill=legacy_backfill,
                )
            elif legacy_backfill:
                reward.metadata_json = {
                    **(reward.metadata_json or {}),
                    "legacy_backfill": True,
                }
            await session.commit()
            return int(reward.id)

    async def apply_pending_referral_rewards(
        self,
        *,
        beneficiary_tg_id: int,
        applied_at: datetime | None = None,
        legacy_backfill: bool = False,
    ) -> int:
        if not self.features.db_dual_write_growth:
            return 0

        async with get_db_session() as session:
            user_id = await self._resolve_user_id(session, int(beneficiary_tg_id))
            rewards = (
                await session.execute(
                    select(ReferralReward)
                    .where(
                        ReferralReward.beneficiary_user_id == user_id,
                        ReferralReward.applied_at.is_(None),
                        ReferralReward.canceled_at.is_(None),
                    )
                    .order_by(ReferralReward.created_at, ReferralReward.id)
                )
            ).scalars().all()
            if not rewards:
                await session.commit()
                return 0

            effective_applied_at = applied_at or datetime.now(timezone.utc)
            final_expiry = await self._load_current_expiry(
                session,
                tg_id=int(beneficiary_tg_id),
                user_id=user_id,
            )
            cursor = None
            if final_expiry is not None:
                total_days = sum(max(0, int(reward.reward_days)) for reward in rewards)
                cursor = final_expiry - timedelta(days=total_days)

            applied_count = 0
            for reward in rewards:
                reward.applied_at = effective_applied_at
                if reward.subscription_grant_id is None:
                    expires_before = cursor
                    expires_after = None
                    if cursor is not None:
                        expires_after = cursor + timedelta(days=int(reward.reward_days))
                        cursor = expires_after
                    grant = await self._create_referral_grant(
                        session,
                        reward=reward,
                        beneficiary_tg_id=int(beneficiary_tg_id),
                        applied_at=effective_applied_at,
                        expires_before=expires_before,
                        expires_after=expires_after,
                        legacy_backfill=legacy_backfill,
                    )
                    reward.subscription_grant_id = int(grant.id)
                applied_count += 1

            await session.commit()
            return applied_count

    async def _ensure_referral_reward_rules(self, session) -> int:
        existing_thresholds = set(
            (await session.execute(select(ReferralRewardRule.paid_referrals_threshold)))
            .scalars()
            .all()
        )
        created = 0
        for seed in DEFAULT_REFERRAL_REWARD_RULE_SEEDS:
            if seed.paid_referrals_threshold in existing_thresholds:
                continue
            session.add(
                ReferralRewardRule(
                    paid_referrals_threshold=seed.paid_referrals_threshold,
                    reward_days=seed.reward_days,
                    is_active=True,
                )
            )
            created += 1
        if created:
            await session.flush()
        return created

    async def _get_legacy_promo(self, session, promo_code: str) -> LegacyPromoCode | None:
        return (
            await session.execute(
                select(LegacyPromoCode).where(LegacyPromoCode.code == promo_code)
            )
        ).scalar_one_or_none()

    async def _upsert_promo_code_from_legacy(
        self,
        session,
        *,
        legacy_promo: LegacyPromoCode,
        now: datetime,
    ) -> PromoCode:
        usage_count = (
            await session.execute(
                select(LegacyPromoCodeUsage).where(LegacyPromoCodeUsage.code == legacy_promo.code)
            )
        ).scalars().all()
        usage_total = len(usage_count)
        existing = (
            await session.execute(select(PromoCode).where(PromoCode.code == legacy_promo.code))
        ).scalar_one_or_none()
        seed = get_plan_seed_by_legacy_payload(str(legacy_promo.duration))
        plan = None
        if seed is not None:
            plan = (
                await session.execute(select(Plan).where(Plan.code == seed.code))
            ).scalar_one_or_none()

        max_redemptions = None
        if legacy_promo.remaining_uses is not None:
            max_redemptions = int(legacy_promo.remaining_uses) + usage_total

        payload = {
            "plan_id": int(plan.id) if plan is not None else None,
            "duration_days_override": None
            if plan is not None
            else self._duration_days_from_period(str(legacy_promo.duration)),
            "max_redemptions": max_redemptions,
            "per_user_limit": 1,
            "valid_from": None,
            "valid_until": None,
            "is_active": legacy_promo.remaining_uses is None or int(legacy_promo.remaining_uses) > 0,
            "metadata_json": {
                "legacy_duration": str(legacy_promo.duration),
                "legacy_remaining_uses_snapshot": legacy_promo.remaining_uses,
            },
        }
        if existing is None:
            existing = PromoCode(
                code=str(legacy_promo.code),
                created_at=now,
                **payload,
            )
            session.add(existing)
            await session.flush()
            return existing

        existing.plan_id = payload["plan_id"]
        existing.duration_days_override = payload["duration_days_override"]
        existing.max_redemptions = payload["max_redemptions"]
        existing.per_user_limit = payload["per_user_limit"]
        existing.valid_from = payload["valid_from"]
        existing.valid_until = payload["valid_until"]
        existing.is_active = payload["is_active"]
        existing.metadata_json = payload["metadata_json"]
        return existing

    async def _get_or_create_promo_redemption(
        self,
        session,
        *,
        promo_code_id: int,
        user_id: int,
        redeemed_at: datetime,
    ) -> PromoRedemption:
        redemption = (
            await session.execute(
                select(PromoRedemption).where(
                    PromoRedemption.promo_code_id == promo_code_id,
                    PromoRedemption.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if redemption is not None:
            return redemption

        redemption = PromoRedemption(
            promo_code_id=promo_code_id,
            user_id=user_id,
            redeemed_at=redeemed_at,
            subscription_grant_id=None,
        )
        session.add(redemption)
        await session.flush()
        return redemption

    async def _ensure_promo_grant(
        self,
        session,
        *,
        redemption: PromoRedemption,
        promo: PromoCode,
        legacy_promo: LegacyPromoCode,
        tg_id: int,
        granted_at: datetime,
        legacy_usage_id: int | None,
        legacy_backfill: bool,
    ) -> SubscriptionGrant:
        if redemption.subscription_grant_id is not None:
            grant = await session.get(SubscriptionGrant, redemption.subscription_grant_id)
            if grant is not None:
                return grant

        existing = (
            await session.execute(
                select(SubscriptionGrant).where(
                    SubscriptionGrant.source_type == "promo_redemption",
                    SubscriptionGrant.source_ref == str(redemption.id),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            redemption.subscription_grant_id = int(existing.id)
            return existing

        duration_days = int(
            promo.duration_days_override
            if promo.duration_days_override is not None
            else self._duration_days_from_period(str(legacy_promo.duration))
        )
        expires_after = await self._load_current_expiry(
            session,
            tg_id=tg_id,
            user_id=int(redemption.user_id),
        )
        expires_before = (
            expires_after - timedelta(days=duration_days)
            if expires_after is not None
            else None
        )
        grant = SubscriptionGrant(
            user_id=int(redemption.user_id),
            plan_id=promo.plan_id,
            source_type="promo_redemption",
            source_ref=str(redemption.id),
            status="applied",
            duration_days=duration_days,
            expires_before=expires_before,
            expires_after=expires_after,
            created_at=granted_at,
            applied_at=granted_at,
            metadata_json={
                "promo_code": promo.code,
                "legacy_duration": str(legacy_promo.duration),
                "legacy_usage_id": legacy_usage_id,
                "legacy_backfill": legacy_backfill,
            },
        )
        session.add(grant)
        await session.flush()
        redemption.subscription_grant_id = int(grant.id)
        return grant

    async def _upsert_referral_edge(
        self,
        session,
        *,
        referred_tg_id: int,
        referrer_tg_id: int,
        source: str,
        created_at: datetime,
    ) -> ReferralEdge:
        referred_user_id = await self._resolve_user_id(session, referred_tg_id)
        referrer_user_id = await self._resolve_user_id(session, referrer_tg_id)
        if referred_user_id == referrer_user_id:
            raise ValueError("referral edge must link distinct users")

        edge = (
            await session.execute(
                select(ReferralEdge).where(ReferralEdge.referred_user_id == referred_user_id)
            )
        ).scalar_one_or_none()
        if edge is None:
            edge = ReferralEdge(
                referrer_user_id=referrer_user_id,
                referred_user_id=referred_user_id,
                created_at=created_at,
                source=source,
            )
            session.add(edge)
            await session.flush()
            return edge

        edge.referrer_user_id = referrer_user_id
        edge.source = source
        if edge.created_at is None or created_at < self._ensure_utc(edge.created_at):
            edge.created_at = created_at
        return edge

    async def _get_or_create_referral_reward(
        self,
        session,
        *,
        edge_id: int | None,
        beneficiary_user_id: int,
        reward_days: int,
        context: ReferralRewardContext,
        created_at: datetime,
    ) -> ReferralReward:
        reward = (
            await session.execute(
                select(ReferralReward).where(
                    ReferralReward.beneficiary_user_id == beneficiary_user_id,
                    ReferralReward.trigger_type == context.trigger_type,
                    ReferralReward.trigger_ref == str(context.trigger_ref),
                )
            )
        ).scalar_one_or_none()
        rule_id = await self._resolve_referral_rule_id(
            session,
            paid_count_after_award=context.paid_count_after_award,
        )
        metadata_json = {
            **(context.metadata or {}),
            "referred_tg_id": int(context.referred_tg_id),
            "referrer_tg_id": context.referrer_tg_id,
            "source": context.source,
            "paid_count_after_award": context.paid_count_after_award,
        }
        if reward is None:
            reward = ReferralReward(
                referral_edge_id=edge_id,
                beneficiary_user_id=beneficiary_user_id,
                referral_reward_rule_id=rule_id,
                trigger_type=context.trigger_type,
                trigger_ref=str(context.trigger_ref),
                reward_days=reward_days,
                created_at=created_at,
                applied_at=None,
                canceled_at=None,
                subscription_grant_id=None,
                metadata_json=metadata_json,
            )
            session.add(reward)
            await session.flush()
            return reward

        reward.referral_edge_id = edge_id
        reward.referral_reward_rule_id = rule_id
        reward.reward_days = reward_days
        reward.metadata_json = metadata_json
        return reward

    async def _apply_single_referral_reward(
        self,
        session,
        *,
        reward: ReferralReward,
        beneficiary_tg_id: int,
        applied_at: datetime,
        legacy_backfill: bool,
    ) -> None:
        reward.applied_at = applied_at
        if reward.subscription_grant_id is not None:
            return
        expires_after = await self._load_current_expiry(
            session,
            tg_id=beneficiary_tg_id,
            user_id=int(reward.beneficiary_user_id),
        )
        expires_before = (
            expires_after - timedelta(days=int(reward.reward_days))
            if expires_after is not None
            else None
        )
        grant = await self._create_referral_grant(
            session,
            reward=reward,
            beneficiary_tg_id=beneficiary_tg_id,
            applied_at=applied_at,
            expires_before=expires_before,
            expires_after=expires_after,
            legacy_backfill=legacy_backfill,
        )
        reward.subscription_grant_id = int(grant.id)

    async def _create_referral_grant(
        self,
        session,
        *,
        reward: ReferralReward,
        beneficiary_tg_id: int,
        applied_at: datetime,
        expires_before: datetime | None,
        expires_after: datetime | None,
        legacy_backfill: bool,
    ) -> SubscriptionGrant:
        existing = (
            await session.execute(
                select(SubscriptionGrant).where(
                    SubscriptionGrant.source_type == "referral_reward",
                    SubscriptionGrant.source_ref == str(reward.id),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        grant = SubscriptionGrant(
            user_id=int(reward.beneficiary_user_id),
            plan_id=None,
            source_type="referral_reward",
            source_ref=str(reward.id),
            status="applied",
            duration_days=int(reward.reward_days),
            expires_before=expires_before,
            expires_after=expires_after,
            created_at=reward.created_at,
            applied_at=applied_at,
            metadata_json={
                **(reward.metadata_json or {}),
                "legacy_backfill": legacy_backfill,
                "beneficiary_tg_id": beneficiary_tg_id,
            },
        )
        session.add(grant)
        await session.flush()
        return grant

    async def _resolve_user_id(self, session, tg_id: int) -> int:
        account = (
            await session.execute(
                select(TelegramAccount).where(TelegramAccount.telegram_id == tg_id)
            )
        ).scalar_one_or_none()
        if account is None:
            raise ValueError(f"Telegram account is not synced in current storage for tg_id={tg_id}")
        return int(account.user_id)

    async def _resolve_referral_rule_id(
        self,
        session,
        *,
        paid_count_after_award: int | None,
    ) -> int | None:
        if paid_count_after_award is None:
            return None
        rule = (
            await session.execute(
                select(ReferralRewardRule).where(
                    ReferralRewardRule.paid_referrals_threshold == paid_count_after_award
                )
            )
        ).scalar_one_or_none()
        return int(rule.id) if rule is not None else None

    async def _load_current_expiry(
        self,
        session,
        *,
        tg_id: int,
        user_id: int,
    ) -> datetime | None:
        state = await session.get(SubscriptionState, user_id)
        if state is not None and state.current_expires_at is not None:
            return self._ensure_utc(state.current_expires_at)

        legacy_user = (
            await session.execute(select(LegacyUser).where(LegacyUser.tg_id == tg_id))
        ).scalar_one_or_none()
        if legacy_user is None or legacy_user.expiration_date is None:
            return None
        return self._legacy_ts_to_datetime(legacy_user.expiration_date)

    @staticmethod
    def _duration_days_from_period(period: str) -> int:
        seed = get_plan_seed_by_legacy_payload(str(period or "").strip().lower())
        if seed is not None:
            return int(seed.duration_days)

        normalized = str(period or "").strip().lower()
        match = re.fullmatch(r"([a-z]+)?(\d+)", normalized)
        if match:
            unit = match.group(1) or "day"
            value = int(match.group(2))
        else:
            match = re.fullmatch(r"(\d+)([a-z]+)", normalized)
            if not match:
                raise ValueError(f"Unsupported period format: {period!r}")
            value = int(match.group(1))
            unit = match.group(2)

        if unit in {"day", "days"}:
            return value
        if unit in {"month", "months"}:
            return value * 30
        if unit in {"year", "years"}:
            return value * 365
        raise ValueError(f"Unsupported period unit: {period!r}")

    @staticmethod
    def _legacy_ts_to_datetime(timestamp_ms: int | None) -> datetime | None:
        if timestamp_ms is None:
            return None
        return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)

    @staticmethod
    def _ensure_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
