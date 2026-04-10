from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import telegram_bot.services.subscriptions.standard_user_subscription_service as standard_module
import shared.infrastructure.users.telegram_user_repository as telegram_user_repo_module
from shared.models import register_models
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from telegram_bot.services.subscriptions.standard_user_subscription_service import (
    StandardUserSubscriptionService,
)

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
def service_and_mocks(session_factory, monkeypatch):
    @asynccontextmanager
    async def test_get_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(standard_module, "get_db_session", test_get_db_session)
    monkeypatch.setattr(
        standard_module,
        "API_SERVERS",
        {
            "de": {
                "username": "user",
                "password": "pass",
                "domain": "de.example.com",
                "port": "443",
                "path": "api",
                "subscription_port": "443",
                "subscription_path": "subscription",
                "inbound_id": [3],
            }
        },
    )

    client_manager = AsyncMock()
    uuidgen = MagicMock()
    uuidgen.generate_id.side_effect = ["std-uuid-1", "std-sub-1"]

    service = StandardUserSubscriptionService(
        client_manager=client_manager,
        uuidgen=uuidgen,
    )
    return SimpleNamespace(
        service=service,
        client_manager=client_manager,
        uuidgen=uuidgen,
    )


@pytest.fixture
async def seeded_identity(session_factory):
    async with session_factory() as session:
        app_user = AppUser(
            created_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
        )
        session.add(app_user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(app_user.id),
                telegram_id=100,
                username="alice",
                linked_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        await session.commit()
        return int(app_user.id)


@pytest.mark.asyncio
async def test_activate_days_creates_standard_client_for_telegram_only_user(
    service_and_mocks,
    session_factory,
    seeded_identity,
):
    result = await service_and_mocks.service.activate_days(
        user_id=seeded_identity,
        duration_days=30,
    )

    async with session_factory() as session:
        vpn_clients = (await session.execute(select(VpnClient))).scalars().all()
        states = (await session.execute(select(SubscriptionState))).scalars().all()

    assert result.user_id == seeded_identity
    assert result.was_created is True
    assert len(vpn_clients) == 1
    assert len(states) == 1
    assert vpn_clients[0].external_client_uuid == "std-uuid-1"
    assert vpn_clients[0].subscription_external_id == "std-sub-1"
    assert vpn_clients[0].external_email.startswith("alice-")

    service_and_mocks.client_manager.add_scoped_client.assert_awaited_once()
    service_and_mocks.client_manager.sync_v2_scoped_topology.assert_awaited_once_with(
        vpn_client_id=int(vpn_clients[0].id),
        scope="standard",
    )


@pytest.mark.asyncio
async def test_activate_days_reprovisions_existing_standard_client_when_remote_client_missing(
    service_and_mocks,
    session_factory,
    seeded_identity,
):
    async with session_factory() as session:
        session.add(
            VpnClient(
                user_id=seeded_identity,
                scope="standard",
                provider="3x-ui",
                external_client_uuid="existing-uuid",
                external_email="existing-email",
                subscription_external_id="existing-sub-id",
                metadata_json={},
                created_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                deactivated_at=None,
            )
        )
        await session.commit()

    service_and_mocks.client_manager.client_exists.return_value = False

    result = await service_and_mocks.service.activate_days(
        user_id=seeded_identity,
        duration_days=30,
    )

    assert result.was_created is False
    service_and_mocks.client_manager.add_scoped_client.assert_awaited_once()
    service_and_mocks.client_manager.update_scoped_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_access_keeps_subscription_state_unblocked(
    service_and_mocks,
    session_factory,
    seeded_identity,
):
    async with session_factory() as session:
        session.add(
            VpnClient(
                user_id=seeded_identity,
                scope="standard",
                provider="3x-ui",
                external_client_uuid="existing-uuid",
                external_email="existing-email",
                subscription_external_id="existing-sub-id",
                metadata_json={},
                created_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                deactivated_at=None,
            )
        )
        session.add(
            SubscriptionState(
                user_id=seeded_identity,
                current_expires_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
                trial_activated_at=None,
                info_channel_activated_at=None,
                blocked_at=None,
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                version=0,
            )
        )
        await session.commit()

    revoked = await service_and_mocks.service.revoke_access(user_id=seeded_identity)

    assert revoked is True
    async with session_factory() as session:
        state = await session.get(SubscriptionState, seeded_identity)
    assert state is not None
    assert state.blocked_at is None


@pytest.mark.asyncio
async def test_telegram_repo_is_blocked_ignores_subscription_state_block(
    session_factory,
    monkeypatch,
):
    @asynccontextmanager
    async def test_get_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(telegram_user_repo_module, "get_db_session", test_get_db_session)
    repo = TelegramUserRepository()
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)

    async with session_factory() as session:
        user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(user.id),
                telegram_id=100,
                username="alice",
                linked_at=now,
                first_seen_at=now,
                last_seen_at=now,
                revoked_at=None,
            )
        )
        session.add(
            SubscriptionState(
                user_id=int(user.id),
                current_expires_at=now,
                trial_activated_at=None,
                info_channel_activated_at=None,
                blocked_at=now,
                updated_at=now,
                version=1,
            )
        )
        await session.commit()

    assert await repo.is_blocked(100) is False
