from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.subscriptions.subscription_reminder_service import (
    SubscriptionReminderService,
)


@pytest.fixture
def service_and_mocks():
    repo = AsyncMock()
    info_service = AsyncMock()
    timestamp = MagicMock()
    reminder_queue_service = AsyncMock()
    service = SubscriptionReminderService(
        repo=repo,
        user_subscription_info_service=info_service,
        timestamp=timestamp,
        reminder_queue_service=reminder_queue_service,
        retry_base_seconds=10,
        max_retries=2,
        worker_pop_timeout_seconds=3,
        dedupe_ttl_seconds=100,
    )
    return service, repo, info_service, timestamp, reminder_queue_service


@pytest.mark.asyncio
async def test_send_renewal_reminder_sends_message_with_markup(service_and_mocks):
    service, _repo, info_service, _timestamp, _queue = service_and_mocks
    info_service.expiry_date_view.return_value = "expiry text"

    with (
        patch(
            "telegram_bot.services.subscriptions.subscription_reminder_service.types.InlineKeyboardMarkup"
        ) as markup_class,
        patch(
            "telegram_bot.services.subscriptions.subscription_reminder_service.types.InlineKeyboardButton"
        ) as button_class,
        patch(
            "telegram_bot.services.subscriptions.subscription_reminder_service.messages.get_random_message",
            return_value="Продлить",
        ) as get_message,
        patch(
            "telegram_bot.services.subscriptions.subscription_reminder_service.bot.send_message"
        ) as send_message,
    ):
        markup = MagicMock()
        button = MagicMock()
        markup_class.return_value = markup
        button_class.return_value = button

        await service.send_renewal_reminder(123)

    info_service.expiry_date_view.assert_awaited_once_with("renewal_reminder", 123)
    get_message.assert_called_once_with("renewal_update_sub_message")
    button_class.assert_called_once_with(
        text="Продлить",
        callback_data="profile_subscriptions",
    )
    markup.add.assert_called_once_with(button)
    send_message.assert_awaited_once_with(
        chat_id=123,
        text="expiry text",
        parse_mode="Markdown",
        reply_markup=markup,
    )


@pytest.mark.asyncio
async def test_enqueue_expiring_users_enqueues_only_new_expiring_users(service_and_mocks):
    service, repo, _info_service, timestamp, queue = service_and_mocks
    timestamp.current_timestamp.return_value = 1_000
    repo.get_users_expiring_between.return_value = [
        SimpleNamespace(
            tg_id=1,
            uuid="u1",
            email="a@example.com",
            expiration_date=2_000,
            login_date=1,
            trial_date=None,
            sub_id="sub-1",
        ),
        SimpleNamespace(
            tg_id=2,
            uuid="u2",
            email="b@example.com",
            expiration_date=None,
            login_date=1,
            trial_date=None,
            sub_id="sub-2",
        ),
        SimpleNamespace(
            tg_id=3,
            uuid="u3",
            email="c@example.com",
            expiration_date=3_000,
            login_date=1,
            trial_date=None,
            sub_id="sub-3",
        ),
    ]
    queue.enqueue_if_new.side_effect = [True, False]

    count = await service.enqueue_expiring_users()

    repo.get_users_expiring_between.assert_awaited_once()
    assert queue.enqueue_if_new.await_count == 2
    first_payload = queue.enqueue_if_new.await_args_list[0].args[0]
    second_payload = queue.enqueue_if_new.await_args_list[1].args[0]
    assert first_payload["tg_id"] == 1
    assert second_payload["tg_id"] == 3
    assert count == 1


@pytest.mark.asyncio
async def test_process_queue_once_skips_stale_payload(service_and_mocks):
    service, repo, _info_service, timestamp, queue = service_and_mocks
    queue.pop_ready.return_value = {"tg_id": 1, "expiration_date": 2_000, "attempt": 0}
    repo.get.return_value = SimpleNamespace(expiration_date=1_500)
    timestamp.current_timestamp.return_value = 1_000

    processed = await service.process_queue_once()

    queue.promote_delayed.assert_awaited_once()
    queue.pop_ready.assert_awaited_once_with(timeout_seconds=3)
    assert processed is True
    repo.get.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_process_queue_once_sends_reminder_for_fresh_payload(service_and_mocks):
    service, repo, _info_service, timestamp, queue = service_and_mocks
    queue.pop_ready.return_value = {"tg_id": 1, "expiration_date": 2_000, "attempt": 0}
    repo.get.return_value = SimpleNamespace(expiration_date=2_000)
    timestamp.current_timestamp.return_value = 1_000

    with patch.object(service, "send_renewal_reminder", new_callable=AsyncMock) as send_reminder:
        processed = await service.process_queue_once()

    assert processed is True
    send_reminder.assert_awaited_once_with(1)
    queue.enqueue.assert_not_called()
    queue.push_dead_letter.assert_not_called()


@pytest.mark.asyncio
async def test_process_queue_once_retries_failed_reminder(service_and_mocks):
    service, repo, _info_service, timestamp, queue = service_and_mocks
    queue.pop_ready.return_value = {"tg_id": 1, "expiration_date": 2_000, "attempt": 0}
    repo.get.return_value = SimpleNamespace(expiration_date=2_000)
    timestamp.current_timestamp.return_value = 1_000

    with patch.object(
        service,
        "send_renewal_reminder",
        new_callable=AsyncMock,
        side_effect=RuntimeError("send failed"),
    ):
        processed = await service.process_queue_once()

    assert processed is True
    queue.enqueue.assert_awaited_once_with(
        {
            "tg_id": 1,
            "expiration_date": 2_000,
            "attempt": 1,
            "last_error": "send failed",
        },
        delay_seconds=10,
    )
    queue.push_dead_letter.assert_not_called()


@pytest.mark.asyncio
async def test_retry_or_dead_letter_pushes_to_dlq_after_max_retries(service_and_mocks):
    service, _repo, _info_service, _timestamp, queue = service_and_mocks
    payload = {"tg_id": 1, "expiration_date": 2_000, "attempt": 2}

    await service._retry_or_dead_letter(payload, "still failing")

    queue.enqueue.assert_not_called()
    queue.push_dead_letter.assert_awaited_once_with(
        {
            "tg_id": 1,
            "expiration_date": 2_000,
            "attempt": 3,
            "last_error": "still failing",
        },
        "still failing",
    )
