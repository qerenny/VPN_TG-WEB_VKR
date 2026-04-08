from __future__ import annotations

from telebot.types import CallbackQuery, InlineKeyboardMarkup, InputMediaPhoto, Message

from telegram_bot.bot import bot


MENU_LOADING_TEXT = "Загружаем..."


async def render_photo_menu(
    *,
    target: Message | CallbackQuery,
    photo: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "Markdown",
    bot_client=bot,
):
    source_message = getattr(target, "message", None)
    if source_message is not None:
        if getattr(source_message, "message_id", None) is not None:
            try:
                await bot_client.edit_message_media(
                    media=InputMediaPhoto(
                        media=photo,
                        caption=caption,
                        parse_mode=parse_mode,
                    ),
                    chat_id=source_message.chat.id,
                    message_id=source_message.message_id,
                    reply_markup=reply_markup,
                )
                return
            except Exception:
                pass

        target = source_message

    await bot_client.send_photo(
        chat_id=target.chat.id,
        photo=photo,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )


async def send_loading_message(chat_id: int, *, text: str = MENU_LOADING_TEXT, bot_client=bot) -> int | None:
    try:
        message = await bot_client.send_message(chat_id=chat_id, text=text)
        return getattr(message, "message_id", None)
    except Exception:
        return None


async def dismiss_loading_message(chat_id: int, message_id: int | None, *, bot_client=bot) -> None:
    if message_id is None:
        return
    try:
        await bot_client.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass
