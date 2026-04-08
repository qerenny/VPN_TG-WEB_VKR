from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config.config import BOT_RETURN_URL
from shared.migration_support.models.payments.payment_model import Payment
from telegram_bot.presentation.payments.payment_command_handler import PaymentCommandHandler


class DummyBot:
    def __init__(self):
        self.send_message = AsyncMock()
        self.send_photo = AsyncMock()
        self.answer_callback_query = AsyncMock()


@pytest.fixture
def handler_and_mocks():
    gateways = {
        "cryptopay": AsyncMock(),
        "yookassa": AsyncMock(),
    }
    repo = AsyncMock()
    timestamp = MagicMock()
    timestamp.current_timestamp.return_value = 42
    bot = DummyBot()

    with patch(
        "telegram_bot.presentation.payments.payment_command_handler.bot",
        bot,
    ):
        handler = PaymentCommandHandler(
            gateways=gateways,
            repo=repo,
            timestamp=timestamp,
        )
        yield (
            handler,
            repo,
            gateways,
            timestamp,
            bot,
        )


def make_message(chat_id=1):
    return SimpleNamespace(chat=SimpleNamespace(id=chat_id))


@pytest.mark.asyncio
async def test_ask_payment_method_sends_buttons(handler_and_mocks):
    handler, _, _, _, bot = handler_and_mocks
    product = {"label": "Prod", "payload": "pl", "amount": 100}

    await handler.ask_payment_method(make_message(), product)

    bot.send_photo.assert_awaited_once()
    _, kwargs = bot.send_photo.await_args
    assert kwargs["chat_id"] == 1
    assert "Prod" in kwargs["caption"]
    markup = kwargs["reply_markup"]
    rows = markup.keyboard
    assert rows[0][0].callback_data == "pay_method:yookassa:pl"
    assert rows[1][0].callback_data == "pay_method:cryptopay:pl"


@pytest.mark.asyncio
async def test_ask_payment_method_rejects_zero_amount_product(handler_and_mocks):
    handler, _, _, _, bot = handler_and_mocks
    product = {"label": "Prod", "payload": "pl", "amount": 0}

    await handler.ask_payment_method(make_message(), product)

    bot.send_message.assert_awaited_once()
    _, kwargs = bot.send_message.await_args
    assert "Цена для этого продукта пока не настроена" in kwargs["text"]


@pytest.mark.asyncio
async def test_ask_payment_method_supports_paid_whitelist_product(handler_and_mocks):
    handler, _, _, _, bot = handler_and_mocks
    product = {"label": "Лимит трафика 15 GB", "payload": "whitelist15gb", "amount": 9900}

    await handler.ask_payment_method(make_message(), product)

    bot.send_photo.assert_awaited_once()
    _, kwargs = bot.send_photo.await_args
    assert "Лимит трафика 15 GB" in kwargs["caption"]
    markup = kwargs["reply_markup"]
    assert markup.keyboard[0][0].callback_data == "pay_method:yookassa:whitelist15gb"


@pytest.mark.asyncio
async def test_initiate_payment_success(handler_and_mocks):
    handler, repo, gateways, _, bot = handler_and_mocks
    gateways["cryptopay"].create_payment.return_value = {
        "id": "pid",
        "status": "pending",
        "url": "http://pay",
        "confirmed": False,
    }
    product = {"label": "Prod", "payload": "pl"}

    with patch(
        "telegram_bot.presentation.payments.payment_command_handler.messages.get_random_message",
        return_value="txt",
    ):
        await handler.initiate_payment(make_message(), product, "cryptopay")

    gateways["cryptopay"].create_payment.assert_awaited_once_with(
        tg_id=1,
        return_url=BOT_RETURN_URL,
        product=product,
    )
    repo.create.assert_awaited_once()
    created_payment: Payment = repo.create.call_args.args[0]
    assert created_payment.payment_id == "pid"
    assert created_payment.tg_id == 1
    assert created_payment.status == "pending"
    assert created_payment.payload == "pl"
    assert created_payment.method == "cryptopay"
    assert created_payment.created_at == 42
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_initiate_payment_invalid_method(handler_and_mocks):
    handler, _, _, _, _ = handler_and_mocks
    with pytest.raises(ValueError, match="Unsupported payment method: bad"):
        await handler.initiate_payment(make_message(), {"label": "L", "payload": "p"}, "bad")
