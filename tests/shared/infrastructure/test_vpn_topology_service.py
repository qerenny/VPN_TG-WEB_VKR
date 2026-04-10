from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import shared.infrastructure.vpn_topology_service as topology_module
from shared.config.settings import RuntimeSyncFlags
from shared.infrastructure.vpn_topology_service import VpnTopologyService
from shared.models import register_models
from shared.models.users.app_user_model import AppUser
from shared.models.vpn.vpn_access_point_model import VpnAccessPoint
from shared.models.vpn.vpn_client_deployment_model import VpnClientDeployment
from shared.models.vpn.vpn_client_model import VpnClient
from shared.models.vpn.vpn_control_plane_model import VpnControlPlane
from shared.models.vpn.vpn_location_model import VpnLocation

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
def topology_service(session_factory, monkeypatch):
    @asynccontextmanager
    async def test_get_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(topology_module, "get_db_session", test_get_db_session)
    monkeypatch.setattr(
        topology_module,
        "API_SERVERS",
        {
            "russia": {
                "domain": "ru.example.test",
                "port": "443",
                "path": "api",
                "subscription_port": "8443",
                "subscription_path": "sub",
                "inbounds": [
                    {"id": 1, "location_code": "germany"},
                    {"id": 2, "location_code": "estonia"},
                ],
                "inbound_id": [1, 2],
            }
        },
    )
    monkeypatch.setattr(topology_module, "TRAFFIC_LIMITED_API_SERVERS", {})
    monkeypatch.setattr(
        topology_module,
        "LOCATION_LABELS",
        {
            "germany": "Germany",
            "estonia": "Estonia",
            "default": "VPN",
        },
    )
    return VpnTopologyService(RuntimeSyncFlags(vpn_topology_sync_enabled=True))


@pytest.fixture
async def standard_vpn_client_id(session_factory):
    async with session_factory() as session:
        app_user = AppUser(
            created_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
        )
        session.add(app_user)
        await session.flush()
        session.add(
            VpnClient(
                user_id=int(app_user.id),
                scope="standard",
                provider="3x-ui",
                external_client_uuid="uuid-100",
                external_email="vpn-user-100@example.com",
                subscription_external_id="sub-100",
                metadata_json={},
                created_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
                deactivated_at=None,
            )
        )
        await session.flush()
        vpn_client = (
            await session.execute(select(VpnClient).where(VpnClient.user_id == int(app_user.id)))
        ).scalar_one()
        await session.commit()
        await session.refresh(vpn_client)
        return int(vpn_client.id)


@pytest.mark.asyncio
async def test_seed_topology_creates_expected_shadow_inventory(topology_service, session_factory):
    result = await topology_service.seed_topology()

    async with session_factory() as session:
        control_planes = (await session.execute(select(VpnControlPlane))).scalars().all()
        locations = (await session.execute(select(VpnLocation))).scalars().all()
        access_points = (await session.execute(select(VpnAccessPoint))).scalars().all()

    assert result.control_planes_created == 1
    assert result.locations_created == 2
    assert result.access_points_created == 2
    assert [plane.code for plane in control_planes] == ["russia"]
    assert control_planes[0].scope == "standard"
    assert control_planes[0].server_name == "russia"
    assert sorted(location.code for location in locations) == ["estonia", "germany"]
    assert sorted(point.code for point in access_points) == [
        "russia-inbound-1",
        "russia-inbound-2",
    ]
    assert all(point.scope == "standard" for point in access_points)


@pytest.mark.asyncio
async def test_sync_vpn_client_deployments_creates_active_rows_for_standard_scope(
    topology_service,
    session_factory,
    standard_vpn_client_id,
):
    await topology_service.seed_topology()
    created = await topology_service.sync_vpn_client_deployments(
        standard_vpn_client_id,
        scope="standard",
    )

    async with session_factory() as session:
        deployments = (
            await session.execute(
                select(VpnClientDeployment).order_by(VpnClientDeployment.access_point_id)
            )
        ).scalars().all()

    assert created == 2
    assert len(deployments) == 2
    assert all(deployment.status == "active" for deployment in deployments)
    assert [deployment.external_remark for deployment in deployments] == [
        "vpn-user-100@example.com_1",
        "vpn-user-100@example.com_2",
    ]


@pytest.mark.asyncio
async def test_sync_vpn_client_deployments_creates_traffic_limited_rows(
    topology_service,
    session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        topology_module,
        "TRAFFIC_LIMITED_API_SERVERS",
        {
            "wl-ru": {
                "domain": "wl.example.test",
                "port": "443",
                "path": "api",
                "subscription_port": "9443",
                "subscription_path": "sub",
                "inbounds": [
                    {"id": 2, "location_code": "estonia"},
                ],
                "inbound_id": [2],
            }
        },
    )

    async with session_factory() as session:
        app_user = AppUser(
            created_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
        )
        session.add(app_user)
        await session.flush()
        vpn_client = VpnClient(
            user_id=int(app_user.id),
            scope="traffic_limited",
            provider="3x-ui",
            external_client_uuid="wl-uuid-100",
            external_email="wl-user-100@example.com",
            subscription_external_id="wl-sub-100",
            metadata_json={},
            created_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
            deactivated_at=None,
        )
        session.add(vpn_client)
        await session.commit()
        await session.refresh(vpn_client)
        vpn_client_id = int(vpn_client.id)

    created = await topology_service.sync_vpn_client_deployments(
        vpn_client_id,
        scope="traffic_limited",
    )

    async with session_factory() as session:
        access_points = (
            await session.execute(
                select(VpnAccessPoint).where(VpnAccessPoint.scope == "traffic_limited")
            )
        ).scalars().all()
        deployments = (
            await session.execute(
                select(VpnClientDeployment).order_by(VpnClientDeployment.access_point_id)
            )
        ).scalars().all()
        control_planes = (await session.execute(select(VpnControlPlane))).scalars().all()

    assert created == 1
    assert [point.code for point in access_points] == ["traffic_limited:wl-ru-inbound-2"]
    assert any(plane.code == "traffic_limited:wl-ru" for plane in control_planes)
    assert len(deployments) == 1
    assert deployments[0].external_client_id == "wl-uuid-100"
    assert deployments[0].external_remark == "wl-user-100@example.com_2"


@pytest.mark.asyncio
async def test_seed_topology_refuses_destructive_sync_without_explicit_flag(
    topology_service,
    session_factory,
):
    async with session_factory() as session:
        stale_plane = VpnControlPlane(
            code="stale",
            scope="standard",
            server_name="stale",
            provider="3x-ui",
            api_base_url="https://stale.example.test:443/api/",
            subscription_base_url="https://stale.example.test:8443/sub/",
            is_enabled=True,
            accepts_new_deployments=True,
            metadata_json={"scope": "standard", "server_name": "stale"},
            created_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
        )
        session.add(stale_plane)
        await session.flush()
        session.add(
            VpnAccessPoint(
                control_plane_id=int(stale_plane.id),
                location_id=None,
                code="stale-inbound-9",
                scope="standard",
                kind="inbound",
                external_id="9",
                is_enabled=True,
                priority=1,
                capacity_limit=None,
                metadata_json={"scope": "standard", "server_name": "stale"},
                created_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
            )
        )
        await session.commit()

    with pytest.raises(ValueError, match="Refusing destructive vpn topology sync"):
        await topology_service.seed_topology()


@pytest.mark.asyncio
async def test_seed_topology_can_disable_stale_inventory_with_explicit_flag(
    topology_service,
    session_factory,
):
    async with session_factory() as session:
        stale_plane = VpnControlPlane(
            code="stale",
            scope="standard",
            server_name="stale",
            provider="3x-ui",
            api_base_url="https://stale.example.test:443/api/",
            subscription_base_url="https://stale.example.test:8443/sub/",
            is_enabled=True,
            accepts_new_deployments=True,
            metadata_json={"scope": "standard", "server_name": "stale"},
            created_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
        )
        session.add(stale_plane)
        await session.flush()
        stale_point = VpnAccessPoint(
            control_plane_id=int(stale_plane.id),
            location_id=None,
            code="stale-inbound-9",
            scope="standard",
            kind="inbound",
            external_id="9",
            is_enabled=True,
            priority=1,
            capacity_limit=None,
            metadata_json={"scope": "standard", "server_name": "stale"},
            created_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
        )
        session.add(stale_point)
        await session.commit()

    await topology_service.seed_topology(allow_destructive_sync=True)

    async with session_factory() as session:
        plane = (
            await session.execute(
                select(VpnControlPlane).where(VpnControlPlane.code == "stale")
            )
        ).scalar_one()
        point = (
            await session.execute(
                select(VpnAccessPoint).where(VpnAccessPoint.code == "stale-inbound-9")
            )
        ).scalar_one()

    assert plane.is_enabled is False
    assert plane.accepts_new_deployments is False
    assert point.is_enabled is False
