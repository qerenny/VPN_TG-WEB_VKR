from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.shared.utils import menu_rendering


class _Message:
    def __init__(self, *, chat_id: int, message_id: int | None = None):
        self.chat = SimpleNamespace(id=chat_id)
        self.message_id = message_id


class _Callback:
    def __init__(self, *, chat_id: int, message_id: int):
        self.message = _Message(chat_id=chat_id, message_id=message_id)


@pytest.mark.asyncio
async def test_render_photo_menu_reuses_stored_message_for_plain_message_target():
    bot_client = SimpleNamespace(
        edit_message_media=AsyncMock(),
        send_photo=AsyncMock(),
        edit_message_text=AsyncMock(),
        send_message=AsyncMock(),
    )
    menu_rendering.clear_menu_message_id(42)
    menu_rendering._remember_menu_message(42, 777)

    await menu_rendering.render_photo_menu(
        target=_Message(chat_id=42, message_id=10),
        photo="photo-id",
        caption="Menu",
        bot_client=bot_client,
    )

    bot_client.edit_message_media.assert_awaited_once()
    _, kwargs = bot_client.edit_message_media.await_args
    assert kwargs["chat_id"] == 42
    assert kwargs["message_id"] == 777
    bot_client.send_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_render_photo_menu_remembers_callback_message_id():
    bot_client = SimpleNamespace(
        edit_message_media=AsyncMock(),
        send_photo=AsyncMock(),
        edit_message_text=AsyncMock(),
        send_message=AsyncMock(),
    )
    menu_rendering.clear_menu_message_id(84)

    await menu_rendering.render_photo_menu(
        target=_Callback(chat_id=84, message_id=123),
        photo="photo-id",
        caption="Menu",
        bot_client=bot_client,
    )

    assert menu_rendering.get_menu_message_id(84) == 123
    bot_client.edit_message_media.assert_awaited_once()


@pytest.mark.asyncio
async def test_render_photo_menu_force_new_sends_new_message():
    bot_client = SimpleNamespace(
        edit_message_media=AsyncMock(),
        send_photo=AsyncMock(return_value=SimpleNamespace(message_id=999)),
        edit_message_text=AsyncMock(),
        send_message=AsyncMock(),
    )
    menu_rendering.clear_menu_message_id(21)
    menu_rendering._remember_menu_message(21, 555)

    await menu_rendering.render_photo_menu(
        target=_Message(chat_id=21, message_id=10),
        photo="photo-id",
        caption="Menu",
        force_new=True,
        bot_client=bot_client,
    )

    bot_client.edit_message_media.assert_not_awaited()
    bot_client.send_photo.assert_awaited_once()
    assert menu_rendering.get_menu_message_id(21) == 999
