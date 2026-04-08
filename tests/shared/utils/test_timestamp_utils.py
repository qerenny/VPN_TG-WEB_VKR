from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import pytz
from dateutil.relativedelta import relativedelta

from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.shared.config.navigation import EXPIRED, LESS_THAN_HOUR


MOSCOW = pytz.timezone("Europe/Moscow")
FROZEN_NOW = datetime(2025, 1, 1, 10, 0, 0)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FROZEN_NOW
        return tz.localize(FROZEN_NOW)


@pytest.fixture
def utils() -> TimestampUtils:
    return TimestampUtils()


@pytest.fixture
def frozen_time():
    with patch("shared.utils.timestamp_utils.datetime", FrozenDateTime):
        yield


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("day10", relativedelta(days=10)),
        ("month3", relativedelta(months=3)),
        ("year2", relativedelta(years=2)),
        ("10", relativedelta(days=10)),
    ],
)
def test_str_to_relativedelta_supports_current_formats(utils, period, expected):
    assert utils.str_to_relativedelta(period) == expected


@pytest.mark.parametrize("period", ["", "abc", "123abc"])
def test_str_to_relativedelta_rejects_invalid_formats(utils, period):
    with pytest.raises(ValueError):
        utils.str_to_relativedelta(period)


def test_current_timestamp_uses_moscow_timezone(utils, frozen_time):
    expected = int(MOSCOW.localize(FROZEN_NOW).timestamp() * 1000)

    assert utils.current_timestamp() == expected


def test_get_timestamp_with_reminder_time_returns_next_23_and_24_hours(utils, frozen_time):
    ts_23h, ts_24h = utils.get_timestamp_with_reminder_time()
    base = MOSCOW.localize(FROZEN_NOW)

    assert ts_23h == int((base + timedelta(hours=23)).timestamp() * 1000)
    assert ts_24h == int((base + timedelta(hours=24)).timestamp() * 1000)


def test_date_to_timestamp_and_back(utils):
    current = MOSCOW.localize(datetime(2025, 1, 1, 10, 0))

    timestamp = utils.date_to_timestamp(current)
    restored = utils.timestamp_to_date(timestamp)

    assert abs((restored - current).total_seconds()) < 1


def test_set_client_date_uses_current_time(utils, frozen_time):
    expected = int(MOSCOW.localize(datetime(2025, 1, 4, 10, 0)).timestamp() * 1000)

    assert utils.set_client_date("day3") == expected


def test_update_client_date_resets_from_now_when_subscription_expired(utils, frozen_time):
    expired_timestamp = int(MOSCOW.localize(datetime(2024, 12, 25, 10, 0)).timestamp() * 1000)
    expected = int(MOSCOW.localize(datetime(2025, 1, 4, 10, 0)).timestamp() * 1000)

    assert utils.update_client_date(expired_timestamp, "day3") == expected


def test_update_client_date_extends_active_subscription(utils, frozen_time):
    active_timestamp = int(MOSCOW.localize(datetime(2025, 1, 5, 10, 0)).timestamp() * 1000)
    expected = int(MOSCOW.localize(datetime(2025, 1, 8, 10, 0)).timestamp() * 1000)

    assert utils.update_client_date(active_timestamp, "day3") == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1, "день"),
        (2, "дня"),
        (5, "дней"),
        (21, "день"),
    ],
)
def test_get_word_form_handles_core_pluralization_cases(utils, number, expected):
    assert utils.get_word_form(number, ("день", "дня", "дней")) == expected


def test_calculate_time_difference_returns_expired_for_past_dates(utils, frozen_time):
    past_timestamp = int(MOSCOW.localize(datetime(2024, 12, 31, 10, 0)).timestamp() * 1000)

    assert utils.calculate_time_difference(past_timestamp) == EXPIRED


def test_calculate_time_difference_returns_less_than_hour(utils, frozen_time):
    timestamp = int(MOSCOW.localize(datetime(2025, 1, 1, 10, 30)).timestamp() * 1000)

    assert utils.calculate_time_difference(timestamp) == LESS_THAN_HOUR


def test_calculate_time_difference_builds_human_readable_delta(utils, frozen_time):
    target = MOSCOW.localize(datetime(2026, 2, 2, 15, 0))

    result = utils.calculate_time_difference(int(target.timestamp() * 1000))

    assert all(part in result for part in ("1 год", "1 месяц", "1 день", "5 часов"))
