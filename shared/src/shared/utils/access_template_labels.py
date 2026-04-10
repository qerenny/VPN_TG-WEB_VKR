ACCESS_TEMPLATE_LABELS = {
    "month_1": "1 месяц · Базовая конфигурация",
    "month_3": "3 месяца · Базовая конфигурация",
    "month_6": "6 месяцев · Базовая конфигурация",
    "year_1": "12 месяцев · Базовая конфигурация",
    "traffic_limited_15gb": "15 GB · Лимит трафика",
    "traffic_limited_35gb": "35 GB · Лимит трафика",
    "traffic_limited_80gb": "80 GB · Лимит трафика",
}

REQUESTABLE_ACCESS_TEMPLATE_CODES = (
    "month_1",
    "month_3",
    "month_6",
    "year_1",
    "traffic_limited_15gb",
    "traffic_limited_35gb",
    "traffic_limited_80gb",
)


def format_access_template_label(template_code: str | None, *, fallback: str = "Не указан") -> str:
    normalized = str(template_code or "").strip().lower()
    if not normalized:
        return fallback
    return ACCESS_TEMPLATE_LABELS.get(normalized, normalized)


def is_requestable_access_template_code(template_code: str | None) -> bool:
    normalized = str(template_code or "").strip().lower()
    return bool(normalized) and normalized in REQUESTABLE_ACCESS_TEMPLATE_CODES
