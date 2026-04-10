from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.shared.utils.menu_rendering import render_photo_menu


@pytest.mark.asyncio
async def test_render_photo_menu_falls_back_to_send_message_when_photo_is_empty():
    bot_client = SimpleNamespace(
        send_message=AsyncMock(),
        send_photo=AsyncMock(),
        edit_message_media=AsyncMock(),
    )
    target = SimpleNamespace(chat=SimpleNamespace(id=42))

    await render_photo_menu(
        target=target,
        photo="",
        caption="plain text menu",
        reply_markup=None,
        parse_mode="Markdown",
        bot_client=bot_client,
    )

    bot_client.send_message.assert_awaited_once_with(
        chat_id=42,
        text="plain text menu",
        reply_markup=None,
        parse_mode="Markdown",
    )
    bot_client.send_photo.assert_not_awaited()
    bot_client.edit_message_media.assert_not_awaited()
