import asyncio
import inspect
from pathlib import Path

from shared.config.settings import get_effective_product_feature_settings, load_settings
from shared.utils.logging_utils import logger
from telegram_bot.bootstrap import TelegramBotApp, build_bot_app
from telegram_bot.presentation.admin.admin_router import register_admin_routes
from telegram_bot.presentation.payments.payments_router import register_payments_routes
from telegram_bot.presentation.referrals.referrals_router import register_referrals_routes
from telegram_bot.presentation.start.start_router import register_start_routes
from telegram_bot.presentation.subscriptions.subscription_router import register_subscription_routes
from telegram_bot.presentation.subscriptions.promo_router import register_promo_routes


POLLING_RETRY_BASE_DELAY_SECONDS = 3
POLLING_RETRY_MAX_DELAY_SECONDS = 60
POLLING_TIMEOUT_SECONDS = 20
POLLING_REQUEST_TIMEOUT_SECONDS = 60
TELEGRAM_READY_MARKER_PATH = Path("/tmp/telegram-bot-ready")
POLLING_TRANSIENT_ERROR_MARKERS = (
    "timed out",
    "timeout",
    "server disconnected",
    "connection reset",
    "network is unreachable",
    "temporary failure",
    "temporarily unavailable",
)


def _is_transient_polling_error(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return True

    error_type = type(error).__name__.lower()
    if error_type in {
        "serverdisconnectederror",
        "clientconnectionerror",
        "clientconnectorerror",
        "clientoserror",
    }:
        return True

    message = str(error).lower()
    return any(marker in message for marker in POLLING_TRANSIENT_ERROR_MARKERS)


async def _run_polling_with_backoff(bot_instance) -> None:
    retry_delay = POLLING_RETRY_BASE_DELAY_SECONDS

    while True:
        try:
            logger.info("Start polling bot_fun...")
            await bot_instance.infinity_polling(
                timeout=POLLING_TIMEOUT_SECONDS,
                request_timeout=POLLING_REQUEST_TIMEOUT_SECONDS,
            )
            logger.warning(
                "Telegram polling stopped without exception. Restarting in "
                f"{POLLING_RETRY_BASE_DELAY_SECONDS}s."
            )
            await asyncio.sleep(POLLING_RETRY_BASE_DELAY_SECONDS)
            retry_delay = POLLING_RETRY_BASE_DELAY_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not _is_transient_polling_error(error):
                raise

            logger.warning(
                f"Transient Telegram polling error: {error}. "
                f"Restarting in {retry_delay}s."
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, POLLING_RETRY_MAX_DELAY_SECONDS)


def _mark_telegram_ready(is_ready: bool) -> None:
    if is_ready:
        TELEGRAM_READY_MARKER_PATH.write_text("ready\n", encoding="utf-8")
        return

    try:
        TELEGRAM_READY_MARKER_PATH.unlink()
    except FileNotFoundError:
        pass


async def _wait_for_telegram_api(bot_instance) -> None:
    retry_delay = POLLING_RETRY_BASE_DELAY_SECONDS

    while True:
        try:
            me = bot_instance.get_me()
            if inspect.isawaitable(me):
                me = await me
            _mark_telegram_ready(True)
            logger.info(
                f"Telegram API is reachable. Bot username={getattr(me, 'username', None)}."
            )
            return
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not _is_transient_polling_error(error):
                raise

            logger.warning(
                f"Telegram API is not reachable yet: {error}. "
                f"Retrying in {retry_delay}s."
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, POLLING_RETRY_MAX_DELAY_SECONDS)


async def _run_disabled_bot_runtime() -> None:
    logger.info("Telegram bot runtime is disabled by product settings. Container will stay idle.")
    _mark_telegram_ready(True)
    try:
        await asyncio.Event().wait()
    finally:
        _mark_telegram_ready(False)


async def run_bot(app: TelegramBotApp) -> None:
    logger.info("Connecting to external services...")
    features = get_effective_product_feature_settings()
    if not features.telegram_bot_enabled:
        await _run_disabled_bot_runtime()
        return

    register_start_routes(
        app.start_handler,
        app.profile_handler,
        app.support_handler,
        app.instructions_handler,
    )
    traffic_limited_config_enabled = getattr(
        getattr(app, "subscription_menu_handler", None),
        "traffic_limited_config_enabled",
        getattr(features, "traffic_limited_config_enabled", True),
    )
    if not isinstance(traffic_limited_config_enabled, bool):
        traffic_limited_config_enabled = getattr(
            features,
            "traffic_limited_config_enabled",
            True,
        )

    subscription_route_kwargs = {
        "commerce_enabled": features.commerce_enabled,
        "standard_config_enabled": getattr(features, "standard_config_enabled", True),
        "traffic_limited_config_enabled": traffic_limited_config_enabled,
    }
    register_subscription_routes(
        app.payment_command_handler,
        app.subscription_menu_handler,
        app.subscription_access_request_handler,
        app.subscription_trial_handler,
        app.subscription_info_channel_handler,
        access_requests_enabled=getattr(features, "access_requests_enabled", False),
        **subscription_route_kwargs,
    )
    if features.promos_enabled:
        register_promo_routes(app.subscription_promo_handler)
    else:
        logger.info("Promo Telegram routes are disabled by product settings.")
    if features.referrals_enabled:
        register_referrals_routes(app.referral_menu_handler)
    else:
        logger.info("Referral Telegram routes are disabled by product settings.")
    register_admin_routes(app.admin_command_handler)
    if features.commerce_enabled:
        register_payments_routes(app.payment_command_handler)
    else:
        logger.info("Payment Telegram routes are disabled by product settings.")

    logger.info("All services are connected.")
    _mark_telegram_ready(False)
    await _wait_for_telegram_api(app.bot)

    logger.info("Start of background tasks...")
    reminder_scheduler_task = asyncio.create_task(app.reminder_service.run_scheduler())
    reminder_worker_task = asyncio.create_task(app.reminder_service.run_worker())
    access_lifecycle_task = None
    if getattr(features, "standard_config_enabled", True) or traffic_limited_config_enabled:
        access_lifecycle_task = asyncio.create_task(app.access_lifecycle_service.run_scheduler())
    else:
        logger.info("Access lifecycle scheduler is disabled because all access modules are off.")
    traffic_limited_sync_task = None
    if traffic_limited_config_enabled:
        traffic_limited_sync_task = asyncio.create_task(
            app.traffic_limited_sync_service.run_scheduler()
        )
    else:
        logger.info("Traffic-limited configuration sync is disabled by product settings.")
    payment_tasks: list[asyncio.Task] = []
    if features.commerce_enabled:
        payment_tasks = [
            asyncio.create_task(app.payment_status_checker.run_scheduler()),
            asyncio.create_task(app.payment_fulfillment_service.run_scheduler()),
            asyncio.create_task(app.payment_fulfillment_service.run_worker()),
        ]
    else:
        logger.info("Payment background workers are disabled by product settings.")

    try:
        await _run_polling_with_backoff(app.bot)
    finally:
        _mark_telegram_ready(False)
        reminder_scheduler_task.cancel()
        reminder_worker_task.cancel()
        if access_lifecycle_task is not None:
            access_lifecycle_task.cancel()
        if traffic_limited_sync_task is not None:
            traffic_limited_sync_task.cancel()
        for task in payment_tasks:
            task.cancel()
        await asyncio.gather(
            reminder_scheduler_task,
            reminder_worker_task,
            *([access_lifecycle_task] if access_lifecycle_task is not None else []),
            *([traffic_limited_sync_task] if traffic_limited_sync_task is not None else []),
            *payment_tasks,
            return_exceptions=True,
        )
        await app.reminder_service.shutdown()
        await app.payment_fulfillment_service.shutdown()
        if access_lifecycle_task is not None:
            await app.access_lifecycle_service.shutdown()


def main():
    logger.info("Bot entrypoint started.")
    settings = load_settings()
    features = get_effective_product_feature_settings()

    try:
        if not features.telegram_bot_enabled:
            asyncio.run(_run_disabled_bot_runtime())
        else:
            app = build_bot_app(settings)
            asyncio.run(run_bot(app))
    except KeyboardInterrupt:
        logger.info("Bot is stopped by User.")
    except Exception as e:
        logger.error(f"Critical error in main: {str(e)}")
        raise

    logger.info("The bot has completed its work correctly.")


if __name__ == "__main__":
    main()
