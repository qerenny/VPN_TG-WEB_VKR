import yaml
from pathlib import Path
import json
import os
from urllib.parse import urlparse
import ipaddress

CONFIG_OVERRIDE_ENV_VAR = "APP_CONFIG_PATH"
LEGACY_CONFIG_OVERRIDE_ENV_VAR = "NOWMEOW_CONFIG_PATH"


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def find_env_file(
    preferred_name="local_env.yaml",
    pattern="*_env.yaml",
    max_depth=5,
) -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        yaml_files = [candidate for candidate in parent.glob(pattern) if candidate.is_file()]
        legacy_env = parent / "env.yaml"

        if yaml_files:
            # Если среди найденных есть preferred_name — возвращаем его
            for file in yaml_files:
                if file.name == preferred_name:
                    return file

            # Если preferred_name не найден, возвращаем первый попавшийся
            return yaml_files[0]

        # Legacy fallback for old CI/test setups.
        if legacy_env.is_file():
            return legacy_env

        # Ограничение глубины
        max_depth -= 1
        if max_depth == 0:
            break

    raise FileNotFoundError(
        f"No {pattern} or legacy env.yaml found in parent directories."
    )

config_override_env_var = CONFIG_OVERRIDE_ENV_VAR
config_override = os.getenv(CONFIG_OVERRIDE_ENV_VAR, "").strip()
if not config_override:
    config_override_env_var = LEGACY_CONFIG_OVERRIDE_ENV_VAR
    config_override = os.getenv(LEGACY_CONFIG_OVERRIDE_ENV_VAR, "").strip()

if config_override:
    CONFIG_PATH = Path(config_override).expanduser().resolve()
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"{config_override_env_var} points to missing file: {CONFIG_PATH}"
        )
    if not CONFIG_PATH.is_file():
        raise IsADirectoryError(
            f"{config_override_env_var} must point to a file, got: {CONFIG_PATH}"
        )
else:
    CONFIG_PATH = find_env_file()


with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)


def _get_config_section(name: str) -> dict:
    section = config.get(name, {})
    return section if isinstance(section, dict) else {}


def _config_text(section: dict, key: str, default: str) -> str:
    value = section.get(key, default)
    return str(value if value is not None else default).strip()


_PRODUCT_CONFIG = _get_config_section("product")
PRODUCT_NAME = _config_text(_PRODUCT_CONFIG, "name", "Remote Access Service")
PRODUCT_REDIS_PREFIX = _config_text(_PRODUCT_CONFIG, "redis_prefix", "remote_access")
PRODUCT_COOKIE_PREFIX = _config_text(_PRODUCT_CONFIG, "cookie_prefix", "remote_access")
PRODUCT_PROFILE_TAG = _config_text(_PRODUCT_CONFIG, "profile_tag", "🔐")

_FEATURES_CONFIG = _get_config_section("features")
FEATURE_COMMERCE_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("commerce_enabled"),
    default=True,
)
FEATURE_REFERRALS_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("referrals_enabled"),
    default=True,
)
FEATURE_PROMOS_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("promos_enabled"),
    default=True,
)
FEATURE_WEB_PURCHASE_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("web_purchase_enabled"),
    default=True,
)
FEATURE_TELEGRAM_BOT_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("telegram_bot_enabled"),
    default=True,
)
FEATURE_TELEGRAM_PROXY_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("telegram_proxy_enabled"),
    default=False,
)
FEATURE_TRAFFIC_LIMITED_CONFIG_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("traffic_limited_config_enabled"),
    default=True,
)


def _normalize_location_label(value, *, fallback: str) -> str:
    normalized = str(value or "").strip()
    return normalized or fallback


def _build_vpn_locations(raw_locations: dict | list | None) -> dict[str, str]:
    if isinstance(raw_locations, dict):
        result: dict[str, str] = {}
        for code, payload in raw_locations.items():
            if isinstance(payload, dict):
                result[str(code)] = _normalize_location_label(
                    payload.get("label"),
                    fallback=str(code),
                )
            else:
                result[str(code)] = _normalize_location_label(payload, fallback=str(code))
        return result

    if isinstance(raw_locations, list):
        result = {}
        for item in raw_locations:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            result[code] = _normalize_location_label(item.get("label"), fallback=code)
        return result

    return {}


def _legacy_inbound_location_map() -> dict[int, str]:
    return {
        # 1: "netherlands",
        1: "germany",
        2: "estonia",
    }


def get_server_inbound_specs(server_config: dict) -> list[dict[str, object]]:
    raw_inbounds = server_config.get("inbounds")
    if isinstance(raw_inbounds, dict) and raw_inbounds:
        specs: list[dict[str, object]] = []
        for inbound_id, location_code in raw_inbounds.items():
            try:
                normalized_inbound_id = int(inbound_id)
            except (TypeError, ValueError):
                continue
            normalized_location_code = str(location_code or "").strip() or None
            specs.append(
                {
                    "id": normalized_inbound_id,
                    "location_code": normalized_location_code,
                }
            )
        if specs:
            return specs

    if isinstance(raw_inbounds, list) and raw_inbounds:
        specs: list[dict[str, object]] = []
        for item in raw_inbounds:
            if not isinstance(item, dict):
                continue
            inbound_id = item.get("id", item.get("inbound_id"))
            if inbound_id is None:
                continue
            specs.append(
                {
                    "id": int(inbound_id),
                    "location_code": str(item.get("location_code") or "").strip() or None,
                }
            )
        if specs:
            return specs

    inbound_ids = server_config.get("inbound_id", [])
    if isinstance(inbound_ids, list):
        normalized_ids = [int(value) for value in inbound_ids]
    else:
        normalized_ids = [int(inbound_ids)]

    legacy_map = _legacy_inbound_location_map()
    return [
        {"id": int(inbound_id), "location_code": legacy_map.get(int(inbound_id))}
        for inbound_id in normalized_ids
    ]


# ========== SERVERS ==========
API_SERVERS = config["servers"]
WHITELIST_API_SERVERS = config.get("whitelist_servers", {})
VPN_LOCATION_LABELS = _build_vpn_locations(config.get("vpn_locations"))
if not VPN_LOCATION_LABELS:
    VPN_LOCATION_LABELS = {
        # "netherlands": "🇳🇱Нидерланды",
        "germany": "🇩🇪Германия",
        "estonia": "🇪🇪Эстония",
    }

# ========== INBOUND ==========
INBOUND_AMOUNT_OF_DEVICES = config["inbound"]["amount_of_devices"]

# ========== CRYPTOPAY ==========
CRYPTOPAY_TOKEN = _config_text(_get_config_section("cryptopay"), "token", "")

# ========== YOOKASSA ==========
_YOOKASSA_CONFIG = _get_config_section("yookassa")
CONFIGURATION_ACCOUNT_ID = _config_text(_YOOKASSA_CONFIG, "account_id", "")
CONFIGURATION_SECRET_KEY = _config_text(_YOOKASSA_CONFIG, "secret_key", "")

# ========== BOT ==========
_BOT_CONFIG = _get_config_section("bot")
BOT_TG_ID = _config_text(_BOT_CONFIG, "tg_id", "")
BOT_API = _config_text(_BOT_CONFIG, "api", "")
_BOT_ADMIN_IDS_RAW = _BOT_CONFIG.get("admin_ids", "[]")
BOT_ADMIN_IDS = (
    _BOT_ADMIN_IDS_RAW
    if isinstance(_BOT_ADMIN_IDS_RAW, list)
    else json.loads(str(_BOT_ADMIN_IDS_RAW))
)
BOT_MAINTENANCE_MODE = str(
    _BOT_CONFIG.get("maintenance_mode", False)
).strip().lower() in {"1", "true", "yes", "on"}
BOT_MAINTENANCE_MESSAGE = str(
    _BOT_CONFIG.get(
        "maintenance_message",
        "Сейчас идут технические работы. Попробуйте немного позже.",
    )
).strip()
BOT_BONUS_REFERRER_INT = int(_BOT_CONFIG.get("bonus_referrer", 0))
BOT_BONUS_NEW_USER_INT = int(_BOT_CONFIG.get("bonus_new_user", 0))
BOT_NEWS_TG_ID = _config_text(_BOT_CONFIG, "news_channel_id", "")
BOT_NEWS_USERNAME = _config_text(_BOT_CONFIG, "news_channel", "")
BOT_SUPPORT_TG_ID = _config_text(_BOT_CONFIG, "support", "")

BOT_SUPPORT_TG_LINK = f"https://t.me/{BOT_SUPPORT_TG_ID}"
BOT_RETURN_URL = f"https://t.me/{BOT_TG_ID}"
BOT_REFERRAL_LINK = f"https://t.me/{BOT_TG_ID}?start="
BOT_NEWS_TG_LINK = f"https://t.me/{BOT_NEWS_USERNAME}"

# ========== IMAGES ==========
_IMAGES_CONFIG = _get_config_section("images")
PHOTO_subscriptions = _config_text(_IMAGES_CONFIG, "subscriptions", "")
PHOTO_instructions = _config_text(_IMAGES_CONFIG, "instructions", "")
PHOTO_menu = _config_text(_IMAGES_CONFIG, "menu", "")
PHOTO_my_subscription = _config_text(_IMAGES_CONFIG, "my_subscription", "")
PHOTO_help = _config_text(_IMAGES_CONFIG, "help", "")
PHOTO_referral_program = _config_text(_IMAGES_CONFIG, "referral_program", "")

# ========== DATABASE ==========
DB_NAME = config["db"]["name"]
DB_USERNAME = config["db"]["username"]
DB_PASSWORD = config["db"]["password"]
DB_HOST = config["db"]["host"]
DB_URL = f"postgresql+asyncpg://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:5432/{DB_NAME}"
DB_SQL_ECHO = _as_bool(config.get("db", {}).get("sql_echo", False))

# ========== FRONTEND ==========
FRONTEND_SUBSCRIPTION_LINK = config["frontend"]["subscription_link"]
FRONTEND_LINK = config["frontend"]["link"]
FRONTEND_ADMIN_PATH = str(config["frontend"].get("admin_path", "")).strip().strip("/")
FRONTEND_FAQ_LINK = str(
    config["frontend"].get("faq_link", "https://docs.example.com/faq/")
).strip()
FRONTEND_DEVICES_LINK = str(
    config["frontend"].get("devices_link", "https://docs.example.com/devices/")
).strip()
FRONTEND_ABOUT_LINK = str(
    config["frontend"].get("about_link", "https://docs.example.com/")
).strip()
FRONTEND_TELEGRAM_PROXY_URL = str(
    config["frontend"].get("telegram_proxy_url", "")
).strip()
FRONTEND_HAPP_SUBSCRIPTION_ADD_LINK = str(
    config["frontend"].get("happ_subscription_add_link", "happ://add/")
).strip()
FRONTEND_APP_LINK_HAPP_IOS = str(
    config["frontend"].get(
        "app_link_happ_ios",
        "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973",
    )
).strip()
FRONTEND_APP_LINK_HAPP_ANDROID = str(
    config["frontend"].get(
        "app_link_happ_android",
        "https://play.google.com/store/apps/details?id=com.happproxy",
    )
).strip()
FRONTEND_APP_LINK_HAPP_WINDOWS = str(
    config["frontend"].get(
        "app_link_happ_windows",
        "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe",
    )
).strip()
FRONTEND_APP_LINK_HAPP_MACOS = str(
    config["frontend"].get(
        "app_link_happ_macos",
        "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973",
    )
).strip()
FRONTEND_APP_LINK_HAPP_LINUX = str(
    config["frontend"].get(
        "app_link_happ_linux",
        "https://www.happ.su/main/ru",
    )
).strip()
FRONTEND_APP_LINK_WINDOWS_NEKORAY = str(
    config["frontend"].get(
        "app_link_windows_nekoray",
        "https://github.com/MatsuriDayo/nekoray/releases/download/4.0.1/nekoray-4.0.1-2024-12-12-windows64.zip",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_IOS = str(
    config["frontend"].get(
        "instruction_link_ios",
        "https://docs.example.com/devices/ios.html",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_ANDROID = str(
    config["frontend"].get(
        "instruction_link_android",
        "https://docs.example.com/devices/android.html",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_WINDOWS = str(
    config["frontend"].get(
        "instruction_link_windows",
        "https://docs.example.com/devices/windows.html",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_MACOS = str(
    config["frontend"].get(
        "instruction_link_macos",
        "https://docs.example.com/devices/macos.html",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_LINUX = str(
    config["frontend"].get(
        "instruction_link_linux",
        "https://docs.example.com/devices/linux.html",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_WINDOWS_NEKORAY = str(
    config["frontend"].get(
        "instruction_link_windows_nekoray",
        "https://docs.example.com/devices/windows-nekoray.html",
    )
).strip()
FRONTEND_ADMIN_LINK = (
    f"{FRONTEND_LINK.rstrip('/')}/{FRONTEND_ADMIN_PATH}"
    if FRONTEND_ADMIN_PATH
    else FRONTEND_LINK.rstrip("/")
)
FRONTEND_TELEGRAM_SUBSCRIPTION_LINK = config["frontend"].get(
    "telegram_subscription_link"
)
FRONTEND_TELEGRAM_WHITELIST_SUBSCRIPTION_LINK = (
    f"{FRONTEND_TELEGRAM_SUBSCRIPTION_LINK.rstrip('/')}/whitelist"
    if FRONTEND_TELEGRAM_SUBSCRIPTION_LINK
    else None
)

# ========== BACKEND ==========
BACKEND_SUBSCRIPTION_LINK = config["backend"]["subscription_link"].rstrip("/")
BACKEND_TELEGRAM_SUBSCRIPTION_LINK = (
    config["backend"].get("telegram_subscription_link") or BACKEND_SUBSCRIPTION_LINK
).rstrip("/")
BACKEND_TELEGRAM_BASE_LINK = BACKEND_TELEGRAM_SUBSCRIPTION_LINK.rsplit(
    "/subscription/build",
    1,
)[0]
BACKEND_TELEGRAM_WHITELIST_SUBSCRIPTION_LINK = (
    f"{BACKEND_TELEGRAM_BASE_LINK}/subscription/whitelist/build"
)
BACKEND_PREFIX = config["backend"]["prefix"]

# ========== ADMIN ==========
ADMIN_PANEL_ENABLED = _as_bool(
    config.get("admin", {}).get("enabled", True),
    default=True,
)
ADMIN_TOKEN = str(
    config.get("admin", {}).get("token")
    or os.getenv("APP_ADMIN_TOKEN", "")
    or os.getenv("NOWMEOW_ADMIN_TOKEN", "")
).strip()
ADMIN_DEFAULT_ROLE = str(
    config.get("admin", {}).get("default_role", "superadmin")
).strip().lower()
ADMIN_SESSION_TTL_MINUTES = int(
    config.get("admin", {}).get("session_ttl_minutes", 480)
)
ADMIN_LOGIN_ATTEMPT_WINDOW_SECONDS = int(
    config.get("admin", {}).get("login_attempt_window_seconds", 900)
)
ADMIN_LOGIN_MAX_ATTEMPTS = int(
    config.get("admin", {}).get("login_max_attempts", 5)
)
ADMIN_LOGIN_LOCKOUT_SECONDS = int(
    config.get("admin", {}).get("login_lockout_seconds", 1800)
)

# ========== AUTH ==========
AUTH_WEB_SESSION_TTL_MINUTES = int(
    config.get("auth", {}).get("web_session_ttl_minutes", 43200)
)
AUTH_EMAIL_CODE_TTL_MINUTES = int(
    config.get("auth", {}).get("email_code_ttl_minutes", 15)
)
AUTH_IDENTITY_LINK_TOKEN_TTL_MINUTES = int(
    config.get("auth", {}).get("identity_link_token_ttl_minutes", 30)
)
AUTH_CHALLENGE_RESEND_COOLDOWN_SECONDS = int(
    config.get("auth", {}).get("challenge_resend_cooldown_seconds", 60)
)
AUTH_CHALLENGE_REQUEST_WINDOW_SECONDS = int(
    config.get("auth", {}).get("challenge_request_window_seconds", 3600)
)
AUTH_CHALLENGE_MAX_REQUESTS_PER_WINDOW_PER_EMAIL = int(
    config.get("auth", {}).get("challenge_max_requests_per_window_per_email", 5)
)
AUTH_CHALLENGE_MAX_REQUESTS_PER_WINDOW_PER_IP = int(
    config.get("auth", {}).get("challenge_max_requests_per_window_per_ip", 20)
)
AUTH_CHALLENGE_MAX_FAILED_ATTEMPTS = int(
    config.get("auth", {}).get("challenge_max_failed_attempts", 5)
)
AUTH_PASSWORD_MIN_LENGTH = int(
    config.get("auth", {}).get("password_min_length", 8)
)

# ========== MAIL ==========
MAIL_ENABLED = _as_bool(
    config.get("mail", {}).get("enabled", False),
    default=False,
)
MAIL_PROVIDER = str(
    config.get("mail", {}).get("provider", "noop")
).strip().lower()
MAIL_FROM_EMAIL = str(
    config.get("mail", {}).get("from_email", "noreply@example.com")
).strip()
MAIL_FROM_NAME = str(
    config.get("mail", {}).get("from_name", PRODUCT_NAME)
).strip()
MAIL_REPLY_TO = str(
    config.get("mail", {}).get("reply_to", "")
).strip()
MAIL_SMTP_HOST = str(
    config.get("mail", {}).get("smtp_host", "")
).strip()
MAIL_SMTP_PORT = int(
    config.get("mail", {}).get("smtp_port", 587)
)
MAIL_SMTP_USERNAME = str(
    config.get("mail", {}).get("smtp_username", "")
).strip()
MAIL_SMTP_PASSWORD = str(
    config.get("mail", {}).get("smtp_password", "")
).strip()
MAIL_SMTP_STARTTLS = _as_bool(
    config.get("mail", {}).get("smtp_starttls", True),
    default=True,
)
MAIL_SMTP_SSL = _as_bool(
    config.get("mail", {}).get("smtp_ssl", False),
    default=False,
)
MAIL_TIMEOUT_SECONDS = int(
    config.get("mail", {}).get("timeout_seconds", 10)
)

# ========== REDIS ==========
REDIS_URL = config.get("redis", {}).get("url") or os.getenv(
    "REDIS_URL", "redis://redis:6379/0"
)
REDIS_SUBSCRIPTION_BUILD_TTL = int(
    config.get("redis", {}).get("subscription_build_ttl", 60)
)
REDIS_SUBSCRIPTION_INFO_TTL = int(
    config.get("redis", {}).get("subscription_info_ttl", 30)
)
REDIS_REMINDER_READY_QUEUE_KEY = config.get("redis", {}).get(
    "reminder_ready_queue_key",
    f"{PRODUCT_REDIS_PREFIX}:queue:subscription_reminders:ready",
)
REDIS_REMINDER_RETRY_QUEUE_KEY = config.get("redis", {}).get(
    "reminder_retry_queue_key",
    f"{PRODUCT_REDIS_PREFIX}:queue:subscription_reminders:retry",
)
REDIS_REMINDER_DEAD_LETTER_QUEUE_KEY = config.get("redis", {}).get(
    "reminder_dead_letter_queue_key",
    f"{PRODUCT_REDIS_PREFIX}:queue:subscription_reminders:dead_letter",
)
REDIS_REMINDER_DEDUPE_PREFIX = config.get("redis", {}).get(
    "reminder_dedupe_prefix",
    f"{PRODUCT_REDIS_PREFIX}:queue:subscription_reminders:dedupe",
)
REDIS_REMINDER_DEDUPE_TTL_SECONDS = int(
    config.get("redis", {}).get("reminder_dedupe_ttl_seconds", 172800)
)
REDIS_REMINDER_SCAN_INTERVAL_SECONDS = int(
    config.get("redis", {}).get("reminder_scan_interval_seconds", 300)
)
REDIS_REMINDER_LOOKAHEAD_HOURS = int(
    config.get("redis", {}).get("reminder_lookahead_hours", 24)
)
REDIS_REMINDER_RETRY_BASE_SECONDS = int(
    config.get("redis", {}).get("reminder_retry_base_seconds", 30)
)
REDIS_REMINDER_MAX_RETRIES = int(
    config.get("redis", {}).get("reminder_max_retries", 3)
)
REDIS_REMINDER_WORKER_POP_TIMEOUT_SECONDS = int(
    config.get("redis", {}).get("reminder_worker_pop_timeout_seconds", 5)
)
REDIS_PAYMENT_READY_QUEUE_KEY = config.get("redis", {}).get(
    "payment_ready_queue_key",
    f"{PRODUCT_REDIS_PREFIX}:queue:payments:ready",
)
REDIS_PAYMENT_RETRY_QUEUE_KEY = config.get("redis", {}).get(
    "payment_retry_queue_key",
    f"{PRODUCT_REDIS_PREFIX}:queue:payments:retry",
)
REDIS_PAYMENT_DEAD_LETTER_QUEUE_KEY = config.get("redis", {}).get(
    "payment_dead_letter_queue_key",
    f"{PRODUCT_REDIS_PREFIX}:queue:payments:dead_letter",
)
REDIS_PAYMENT_DEDUPE_PREFIX = config.get("redis", {}).get(
    "payment_dedupe_prefix",
    f"{PRODUCT_REDIS_PREFIX}:queue:payments:dedupe",
)
REDIS_PAYMENT_DEDUPE_TTL_SECONDS = int(
    config.get("redis", {}).get("payment_dedupe_ttl_seconds", 120)
)
REDIS_PAYMENT_RETRY_BASE_SECONDS = int(
    config.get("redis", {}).get("payment_retry_base_seconds", 30)
)
REDIS_PAYMENT_MAX_RETRIES = int(
    config.get("redis", {}).get("payment_max_retries", 8)
)
REDIS_PAYMENT_SCAN_INTERVAL_SECONDS = int(
    config.get("redis", {}).get("payment_scan_interval_seconds", 30)
)
REDIS_PAYMENT_WORKER_POP_TIMEOUT_SECONDS = int(
    config.get("redis", {}).get("payment_worker_pop_timeout_seconds", 5)
)
PAYMENT_STATUS_SCAN_INTERVAL_SECONDS = int(
    config.get("redis", {}).get("payment_status_scan_interval_seconds", 30)
)
WHITELIST_TRAFFIC_SYNC_INTERVAL_SECONDS = int(
    config.get("redis", {}).get("whitelist_traffic_sync_interval_seconds", 120)
)
PAYMENT_WEBHOOK_TOKEN = str(
    config.get("payments", {}).get("webhook_token", "")
).strip()
_PAYMENTS_CONFIG = _get_config_section("payments")
PAYMENT_PROVIDER_CARD_CODE = _config_text(
    _PAYMENTS_CONFIG,
    "card_gateway_code",
    "external_card",
)
PAYMENT_PROVIDER_CARD_LABEL = _config_text(
    _PAYMENTS_CONFIG,
    "card_gateway_label",
    "Банковская карта",
)
PAYMENT_PROVIDER_WALLET_CODE = _config_text(
    _PAYMENTS_CONFIG,
    "wallet_gateway_code",
    "external_wallet",
)
PAYMENT_PROVIDER_WALLET_LABEL = _config_text(
    _PAYMENTS_CONFIG,
    "wallet_gateway_label",
    "Электронный кошелёк",
)
PAYMENT_DEMO_CHECKOUT_PATH = _config_text(
    _PAYMENTS_CONFIG,
    "demo_checkout_path",
    "/demo-payment",
)
PAYMENT_DEMO_AUTO_PAID = _as_bool(
    _PAYMENTS_CONFIG.get("demo_auto_paid"),
    default=True,
)

# ========== JWT ==========
JWT_SECRET = config["jwt"]["secret"]
JWT_ALGORITHM = config["jwt"]["algorithm"]
JWT_EXP_MIN = config["jwt"]["exp_min"]

# ========== LOGGER ==========
TELEGRAM_LOGGER_TOKEN = config["logger"]["telegram_token"]
TELEGRAM_LOGGER_CHAT_ID = config["logger"]["telegram_chat_id"]

# ========== SENTRY ==========
SENTRY_DSN = config.get("sentry", {}).get("dsn")

LOCATION_LABELS = {
    **VPN_LOCATION_LABELS,
    "default": "🌍VPN",
}

KEY_PROFILE_TAG = PRODUCT_PROFILE_TAG

INBOUND_ID_MAP = _legacy_inbound_location_map()

# ========== UTILS ==========
def build_base_url(server_config: dict) -> str:
    return f"https://{server_config['domain']}:{server_config['port']}/{server_config['path']}"

def build_subscription_url(server_config: dict) -> str:
    return f"https://{server_config['domain']}:{server_config['subscription_port']}/{server_config['subscription_path']}/"

def build_inbound_api_base(server_config: dict) -> str:
    return f"https://{server_config['domain']}:{server_config['port']}/{server_config['path']}/panel/api/inbounds/"


def _is_local_or_private_host(hostname: str | None) -> bool:
    if not hostname:
        return True

    normalized = hostname.strip().strip("[]").lower()
    if normalized in {"localhost", "0.0.0.0", "::1"}:
        return True
    if normalized.endswith(".local"):
        return True

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False

    return not address.is_global


def normalize_telegram_button_url(url: str | None) -> str:
    if not url:
        return ""

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return ""
    if _is_local_or_private_host(parsed.hostname):
        return ""

    return url.rstrip("/")


def extract_url_origin(url: str | None) -> str:
    if not url:
        return ""

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""

    return f"{parsed.scheme}://{parsed.netloc}"


def get_frontend_allowed_origins() -> list[str]:
    origins: list[str] = []

    for candidate in (FRONTEND_LINK, FRONTEND_TELEGRAM_SUBSCRIPTION_LINK):
        origin = extract_url_origin(candidate)
        if origin and origin not in origins:
            origins.append(origin)

    return origins


FRONTEND_TELEGRAM_SUBSCRIPTION_LINK = normalize_telegram_button_url(
    FRONTEND_TELEGRAM_SUBSCRIPTION_LINK or FRONTEND_SUBSCRIPTION_LINK
)
