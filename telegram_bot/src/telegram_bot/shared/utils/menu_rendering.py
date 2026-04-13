from __future__ import annotations

from telebot.types import CallbackQuery, InlineKeyboardMarkup, InputMediaPhoto, Message

from telegram_bot.bot import bot


MENU_LOADING_TEXT = "Загружаем..."
_CHAT_MENU_MESSAGE_IDS: dict[int, int] = {}


def _remember_menu_message(chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    _CHAT_MENU_MESSAGE_IDS[int(chat_id)] = int(message_id)


def get_menu_message_id(chat_id: int) -> int | None:
    return _CHAT_MENU_MESSAGE_IDS.get(int(chat_id))


async def render_photo_menu(
    *,
    target: Message | CallbackQuery,
    photo: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "Markdown",
    force_new: bool = False,
    bot_client=bot,
):
    source_message = getattr(target, "message", None)
    target_message = source_message or target
    chat_id = int(target_message.chat.id)
    candidate_message_ids: list[int] = []
    if not force_new and source_message is not None and getattr(source_message, "message_id", None) is not None:
        candidate_message_ids.append(int(source_message.message_id))
    stored_message_id = get_menu_message_id(chat_id)
    if not force_new and stored_message_id is not None and stored_message_id not in candidate_message_ids:
        candidate_message_ids.append(int(stored_message_id))

    if not str(photo or "").strip():
        for message_id in candidate_message_ids:
            try:
                await bot_client.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=caption,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
                _remember_menu_message(chat_id, message_id)
                return
            except Exception:
                pass

        message = await bot_client.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        _remember_menu_message(chat_id, getattr(message, "message_id", None))
        return

    for message_id in candidate_message_ids:
        try:
            await bot_client.edit_message_media(
                media=InputMediaPhoto(
                    media=photo,
                    caption=caption,
                    parse_mode=parse_mode,
                ),
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
            )
            _remember_menu_message(chat_id, message_id)
            return
        except Exception:
            pass

    message = await bot_client.send_photo(
        chat_id=chat_id,
        photo=photo,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    _remember_menu_message(chat_id, getattr(message, "message_id", None))


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
