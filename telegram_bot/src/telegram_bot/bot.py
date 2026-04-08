import asyncio
from functools import wraps
import os
from urllib.parse import urlparse

from telebot import apihelper, asyncio_helper
from telebot.apihelper import ApiTelegramException
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_handler_backends import BaseMiddleware, CancelUpdate
from telebot.types import CallbackQuery, Message

from shared.config.config import (
    BOT_ADMIN_IDS,
    BOT_API,
    BOT_MAINTENANCE_MESSAGE,
    BOT_MAINTENANCE_MODE,
)
from shared.utils.context import chat_id_var, user_id_var, username_var
from shared.utils.logging_utils import logger

TELEGRAM_API_CONNECT_TIMEOUT_SECONDS = 20
TELEGRAM_API_REQUEST_TIMEOUT_SECONDS = 60
TELEGRAM_API_TRANSIENT_RETRIES = 2
TELEGRAM_API_TRANSIENT_RETRY_DELAY_SECONDS = 1
SUPPORTED_TELEGRAM_PROXY_SCHEMES = {"http", "https"}
CALLBACK_QUERY_EXPIRED_ERROR_MARKERS = (
    "query is too old",
    "query id is invalid",
    "response timeout expired",
)
TRANSIENT_TELEGRAM_ERROR_MARKERS = (
    "request timeout",
    "timed out",
    "timeout",
    "clientconnectorerror",
    "server disconnected",
    "connection reset",
    "temporarily unavailable",
    "temporary failure",
)


class ContextMiddleware(BaseMiddleware):
    def __init__(self):
        self.update_types = ["message", "callback_query"]

    async def pre_process(self, update, data):
        if isinstance(update, Message):
            if update.chat:
                chat_id_var.set(update.chat.id)
            if update.from_user:
                user_id_var.set(update.from_user.id)
                username_var.set(update.from_user.username)
        elif isinstance(update, CallbackQuery):
            if update.message and update.message.chat:
                chat_id_var.set(update.message.chat.id)
            if update.from_user:
                user_id_var.set(update.from_user.id)
                username_var.set(update.from_user.username)

    async def post_process(self, update, data, exception):
        pass


class MaintenanceModeMiddleware(BaseMiddleware):
    def __init__(self, bot_instance: AsyncTeleBot):
        self.bot = bot_instance
        self.update_types = ["message", "callback_query"]

    @staticmethod
    def _is_admin(update) -> bool:
        user_id = getattr(getattr(update, "from_user", None), "id", None)
        chat_id = getattr(getattr(update, "chat", None), "id", None)
        callback_chat_id = getattr(
            getattr(getattr(update, "message", None), "chat", None),
            "id",
            None,
        )
        return any(candidate in BOT_ADMIN_IDS for candidate in (user_id, chat_id, callback_chat_id))

    async def pre_process(self, update, data):
        if not BOT_MAINTENANCE_MODE or self._is_admin(update):
            return None

        if isinstance(update, CallbackQuery):
            await self.bot.answer_callback_query(
                callback_query_id=update.id,
                text=BOT_MAINTENANCE_MESSAGE[:190],
                show_alert=True,
            )
            return CancelUpdate()

        if isinstance(update, Message) and update.chat:
            await self.bot.send_message(
                chat_id=update.chat.id,
                text=BOT_MAINTENANCE_MESSAGE,
            )
            return CancelUpdate()

        return None

    async def post_process(self, update, data, exception):
        pass


def _configure_telegram_api_timeouts() -> None:
    asyncio_helper.CONNECT_TIMEOUT = TELEGRAM_API_CONNECT_TIMEOUT_SECONDS
    asyncio_helper.READ_TIMEOUT = TELEGRAM_API_REQUEST_TIMEOUT_SECONDS
    asyncio_helper.REQUEST_TIMEOUT = TELEGRAM_API_REQUEST_TIMEOUT_SECONDS


def _set_telegram_proxy(raw_proxy: str | None, *, log_reason: str | None = None) -> None:
    if not raw_proxy:
        asyncio_helper.proxy = None
        apihelper.proxy = None
        if log_reason:
            logger.warning(log_reason)
        return

    scheme = urlparse(raw_proxy).scheme.lower()
    if scheme not in SUPPORTED_TELEGRAM_PROXY_SCHEMES:
        raise ValueError(
            "Unsupported TELEGRAM_PROXY_URL scheme. Use http://... or https://... . "
            "Direct vless:// links are not supported by the Telegram aiohttp client; "
            "expose an HTTP proxy inbound on your Xray host and point TELEGRAM_PROXY_URL to it."
        )

    asyncio_helper.proxy = raw_proxy
    apihelper.proxy = raw_proxy
    if log_reason:
        logger.warning(log_reason)
    else:
        logger.info("Telegram API proxy is configured.")


def get_configured_telegram_proxy() -> str:
    return os.getenv("TELEGRAM_PROXY_URL", "").strip()


def _configure_telegram_proxy() -> None:
    _set_telegram_proxy(get_configured_telegram_proxy() or None)


def _is_expired_callback_query_error(error: ApiTelegramException) -> bool:
    description = str(getattr(error, "description", "")).lower()
    return error.error_code == 400 and any(
        marker in description for marker in CALLBACK_QUERY_EXPIRED_ERROR_MARKERS
    )


def _is_transient_telegram_error(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return True

    error_type = type(error).__name__.lower()
    if error_type in {
        "requesttimeout",
        "serverdisconnectederror",
        "clientconnectionerror",
        "clientconnectorerror",
        "clientoserror",
    }:
        return True

    message = str(error).lower()
    return any(marker in message for marker in TRANSIENT_TELEGRAM_ERROR_MARKERS)


def _wrap_transient_retry(bot_instance: AsyncTeleBot, method_name: str) -> None:
    original_method = getattr(bot_instance, method_name)

    @wraps(original_method)
    async def wrapped(*args, **kwargs):
        last_error: Exception | None = None

        for attempt in range(1, TELEGRAM_API_TRANSIENT_RETRIES + 1):
            try:
                return await original_method(*args, **kwargs)
            except Exception as error:
                if not _is_transient_telegram_error(error):
                    raise

                last_error = error
                if attempt >= TELEGRAM_API_TRANSIENT_RETRIES:
                    raise

                logger.warning(
                    f"Transient Telegram API error during {method_name}; "
                    f"retrying {attempt}/{TELEGRAM_API_TRANSIENT_RETRIES - 1}: {error}"
                )
                await asyncio.sleep(TELEGRAM_API_TRANSIENT_RETRY_DELAY_SECONDS)

        raise last_error  # pragma: no cover

    setattr(bot_instance, method_name, wrapped)


def _wrap_answer_callback_query(bot_instance: AsyncTeleBot) -> None:
    original_method = bot_instance.answer_callback_query

    @wraps(original_method)
    async def safe_answer_callback_query(*args, **kwargs):
        for attempt in range(1, TELEGRAM_API_TRANSIENT_RETRIES + 1):
            try:
                return await original_method(*args, **kwargs)
            except ApiTelegramException as error:
                if _is_expired_callback_query_error(error):
                    callback_query_id = kwargs.get("callback_query_id")
                    if callback_query_id is None and args:
                        callback_query_id = args[0]

                    logger.info(
                        "Ignoring expired Telegram callback query response: "
                        f"callback_query_id={callback_query_id}, error={error.description}"
                    )
                    return None
                if not _is_transient_telegram_error(error) or attempt >= TELEGRAM_API_TRANSIENT_RETRIES:
                    raise
                logger.warning(
                    f"Transient Telegram API error during answer_callback_query; "
                    f"retrying {attempt}/{TELEGRAM_API_TRANSIENT_RETRIES - 1}: {error}"
                )
                await asyncio.sleep(TELEGRAM_API_TRANSIENT_RETRY_DELAY_SECONDS)
            except Exception as error:
                if not _is_transient_telegram_error(error) or attempt >= TELEGRAM_API_TRANSIENT_RETRIES:
                    raise
                logger.warning(
                    f"Transient Telegram API error during answer_callback_query; "
                    f"retrying {attempt}/{TELEGRAM_API_TRANSIENT_RETRIES - 1}: {error}"
                )
                await asyncio.sleep(TELEGRAM_API_TRANSIENT_RETRY_DELAY_SECONDS)

    bot_instance.answer_callback_query = safe_answer_callback_query


def build_bot() -> AsyncTeleBot:
    logger.info("Building new Telegram Bot instance...")
    _configure_telegram_api_timeouts()
    _configure_telegram_proxy()
    bot_instance = AsyncTeleBot(BOT_API)
    for method_name in ("send_message", "send_photo", "edit_message_media"):
        _wrap_transient_retry(bot_instance, method_name)
    _wrap_answer_callback_query(bot_instance)
    bot_instance.setup_middleware(ContextMiddleware())
    bot_instance.setup_middleware(MaintenanceModeMiddleware(bot_instance))
    return bot_instance


bot = build_bot()
