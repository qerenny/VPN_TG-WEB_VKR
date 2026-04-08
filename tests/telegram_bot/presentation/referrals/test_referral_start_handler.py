from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest

from telegram_bot.presentation.referrals.referral_start_handler import ReferralStartHandler


@pytest.fixture
def registration_service():
    return AsyncMock()


@pytest.fixture
def handler(registration_service):
    return ReferralStartHandler(registration_service)


class FakeMessage:
    def __init__(self, chat_id):
        self.chat = SimpleNamespace(id=chat_id)
        self.from_user = SimpleNamespace(username="user")


@pytest.mark.asyncio
async def test_invalid_code(handler, registration_service):
    msg = FakeMessage(1)
    registration_service.register_user.return_value = (False, "invalid_code")

    with (
        patch(
            "telegram_bot.presentation.referrals.referral_start_handler.messages.get_random_message",
            return_value="bad",
        ) as mock_msg,
        patch(
            "telegram_bot.presentation.referrals.referral_start_handler.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await handler.process_start_command(msg, ["/start", "2"], user_created=True)

    registration_service.register_user.assert_awaited_once_with(
        1,
        ["/start", "2"],
        user_created=True,
    )
    mock_msg.assert_called_once_with("referral_invalid_code")
    mock_send.assert_awaited_once_with(chat_id=1, text="bad")


@pytest.mark.asyncio
async def test_code_activated(handler, registration_service):
    msg = FakeMessage(5)
    registration_service.register_user.return_value = (True, "code_activated")

    with (
        patch(
            "telegram_bot.presentation.referrals.referral_start_handler.messages.get_random_message",
            side_effect=["activated", "used"],
        ) as mock_msg,
        patch(
            "telegram_bot.presentation.referrals.referral_start_handler.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await handler.process_start_command(msg, ["/start", "10"], user_created=True)

    registration_service.register_user.assert_awaited_once_with(
        5,
        ["/start", "10"],
        user_created=True,
    )
    assert mock_msg.call_args_list[0].args[0] == "referral_code_activated"
    assert mock_msg.call_args_list[1].args[0] == "referral_code_used"
    mock_send.assert_has_awaits(
        [
            call(chat_id=5, text="activated", parse_mode="Markdown"),
            call(chat_id=10, text="used", parse_mode="Markdown"),
        ]
    )


@pytest.mark.asyncio
async def test_code_updated(handler, registration_service):
    msg = FakeMessage(9)
    registration_service.register_user.return_value = (True, "code_updated")

    with (
        patch(
            "telegram_bot.presentation.referrals.referral_start_handler.messages.get_random_message",
            return_value="updated",
        ) as mock_msg,
        patch(
            "telegram_bot.presentation.referrals.referral_start_handler.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await handler.process_start_command(msg, ["/start", "7"], user_created=True)

    registration_service.register_user.assert_awaited_once_with(
        9,
        ["/start", "7"],
        user_created=True,
    )
    mock_msg.assert_called_once_with("referral_code_changed")
    mock_send.assert_awaited_once_with(chat_id=9, text="updated", parse_mode="Markdown")


@pytest.mark.asyncio
async def test_no_message_on_other_status(handler, registration_service):
    msg = FakeMessage(4)
    registration_service.register_user.return_value = (True, "no_code")

    with patch(
        "telegram_bot.presentation.referrals.referral_start_handler.bot.send_message",
        new_callable=AsyncMock,
    ) as mock_send:
        await handler.process_start_command(msg, ["/start"], user_created=False)

    registration_service.register_user.assert_awaited_once_with(
        4,
        ["/start"],
        user_created=False,
    )
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_user_gets_dedicated_message(handler, registration_service):
    msg = FakeMessage(6)
    registration_service.register_user.return_value = (False, "existing_user")

    with (
        patch(
            "telegram_bot.presentation.referrals.referral_start_handler.messages.get_random_message",
            return_value="existing",
        ) as mock_msg,
        patch(
            "telegram_bot.presentation.referrals.referral_start_handler.bot.send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await handler.process_start_command(msg, ["/start", "7"], user_created=False)

    registration_service.register_user.assert_awaited_once_with(
        6,
        ["/start", "7"],
        user_created=False,
    )
    mock_msg.assert_called_once_with("referral_existing_user")
    mock_send.assert_awaited_once_with(chat_id=6, text="existing")
