from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from shared.config.settings import RolloutFeatureFlags
from shared.migration_support.models.users.user_model import User
from shared.migration_support.repositories.users.user_repository import UserRepository
from shared.models import register_models
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount

DATABASE_URL = "sqlite+aiosqlite://"


def _dt_to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


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
def repo(session_factory):
    class TestableUserRepository(UserRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    return TestableUserRepository(
        features=RolloutFeatureFlags()
    )


@pytest.fixture
async def seeded_state(session_factory):
    async with session_factory() as session:
        legacy_user = User(
            tg_id=100,
            email="user100@example.com",
            expiration_date=1_700_000_000_000,
            login_date=1_600_000_000_000,
            trial_date=1_650_000_000_000,
            news_channel_date=1_660_000_000_000,
            sub_id="sub-100",
        )
        app_user = AppUser(
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        )
        session.add(legacy_user)
        session.add(app_user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(app_user.id),
                telegram_id=100,
                username="alice",
                linked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        session.add(
            SubscriptionState(
                user_id=int(app_user.id),
                current_expires_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
                trial_activated_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
                news_bonus_activated_at=datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc),
                blocked_at=None,
                updated_at=datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc),
                version=1,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_get_uses_subscription_state_when_read_cutover_enabled(repo, seeded_state):
    user = await repo.get(100)

    assert user is not None
    assert user.expiration_date == _dt_to_ms(
        datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    )
    assert user.trial_date == _dt_to_ms(
        datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
    )
    assert user.news_channel_date == _dt_to_ms(
        datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    )


@pytest.mark.asyncio
async def test_get_returns_empty_subscription_fields_when_state_is_missing(repo, session_factory):
    async with session_factory() as session:
        app_user = AppUser(
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        )
        session.add(app_user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(app_user.id),
                telegram_id=200,
                username="user200",
                linked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        await session.commit()

    user = await repo.get(200)

    assert user is not None
    assert user.expiration_date is None
    assert user.trial_date is None
    assert user.news_channel_date is None


@pytest.mark.asyncio
async def test_get_active_users_filters_on_v2_subscription_state(repo, session_factory):
    async with session_factory() as session:
        legacy_users = [
            User(
                tg_id=301,
                email="user301@example.com",
                expiration_date=1_700_000_000_000,
                login_date=1_600_000_000_000,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-301",
            ),
            User(
                tg_id=302,
                email="user302@example.com",
                expiration_date=1_900_000_000_000,
                login_date=1_600_000_000_000,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-302",
            ),
            User(
                tg_id=303,
                email="user303@example.com",
                expiration_date=1_900_000_000_000,
                login_date=1_600_000_000_000,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-303",
            ),
        ]
        session.add_all(legacy_users)
        await session.flush()

        app_users = [
            AppUser(
                created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
            )
            for _ in range(3)
        ]
        session.add_all(app_users)
        await session.flush()

        telegram_accounts = [
            TelegramAccount(
                user_id=int(app_user.id),
                telegram_id=tg_id,
                username=f"user{tg_id}",
                linked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
            for app_user, tg_id in zip(app_users, [301, 302, 303], strict=True)
        ]
        session.add_all(telegram_accounts)
        session.add_all(
            [
                SubscriptionState(
                    user_id=int(app_users[0].id),
                    current_expires_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
                    trial_activated_at=None,
                    news_bonus_activated_at=None,
                    blocked_at=None,
                    updated_at=datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc),
                    version=0,
                ),
                SubscriptionState(
                    user_id=int(app_users[1].id),
                    current_expires_at=datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
                    trial_activated_at=None,
                    news_bonus_activated_at=None,
                    blocked_at=None,
                    updated_at=datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc),
                    version=0,
                ),
                SubscriptionState(
                    user_id=int(app_users[2].id),
                    current_expires_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
                    trial_activated_at=None,
                    news_bonus_activated_at=None,
                    blocked_at=datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc),
                    version=1,
                ),
            ]
        )
        await session.commit()

    active_users = await repo.get_active_users(
        _dt_to_ms(datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc))
    )

    assert [user.tg_id for user in active_users] == [301]


@pytest.mark.asyncio
async def test_get_users_expiring_between_uses_v2_subscription_state(repo, session_factory):
    async with session_factory() as session:
        legacy_users = [
            User(
                tg_id=401,
                email="user401@example.com",
                expiration_date=1_900_000_000_000,
                login_date=1_600_000_000_000,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-401",
            ),
            User(
                tg_id=402,
                email="user402@example.com",
                expiration_date=1_900_000_000_000,
                login_date=1_600_000_000_000,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-402",
            ),
        ]
        session.add_all(legacy_users)
        await session.flush()

        app_users = [
            AppUser(
                created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
            )
            for _ in range(2)
        ]
        session.add_all(app_users)
        await session.flush()

        session.add_all(
            [
                TelegramAccount(
                    user_id=int(app_users[0].id),
                    telegram_id=401,
                    username="user401",
                    linked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                    first_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                    last_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                    revoked_at=None,
                ),
                TelegramAccount(
                    user_id=int(app_users[1].id),
                    telegram_id=402,
                    username="user402",
                    linked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                    first_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                    last_seen_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
                    revoked_at=None,
                ),
            ]
        )
        session.add_all(
            [
                SubscriptionState(
                    user_id=int(app_users[0].id),
                    current_expires_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
                    trial_activated_at=None,
                    news_bonus_activated_at=None,
                    blocked_at=None,
                    updated_at=datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc),
                    version=0,
                ),
                SubscriptionState(
                    user_id=int(app_users[1].id),
                    current_expires_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                    trial_activated_at=None,
                    news_bonus_activated_at=None,
                    blocked_at=None,
                    updated_at=datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc),
                    version=0,
                ),
            ]
        )
        await session.commit()

    users = await repo.get_users_expiring_between(
        _dt_to_ms(datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)),
        _dt_to_ms(datetime(2026, 4, 5, 0, 0, tzinfo=timezone.utc)),
    )

    assert [user.tg_id for user in users] == [401]
