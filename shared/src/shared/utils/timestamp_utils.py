import re
from datetime import datetime, timedelta, timezone
from typing import Tuple

import pytz
from dateutil.relativedelta import relativedelta

from shared.utils.logging_utils import log_function_call, setup_logger

logger = setup_logger("utils.timestamp", "utils.log")

EXPIRED = "0 дней"
LESS_THAN_HOUR = "Менее часа"


def ensure_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def datetime_to_legacy_ms(value: datetime | None, *, none_value: int | None = None) -> int | None:
    normalized = ensure_utc_datetime(value)
    if normalized is None:
        return none_value
    return int(normalized.timestamp() * 1000)


def datetime_to_utc_isoformat(value: datetime | None) -> str | None:
    normalized = ensure_utc_datetime(value)
    return normalized.isoformat() if normalized is not None else None


class TimestampUtils:
    def __init__(self):
        self.moscow = pytz.timezone("Europe/Moscow")
        self.milliseconds = 1000

    @log_function_call(logger)
    def str_to_relativedelta(self, period: str) -> relativedelta:
        if not isinstance(period, str) or not period:
            raise ValueError(f"Invalid period format: {period}")

        # Support both "day10" and "10d" style notations
        match = re.fullmatch(r"([a-zA-Z]+)?(\d+)", period)
        if match:
            unit = match.group(1) or "day"
            value = int(match.group(2))
        else:
            match = re.fullmatch(r"(\d+)([a-zA-Z]+)", period)
            if not match:
                raise ValueError(f"Invalid period format: {period}")
            value = int(match.group(1))
            unit = match.group(2)

        unit_map = {
            "day": "days",
            "days": "days",
            "month": "months",
            "months": "months",
            "year": "years",
            "years": "years",
        }

        if unit not in unit_map:
            raise ValueError(f"Unsupported time unit: {unit}")

        return relativedelta(**{unit_map[unit]: value})

    @log_function_call(logger)
    def current_timestamp(self) -> int:
        return int(datetime.now(self.moscow).timestamp() * self.milliseconds)

    @log_function_call(logger)
    def get_timestamp_with_reminder_time(self) -> Tuple[int, int]:
        now = datetime.now(self.moscow)
        return (
            int((now + timedelta(hours=23)).timestamp() * self.milliseconds),
            int((now + timedelta(hours=24)).timestamp() * self.milliseconds),
        )

    @log_function_call(logger)
    def current_time(self) -> datetime:
        return datetime.now(self.moscow)

    @log_function_call(logger)
    def date_to_timestamp(self, date: datetime) -> int:
        return int(date.timestamp() * self.milliseconds)

    @log_function_call(logger)
    def timestamp_to_date(self, timestamp: int) -> datetime:
        return datetime.fromtimestamp(timestamp / self.milliseconds, self.moscow)

    @log_function_call(logger)
    def set_client_date(self, period: str) -> int:
        date = datetime.now(self.moscow) + self.str_to_relativedelta(period)
        logger.info(f"Calculated client date: {date} with period={period}")
        return self.date_to_timestamp(date)

    @log_function_call(logger)
    def update_client_date(self, previous_expiry: int, period: str) -> int:
        expiry_dt = self.timestamp_to_date(previous_expiry)
        now = self.current_time()
        base = now if expiry_dt <= now else expiry_dt
        updated = base + self.str_to_relativedelta(period)
        logger.info(f"Updating client date from {expiry_dt} to {updated} with period={period}")
        return self.date_to_timestamp(updated)

    @log_function_call(logger)
    def get_word_form(self, number: int, forms: Tuple[str, str, str]) -> str:
        n = abs(number) % 100
        n1 = n % 10
        if 10 < n < 20:
            return forms[2]
        if n1 == 1:
            return forms[0]
        if 2 <= n1 <= 4:
            return forms[1]
        return forms[2]

    @log_function_call(logger)
    def calculate_time_difference(self, user_ts: int) -> str:
        user_date = self.timestamp_to_date(user_ts)
        now = self.current_time()

        if user_date < now:
            return EXPIRED

        diff = relativedelta(user_date, now)
        parts = []

        if diff.years:
            parts.append(f"{diff.years} {self.get_word_form(diff.years, ('год', 'года', 'лет'))}")
        if diff.months:
            parts.append(f"{diff.months} {self.get_word_form(diff.months, ('месяц', 'месяца', 'месяцев'))}")
        if diff.days:
            parts.append(f"{diff.days} {self.get_word_form(diff.days, ('день', 'дня', 'дней'))}")
        if diff.hours:
            parts.append(f"{diff.hours} {self.get_word_form(diff.hours, ('час', 'часа', 'часов'))}")

        logger.info(f"Calculated time difference: {parts} for timestamp={user_ts}")
        return ", ".join(parts) if parts else LESS_THAN_HOUR
