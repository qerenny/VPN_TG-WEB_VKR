from unittest.mock import AsyncMock

import pytest
from telebot.types import Chat

from telegram_bot.presentation.start import start_router

register_start_routes = start_router.register_start_routes


class MockBot:
    def __init__(self):
        self.callback_query_handlers = []
        self.message_handlers = []
        self.answered = []

    def callback_query_handler(self, func):
        def decorator(handler):
            self.callback_query_handlers.append((func, handler))
            return handler

        return decorator

    def message_handler(self, commands=None):
        def decorator(handler):
            self.message_handlers.append((commands, handler))
            return handler

        return decorator

    async def answer_callback_query(self, cid):
        self.answered.append(cid)


@pytest.fixture
def bot(monkeypatch):
    mock = MockBot()
    monkeypatch.setattr(start_router, "bot", mock)
    return mock


class FakeMessage:
    def __init__(self, chat_id):
        self.chat = Chat(id=chat_id, type="private")


class FakeCallback:
    def __init__(self, data, chat_id=1, cid=1):
        self.id = cid
        self.data = data
        self.message = FakeMessage(chat_id)


@pytest.mark.asyncio
async def test_register_and_handle_callbacks(bot):
    start = AsyncMock()
    profile = AsyncMock()
    support = AsyncMock()
    instructions = AsyncMock()

    register_start_routes(start, profile, support, instructions)

    filter_func, handler = bot.callback_query_handlers[0]
    assert filter_func(FakeCallback("menu_start"))
    assert not filter_func(FakeCallback("other"))

    cb = FakeCallback("menu_help")
    await handler(cb)
    support.show.assert_awaited_once_with(cb)
    assert bot.answered == [cb.id]

    cb = FakeCallback("menu_profile")
    await handler(cb)
    profile.show.assert_awaited_once_with(cb)

    cb = FakeCallback("menu_instructions")
    await handler(cb)
    instructions.show.assert_awaited_once_with(cb)

    cb = FakeCallback("menu_start")
    await handler(cb)
    start.send_main_menu.assert_awaited_with(cb)


@pytest.mark.asyncio
async def test_register_and_handle_start_message(bot):
    start = AsyncMock()
    register_start_routes(start, AsyncMock(), AsyncMock(), AsyncMock())
    commands, handler = bot.message_handlers[0]
    assert commands == ["start"]
    msg = FakeMessage(5)
    await handler(msg)
    start.process_start_command.assert_awaited_once_with(msg)
