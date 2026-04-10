from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.payments.payment_fulfillment_service import (
    DEAD_LETTER_DEDUPE_TTL_SECONDS,
    PaymentFulfillmentService,
)
from telegram_bot.shared.config.navigation import OPEN_CABINET


def make_service(subscription_link: str | None = None):
    repo = AsyncMock()
    payment_processing = AsyncMock()
    queue_service = AsyncMock()
    subscription_service = AsyncMock()
    telegram_link_service = AsyncMock()
    telegram_link_service.create_web_link.return_value = "https://example.com/app"
    subscription_service.get_subscription_link.return_value = subscription_link

    service = PaymentFulfillmentService(
        repo=repo,
        payment_processing=payment_processing,
        queue_service=queue_service,
        subscription_service=subscription_service,
        scan_interval_seconds=1,
        retry_base_seconds=1,
        max_retries=3,
        worker_pop_timeout_seconds=1,
        dedupe_ttl_seconds=60,
        telegram_link_service=telegram_link_service,
    )
    return service, subscription_service, repo, payment_processing, queue_service, telegram_link_service


@pytest.mark.asyncio
async def test_notify_user_adds_profile_navigation_buttons():
    service, subscription_service, _, _, _, telegram_link_service = make_service("https://example.com/subscription")
    bot_mock = MagicMock(send_message=AsyncMock(), send_photo=AsyncMock())

    with patch("telegram_bot.services.payments.payment_fulfillment_service.bot", bot_mock), patch(
        "telegram_bot.services.payments.payment_fulfillment_service.PHOTO_menu",
        "photo.png",
    ):
        await service._notify_user(
            tg_id=1,
            subscription_updated_text="updated",
            subscription_update_date_text="open subscription",
            grant_tg_id_text=None,
            grant_referrer_id_text=None,
            referrer_tg_id=None,
            subscription_link_scope="standard",
        )

    subscription_service.get_subscription_link.assert_not_awaited()
    assert telegram_link_service.create_web_link.await_count == 2
    _, kwargs = bot_mock.send_message.await_args
    assert kwargs["chat_id"] == 1
    assert kwargs["text"] == "✅ Оплата подтверждена.\nДоступ обновлен в веб-кабинете.\n\nopen subscription"
    assert kwargs["reply_markup"].keyboard[0][0].text == OPEN_CABINET
    assert kwargs["reply_markup"].keyboard[0][0].url == "https://example.com/app"
    bot_mock.send_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_notify_user_still_sends_navigation_and_bonus_message():
    service, subscription_service, _, _, _, _ = make_service(None)
    bot_mock = MagicMock(send_message=AsyncMock(), send_photo=AsyncMock())

    with patch("telegram_bot.services.payments.payment_fulfillment_service.bot", bot_mock), patch(
        "telegram_bot.services.payments.payment_fulfillment_service.PHOTO_menu",
        "photo.png",
    ):
        await service._notify_user(
            tg_id=1,
            subscription_updated_text="updated",
            subscription_update_date_text="open subscription",
            grant_tg_id_text="bonus",
            grant_referrer_id_text=None,
            referrer_tg_id=None,
            subscription_link_scope="standard",
        )

    subscription_service.get_subscription_link.assert_not_awaited()
    first_call = bot_mock.send_message.await_args_list[0].kwargs
    second_call = bot_mock.send_message.await_args_list[1].kwargs
    assert first_call["reply_markup"].keyboard[0][0].text == OPEN_CABINET
    assert second_call["text"] == "bonus"
    bot_mock.send_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_notify_user_can_skip_link_lookup_explicitly():
    service, subscription_service, _, _, _, _ = make_service("https://example.com/subscription")
    bot_mock = MagicMock(send_message=AsyncMock(), send_photo=AsyncMock())

    with patch("telegram_bot.services.payments.payment_fulfillment_service.bot", bot_mock), patch(
        "telegram_bot.services.payments.payment_fulfillment_service.PHOTO_menu",
        "photo.png",
    ):
        await service._notify_user(
            tg_id=1,
            subscription_updated_text="updated",
            subscription_update_date_text="traffic_limited ready",
            grant_tg_id_text=None,
            grant_referrer_id_text=None,
            referrer_tg_id=None,
            subscription_link_scope=None,
        )

    subscription_service.get_subscription_link.assert_not_awaited()
    _, kwargs = bot_mock.send_message.await_args
    assert kwargs["reply_markup"].keyboard[0][0].text == OPEN_CABINET
    bot_mock.send_photo.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_queue_once_marks_payment_confirmed():
    service, _, repo, payment_processing, queue_service, _ = make_service(None)
    queue_service.pop_ready.return_value = {"payment_id": "pay-1", "attempt": 0}
    repo.get_by_payment_id.return_value = MagicMock(
        payment_id="pay-1",
        tg_id=1,
        payload="month1",
        status="paid",
        confirmed=False,
        method="external_wallet",
    )
    payment_processing.payment_processing.return_value = (
        "updated",
        "expires",
        None,
        None,
        None,
    )

    bot_mock = MagicMock(send_message=AsyncMock())
    with patch("telegram_bot.services.payments.payment_fulfillment_service.bot", bot_mock):
        result = await service.process_queue_once()

    assert result is True
    queue_service.refresh_dedupe.assert_awaited_once_with(
        {"payment_id": "pay-1", "attempt": 0},
        ttl_seconds=60,
    )
    repo.update_status.assert_awaited_once_with(
        payment_id="pay-1",
        status="paid",
        confirmed=True,
    )


@pytest.mark.asyncio
async def test_process_queue_once_does_not_lookup_traffic_limited_link_for_traffic_limited_payment():
    service, subscription_service, repo, payment_processing, queue_service, _ = make_service(
        "https://example.com/subscription"
    )
    queue_service.pop_ready.return_value = {"payment_id": "pay-wl", "attempt": 0}
    repo.get_by_payment_id.return_value = MagicMock(
        payment_id="pay-wl",
        tg_id=1,
        payload="traffic_limited15gb",
        status="paid",
        confirmed=False,
        method="external_wallet",
    )
    payment_processing.payment_processing.return_value = (
        "updated",
        "traffic added",
        None,
        None,
        None,
    )

    bot_mock = MagicMock(send_message=AsyncMock())
    with patch("telegram_bot.services.payments.payment_fulfillment_service.bot", bot_mock):
        result = await service.process_queue_once()

    assert result is True
    subscription_service.get_subscription_link.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_or_dead_letter_refreshes_dedupe_for_retry():
    service, _, _, _, queue_service, _ = make_service(None)

    payload = {"payment_id": "pay-1", "attempt": 1}
    await service._retry_or_dead_letter(payload, "boom")

    queue_service.refresh_dedupe.assert_awaited_once_with(
        {"payment_id": "pay-1", "attempt": 2, "last_error": "boom"},
        ttl_seconds=62,
    )
    queue_service.enqueue.assert_awaited_once_with(
        {"payment_id": "pay-1", "attempt": 2, "last_error": "boom"},
        delay_seconds=2,
    )
    queue_service.push_dead_letter.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_or_dead_letter_refreshes_dedupe_for_dead_letter():
    service, _, _, _, queue_service, _ = make_service(None)

    payload = {"payment_id": "pay-1", "attempt": 3}
    await service._retry_or_dead_letter(payload, "boom")

    queue_service.refresh_dedupe.assert_awaited_once_with(
        {"payment_id": "pay-1", "attempt": 4, "last_error": "boom"},
        ttl_seconds=DEAD_LETTER_DEDUPE_TTL_SECONDS,
    )
    queue_service.push_dead_letter.assert_awaited_once_with(
        {"payment_id": "pay-1", "attempt": 4, "last_error": "boom"},
        "boom",
    )
    queue_service.enqueue.assert_not_awaited()
