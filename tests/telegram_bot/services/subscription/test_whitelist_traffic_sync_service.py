from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import telegram_bot.services.subscriptions.whitelist_traffic_sync_service as sync_module
from shared.models import register_models
from shared.models.traffic.traffic_state_model import TrafficState
from shared.models.users.app_user_model import AppUser
from shared.models.vpn.vpn_client_model import VpnClient
from telegram_bot.services.subscriptions.whitelist_traffic_sync_service import (
    WhiteListTrafficSyncService,
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

    monkeypatch.setattr(sync_module, "get_db_session", test_get_db_session)
    monkeypatch.setattr(
        sync_module,
        "WHITELIST_API_SERVERS",
        {
            "wl-ru": {
                "inbound_id": [9],
            }
        },
    )

    client_manager = AsyncMock()
    service = WhiteListTrafficSyncService(
        client_manager=client_manager,
        scan_interval_seconds=1,
    )
    return SimpleNamespace(service=service, client_manager=client_manager)


@pytest.fixture
async def seeded_state(session_factory):
    async with session_factory() as session:
        app_user = AppUser(
            created_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
        )
        session.add(app_user)
        await session.flush()
        vpn_client = VpnClient(
            user_id=int(app_user.id),
            scope="whitelist",
            provider="3x-ui",
            external_client_uuid="wl-uuid-1",
            external_email="wl-user@example.com",
            subscription_external_id="wl-sub-1",
            metadata_json={},
            created_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
            deactivated_at=None,
        )
        session.add(vpn_client)
        await session.flush()
        session.add(
            TrafficState(
                vpn_client_id=int(vpn_client.id),
                scope="whitelist",
                allocated_bytes=1000,
                used_bytes=0,
                remaining_bytes=1000,
                expires_at=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
                is_blocked=True,
                block_reason="quota_depleted",
                last_provider_sync_at=None,
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
            )
        )
        await session.commit()
        return int(vpn_client.id)


@pytest.mark.asyncio
async def test_sync_all_clients_once_updates_usage_from_provider(
    service_and_mocks,
    session_factory,
    seeded_state,
):
    service_and_mocks.client_manager.get_scoped_client_usage_bytes.return_value = 250

    synced = await service_and_mocks.service.sync_all_clients_once()

    assert synced == 1
    service_and_mocks.client_manager.get_scoped_client_usage_bytes.assert_awaited_once_with(
        server_pool=sync_module.WHITELIST_API_SERVERS,
        cache_namespace="whitelist",
        email="wl-user@example.com",
    )

    async with session_factory() as session:
        state = await session.get(TrafficState, seeded_state)

    assert state.used_bytes == 250
    assert state.remaining_bytes == 750
    assert state.is_blocked is False
    assert state.block_reason is None
    assert state.last_provider_sync_at is not None


@pytest.mark.asyncio
async def test_sync_all_clients_once_continues_when_provider_call_fails(
    service_and_mocks,
    session_factory,
    seeded_state,
):
    service_and_mocks.client_manager.get_scoped_client_usage_bytes.side_effect = Exception("boom")

    synced = await service_and_mocks.service.sync_all_clients_once()

    assert synced == 0

    async with session_factory() as session:
        state = await session.get(TrafficState, seeded_state)

    assert state.used_bytes == 0
    assert state.remaining_bytes == 1000
