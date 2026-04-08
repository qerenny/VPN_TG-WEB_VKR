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
    topology_sync_service = AsyncMock()
    manager = ClientManager(
        repo=repo,
        timestamp=timestamp,
        jsonutils=jsonutils,
        uuidgen=uuidgen,
        topology_sync_service=topology_sync_service,
    )
    return manager, repo, timestamp, topology_sync_service


@pytest.mark.asyncio
async def test_add_client_syncs_phase1_state_after_legacy_expiration_update(manager_deps):
    manager, repo, timestamp, topology_sync_service = manager_deps
    repo.get.return_value = SimpleNamespace(
        tg_id=42,
        uuid="uuid-1",
        sub_id="sub-1",
        email="cat@example.com",
        expiration_date=None,
    )
    timestamp.set_client_date.return_value = 2000
    manager._process_on_all_servers = AsyncMock(return_value=None)

    await manager.add_client(tg_id=42, period="day30")

    repo.update_expiration.assert_awaited_once_with(expiration_date=2000, tg_id=42)
    topology_sync_service.sync_legacy_user_deployments.assert_awaited_once_with(
        repo.get.return_value
    )


@pytest.mark.asyncio
async def test_update_client_syncs_phase1_state_after_legacy_expiration_update(manager_deps):
    manager, repo, timestamp, topology_sync_service = manager_deps
    repo.get.return_value = SimpleNamespace(
        tg_id=42,
        uuid="uuid-1",
        sub_id="sub-1",
        email="cat@example.com",
        expiration_date=1000,
    )
    timestamp.update_client_date.return_value = 2500
    manager._process_on_all_servers = AsyncMock(return_value=None)

    await manager.update_client(tg_id=42, period="day30")

    repo.update_expiration.assert_awaited_once_with(expiration_date=2500, tg_id=42)
    topology_sync_service.sync_legacy_user_deployments.assert_awaited_once_with(
        repo.get.return_value
    )
