from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import telegram_bot.services.subscriptions.subscription_provisioning_service as provisioning_module
from shared.models import register_models
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.infrastructure.users.telegram_user_repository import TelegramUserSnapshot
from telegram_bot.services.subscriptions.subscription_provisioning_service import (
    SubscriptionProvisioningService,
)
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator

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
def service_and_mocks():
    repo = AsyncMock()
    timestamp = MagicMock()
    client = AsyncMock()
    jwt_encoder = MagicMock()
    uuidgen = MagicMock(spec=UUIDGenerator)
    service = SubscriptionProvisioningService(
        repo=repo,
        timestamputils=timestamp,
        client=client,
        jwt_encoder=jwt_encoder,
        uuidgen=uuidgen,
    )
    return service, repo, client, jwt_encoder, uuidgen


@pytest.fixture
def active_user():
    return SimpleNamespace(
        tg_id=12345,
        uuid="test-uuid-123",
        email="user@example.com",
        expiration_date=1700000000,
        info_channel_date=None,
        sub_id="sub-123",
    )


@pytest.fixture
def inactive_user():
    return SimpleNamespace(
        tg_id=12345,
        uuid="test-uuid-123",
        email="user@example.com",
        expiration_date=None,
        info_channel_date=None,
        sub_id="sub-123",
    )


@pytest.mark.asyncio
async def test_create_or_update_user_updates_existing_subscription(service_and_mocks, active_user):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = active_user
    client.client_exists.return_value = True

    result = await service.create_or_update_user(tg_id=12345, period="30d")

    assert result is None
    client.client_exists.assert_awaited_once_with("test-uuid-123")
    client.update_client.assert_awaited_once_with(12345, "30d", user=active_user)
    client.add_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_or_update_user_recreates_missing_client_with_preserved_expiry(
    service_and_mocks,
    active_user,
):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = active_user
    client.client_exists.return_value = False
    service.timestamputils.update_client_date.return_value = 1800000000

    await service.create_or_update_user(tg_id=12345, period="7d")

    client.add_client.assert_awaited_once_with(
        12345,
        "7d",
        user=active_user,
        target_expiration_date=1800000000,
    )
    client.update_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_or_update_user_adds_user_without_expiration(service_and_mocks, inactive_user):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = inactive_user

    await service.create_or_update_user(tg_id=12345, period="7d")

    client.client_exists.assert_not_awaited()
    client.add_client.assert_awaited_once_with(12345, "7d", user=inactive_user)
    client.update_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_or_update_user_raises_for_unknown_user(service_and_mocks):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = None

    with pytest.raises(AttributeError, match="User not found"):
        await service.create_or_update_user(tg_id=999, period="30d")

    client.add_client.assert_not_awaited()
    client.update_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_subscription_link_returns_empty_without_expiration(service_and_mocks, inactive_user):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = inactive_user

    assert await service.get_subscription_link(tg_id=12345) == ""
    jwt_encoder.encode.assert_not_called()


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://frontend.example.com/subscription", "https://frontend.example.com/subscription/jwt-token"),
        ("https://frontend.example.com/subscription/", "https://frontend.example.com/subscription/jwt-token"),
        ("", ""),
    ],
)
@pytest.mark.asyncio
async def test_get_subscription_link_normalizes_base_url(
    service_and_mocks, active_user, base_url, expected
):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = active_user
    jwt_encoder.encode.return_value = "jwt-token"

    with patch(
        "telegram_bot.services.subscriptions.subscription_provisioning_service.FRONTEND_TELEGRAM_SUBSCRIPTION_LINK",
        base_url,
    ):
        assert await service.get_subscription_link(tg_id=12345) == expected


@pytest.mark.asyncio
async def test_get_subscription_link_returns_traffic_limited_link(
    service_and_mocks,
    session_factory,
):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    jwt_encoder.encode.return_value = "traffic_limited-jwt"

    @asynccontextmanager
    async def test_get_db_session():
        async with session_factory() as session:
            yield session

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
                telegram_id=12345,
                username="alice",
                linked_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        session.add(
            VpnClient(
                user_id=int(app_user.id),
                scope="traffic_limited",
                provider="3x-ui",
                external_client_uuid="wl-uuid-1",
                external_email="wl-user@example.com",
                subscription_external_id="wl-sub-1",
                metadata_json={},
                created_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                deactivated_at=None,
            )
        )
        await session.commit()

    with (
        patch.object(provisioning_module, "get_db_session", test_get_db_session),
        patch.object(
            provisioning_module,
            "FRONTEND_TELEGRAM_TRAFFIC_LIMITED_SUBSCRIPTION_LINK",
            "https://frontend.example.com/subscription/traffic-limited",
        ),
    ):
        result = await service.get_subscription_link(tg_id=12345, scope="traffic_limited")

    assert result == "https://frontend.example.com/subscription/traffic-limited/traffic_limited-jwt"
    jwt_encoder.encode.assert_called_once_with(
        {
            "tg_id": 12345,
            "email": "wl-user@example.com",
            "scope": "traffic_limited",
        }
    )


@pytest.mark.asyncio
async def test_client_exists_returns_false_when_user_is_missing(service_and_mocks):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = None

    assert await service.client_exists(12345) is False
    client.client_exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_client_uses_user_uuid(service_and_mocks, active_user):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = active_user

    await service.delete_client(12345)

    client.delete_client.assert_awaited_once_with("test-uuid-123")


@pytest.mark.asyncio
async def test_delete_user_returns_false_when_user_missing(service_and_mocks):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = None

    assert await service.delete_user(12345) is False

    client.client_exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_or_update_user_repairs_empty_standard_identifiers_before_adding_client(
    service_and_mocks,
):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    stale_user = TelegramUserSnapshot(
        tg_id=12345,
        uuid="",
        email="",
        expiration_date=None,
        sub_id="",
        login_date=1700000000,
        trial_date=None,
        info_channel_date=None,
        username="alice",
    )
    repo.get.return_value = stale_user
    uuidgen.generate_id.side_effect = ["generated-uuid", "generated-sub-id"]
    uuidgen.generate_email.return_value = "bold-union-6aa5f0f9"

    await service.create_or_update_user(tg_id=12345, period="7d")

    repaired = repo.create.await_args.args[0]
    assert repaired.uuid == "generated-uuid"
    assert repaired.email == "alice-bold-union-6aa5f0f9"
    assert repaired.sub_id == "generated-sub-id"
    client.add_client.assert_awaited_once_with(12345, "7d", user=repaired)


@pytest.mark.asyncio
async def test_delete_user_skips_panel_delete_when_client_is_absent(service_and_mocks, active_user):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = active_user
    client.client_exists.return_value = False

    with (
        patch.object(service, "_delete_from_datastores", new=AsyncMock()) as delete_mock,
        patch.object(service, "_list_active_panel_clients", new=AsyncMock(return_value=[("standard", "test-uuid-123")])),
    ):
        assert await service.delete_user(12345) is True

    client.delete_client.assert_not_awaited()
    delete_mock.assert_awaited_once_with(12345)


@pytest.mark.asyncio
async def test_delete_user_removes_panel_client_before_datastore_cleanup(service_and_mocks, active_user):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = active_user
    client.client_exists.return_value = True

    with (
        patch.object(service, "_delete_from_datastores", new=AsyncMock()) as delete_mock,
        patch.object(service, "_list_active_panel_clients", new=AsyncMock(return_value=[("standard", "test-uuid-123")])),
    ):
        assert await service.delete_user(12345) is True

    client.delete_client.assert_awaited_once_with("test-uuid-123")
    delete_mock.assert_awaited_once_with(12345)


@pytest.mark.asyncio
async def test_delete_user_removes_traffic_limited_panel_client_before_datastore_cleanup(
    service_and_mocks,
    active_user,
):
    service, repo, client, jwt_encoder, uuidgen = service_and_mocks
    repo.get.return_value = active_user

    with (
        patch.object(service, "_delete_from_datastores", new=AsyncMock()) as delete_mock,
        patch.object(
            service,
            "_list_active_panel_clients",
            new=AsyncMock(
                return_value=[
                    ("standard", "test-uuid-123"),
                    ("traffic_limited", "traffic-uuid-456"),
                ]
            ),
        ),
    ):
        client.client_exists.return_value = True
        assert await service.delete_user(12345) is True

    client.delete_client.assert_awaited_once_with("test-uuid-123")
    client.delete_scoped_client.assert_awaited_once()
    _, kwargs = client.delete_scoped_client.await_args
    assert kwargs["cache_namespace"] == "traffic_limited"
    assert kwargs["client_uuid"] == "traffic-uuid-456"
    delete_mock.assert_awaited_once_with(12345)
