from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import telegram_bot.services.subscriptions.traffic_limited_service as traffic_module
from shared.infrastructure.payment_plan_catalog import iter_default_plan_seeds
from shared.models import register_models
from shared.models.payments.plan_model import Plan
from shared.models.traffic.traffic_grant_model import TrafficGrant
from shared.models.traffic.traffic_state_model import TrafficState
from telegram_bot.services.subscriptions.traffic_limited_service import (
    TrafficLimitedService,
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
async def seeded_plans(session_factory, monkeypatch):
    @asynccontextmanager
    async def test_get_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(traffic_module, "get_db_session", test_get_db_session)
    async with session_factory() as session:
        for seed in iter_default_plan_seeds():
            session.add(
                Plan(
                    code=seed.code,
                    name=seed.name,
                    kind=seed.kind,
                    payload=seed.payload,
                    scope=seed.scope,
                    entitlement_kind=seed.entitlement_kind,
                    duration_days=seed.duration_days,
                    quota_bytes=seed.quota_bytes,
                    price_amount=seed.price_amount,
                    currency=seed.currency,
                    is_active=True,
                    metadata_json={},
                )
            )
        await session.commit()


@pytest.fixture
def service_and_mocks(seeded_plans):
    provisioning_service = MagicMock()
    provisioning_service._get_server_pool.return_value = {"wl-1": {"inbound_id": [9]}}
    provisioning_service.ensure_traffic_limited_client = AsyncMock(return_value=SimpleNamespace(
        user_id=10,
        vpn_client_id=20,
        client_uuid="wl-client-uuid",
        email="wl-user@example.com",
        subscription_id="wl-sub-id",
        scope="traffic_limited",
    ))
    provisioning_service.ensure_traffic_limited_client_for_user = AsyncMock(return_value=SimpleNamespace(
        user_id=10,
        vpn_client_id=20,
        client_uuid="wl-client-uuid",
        email="wl-user@example.com",
        subscription_id="wl-sub-id",
        scope="traffic_limited",
    ))
    timestamp = MagicMock()
    client_manager = AsyncMock()
    service = TrafficLimitedService(
        provisioning_service=provisioning_service,
        timestamp=timestamp,
        client_manager=client_manager,
    )
    return service, provisioning_service, client_manager


@pytest.mark.asyncio
async def test_activate_payment_creates_grant_and_state(
    service_and_mocks,
    session_factory,
):
    service, provisioning_service, client_manager = service_and_mocks

    result = await service.activate_payment(
        tg_id=100,
        product="traffic_limited15gb",
        payment_id="pay-wl-1",
    )

    async with session_factory() as session:
        grants = (await session.execute(select(TrafficGrant))).scalars().all()
        state = await session.get(TrafficState, 20)
        plan = (
            await session.execute(select(Plan).where(Plan.code == "traffic_limited_15gb"))
        ).scalar_one()

    assert len(grants) == 1
    assert grants[0].plan_id == plan.id
    assert grants[0].granted_bytes == 15 * 1024 * 1024 * 1024
    assert state.allocated_bytes == 15 * 1024 * 1024 * 1024
    assert state.remaining_bytes == 15 * 1024 * 1024 * 1024
    assert result.granted_bytes == 15 * 1024 * 1024 * 1024
    provisioning_service.ensure_traffic_limited_client.assert_awaited_once()
    client_manager.update_scoped_client.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_payment_is_idempotent_by_payment_id(
    service_and_mocks,
    session_factory,
):
    service, provisioning_service, client_manager = service_and_mocks

    first = await service.activate_payment(
        tg_id=100,
        product="traffic_limited15gb",
        payment_id="pay-wl-1",
    )
    second = await service.activate_payment(
        tg_id=100,
        product="traffic_limited15gb",
        payment_id="pay-wl-1",
    )

    async with session_factory() as session:
        grants = (await session.execute(select(TrafficGrant))).scalars().all()

    assert len(grants) == 1
    assert first.was_created is True
    assert second.was_created is False
    client_manager.update_scoped_client.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_trial_creates_dedicated_trial_grant(
    service_and_mocks,
    session_factory,
):
    service, provisioning_service, client_manager = service_and_mocks

    result = await service.activate_trial(tg_id=100)

    async with session_factory() as session:
        grant = (await session.execute(select(TrafficGrant))).scalar_one()
        state = await session.get(TrafficState, 20)
        plan = (
            await session.execute(select(Plan).where(Plan.code == "traffic_limited_trial_2gb"))
        ).scalar_one()

    assert result.was_created is True
    assert grant.plan_id == plan.id
    assert grant.source_type == "trial"
    assert grant.source_ref == "traffic_limited_trial:100"
    assert grant.is_trial is True
    assert state.allocated_bytes == 2 * 1024 * 1024 * 1024
    provisioning_service.ensure_traffic_limited_client.assert_awaited_once()
    client_manager.update_scoped_client.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_trial_is_idempotent_by_tg_id(
    service_and_mocks,
    session_factory,
):
    service, _, client_manager = service_and_mocks

    first = await service.activate_trial(tg_id=100)
    second = await service.activate_trial(tg_id=100)

    async with session_factory() as session:
        grants = (await session.execute(select(TrafficGrant))).scalars().all()

    assert len(grants) == 1
    assert first.was_created is True
    assert second.was_created is False
    client_manager.update_scoped_client.assert_awaited_once()


@pytest.mark.asyncio
async def test_has_used_trial_reflects_existing_trial_grant(
    service_and_mocks,
):
    service, _, _ = service_and_mocks

    assert await service.has_used_trial(tg_id=100) is False

    await service.activate_trial(tg_id=100)

    assert await service.has_used_trial(tg_id=100) is True


@pytest.mark.asyncio
async def test_activate_payment_extends_active_window_by_plan_duration(
    service_and_mocks,
    session_factory,
):
    service, _, _ = service_and_mocks
    current_expires_at = datetime.now(timezone.utc) + timedelta(days=10)

    async with session_factory() as session:
        session.add(
            TrafficState(
                vpn_client_id=20,
                scope="traffic_limited",
                allocated_bytes=15 * 1024 * 1024 * 1024,
                used_bytes=0,
                remaining_bytes=15 * 1024 * 1024 * 1024,
                expires_at=current_expires_at,
                is_blocked=False,
                block_reason=None,
                last_provider_sync_at=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    result = await service.activate_payment(
        tg_id=100,
        product="traffic_limited35gb",
        payment_id="pay-wl-35",
    )

    expected_expires_at = current_expires_at + timedelta(days=45)
    assert result.expires_at is not None
    assert abs((result.expires_at - expected_expires_at).total_seconds()) < 2
    assert result.allocated_bytes == 50 * 1024 * 1024 * 1024
    assert result.remaining_bytes == 50 * 1024 * 1024 * 1024


@pytest.mark.asyncio
async def test_grant_admin_package_for_user_uses_plan_code(
    service_and_mocks,
    session_factory,
):
    service, provisioning_service, client_manager = service_and_mocks

    result = await service.grant_admin_package_for_user(
        user_id=10,
        plan_code="traffic_limited_15gb",
        source_ref="admin:10:test",
    )

    async with session_factory() as session:
        grant = (await session.execute(select(TrafficGrant))).scalar_one()

    assert result.granted_bytes == 15 * 1024 * 1024 * 1024
    assert grant.source_type == "admin"
    assert grant.source_ref == "admin:10:test"
    provisioning_service.ensure_traffic_limited_client_for_user.assert_awaited_once_with(
        user_id=10,
        traffic_bytes=15 * 1024 * 1024 * 1024,
        duration_days=30,
    )
    client_manager.update_scoped_client.assert_awaited_once()
