from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import shared.infrastructure.growth_service as growth_module
from shared.config.settings import RuntimeSyncFlags
from shared.infrastructure.growth_service import (
    GrowthService,
    ReferralRewardContext,
)
from shared.models import register_models
from shared.models.growth.promo_code_model import PromoCode
from shared.models.growth.promo_redemption_model import PromoRedemption
from shared.models.growth.referral_edge_model import ReferralEdge
from shared.models.growth.referral_reward_model import ReferralReward
from shared.models.growth.referral_reward_rule_model import ReferralRewardRule
from shared.models.subscriptions.subscription_grant_model import SubscriptionGrant
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount

DATABASE_URL = "sqlite+aiosqlite://"


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
def growth_service(session_factory, monkeypatch):
    @asynccontextmanager
    async def test_get_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(growth_module, "get_db_session", test_get_db_session)
    return GrowthService(RuntimeSyncFlags(growth_sync_enabled=True))


@pytest.fixture
async def current_identity_state(session_factory):
    async with session_factory() as session:
        user_100 = AppUser(
            created_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
        )
        user_200 = AppUser(
            created_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
        )
        session.add(user_100)
        session.add(user_200)
        await session.flush()

        session.add(
            TelegramAccount(
                user_id=int(user_100.id),
                telegram_id=100,
                username="alice",
                linked_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        session.add(
            TelegramAccount(
                user_id=int(user_200.id),
                telegram_id=200,
                username="bob",
                linked_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        session.add(
            SubscriptionState(
                user_id=int(user_100.id),
                current_expires_at=datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc),
                trial_activated_at=None,
                info_channel_activated_at=None,
                blocked_at=None,
                updated_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                version=0,
            )
        )
        session.add(
            SubscriptionState(
                user_id=int(user_200.id),
                current_expires_at=datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc),
                trial_activated_at=None,
                info_channel_activated_at=None,
                blocked_at=None,
                updated_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                version=0,
            )
        )
        session.add(
            PromoCode(
                code="PROMO7",
                plan_id=None,
                duration_days_override=7,
                max_redemptions=3,
                per_user_limit=1,
                valid_from=None,
                valid_until=None,
                is_active=True,
                metadata_json={},
                created_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_seed_referral_reward_rules_creates_expected_rules(growth_service, session_factory):
    created = await growth_service.seed_referral_reward_rules()

    async with session_factory() as session:
        rules = (
            await session.execute(
                select(ReferralRewardRule).order_by(ReferralRewardRule.paid_referrals_threshold)
            )
        ).scalars().all()

    assert created == 5
    assert [
        (rule.paid_referrals_threshold, rule.reward_days)
        for rule in rules
    ] == [(1, 7), (3, 10), (5, 15), (10, 31), (15, 62)]


@pytest.mark.asyncio
async def test_sync_promo_redemption_creates_catalog_redemption_and_grant(
    growth_service,
    session_factory,
    current_identity_state,
):
    await growth_service.sync_promo_redemption(
        tg_id=100,
        promo_code="PROMO7",
    )

    async with session_factory() as session:
        promo = (await session.execute(select(PromoCode))).scalar_one()
        redemption = (await session.execute(select(PromoRedemption))).scalar_one()
        grant = (await session.execute(select(SubscriptionGrant))).scalar_one()

    assert promo.code == "PROMO7"
    assert promo.duration_days_override == 7
    assert redemption.subscription_grant_id == grant.id
    assert grant.source_type == "promo_redemption"


@pytest.mark.asyncio
async def test_referral_rewards_can_be_created_pending_and_applied(
    growth_service,
    session_factory,
    current_identity_state,
):
    context = ReferralRewardContext(
        referred_tg_id=100,
        referrer_tg_id=200,
        trigger_type="invite_registered",
        trigger_ref="100",
        source="telegram_start",
    )

    await growth_service.sync_referral_reward(
        beneficiary_tg_id=100,
        reward_days=5,
        context=context,
        applied=False,
    )
    applied_count = await growth_service.apply_pending_referral_rewards(beneficiary_tg_id=100)

    async with session_factory() as session:
        edge = (await session.execute(select(ReferralEdge))).scalar_one()
        reward = (await session.execute(select(ReferralReward))).scalar_one()
        grant = (await session.execute(select(SubscriptionGrant))).scalar_one()

    assert applied_count == 1
    assert edge.referrer_user_id != edge.referred_user_id
    assert reward.applied_at is not None
    assert reward.subscription_grant_id == grant.id
