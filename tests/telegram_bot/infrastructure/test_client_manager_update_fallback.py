from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.infrastructure.api.client_manager import ClientManager


def _response(payload: dict):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    response.text = str(payload)
    response.status_code = 200
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


def test_normalize_inbound_ids_casts_strings_to_ints():
    assert ClientManager._normalize_inbound_ids("3") == [3]
    assert ClientManager._normalize_inbound_ids(["3", 4]) == [3, 4]


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


@pytest.mark.asyncio
async def test_process_on_server_pool_passes_integer_inbound_ids(manager_deps):
    manager, _, _, _ = manager_deps

    captured_inbound_ids = None

    async def handler_func(*, session, inbound_url, server_name, inbound_ids):
        nonlocal captured_inbound_ids
        captured_inbound_ids = inbound_ids

    with patch("telegram_bot.infrastructure.api.client_manager.APIConnection") as api_connection_cls:
        api_connection = MagicMock()
        api_connection.login = AsyncMock(return_value=AsyncMock())
        api_connection.release = MagicMock()
        api_connection_cls.return_value = api_connection

        await manager._process_on_server_pool(
            handler_func,
            server_pool={
                "germany": {
                    "domain": "example.test",
                    "port": 443,
                    "path": "panel",
                    "inbound_id": "3",
                }
            },
            cache_namespace="standard",
        )

    assert captured_inbound_ids == [3]


@pytest.mark.asyncio
async def test_client_exists_returns_false_on_http_200_with_unsuccessful_payload(manager_deps):
    manager, _, _, _ = manager_deps

    session = AsyncMock()
    session.get = AsyncMock(
        return_value=_response(
            {"success": False, "msg": "Something went wrong (empty client ID\n)", "obj": None}
        )
    )

    with patch("telegram_bot.infrastructure.api.client_manager.APIConnection") as api_connection_cls:
        api_connection = MagicMock()
        api_connection.login = AsyncMock(return_value=session)
        api_connection.release = MagicMock()
        api_connection_cls.return_value = api_connection

        manager_exists = await manager.client_exists("uuid-1")

    assert manager_exists is False


@pytest.mark.asyncio
async def test_update_scoped_client_falls_back_to_add_when_panel_returns_empty_client_id(manager_deps):
    manager, _, _, jsonutils = manager_deps
    jsonutils.update_post_client_json.side_effect = (
        lambda tg_id, template, client_id, email, date, sub_id, total_bytes=None: {
            "id": template["id"],
            "settings": f'{{"clients":[{{"id":"{client_id}","email":"{email}"}}]}}',
        }
    )

    session = AsyncMock()
    session.post = AsyncMock(
        side_effect=[
            _response(
                {"success": False, "msg": "Something went wrong (empty client ID\n)", "obj": None}
            ),
            _response({"success": True, "obj": None}),
        ]
    )

    async def run_handler(handler_func, **_kwargs):
        await handler_func(
            session=session,
            inbound_url="https://ru.example.test/panel/api/inbounds/",
            server_name="russia",
            inbound_ids=[3],
        )

    manager._process_on_server_pool = AsyncMock(side_effect=run_handler)

    with patch(
        "telegram_bot.infrastructure.api.client_manager.build_client_template",
        return_value={"id": 3, "settings": {"clients": [{}]}},
    ):
        await manager.update_scoped_client(
            server_pool={"russia": {"inbound_id": [3]}},
            cache_namespace="standard",
            tg_id=42,
            client_uuid="uuid-1",
            email="cat@example.com",
            sub_id="sub-1",
            expires_at=2000,
            total_bytes=0,
        )

    called_urls = [call.args[0] for call in session.post.await_args_list]
    assert called_urls == [
        "https://ru.example.test/panel/api/inbounds/updateClient/uuid-1",
        "https://ru.example.test/panel/api/inbounds/addClient",
    ]
