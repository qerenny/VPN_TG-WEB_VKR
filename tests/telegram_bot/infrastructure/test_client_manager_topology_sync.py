from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.infrastructure.api.client_manager import ClientManager


@pytest.fixture
def manager_deps():
    repo = AsyncMock()
    timestamp = MagicMock()
    jsonutils = MagicMock()
    uuidgen = MagicMock()
    topology_service = AsyncMock()
    manager = ClientManager(
        repo=repo,
        timestamp=timestamp,
        jsonutils=jsonutils,
        uuidgen=uuidgen,
        topology_service=topology_service,
    )
    return manager, repo, timestamp, topology_service


@pytest.mark.asyncio
async def test_add_client_syncs_standard_topology_after_expiration_update(manager_deps):
    manager, repo, timestamp, topology_service = manager_deps
    repo.get.return_value = SimpleNamespace(
        tg_id=42,
        uuid="uuid-1",
        sub_id="sub-1",
        email="user@example.com",
        expiration_date=None,
    )
    repo.get_standard_vpn_client_id.return_value = 501
    timestamp.set_client_date.return_value = 2000
    manager._process_on_all_servers = AsyncMock(return_value=None)

    await manager.add_client(tg_id=42, period="day30")

    repo.update_expiration.assert_awaited_once_with(expiration_date=2000, tg_id=42)
    repo.get_standard_vpn_client_id.assert_awaited_once_with(42)
    topology_service.sync_vpn_client_deployments.assert_awaited_once_with(
        501,
        scope="standard",
    )


@pytest.mark.asyncio
async def test_update_client_syncs_standard_topology_after_expiration_update(manager_deps):
    manager, repo, timestamp, topology_service = manager_deps
    repo.get.return_value = SimpleNamespace(
        tg_id=42,
        uuid="uuid-1",
        sub_id="sub-1",
        email="user@example.com",
        expiration_date=1000,
    )
    repo.get_standard_vpn_client_id.return_value = 502
    timestamp.update_client_date.return_value = 2500
    manager._process_on_all_servers = AsyncMock(return_value=None)

    await manager.update_client(tg_id=42, period="day30")

    repo.update_expiration.assert_awaited_once_with(expiration_date=2500, tg_id=42)
    repo.get_standard_vpn_client_id.assert_awaited_once_with(42)
    topology_service.sync_vpn_client_deployments.assert_awaited_once_with(
        502,
        scope="standard",
    )
