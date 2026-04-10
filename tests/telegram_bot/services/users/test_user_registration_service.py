from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from shared.infrastructure.users.telegram_user_repository import TelegramUserSnapshot
from telegram_bot.services.users.user_registration_service import UserRegistrationService


def make_message(chat_id: int, username: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id, username=username))


@pytest.fixture
def service_and_mocks():
    repo = AsyncMock()
    timestamp = MagicMock()
    uuidgen = MagicMock()
    service = UserRegistrationService(
        repo=repo,
        timestamp=timestamp,
        uuidgen=uuidgen,
    )
    return service, repo, timestamp, uuidgen


@pytest.fixture
def mock_logger():
    with patch("telegram_bot.services.users.user_registration_service.logger") as mock_log:
        yield mock_log


@pytest.mark.asyncio
async def test_register_user_creates_new_user(service_and_mocks, mock_logger):
    service, repo, timestamp, uuidgen = service_and_mocks
    repo.get.return_value = None
    uuidgen.generate_id.side_effect = ["uid-1", "sub-1"]
    uuidgen.generate_email.return_value = "example.com"
    timestamp.current_timestamp.return_value = 123456

    result = await service.register_user(make_message(555))

    repo.get.assert_awaited_once_with(555)
    repo.create.assert_awaited_once()

    created_user = repo.create.await_args.args[0]
    assert isinstance(created_user, TelegramUserSnapshot)
    assert created_user.tg_id == 555
    assert created_user.uuid == "uid-1"
    assert created_user.email == "example-com"
    assert created_user.sub_id == "sub-1"
    assert created_user.login_date == 123456
    repo.create.assert_awaited_once_with(
        created_user,
        telegram_username=None,
    )
    assert result is True
    mock_logger.info.assert_called_once_with("User 555 registered successfully.")


@pytest.mark.asyncio
async def test_register_user_uses_username_prefix_when_present(service_and_mocks):
    service, repo, timestamp, uuidgen = service_and_mocks
    repo.get.return_value = None
    uuidgen.generate_id.side_effect = ["uid-2", "sub-2"]
    uuidgen.generate_email.return_value = "mail.test"
    timestamp.current_timestamp.return_value = 1

    result = await service.register_user(make_message(7, username="alice"))

    created_user = repo.create.await_args.args[0]
    assert created_user.email == "alice-mail-test"
    repo.create.assert_awaited_once_with(
        created_user,
        telegram_username="alice",
    )
    assert result is True


@pytest.mark.asyncio
async def test_register_user_skips_existing_user(service_and_mocks, mock_logger):
    service, repo, _timestamp, uuidgen = service_and_mocks
    repo.get.return_value = TelegramUserSnapshot(
        tg_id=42,
        uuid="existing-uuid",
        email="exist@example.com",
        expiration_date=None,
        login_date=1234567890,
        trial_date=None,
        info_channel_date=None,
        sub_id="sub-existing",
    )

    result = await service.register_user(make_message(42))

    repo.create.assert_not_awaited()
    uuidgen.generate_id.assert_not_called()
    uuidgen.generate_email.assert_not_called()
    repo.touch_identity.assert_awaited_once_with(
        tg_id=42,
        telegram_username=None,
        seen_at=service.timestamp.current_timestamp.return_value,
    )
    assert result is False
    mock_logger.info.assert_called_once_with("User 42 already exists.")


@pytest.mark.asyncio
async def test_register_user_propagates_uuid_generation_error(service_and_mocks):
    service, repo, _timestamp, uuidgen = service_and_mocks
    repo.get.return_value = None
    uuidgen.generate_id.side_effect = RuntimeError("UUID generation failed")

    with pytest.raises(RuntimeError, match="UUID generation failed"):
        await service.register_user(make_message(777))

    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_user_propagates_repository_error(service_and_mocks):
    service, repo, _timestamp, _uuidgen = service_and_mocks
    repo.get.side_effect = RuntimeError("Database query failed")

    with pytest.raises(RuntimeError, match="Database query failed"):
        await service.register_user(make_message(123))

    repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_user_handles_duplicate_telegram_account_race(
    service_and_mocks,
    mock_logger,
):
    service, repo, timestamp, uuidgen = service_and_mocks
    repo.get.return_value = None
    uuidgen.generate_id.side_effect = ["uid-race", "sub-race"]
    uuidgen.generate_email.return_value = "mail.test"
    timestamp.current_timestamp.return_value = 111
    repo.create.side_effect = IntegrityError(
        statement="INSERT INTO telegram_accounts ...",
        params={},
        orig=Exception('duplicate key value violates unique constraint "telegram_accounts_telegram_id_key"'),
    )

    result = await service.register_user(make_message(888, username="alice"))

    assert result is False
    repo.touch_identity.assert_awaited_once_with(
        tg_id=888,
        telegram_username="alice",
        seen_at=111,
    )
    mock_logger.warning.assert_called_once()
