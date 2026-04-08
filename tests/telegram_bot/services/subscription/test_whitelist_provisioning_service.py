from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import telegram_bot.services.subscriptions.whitelist_provisioning_service as whitelist_module
from shared.migration_support.models.users.user_model import User
from shared.models import register_models
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient
from telegram_bot.services.subscriptions.whitelist_provisioning_service import (
    WhiteListProvisioningService,
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

    monkeypatch.setattr(whitelist_module, "get_db_session", test_get_db_session)
    monkeypatch.setattr(
        whitelist_module,
        "WHITELIST_API_SERVERS",
        {
            "wl-ru": {
                "username": "wl-user",
                "password": "wl-pass",
                "domain": "wl.example.com",
                "port": "443",
                "path": "api",
                "subscription_port": "443",
                "subscription_path": "subscription",
                "inbound_id": [9],
            }
        },
    )

    repo = AsyncMock()
    timestamp = MagicMock()
    timestamp.set_client_date.return_value = 1234567890000
    timestamp.current_time.return_value = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
    client_manager = AsyncMock()
    uuidgen = MagicMock()
    uuidgen.generate_id.side_effect = ["uuid-wl-1", "sub-wl-1"]

    service = WhiteListProvisioningService(
        repo=repo,
        timestamp=timestamp,
        client_manager=client_manager,
        uuidgen=uuidgen,
    )
    return SimpleNamespace(
        service=service,
        repo=repo,
        timestamp=timestamp,
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
async def test_ensure_whitelist_client_provisions_new_client(
    service_and_mocks,
    session_factory,
    seeded_identity,
):
    service_and_mocks.repo.get.return_value = User(
        tg_id=100,
        uuid="uuid-100",
        email="user100@example.com",
        expiration_date=None,
        login_date=1_710_000_000_000,
        trial_date=None,
        news_channel_date=None,
        sub_id="sub-100",
    )

    result = await service_and_mocks.service.ensure_whitelist_client(
        100,
        traffic_bytes=15 * 1024 * 1024,
        duration_days=30,
    )

    async with session_factory() as session:
        vpn_clients = (await session.execute(select(VpnClient))).scalars().all()

    assert result.scope == "whitelist"
    assert len(vpn_clients) == 1
    assert vpn_clients[0].user_id == seeded_identity
    assert vpn_clients[0].scope == "whitelist"
    assert vpn_clients[0].external_client_uuid == "uuid-wl-1"
    assert vpn_clients[0].subscription_external_id == "sub-wl-1"
    assert vpn_clients[0].metadata_json["bootstrap_traffic_bytes"] == 15 * 1024 * 1024

    service_and_mocks.client_manager.add_scoped_client.assert_awaited_once_with(
        server_pool=whitelist_module.WHITELIST_API_SERVERS,
        cache_namespace="whitelist",
        tg_id=100,
        client_uuid="uuid-wl-1",
        email=vpn_clients[0].external_email,
        sub_id="sub-wl-1",
        expires_at=1234567890000,
        total_bytes=15 * 1024 * 1024,
    )
    service_and_mocks.client_manager.sync_v2_scoped_topology.assert_awaited_once_with(
        vpn_client_id=int(vpn_clients[0].id),
        scope="whitelist",
    )


@pytest.mark.asyncio
async def test_ensure_whitelist_client_reuses_existing_active_client(
    service_and_mocks,
    session_factory,
    seeded_identity,
):
    service_and_mocks.repo.get.return_value = User(
        tg_id=100,
        uuid="uuid-100",
        email="user100@example.com",
        expiration_date=None,
        login_date=1_710_000_000_000,
        trial_date=None,
        news_channel_date=None,
        sub_id="sub-100",
    )

    async with session_factory() as session:
        session.add(
            VpnClient(
                user_id=seeded_identity,
                scope="whitelist",
                provider="3x-ui",
                external_client_uuid="existing-wl-uuid",
                external_email="wl-existing@example.com",
                subscription_external_id="existing-wl-sub",
                metadata_json={},
                created_at=datetime(2026, 4, 2, 11, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 2, 11, 0, tzinfo=timezone.utc),
                deactivated_at=None,
            )
        )
        await session.commit()

    result = await service_and_mocks.service.ensure_whitelist_client(
        100,
        traffic_bytes=15 * 1024 * 1024,
        duration_days=30,
    )

    assert result.client_uuid == "existing-wl-uuid"
    service_and_mocks.client_manager.add_scoped_client.assert_not_awaited()
    service_and_mocks.client_manager.sync_v2_scoped_topology.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_whitelist_client_requires_configured_servers(
    service_and_mocks,
    monkeypatch,
    seeded_identity,
):
    service_and_mocks.repo.get.return_value = User(
        tg_id=100,
        uuid="uuid-100",
        email="user100@example.com",
        expiration_date=None,
        login_date=1_710_000_000_000,
        trial_date=None,
        news_channel_date=None,
        sub_id="sub-100",
    )
    monkeypatch.setattr(whitelist_module, "WHITELIST_API_SERVERS", {})

    with pytest.raises(ValueError, match="configured"):
        await service_and_mocks.service.ensure_whitelist_client(
            100,
            traffic_bytes=15 * 1024 * 1024,
            duration_days=30,
        )

    service_and_mocks.client_manager.add_scoped_client.assert_not_awaited()
