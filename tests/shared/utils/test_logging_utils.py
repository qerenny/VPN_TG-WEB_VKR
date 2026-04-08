import logging

from shared.utils import logging_utils


def setup_function():
    logging_utils._throttled_log_timestamps.clear()


def test_should_downgrade_stdlib_record_for_transient_aiohttp_errors():
    record = logging.LogRecord(
        name="telebot",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="Aiohttp ClientError: ServerDisconnectedError",
        args=(),
        exc_info=None,
    )

    assert logging_utils._should_downgrade_stdlib_record(record) is True


def test_should_downgrade_stdlib_record_for_telegram_getupdates_timeout():
    record = logging.LogRecord(
        name="telebot",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg=(
            "Unhandled exception (full traceback for debug level): Request timeout. "
            "Request: method=get url=getUpdates params=<aiohttp.formdata.FormData object> "
            "files=None request_timeout=60"
        ),
        args=(),
        exc_info=None,
    )

    assert logging_utils._should_downgrade_stdlib_record(record) is True


def test_should_not_downgrade_regular_error_record():
    record = logging.LogRecord(
        name="telegram_bot.services.payments.payment_fulfillment_service",
        level=logging.ERROR,
        pathname=__file__,
        lineno=25,
        msg="Payment fulfillment worker iteration failed: RedisClientError('boom')",
        args=(),
        exc_info=None,
    )

    assert logging_utils._should_downgrade_stdlib_record(record) is False


def test_log_with_throttle_suppresses_repeated_messages(monkeypatch):
    logged = []
    monkeypatch.setattr(
        logging_utils.logger,
        "log",
        lambda level, message: logged.append((level, message)),
    )

    assert logging_utils.log_with_throttle("ERROR", "same-key", "first", cooldown_seconds=60)
    assert not logging_utils.log_with_throttle("ERROR", "same-key", "second", cooldown_seconds=60)
    assert logged == [("ERROR", "first")]


def test_log_with_throttle_allows_logging_after_cooldown(monkeypatch):
    moments = iter([100.0, 161.0])
    logged = []
    monkeypatch.setattr(logging_utils.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(
        logging_utils.logger,
        "log",
        lambda level, message: logged.append((level, message)),
    )

    assert logging_utils.log_with_throttle("WARNING", "same-key", "first", cooldown_seconds=60)
    assert logging_utils.log_with_throttle("WARNING", "same-key", "second", cooldown_seconds=60)
    assert logged == [("WARNING", "first"), ("WARNING", "second")]
