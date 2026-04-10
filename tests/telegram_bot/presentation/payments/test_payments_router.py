from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.presentation.payments.payments_router import PRODUCTS, register_payments_routes


class DummyBot:
    def __init__(self):
        self.send_message = AsyncMock()
        self.delete_message = AsyncMock()
        self.answer_callback_query = AsyncMock()
        self.registered = []

    def callback_query_handler(self, *args, **kwargs):
        def decorator(func):
            self.registered.append(func)
            return func

        return decorator


@pytest.fixture
def bot_patch():
    bot = DummyBot()
    with patch("telegram_bot.presentation.payments.payments_router.bot", bot):
        yield bot


@pytest.mark.asyncio
async def test_register_routes_and_callbacks(bot_patch):
    handler = AsyncMock()
    bot_patch.send_message.return_value = SimpleNamespace(message_id=91)

    register_payments_routes(handler)
    assert len(bot_patch.registered) == 1
    pay_cb = bot_patch.registered[0]

    pay_call = SimpleNamespace(
        id="i", data="pay_method:external_card:month1", message=SimpleNamespace(chat=SimpleNamespace(id=1))
    )
    await pay_cb(pay_call)
    bot_patch.answer_callback_query.assert_awaited_once_with("i")
    handler.initiate_payment.assert_awaited_once_with(pay_call.message, PRODUCTS["month1"], "external_card")
    bot_patch.delete_message.assert_awaited_once_with(chat_id=1, message_id=91)


@pytest.mark.asyncio
async def test_register_routes_supports_traffic_limited_products(bot_patch):
    handler = AsyncMock()
    bot_patch.send_message.return_value = SimpleNamespace(message_id=92)

    register_payments_routes(handler)
    pay_cb = bot_patch.registered[0]

    pay_call = SimpleNamespace(
        id="i",
        data="pay_method:external_wallet:traffic_limited15gb",
        message=SimpleNamespace(chat=SimpleNamespace(id=1)),
    )
    await pay_cb(pay_call)

    handler.initiate_payment.assert_awaited_once_with(
        pay_call.message,
        PRODUCTS["traffic_limited15gb"],
        "external_wallet",
    )
    bot_patch.delete_message.assert_awaited_once_with(chat_id=1, message_id=92)


@pytest.mark.asyncio
async def test_payments_router_invalid_format(bot_patch):
    handler = AsyncMock()

    register_payments_routes(handler)
    pay_cb = bot_patch.registered[0]
    bad_call = SimpleNamespace(id="x", data="bad", message=SimpleNamespace(chat=SimpleNamespace(id=2)))
    await pay_cb(bad_call)
    bot_patch.send_message.assert_awaited_with(2, "Неверный формат выбора оплаты.")


@pytest.mark.asyncio
async def test_payments_router_unknown_product(bot_patch):
    handler = AsyncMock()

    register_payments_routes(handler)
    pay_cb = bot_patch.registered[0]
    call = SimpleNamespace(
        id="x", data="pay_method:external_card:unknown", message=SimpleNamespace(chat=SimpleNamespace(id=3))
    )
    await pay_cb(call)
    bot_patch.send_message.assert_awaited_with(3, "Ошибка: продукт не найден.")
