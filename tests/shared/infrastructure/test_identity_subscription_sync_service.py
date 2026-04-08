from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import shared.infrastructure.identity_subscription_sync_service as sync_module
from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.identity_subscription_sync_service import (
    IdentitySubscriptionSyncService,
)
from shared.migration_support.models.users.user_model import User
from shared.models import register_models
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient

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
def sync_service(session_factory, monkeypatch):
    @asynccontextmanager
    async def test_get_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(sync_module, "get_db_session", test_get_db_session)
    return IdentitySubscriptionSyncService(
        RolloutFeatureFlags(
            db_dual_write_identity=True,
            db_dual_write_subscription=True,
        )
    )


@pytest.fixture
def identity_only_sync_service(session_factory, monkeypatch):
    @asynccontextmanager
    async def test_get_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(sync_module, "get_db_session", test_get_db_session)
    return IdentitySubscriptionSyncService(
        RolloutFeatureFlags(
            db_dual_write_identity=True,
            db_dual_write_subscription=False,
        )
    )


def make_legacy_user(**overrides) -> User:
    payload = dict(
        tg_id=100,
        uuid="uuid-100",
        email="user100@example.com",
        expiration_date=1_700_000_000_000,
        login_date=1_600_000_000_000,
        trial_date=1_650_000_000_000,
        news_channel_date=1_660_000_000_000,
        sub_id="sub-100",
    )
    payload.update(overrides)
    return User(**payload)


@pytest.mark.asyncio
async def test_sync_legacy_user_creates_phase1_rows(sync_service, session_factory):
    legacy_user = make_legacy_user()

    user_id = await sync_service.sync_legacy_user(
        legacy_user,
        telegram_username="alice",
    )

    assert user_id is not None

    async with session_factory() as session:
        users = (await session.execute(select(AppUser))).scalars().all()
        telegram_accounts = (await session.execute(select(TelegramAccount))).scalars().all()
        vpn_clients = (await session.execute(select(VpnClient))).scalars().all()
        states = (await session.execute(select(SubscriptionState))).scalars().all()

    assert len(users) == 1
    assert len(telegram_accounts) == 1
    assert len(vpn_clients) == 1
    assert len(states) == 1
    assert telegram_accounts[0].telegram_id == 100
    assert telegram_accounts[0].username == "alice"
    assert vpn_clients[0].scope == "standard"
    assert vpn_clients[0].subscription_external_id == "sub-100"
    assert _dt_to_legacy_ms(states[0].current_expires_at) == legacy_user.expiration_date
    assert _dt_to_legacy_ms(states[0].trial_activated_at) == legacy_user.trial_date
    assert _dt_to_legacy_ms(states[0].news_bonus_activated_at) == legacy_user.news_channel_date


@pytest.mark.asyncio
async def test_sync_legacy_user_is_idempotent_and_updates_existing_rows(
    sync_service,
    session_factory,
):
    legacy_user = make_legacy_user()
    await sync_service.sync_legacy_user(legacy_user, telegram_username="alice")

    updated_user = make_legacy_user(
        expiration_date=1_800_000_000_000,
        trial_date=None,
        news_channel_date=1_870_000_000_000,
    )
    await sync_service.sync_legacy_user(updated_user, telegram_username="alice2")

    async with session_factory() as session:
        users = (await session.execute(select(AppUser))).scalars().all()
        telegram_account = (
            await session.execute(select(TelegramAccount).where(TelegramAccount.telegram_id == 100))
        ).scalar_one()
        state = await session.get(SubscriptionState, telegram_account.user_id)

    assert len(users) == 1
    assert telegram_account.username == "alice2"
    assert _dt_to_legacy_ms(state.current_expires_at) == updated_user.expiration_date
    assert state.trial_activated_at is None
    assert _dt_to_legacy_ms(state.news_bonus_activated_at) == updated_user.news_channel_date
    assert state.version == 1


@pytest.mark.asyncio
async def test_sync_legacy_user_skips_subscription_table_when_flag_is_disabled(
    identity_only_sync_service,
    session_factory,
):
    await identity_only_sync_service.sync_legacy_user(make_legacy_user())

    async with session_factory() as session:
        states = (await session.execute(select(SubscriptionState))).scalars().all()
        users = (await session.execute(select(AppUser))).scalars().all()

    assert len(users) == 1
    assert states == []


def _dt_to_legacy_ms(value) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)
