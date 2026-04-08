from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from shared.config.settings import RolloutFeatureFlags
from shared.migration_support.models.promos.promo_code_model import PromoCode
from shared.migration_support.models.promos.promo_code_usage_model import PromoCodeUsage
from shared.migration_support.models.referrals.referral_model import Referral
from shared.migration_support.models.users.user_model import User
from shared.migration_support.repositories.promos.promo_code_repository import PromoCodeRepository
from shared.migration_support.repositories.promos.promo_code_usage_repository import PromoCodeUsageRepository
from shared.migration_support.repositories.referrals.referral_repository import ReferralRepository
from shared.models import register_models
from shared.models.growth.promo_code_model import PromoCode as PromoCodeV2
from shared.models.growth.promo_redemption_model import PromoRedemption
from shared.models.growth.referral_edge_model import ReferralEdge
from shared.models.growth.referral_reward_model import ReferralReward
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount

DATABASE_URL = "sqlite+aiosqlite://"


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def async_engine():
    register_models()
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session_factory(async_engine):
    return async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def growth_repos(session_factory):
    class TestablePromoCodeRepository(PromoCodeRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    class TestablePromoCodeUsageRepository(PromoCodeUsageRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    class TestableReferralRepository(ReferralRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    features = RolloutFeatureFlags()
    return (
        TestablePromoCodeRepository(features=features),
        TestablePromoCodeUsageRepository(features=features),
        TestableReferralRepository(features=features),
    )


async def _create_v2_user(session, *, user_id: int | None = None, tg_id: int) -> int:
    app_user = AppUser(
        id=user_id,
        created_at=_dt(2026, 3, 1),
        updated_at=_dt(2026, 3, 1),
        blocked_at=None,
        deleted_at=None,
    )
    session.add(app_user)
    await session.flush()

    session.add(
        TelegramAccount(
            user_id=int(app_user.id),
            telegram_id=tg_id,
            username=f"user{tg_id}",
            linked_at=_dt(2026, 3, 1),
            first_seen_at=_dt(2026, 3, 1),
            last_seen_at=_dt(2026, 3, 1),
            revoked_at=None,
        )
    )
    await session.flush()
    return int(app_user.id)


@pytest.mark.asyncio
async def test_promo_code_repository_prefers_v2_projection(growth_repos, session_factory):
    promo_repo, _, _ = growth_repos

    async with session_factory() as session:
        session.add(PromoCode(code="PROMO7", duration="day7", remaining_uses=99))

        promo_v2 = PromoCodeV2(
            code="PROMO7",
            plan_id=None,
            duration_days_override=7,
            max_redemptions=5,
            per_user_limit=1,
            valid_from=None,
            valid_until=None,
            is_active=True,
            metadata_json={"legacy_duration": "day7"},
            created_at=_dt(2026, 3, 2),
        )
        session.add(promo_v2)
        await session.flush()

        user_id = await _create_v2_user(session, tg_id=100)
        session.add(
            PromoRedemption(
                promo_code_id=int(promo_v2.id),
                user_id=user_id,
                redeemed_at=_dt(2026, 3, 3),
                subscription_grant_id=None,
            )
        )
        await session.commit()

    promo = await promo_repo.get_by_code("PROMO7")

    assert promo is not None
    assert promo.code == "PROMO7"
    assert promo.duration == "day7"
    assert promo.remaining_uses == 4


@pytest.mark.asyncio
async def test_promo_code_usage_repository_reads_v2_redemptions(growth_repos, session_factory):
    _, promo_usage_repo, _ = growth_repos

    async with session_factory() as session:
        user_id = await _create_v2_user(session, tg_id=101)
        promo_v2 = PromoCodeV2(
            code="USEDPROMO",
            plan_id=None,
            duration_days_override=3,
            max_redemptions=None,
            per_user_limit=1,
            valid_from=None,
            valid_until=None,
            is_active=True,
            metadata_json={"legacy_duration": "day3"},
            created_at=_dt(2026, 3, 2),
        )
        session.add(promo_v2)
        await session.flush()
        session.add(
            PromoRedemption(
                promo_code_id=int(promo_v2.id),
                user_id=user_id,
                redeemed_at=_dt(2026, 3, 4),
                subscription_grant_id=None,
            )
        )
        await session.commit()

    assert await promo_usage_repo.is_used(101, "USEDPROMO") is True
    assert await promo_usage_repo.is_used(101, "MISS") is False


@pytest.mark.asyncio
async def test_referral_repository_reads_v2_projection(growth_repos, session_factory):
    _, _, referral_repo = growth_repos

    async with session_factory() as session:
        referred_user_id = await _create_v2_user(session, tg_id=100)
        referrer_user_id = await _create_v2_user(session, tg_id=200)

        edge = ReferralEdge(
            referrer_user_id=referrer_user_id,
            referred_user_id=referred_user_id,
            created_at=_dt(2026, 3, 5),
            source="telegram_start",
        )
        session.add(edge)
        await session.flush()

        session.add(
            ReferralReward(
                referral_edge_id=int(edge.id),
                beneficiary_user_id=referred_user_id,
                referral_reward_rule_id=None,
                trigger_type="invite_registered",
                trigger_ref="100",
                reward_days=5,
                created_at=_dt(2026, 3, 5),
                applied_at=None,
                canceled_at=None,
                subscription_grant_id=None,
                metadata_json={},
            )
        )
        session.add(
            ReferralReward(
                referral_edge_id=int(edge.id),
                beneficiary_user_id=referrer_user_id,
                referral_reward_rule_id=None,
                trigger_type="first_paid_order",
                trigger_ref="100",
                reward_days=7,
                created_at=_dt(2026, 3, 6),
                applied_at=_dt(2026, 3, 6),
                canceled_at=None,
                subscription_grant_id=None,
                metadata_json={"paid_count_after_award": 1},
            )
        )
        await session.commit()

    referral = await referral_repo.get(100)
    users = await referral_repo.get_users_by_referrer(200)

    assert referral is not None
    assert referral.tg_id == 100
    assert referral.referrer_tg_id == 200
    assert referral.days_pending == 5
    assert referral.paid_count == 0
    assert referral.bonus_is_received is True
    assert users == [(100,)]

    referrer_referral = await referral_repo.get(200)
    assert referrer_referral is not None
    assert referrer_referral.paid_count == 1
    assert referrer_referral.days_pending == 0


@pytest.mark.asyncio
async def test_referral_repository_detects_symmetrical_referral_in_v2(
    growth_repos,
    session_factory,
):
    _, _, referral_repo = growth_repos

    async with session_factory() as session:
        user_111 = await _create_v2_user(session, tg_id=111)
        user_222 = await _create_v2_user(session, tg_id=222)
        session.add_all(
            [
                ReferralEdge(
                    referrer_user_id=user_111,
                    referred_user_id=user_222,
                    created_at=_dt(2026, 3, 7),
                    source="telegram_start",
                ),
                ReferralEdge(
                    referrer_user_id=user_222,
                    referred_user_id=user_111,
                    created_at=_dt(2026, 3, 8),
                    source="telegram_start",
                ),
            ]
        )
        await session.commit()

    assert await referral_repo.is_symmetrical_referral(111, 222) is True


@pytest.mark.asyncio
async def test_referral_repository_returns_none_when_v2_identity_is_missing(
    growth_repos,
    session_factory,
):
    _, _, referral_repo = growth_repos

    async with session_factory() as session:
        session.add(
            User(
                tg_id=303,
                email="user303@example.com",
                login_date=1_600_000_000_000,
                expiration_date=None,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-303",
            )
        )
        session.add(
            Referral(
                tg_id=303,
                referrer_tg_id=404,
                days_pending=9,
                invited_count=0,
                paid_count=2,
                bonus_is_received=True,
            )
        )
        await session.commit()

    referral = await referral_repo.get(303)

    assert referral is None


@pytest.mark.asyncio
async def test_promo_usage_repository_returns_false_when_v2_identity_is_missing(
    growth_repos,
    session_factory,
):
    _, promo_usage_repo, _ = growth_repos

    async with session_factory() as session:
        session.add(
            User(
                tg_id=707,
                email="user707@example.com",
                login_date=1_600_000_000_000,
                expiration_date=None,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-707",
            )
        )
        session.add(PromoCodeUsage(tg_id=707, code="LEGACYONLY"))
        await session.commit()

    assert await promo_usage_repo.is_used(707, "LEGACYONLY") is False
