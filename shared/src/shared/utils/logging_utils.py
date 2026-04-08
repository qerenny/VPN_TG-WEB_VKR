import sys
import logging
import inspect
import asyncio
import time
import traceback
from functools import wraps
from typing import Callable, Any
from datetime import datetime, timezone
from html import escape

from loguru import logger
import sentry_sdk

from shared.config.config import TELEGRAM_LOGGER_TOKEN, TELEGRAM_LOGGER_CHAT_ID, SENTRY_DSN
from shared.utils.context import chat_id_var, user_id_var, username_var
from telebot import TeleBot

# Initialize Sentry
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )


TRANSIENT_AIOHTTP_LOG_MARKERS = (
    "aiohttp clienterror: serverdisconnectederror",
    "aiohttp clienterror: clientoserror",
    "aiohttp clienterror: clientconnectionerror",
    "aiohttp clienterror: clientconnectorerror",
    "request timeout. request: method=get url=getme",
    "request timeout. request: method=get url=getupdates",
    "telebot.asyncio_helper.requesttimeout",
)
_throttled_log_timestamps: dict[str, float] = {}
_telegram_bot: TeleBot | None = None
_TELEGRAM_MESSAGE_LIMIT = 3800


def _should_downgrade_stdlib_record(record: logging.LogRecord) -> bool:
    if record.levelno < logging.ERROR:
        return False

    message = record.getMessage().strip().lower()
    return any(marker in message for marker in TRANSIENT_AIOHTTP_LOG_MARKERS)


def log_with_throttle(
    level: str,
    throttle_key: str,
    message: str,
    cooldown_seconds: float = 300.0,
) -> bool:
    now = time.monotonic()
    last_logged_at = _throttled_log_timestamps.get(throttle_key)
    if last_logged_at is not None and (now - last_logged_at) < cooldown_seconds:
        return False

    _throttled_log_timestamps[throttle_key] = now
    logger.log(level.upper(), message)
    return True


def _get_telegram_bot() -> TeleBot | None:
    global _telegram_bot
    if not (TELEGRAM_LOGGER_TOKEN and TELEGRAM_LOGGER_CHAT_ID):
        return None
    if _telegram_bot is None:
        _telegram_bot = TeleBot(TELEGRAM_LOGGER_TOKEN)
    return _telegram_bot


def _truncate(value: str, limit: int = _TELEGRAM_MESSAGE_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _format_traceback_block(exception_info) -> str:
    if not exception_info:
        return ""

    try:
        formatted = "".join(
            traceback.format_exception(
                exception_info.type,
                exception_info.value,
                exception_info.traceback,
            )
        ).strip()
    except Exception:
        formatted = str(exception_info)

    return _truncate(formatted, limit=1800)


def _format_details_block(details: dict[str, Any] | None) -> str:
    if not details:
        return ""

    rows = []
    for key, value in details.items():
        if value is None or value == "":
            continue
        rows.append(f"{key}: {value}")
    return _truncate("\n".join(rows), limit=1200)


def send_telegram_alert(
    *,
    title: str,
    level: str = "ERROR",
    summary: str,
    details: dict[str, Any] | None = None,
    source: str | None = None,
    traceback_text: str | None = None,
) -> None:
    bot = _get_telegram_bot()
    if bot is None:
        return

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    details_block = _format_details_block(details)
    parts = [
        f"<b>{escape(level.upper())}</b> {escape(title)}",
        f"<b>time:</b> <code>{escape(now_iso)}</code>",
    ]
    if source:
        parts.append(f"<b>source:</b> <code>{escape(source)}</code>")
    parts.append(f"<b>summary:</b>\n<pre>{escape(_truncate(summary, limit=1400))}</pre>")
    if details_block:
        parts.append(f"<b>trace:</b>\n<pre>{escape(details_block)}</pre>")
    if traceback_text:
        parts.append(f"<b>traceback:</b>\n<pre>{escape(_truncate(traceback_text, limit=1400))}</pre>")

    message = _truncate("\n".join(parts))
    try:
        bot.send_message(TELEGRAM_LOGGER_CHAT_ID, message, parse_mode="HTML")
    except Exception:
        pass

class InterceptHandler(logging.Handler):
    """
    Intercept standard logging messages and route them to Loguru.
    """
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        if _should_downgrade_stdlib_record(record):
            level = "WARNING"
        else:
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

def setup_telegram_sink():
    """
    Configures a Loguru sink to send ERROR and CRITICAL logs to Telegram.
    Uses a synchronous TeleBot instance running in a separate thread (via enqueue=True).
    """
    if not (TELEGRAM_LOGGER_TOKEN and TELEGRAM_LOGGER_CHAT_ID):
        return

    def telegram_sink(message):
        try:
            record = message.record
            extra = {
                key: value
                for key, value in record["extra"].items()
                if key not in {"exception", "text"}
            }
            send_telegram_alert(
                title="Application error",
                level=record["level"].name,
                summary=record["message"],
                details={
                    "logger": record["name"],
                    "function": record["function"],
                    "line": record["line"],
                    **extra,
                },
                source=f"{record['name']}:{record['function']}:{record['line']}",
                traceback_text=_format_traceback_block(record["exception"]),
            )
        except Exception:
            # Fail silently to avoid infinite loops or crashing the logger
            pass

    logger.add(telegram_sink, level="ERROR", enqueue=True)

def configure_logger():
    """
    Configures Loguru logger with sinks for stdout, Sentry, and Telegram.
    Intercepts standard library logging.
    """
    # Remove default handler
    logger.remove()

    def context_patcher(record):
        # Inject context variables into extra dict if available
        if "chat_id" not in record["extra"]:
            cid = chat_id_var.get()
            if cid:
                record["extra"]["chat_id"] = cid

        if "user_id" not in record["extra"]:
            uid = user_id_var.get()
            if uid:
                record["extra"]["user_id"] = uid

        if "username" not in record["extra"]:
            uname = username_var.get()
            if uname:
                record["extra"]["username"] = uname

    logger.configure(patcher=context_patcher)

    # Add stdout handler
    logger.add(
        sys.stderr,
        level="INFO",
        enqueue=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level> {extra}"
    )

    # Add Sentry sink
    if SENTRY_DSN:
        def sentry_sink(message):
             record = message.record
             level = record["level"].name
             if level in ["ERROR", "CRITICAL"]:
                 sentry_sdk.capture_message(record["message"], level=level)

        logger.add(sentry_sink, level="ERROR")

    setup_telegram_sink()

    # Intercept standard logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Run configuration immediately
configure_logger()

# ==========================
# Compatibility / Deprecated
# ==========================

def setup_logger(name: str, log_file: str = None) -> Any:
    """
    Deprecated: Returns the configured loguru logger bound with the given name.
    The 'log_file' argument is ignored as we log to stdout/stderr.
    """
    return logger.bind(name=name)

def log_function_call(logger_instance: Any = None) -> Callable:
    """
    Deprecated: No-op decorator to replace the old logging decorator.
    """
    def decorator(func: Callable) -> Callable:
        return func
    return decorator

def retry_on_error(retries: int = 3, delay: int = 5) -> Callable:
    """
    Decorator that retries a function call if an exception occurs.
    """
    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs) -> Any:
                last_exception = None
                for attempt in range(retries):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        logger.warning(f"Attempt {attempt + 1}/{retries} failed for {func.__name__}: {str(e)}")
                        if attempt < retries - 1:
                            await asyncio.sleep(delay)
                logger.opt(exception=last_exception).error(
                    f"All {retries} attempts failed for {func.__name__}. Error: {str(last_exception)}"
                )
                raise last_exception
            return wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                last_exception = None
                for attempt in range(retries):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        logger.warning(f"Attempt {attempt + 1}/{retries} failed for {func.__name__}: {str(e)}")
                        if attempt < retries - 1:
                            time.sleep(delay)
                logger.opt(exception=last_exception).error(
                    f"All {retries} attempts failed for {func.__name__}. Error: {str(last_exception)}"
                )
                raise last_exception
            return wrapper
    return decorator
