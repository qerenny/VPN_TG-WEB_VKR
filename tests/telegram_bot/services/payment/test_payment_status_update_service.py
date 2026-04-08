import time
from unittest.mock import AsyncMock

import pytest

from shared.migration_support.models.payments.payment_model import Payment
from telegram_bot.services.payments.payment_status_update_service import PaymentStatusChecker


@pytest.fixture
def checker_and_mocks():
    repo = AsyncMock()
    yookassa = AsyncMock()
    cryptopay = AsyncMock()
    fulfillment = AsyncMock()
    sync_service = AsyncMock()
    checker = PaymentStatusChecker(
        repo=repo,
        yookassa=yookassa,
        cryptopay=cryptopay,
        payment_fulfillment_service=fulfillment,
        scan_interval_seconds=1,
        sync_service=sync_service,
    )
    return checker, repo, yookassa, cryptopay, fulfillment, sync_service


def make_payment(payment_id: str, method: str, status: str = "pending", created_at: int = 0):
    return Payment(
        payment_id=payment_id,
        tg_id=1,
        status=status,
        payload="payload",
        created_at=created_at,
        confirmed=False,
        method=method,
    )


@pytest.mark.asyncio
async def test_cryptopay_paid_payment_updates_status_and_enqueues(checker_and_mocks):
    checker, repo, yookassa, cryptopay, fulfillment, sync_service = checker_and_mocks
    repo.get_unconfirmed.return_value = [make_payment("123", "cryptopay")]
    cryptopay.find_payment_status.return_value = "paid"

    await checker.check_and_update_payment_status()

    cryptopay.find_payment_status.assert_awaited_once_with(123)
    repo.update_status_batch.assert_awaited_once_with([("123", "paid", False)])
    fulfillment.enqueue_payment.assert_awaited_once_with("123")
    yookassa.find_payment_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_yookassa_succeeded_payment_updates_status_and_enqueues(checker_and_mocks):
    checker, repo, yookassa, cryptopay, fulfillment, sync_service = checker_and_mocks
    repo.get_unconfirmed.return_value = [make_payment("abc", "yookassa")]
    yookassa.find_payment_status.return_value = "succeeded"

    await checker.check_and_update_payment_status()

    yookassa.find_payment_status.assert_awaited_once_with("abc")
    repo.update_status_batch.assert_awaited_once_with([("abc", "succeeded", False)])
    fulfillment.enqueue_payment.assert_awaited_once_with("abc")
    cryptopay.find_payment_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_payment_method_is_skipped(checker_and_mocks):
    checker, repo, yookassa, cryptopay, fulfillment, sync_service = checker_and_mocks
    repo.get_unconfirmed.return_value = [make_payment("1", "unknown")]

    await checker.check_and_update_payment_status()

    repo.update_status_batch.assert_not_awaited()
    fulfillment.enqueue_payment.assert_not_awaited()
    yookassa.find_payment_status.assert_not_awaited()
    cryptopay.find_payment_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_unconfirmed_payments_returns_early(checker_and_mocks):
    checker, repo, yookassa, cryptopay, fulfillment, sync_service = checker_and_mocks
    repo.get_unconfirmed.return_value = []

    await checker.check_and_update_payment_status()

    repo.update_status_batch.assert_not_awaited()
    fulfillment.enqueue_payment.assert_not_awaited()
    yookassa.find_payment_status.assert_not_awaited()
    cryptopay.find_payment_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_payment_failure_does_not_block_other_updates(checker_and_mocks):
    checker, repo, yookassa, cryptopay, fulfillment, sync_service = checker_and_mocks
    repo.get_unconfirmed.return_value = [
        make_payment("1", "cryptopay"),
        make_payment("2", "yookassa"),
    ]
    cryptopay.find_payment_status.side_effect = Exception("API error")
    yookassa.find_payment_status.return_value = "succeeded"

    await checker.check_and_update_payment_status()

    repo.update_status_batch.assert_awaited_once_with([("2", "succeeded", False)])
    fulfillment.enqueue_payment.assert_awaited_once_with("2")


@pytest.mark.asyncio
async def test_empty_provider_status_is_skipped_without_updates(checker_and_mocks):
    checker, repo, yookassa, cryptopay, fulfillment, sync_service = checker_and_mocks
    repo.get_unconfirmed.return_value = [make_payment("abc", "yookassa")]
    yookassa.find_payment_status.return_value = None

    await checker.check_and_update_payment_status()

    repo.update_status_batch.assert_not_awaited()
    fulfillment.enqueue_payment.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_unpaid_payment_is_marked_canceled_without_polling(checker_and_mocks):
    checker, repo, yookassa, cryptopay, fulfillment, sync_service = checker_and_mocks
    eight_days_ago_ms = int(time.time() * 1000) - (8 * 24 * 60 * 60 * 1000)
    repo.get_unconfirmed.return_value = [
        make_payment("old-unpaid-1", "yookassa", created_at=eight_days_ago_ms)
    ]

    await checker.check_and_update_payment_status()

    repo.update_status_batch.assert_awaited_once_with([("old-unpaid-1", "canceled", False)])
    fulfillment.enqueue_payment.assert_not_awaited()
    yookassa.find_payment_status.assert_not_awaited()
    cryptopay.find_payment_status.assert_not_awaited()
