from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from shared.migration_support.repositories.referrals.referral_repository import ReferralRepository
from shared.infrastructure import growth_sync_service as growth_sync_module
from shared.models import register_models
from shared.models.growth.referral_edge_model import ReferralEdge
from shared.models.growth.referral_reward_model import ReferralReward
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount

DATABASE_URL = "sqlite+aiosqlite://"


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


async def _create_v2_user(session, *, tg_id: int) -> int:
    app_user = AppUser(
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
def repo(session_factory, monkeypatch):
    @asynccontextmanager
    async def _test_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(growth_sync_module, "get_db_session", _test_db_session)

    class TestableReferralRepository(ReferralRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    return TestableReferralRepository()


@pytest.fixture
async def seeded_users(session_factory):
    async with session_factory() as session:
        for tg_id in (100, 200, 111, 222, 123, 456, 789):
            await _create_v2_user(session, tg_id=tg_id)
        await session.commit()


@pytest.mark.asyncio
async def test_update_and_get_referrer(repo, seeded_users):
    await repo.update_referrer(tg_id=100, referrer_tg_id=200)

    referral = await repo.get(100)
    users = await repo.get_users_by_referrer(referrer_tg_id=200)

    assert referral is not None
    assert referral.tg_id == 100
    assert referral.referrer_tg_id == 200
    assert referral.days_pending == 0
    assert referral.paid_count == 0
    assert referral.bonus_is_received is False
    assert (100,) in users


@pytest.mark.asyncio
async def test_update_days_pending_accumulates_positive_rewards_only(repo, seeded_users):
    await repo.update_referrer(tg_id=100, referrer_tg_id=200)
    await repo.update_days_pending(tg_id=100, amount=5)
    await repo.update_days_pending(tg_id=100, amount=-3)
    await repo.update_days_pending(tg_id=100, amount=2)

    referral = await repo.get(100)
    assert referral is not None
    assert referral.days_pending == 7


@pytest.mark.asyncio
async def test_get_users_by_referrer_empty(repo, seeded_users):
    assert await repo.get_users_by_referrer(referrer_tg_id=9999) == []


@pytest.mark.asyncio
async def test_is_symmetrical_referral(repo, seeded_users):
    await repo.update_referrer(tg_id=111, referrer_tg_id=222)
    await repo.update_referrer(tg_id=222, referrer_tg_id=111)

    assert await repo.is_symmetrical_referral(tg_id=111, referrer_tg_id=222) is True
    assert await repo.is_symmetrical_referral(tg_id=111, referrer_tg_id=9999) is False


@pytest.mark.asyncio
async def test_get_returns_placeholder_for_existing_user_without_referral(repo, seeded_users):
    referral = await repo.get(123)

    assert referral is not None
    assert referral.tg_id == 123
    assert referral.referrer_tg_id is None
    assert referral.days_pending == 0
    assert referral.paid_count == 0


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_user(repo):
    assert await repo.get(9999) is None


@pytest.mark.asyncio
async def test_get_projects_reward_state_from_v2(session_factory, repo, seeded_users):
    async with session_factory() as session:
        referred_user_id = (
            await session.execute(
                select(TelegramAccount.user_id).where(TelegramAccount.telegram_id == 100)
            )
        ).scalar_one()
        referrer_user_id = (
            await session.execute(
                select(TelegramAccount.user_id).where(TelegramAccount.telegram_id == 200)
            )
        ).scalar_one()

        edge = ReferralEdge(
            referrer_user_id=int(referrer_user_id),
            referred_user_id=int(referred_user_id),
            created_at=_dt(2026, 3, 5),
            source="telegram_start",
        )
        session.add(edge)
        await session.flush()

        session.add(
            ReferralReward(
                referral_edge_id=int(edge.id),
                beneficiary_user_id=int(referred_user_id),
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
                beneficiary_user_id=int(referrer_user_id),
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

    referred = await repo.get(100)
    referrer = await repo.get(200)

    assert referred is not None
    assert referred.days_pending == 5
    assert referred.bonus_is_received is True
    assert referrer is not None
    assert referrer.paid_count == 1
