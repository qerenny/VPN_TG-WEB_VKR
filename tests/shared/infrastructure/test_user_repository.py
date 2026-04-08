from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from shared.migration_support.repositories.users.user_repository import UserRepository
from shared.infrastructure import identity_subscription_sync_service as identity_sync_module
from shared.migration_support.models.users.user_model import User
from shared.models import register_models
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient

DATABASE_URL = "sqlite+aiosqlite://"


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


async def _seed_user(
    session,
    *,
    tg_id: int,
    email: str,
    uuid: str,
    sub_id: str,
    first_seen_at: datetime,
    expires_at: datetime | None = None,
    trial_at: datetime | None = None,
    news_at: datetime | None = None,
    blocked_at: datetime | None = None,
) -> int:
    app_user = AppUser(
        created_at=first_seen_at,
        updated_at=first_seen_at,
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
            linked_at=first_seen_at,
            first_seen_at=first_seen_at,
            last_seen_at=first_seen_at,
            revoked_at=None,
        )
    )
    session.add(
        VpnClient(
            user_id=int(app_user.id),
            scope="standard",
            provider="xray",
            external_client_uuid=uuid,
            external_email=email,
            subscription_external_id=sub_id,
            metadata_json={},
            created_at=first_seen_at,
            updated_at=first_seen_at,
            deactivated_at=None,
        )
    )
    session.add(
        SubscriptionState(
            user_id=int(app_user.id),
            current_expires_at=expires_at,
            trial_activated_at=trial_at,
            news_bonus_activated_at=news_at,
            blocked_at=blocked_at,
            updated_at=first_seen_at,
            version=0,
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

    monkeypatch.setattr(identity_sync_module, "get_db_session", _test_db_session)

    class TestableUserRepository(UserRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    return TestableUserRepository()


@pytest.fixture
async def seeded_users(session_factory):
    async with session_factory() as session:
        await _seed_user(
            session,
            tg_id=100,
            email="user100@test.com",
            uuid="uuid-100",
            sub_id="sub-100",
            first_seen_at=_dt(2026, 3, 1),
        )
        await _seed_user(
            session,
            tg_id=200,
            email="user200@test.com",
            uuid="uuid-200",
            sub_id="sub-200",
            first_seen_at=_dt(2026, 3, 2),
            expires_at=_dt(2026, 4, 1),
            trial_at=_dt(2026, 3, 3),
        )
        await _seed_user(
            session,
            tg_id=300,
            email="user300@test.com",
            uuid="uuid-300",
            sub_id="sub-300",
            first_seen_at=_dt(2026, 3, 3),
            expires_at=_dt(2026, 5, 1),
            blocked_at=_dt(2026, 3, 4),
        )
        await session.commit()


@pytest.mark.asyncio
async def test_get_existing_user(repo, seeded_users):
    user = await repo.get(100)

    assert user is not None
    assert user.tg_id == 100
    assert user.email == "user100@test.com"
    assert user.uuid == "uuid-100"
    assert user.sub_id == "sub-100"
    assert user.login_date == _ms(_dt(2026, 3, 1))


@pytest.mark.asyncio
async def test_get_all_users(repo, seeded_users):
    users = await repo.get_all()
    assert [user.tg_id for user in users] == [100, 200, 300]


@pytest.mark.asyncio
async def test_update_expiration_and_trial(repo, seeded_users):
    await repo.update_expiration(100, _ms(_dt(2026, 6, 1)))
    await repo.set_trial_date(100, _ms(_dt(2026, 3, 10)))
    await repo.set_news_channel_date(100, _ms(_dt(2026, 3, 11)))

    user = await repo.get(100)

    assert user is not None
    assert user.expiration_date == _ms(_dt(2026, 6, 1))
    assert user.trial_date == _ms(_dt(2026, 3, 10))
    assert user.news_channel_date == _ms(_dt(2026, 3, 11))


@pytest.mark.asyncio
async def test_get_active_users_and_expiring_between(repo, seeded_users):
    active = await repo.get_active_users(_ms(_dt(2026, 3, 15)))
    expiring = await repo.get_users_expiring_between(
        _ms(_dt(2026, 3, 15)),
        _ms(_dt(2026, 4, 15)),
    )

    assert [user.tg_id for user in active] == [200]
    assert [user.tg_id for user in expiring] == [200]


@pytest.mark.asyncio
async def test_create_user(repo):
    created = await repo.create(
        User(
            tg_id=999,
            email="newuser@test.com",
            login_date=_ms(_dt(2026, 3, 5)),
            expiration_date=None,
            trial_date=None,
            news_channel_date=None,
            uuid="uuid-999",
            sub_id="sub-999",
        ),
        telegram_username="newuser",
    )

    assert created.tg_id == 999
    assert created.email == "newuser@test.com"
    assert created.uuid == "uuid-999"
    assert created.sub_id == "sub-999"

    loaded = await repo.get(999)
    assert loaded is not None
    assert loaded.tg_id == 999


@pytest.mark.asyncio
async def test_delete_user(repo, seeded_users):
    await repo.delete(200)
    assert await repo.get(200) is None


@pytest.mark.asyncio
async def test_get_last_users_orders_by_first_seen_desc(repo, seeded_users):
    users = await repo.get_last_users(limit=2)
    assert [user.tg_id for user in users] == [300, 200]
