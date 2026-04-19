import json
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

CONFIG_OVERRIDE_ENV_VAR = "REMOTE_ACCESS_CONFIG_PATH"
CONFIG_OVERRIDE_FILE_ENV_VAR = "REMOTE_ACCESS_CONFIG_OVERRIDE_PATH"
LEGACY_CONFIG_ENV_PREFIX = "REMOTE_ACCESS__"
CONFIG_ENV_ALLOWED_ROOTS = {
    "admin",
    "auth",
    "backend",
    "bot",
    "db",
    "deploy",
    "features",
    "frontend",
    "images",
    "inbound",
    "jwt",
    "logger",
    "mail",
    "payments",
    "plans",
    "product",
    "redis",
    "referrals",
    "sentry",
    "servers",
    "traffic_limited_servers",
    "vpn_locations",
}
ENV_FILE_CANDIDATES = (
    ".env.local",
    ".env",
    ".env.production",
    ".env.example",
)


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def find_env_file(
    preferred_name: str = ".env.local",
    max_depth: int = 5,
) -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        candidates = [preferred_name, *[name for name in ENV_FILE_CANDIDATES if name != preferred_name]]
        for candidate_name in candidates:
            candidate = parent / candidate_name
            if candidate.is_file():
                return candidate
        max_depth -= 1
        if max_depth == 0:
            break

    raise FileNotFoundError(
        f"No supported env/config file found in parent directories. "
        f"Tried: {', '.join(dict.fromkeys([preferred_name, *ENV_FILE_CANDIDATES]))}"
    )


def find_env_override_file(base_path: Path) -> Path | None:
    explicit_override = os.getenv(CONFIG_OVERRIDE_FILE_ENV_VAR, "").strip()
    if explicit_override:
        override_path = Path(explicit_override).expanduser().resolve()
        if not override_path.exists():
            raise FileNotFoundError(
                f"{CONFIG_OVERRIDE_FILE_ENV_VAR} points to missing file: {override_path}"
            )
        if not override_path.is_file():
            raise IsADirectoryError(
                f"{CONFIG_OVERRIDE_FILE_ENV_VAR} must point to a file, got: {override_path}"
            )
        return override_path

    candidate_names = (
        f"{base_path.name}.override",
        ".env.override",
    )
    for candidate_name in candidate_names:
        candidate_path = base_path.parent / candidate_name
        if candidate_path.is_file():
            return candidate_path
    return None


def _normalize_env_path(parts: list[str]) -> list[str]:
    normalized: list[str] = []
    for part in parts:
        stripped = str(part or "").strip()
        if not stripped:
            continue
        normalized.append(stripped if stripped.isdigit() else stripped.lower())
    return normalized


def _extract_config_key_path(raw_key: str) -> list[str]:
    normalized_key = str(raw_key or "").strip()
    if not normalized_key:
        return []

    if normalized_key.startswith(LEGACY_CONFIG_ENV_PREFIX):
        return _normalize_env_path(
            normalized_key[len(LEGACY_CONFIG_ENV_PREFIX):].split("__")
        )

    if "__" not in normalized_key:
        return []

    parts = _normalize_env_path(normalized_key.split("__"))
    if not parts or parts[0] not in CONFIG_ENV_ALLOWED_ROOTS:
        return []
    return parts


def _build_nested_config(flat_values: dict[str, str]) -> dict:
    root: dict = {}

    def make_container(next_part: str | None, remaining_count: int):
        if next_part is not None and next_part.isdigit() and remaining_count > 1:
            return []
        return {}

    def set_path(container, parts: list[str], value: str) -> None:
        head, *tail = parts
        is_index = head.isdigit()

        if isinstance(container, list):
            if not is_index:
                raise ValueError(f"Expected numeric list index in env path, got: {head}")
            index = int(head)
            while len(container) <= index:
                container.append(None)
            if not tail:
                container[index] = value
                return
            if container[index] is None:
                container[index] = make_container(tail[0], len(tail))
            set_path(container[index], tail, value)
            return

        if not tail:
            container[head] = value
            return

        if head not in container or container[head] is None:
            container[head] = make_container(tail[0], len(tail))
        set_path(container[head], tail, value)

    for raw_key, raw_value in flat_values.items():
        if raw_value is None:
            continue
        path = _extract_config_key_path(raw_key)
        if not path:
            continue
        set_path(root, path, str(raw_value))

    return root


def _read_env_file(path: Path) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in dotenv_values(path).items()
        if key and value is not None
    }


def _load_runtime_env_overrides() -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in os.environ.items()
        if _extract_config_key_path(key)
        if value is not None
    }


def _load_env_config(path: Path) -> dict:
    merged_values: dict[str, str] = {}
    merged_values.update(_read_env_file(path))

    override_path = find_env_override_file(path)
    if override_path is not None:
        merged_values.update(_read_env_file(override_path))

    merged_values.update(_load_runtime_env_overrides())
    return _build_nested_config(merged_values)


def _load_config(path: Path) -> dict:
    return _load_env_config(path)

config_override_env_var = CONFIG_OVERRIDE_ENV_VAR
config_override = os.getenv(CONFIG_OVERRIDE_ENV_VAR, "").strip()

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


config = _load_config(CONFIG_PATH)


def _get_config_section(name: str) -> dict:
    section = config.get(name, {})
    return section if isinstance(section, dict) else {}


def _config_text(section: dict, key: str, default: str) -> str:
    value = section.get(key, default)
    return str(value if value is not None else default).strip()


def _config_json_list(section: dict, key: str, default: list[int] | None = None) -> list:
    raw_value = section.get(key, default or [])
    if isinstance(raw_value, list):
        return raw_value

    normalized = str(raw_value or "").strip()
    if not normalized:
        return list(default or [])

    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return [
            int(item.strip())
            for item in normalized.split(",")
            if item.strip().lstrip("-").isdigit()
        ]

    return parsed if isinstance(parsed, list) else list(default or [])


def _is_required_placeholder(value: object) -> bool:
    normalized = str(value or "").strip()
    return normalized.startswith("__REQUIRED_") and normalized.endswith("__")


def _is_effective_text(value: object) -> bool:
    normalized = str(value or "").strip()
    return bool(normalized) and not _is_required_placeholder(normalized)


def _build_telegram_link(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""

    for prefix in ("https://t.me/", "http://t.me/", "https://telegram.me/", "http://telegram.me/"):
        if normalized.startswith(prefix):
            return f"https://{normalized.split('://', 1)[1]}".rstrip("/")

    if normalized.startswith(("t.me/", "telegram.me/")):
        return f"https://{normalized}".rstrip("/")

    normalized = normalized.lstrip("@").strip("/")
    if not normalized or any(char.isspace() for char in normalized):
        return ""

    return f"https://t.me/{normalized}"


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
FEATURE_ACCESS_REQUESTS_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("access_requests_enabled"),
    default=False,
)
FEATURE_ACCESS_REGISTRY_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("access_registry_enabled"),
    default=False,
)
FEATURE_ACCESS_ADMIN_OVERRIDE_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("access_admin_override_enabled"),
    default=False,
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
FEATURE_STANDARD_CONFIG_ENABLED = _as_bool(
    _FEATURES_CONFIG.get("standard_config_enabled"),
    default=True,
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


def _is_configured_server(server_config: object) -> bool:
    if not isinstance(server_config, dict):
        return False

    required_keys = (
        "username",
        "password",
        "domain",
        "path",
        "subscription_path",
    )
    return all(_is_effective_text(server_config.get(key)) for key in required_keys)


def _filter_server_pool(raw_servers: object) -> dict:
    if not isinstance(raw_servers, dict):
        return {}

    return {
        str(code): server_config
        for code, server_config in raw_servers.items()
        if _is_configured_server(server_config)
    }


# ========== SERVERS ==========
API_SERVERS = _filter_server_pool(config.get("servers"))
TRAFFIC_LIMITED_API_SERVERS = _filter_server_pool(config.get("traffic_limited_servers"))
VPN_LOCATION_LABELS = _build_vpn_locations(config.get("vpn_locations"))
if not VPN_LOCATION_LABELS:
    VPN_LOCATION_LABELS = {
        # "netherlands": "🇳🇱Нидерланды",
        "germany": "🇩🇪Германия",
        "estonia": "🇪🇪Эстония",
    }

# ========== INBOUND ==========
INBOUND_AMOUNT_OF_DEVICES = config["inbound"]["amount_of_devices"]

# ========== BOT ==========
_BOT_CONFIG = _get_config_section("bot")
BOT_TG_ID = _config_text(_BOT_CONFIG, "tg_id", "")
BOT_API = _config_text(_BOT_CONFIG, "api", "")
BOT_ADMIN_IDS = _config_json_list(_BOT_CONFIG, "admin_ids", default=[])
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
BOT_INFO_CHANNEL_TG_ID = _config_text(_BOT_CONFIG, "info_channel_id", "")
BOT_INFO_CHANNEL_USERNAME = _config_text(_BOT_CONFIG, "info_channel", "")
BOT_INFO_CHANNEL_LINK = _config_text(_BOT_CONFIG, "info_channel_link", "")
BOT_SUPPORT_TG_ID = _config_text(_BOT_CONFIG, "support", "")

BOT_SUPPORT_TG_LINK = _build_telegram_link(BOT_SUPPORT_TG_ID)
BOT_RETURN_URL = _build_telegram_link(BOT_TG_ID)
BOT_REFERRAL_LINK = f"https://t.me/{BOT_TG_ID}?start="
BOT_INFO_CHANNEL_TG_LINK = (
    _build_telegram_link(BOT_INFO_CHANNEL_LINK)
    or _build_telegram_link(BOT_INFO_CHANNEL_USERNAME)
)
BOT_INFO_CHANNEL_ENABLED = bool(BOT_INFO_CHANNEL_TG_ID and BOT_INFO_CHANNEL_TG_LINK)

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
FRONTEND_TELEGRAM_LINK = str(config["frontend"].get("telegram_link", "")).strip()
FRONTEND_ADMIN_PATH = str(config["frontend"].get("admin_path", "")).strip().strip("/")
FRONTEND_HAPP_SUBSCRIPTION_ADD_LINK = str(
    config["frontend"].get("happ_subscription_add_link", "happ://add/")
).strip()
FRONTEND_SUBSCRIPTION_CLIENT_NAME = str(
    config["frontend"].get("subscription_client_name", "Happ")
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
FRONTEND_APP_LINK_HAPP_ANDROID_APK = str(
    config["frontend"].get(
        "app_link_happ_android_apk",
        "https://github.com/Happ-proxy/happ-android/releases/latest/download/Happ.apk",
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
FRONTEND_APP_LINK_HAPP_MACOS_DMG = str(
    config["frontend"].get(
        "app_link_happ_macos_dmg",
        "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.macOS.universal.dmg",
    )
).strip()
FRONTEND_APP_LINK_HAPP_LINUX = str(
    config["frontend"].get(
        "app_link_happ_linux",
        "https://www.happ.su/main/ru",
    )
).strip()
FRONTEND_APP_LINK_HAPP_LINUX_RPM = str(
    config["frontend"].get(
        "app_link_happ_linux_rpm",
        "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.rpm",
    )
).strip()
FRONTEND_APP_LINK_HAPP_APPLE_TV = str(
    config["frontend"].get(
        "app_link_happ_apple_tv",
        "https://apps.apple.com/us/app/happ-proxy-utility-for-tv/id6748297274",
    )
).strip()
FRONTEND_APP_LINK_HAPP_ANDROID_TV = str(
    config["frontend"].get(
        "app_link_happ_android_tv",
        FRONTEND_APP_LINK_HAPP_ANDROID,
    )
).strip()
FRONTEND_APP_LINK_HAPP_IOS_GLOBAL = str(
    config["frontend"].get(
        "app_link_happ_ios_global",
        "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215",
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
        "",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_ANDROID = str(
    config["frontend"].get(
        "instruction_link_android",
        "",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_WINDOWS = str(
    config["frontend"].get(
        "instruction_link_windows",
        "",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_MACOS = str(
    config["frontend"].get(
        "instruction_link_macos",
        "",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_LINUX = str(
    config["frontend"].get(
        "instruction_link_linux",
        "",
    )
).strip()
FRONTEND_INSTRUCTION_LINK_WINDOWS_NEKORAY = str(
    config["frontend"].get(
        "instruction_link_windows_nekoray",
        "",
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
FRONTEND_TELEGRAM_TRAFFIC_LIMITED_SUBSCRIPTION_LINK = (
    f"{FRONTEND_TELEGRAM_SUBSCRIPTION_LINK.rstrip('/')}/traffic_limited"
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
BACKEND_TELEGRAM_TRAFFIC_LIMITED_SUBSCRIPTION_LINK = (
    f"{BACKEND_TELEGRAM_BASE_LINK}/subscription/traffic-limited/build"
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
TRAFFIC_LIMITED_SYNC_INTERVAL_SECONDS = int(
    config.get("redis", {}).get("traffic_limited_sync_interval_seconds", 120)
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
JWT_EXP_MIN = int(config["jwt"]["exp_min"])

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
    if normalized.endswith(".localhost"):
        return True
    if normalized in {"example.com", "example.org", "example.net"}:
        return True
    if normalized.endswith(".example") or normalized.endswith(".invalid") or normalized.endswith(".test"):
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

    for candidate in (
        FRONTEND_LINK,
        FRONTEND_TELEGRAM_LINK,
        FRONTEND_TELEGRAM_SUBSCRIPTION_LINK,
    ):
        origin = extract_url_origin(candidate)
        if origin and origin not in origins:
            origins.append(origin)

    return origins


FRONTEND_TELEGRAM_LINK = normalize_telegram_button_url(
    FRONTEND_TELEGRAM_LINK
    or extract_url_origin(FRONTEND_TELEGRAM_SUBSCRIPTION_LINK)
    or FRONTEND_LINK
)
FRONTEND_TELEGRAM_SUBSCRIPTION_LINK = normalize_telegram_button_url(
    FRONTEND_TELEGRAM_SUBSCRIPTION_LINK or FRONTEND_SUBSCRIPTION_LINK
)
