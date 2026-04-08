from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.infrastructure.api.client_manager import ClientManager


def _response(payload: dict):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    response.text = str(payload)
    return response


@pytest.fixture
def manager_deps():
    repo = AsyncMock()
    timestamp = MagicMock()
    jsonutils = MagicMock()
    uuidgen = MagicMock()
    manager = ClientManager(repo=repo, timestamp=timestamp, jsonutils=jsonutils, uuidgen=uuidgen)
    return manager, repo, timestamp, jsonutils


def test_is_empty_client_id_error():
    assert ClientManager._is_empty_client_id_error(
        {"msg": "Something went wrong (empty client ID\\n)"}
    )
    assert not ClientManager._is_empty_client_id_error({"msg": "duplicate email"})


@pytest.mark.asyncio
async def test_update_client_raises_meaningful_error_on_empty_client_id(manager_deps):
    manager, repo, timestamp, jsonutils = manager_deps
    repo.get.return_value = SimpleNamespace(
        uuid="uuid-1",
        sub_id="sub-1",
        email="cat@example.com",
        expiration_date=1000,
    )
    timestamp.update_client_date.return_value = 2000
    jsonutils.update_post_client_json.side_effect = (
        lambda tg_id, template, client_id, email, date, sub_id: {
            "id": 1,
            "settings": f'{{"clients":[{{"id":"{client_id}"}}]}}',
        }
    )

    session = AsyncMock()
    session.post = AsyncMock(
        return_value=_response(
            {"success": False, "msg": "Something went wrong (empty client ID\n)"}
        )
    )

    async def run_handler(handler_func):
        await handler_func(
            session=session,
            inbound_url="https://ru.example.test/panel/api/inbounds/",
            server_name="russia",
            inbound_ids=[1],
        )

    manager._process_on_all_servers = AsyncMock(side_effect=run_handler)

    with patch(
        "telegram_bot.infrastructure.api.client_manager.build_client_template",
        return_value={"id": 1, "settings": {"clients": [{}]}},
    ):
        with pytest.raises(ValueError, match="empty client ID"):
            await manager.update_client(tg_id=42, period="year1")

    called_urls = [call.args[0] for call in session.post.await_args_list]
    assert called_urls == [
        "https://ru.example.test/panel/api/inbounds/updateClient/uuid-1",
    ]
    repo.update_expiration.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_client_raises_when_user_has_empty_uuid(manager_deps):
    manager, repo, _, _ = manager_deps
    repo.get.return_value = SimpleNamespace(
        uuid="",
        sub_id="",
        email="cat@example.com",
        expiration_date=1000,
    )

    with pytest.raises(ValueError, match="empty uuid"):
        await manager.update_client(tg_id=42, period="year1")


@pytest.mark.asyncio
async def test_add_client_treats_known_duplicate_email_as_already_provisioned(manager_deps):
    manager, repo, timestamp, jsonutils = manager_deps
    repo.get.return_value = SimpleNamespace(
        uuid="uuid-1",
        sub_id="sub-1",
        email="gentle-feather",
        expiration_date=None,
    )
    timestamp.set_client_date.return_value = 2000
    jsonutils.update_post_client_json.side_effect = (
        lambda tg_id, template, client_id, email, date, sub_id: {
            "id": template["id"],
            "settings": f'{{"clients":[{{"id":"{client_id}","email":"{email}"}}]}}',
        }
    )

    session = AsyncMock()
    session.post = AsyncMock(
        side_effect=[
            _response({"success": True}),
            _response(
                {
                    "success": False,
                    "msg": "Something went wrong (Duplicate email: gentle-feather_1\n)",
                    "obj": None,
                }
            ),
        ]
    )

    async def run_handler(handler_func):
        await handler_func(
            session=session,
            inbound_url="https://ru.example.test/panel/api/inbounds/",
            server_name="russia",
            inbound_ids=[1, 2],
        )

    manager._process_on_all_servers = AsyncMock(side_effect=run_handler)

    with patch(
        "telegram_bot.infrastructure.api.client_manager.build_client_template",
        side_effect=lambda inbound_id: {"id": inbound_id, "settings": {"clients": [{}]}},
    ):
        await manager.add_client(tg_id=42, period="year1")

    called_urls = [call.args[0] for call in session.post.await_args_list]
    assert called_urls == [
        "https://ru.example.test/panel/api/inbounds/addClient",
        "https://ru.example.test/panel/api/inbounds/addClient",
    ]
    repo.update_expiration.assert_awaited_once_with(expiration_date=2000, tg_id=42)
