from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from shared.config import config as legacy_config


@dataclass(frozen=True, slots=True)
class JwtSettings:
    secret: str
    algorithm: str
    expire_minutes: int


@dataclass(frozen=True, slots=True)
class AdminSettings:
    enabled: bool
    token: str
    default_role: str
    session_ttl_minutes: int
    login_attempt_window_seconds: int
    login_max_attempts: int
    login_lockout_seconds: int


@dataclass(frozen=True, slots=True)
class WebAuthSettings:
    web_session_ttl_minutes: int
    email_code_ttl_minutes: int
    identity_link_token_ttl_minutes: int
    challenge_resend_cooldown_seconds: int
    challenge_request_window_seconds: int
    challenge_max_requests_per_window_per_email: int
    challenge_max_requests_per_window_per_ip: int
    challenge_max_failed_attempts: int
    password_min_length: int


@dataclass(frozen=True, slots=True)
class MailSettings:
    enabled: bool
    provider: str
    from_email: str
    from_name: str
    reply_to: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_starttls: bool
    smtp_ssl: bool
    timeout_seconds: int


def default_admin_settings() -> AdminSettings:
    return AdminSettings(
        enabled=True,
        token="",
        default_role="superadmin",
        session_ttl_minutes=480,
        login_attempt_window_seconds=900,
        login_max_attempts=5,
        login_lockout_seconds=1800,
    )


@dataclass(frozen=True, slots=True)
class ReminderRuntimeSettings:
    ready_queue_key: str
    retry_queue_key: str
    dead_letter_queue_key: str
    dedupe_prefix: str
    dedupe_ttl_seconds: int
    scan_interval_seconds: int
    lookahead_hours: int
    retry_base_seconds: int
    max_retries: int
    worker_pop_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class PaymentRuntimeSettings:
    ready_queue_key: str
    retry_queue_key: str
    dead_letter_queue_key: str
    dedupe_prefix: str
    dedupe_ttl_seconds: int
    scan_interval_seconds: int
    status_scan_interval_seconds: int
    retry_base_seconds: int
    max_retries: int
    worker_pop_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class RolloutFeatureFlags:
    db_dual_write_identity: bool = False
    db_dual_write_subscription: bool = False
    db_dual_write_payments: bool = False
    db_dual_write_growth: bool = False
    db_dual_write_vpn_topology: bool = False


@dataclass(frozen=True, slots=True)
class ProductSettings:
    name: str
    short_name: str
    description: str
    redis_prefix: str
    cookie_prefix: str
    profile_title: str
    traffic_profile_title: str
    announce: str
    support_name: str
    support_link: str
    docs_links: dict[str, str]


@dataclass(frozen=True, slots=True)
class ProductFeatureSettings:
    commerce_enabled: bool
    referrals_enabled: bool
    promos_enabled: bool
    web_purchase_enabled: bool
    telegram_bot_enabled: bool
    telegram_proxy_enabled: bool


@dataclass(frozen=True, slots=True)
class DeploySettings:
    project_slug: str
    remote_app_dir: str
    backup_dir: str
    frontend_public_dir: str
    container_prefix: str
    image_prefix: str
    config_env_var: str
    postgres_db: str
    postgres_user: str


@dataclass(frozen=True, slots=True)
class TelegramBotSettings:
    config_path: Path
    bot_api: str
    redis_url: str
    jwt: JwtSettings
    reminders: ReminderRuntimeSettings
    payments: PaymentRuntimeSettings


@dataclass(frozen=True, slots=True)
class BackendSettings:
    config_path: Path
    frontend_link: str
    frontend_allowed_origins: tuple[str, ...]
    backend_prefix: str
    redis_url: str
    jwt: JwtSettings
    admin: AdminSettings = field(default_factory=default_admin_settings)
    auth: WebAuthSettings = field(
        default_factory=lambda: WebAuthSettings(
            web_session_ttl_minutes=43200,
            email_code_ttl_minutes=15,
            identity_link_token_ttl_minutes=30,
            challenge_resend_cooldown_seconds=60,
            challenge_request_window_seconds=3600,
            challenge_max_requests_per_window_per_email=5,
            challenge_max_requests_per_window_per_ip=20,
            challenge_max_failed_attempts=5,
            password_min_length=8,
        )
    )
    mail: MailSettings = field(
        default_factory=lambda: MailSettings(
            enabled=False,
            provider="noop",
            from_email="noreply@example.com",
            from_name="Remote Access Service",
            reply_to=None,
            smtp_host=None,
            smtp_port=587,
            smtp_username=None,
            smtp_password=None,
            smtp_starttls=True,
            smtp_ssl=False,
            timeout_seconds=10,
        )
    )


@dataclass(frozen=True, slots=True)
class AppSettings:
    product: ProductSettings
    features: ProductFeatureSettings
    deploy: DeploySettings
    telegram_bot: TelegramBotSettings
    backend: BackendSettings


def _get_section(name: str) -> dict:
    section = legacy_config.config.get(name, {})
    return section if isinstance(section, dict) else {}


def _setting_text(section: dict, key: str, default: str) -> str:
    value = section.get(key, default)
    return str(value if value is not None else default).strip()


def _setting_bool(section: dict, key: str, default: bool) -> bool:
    return legacy_config._as_bool(section.get(key), default=default)


def _load_product_settings() -> ProductSettings:
    product = _get_section("product")
    frontend = _get_section("frontend")

    support_name = _setting_text(product, "support_name", "Support")
    support_link = _setting_text(
        product,
        "support_link",
        legacy_config.BOT_SUPPORT_TG_LINK,
    )

    docs_links = product.get("docs_links")
    if not isinstance(docs_links, dict):
        docs_links = {
            "faq": frontend.get("faq_link", ""),
            "devices": frontend.get("devices_link", ""),
            "about": frontend.get("about_link", ""),
        }

    return ProductSettings(
        name=_setting_text(product, "name", "Remote Access Service"),
        short_name=_setting_text(product, "short_name", "Remote Access"),
        description=_setting_text(
            product,
            "description",
            "Automated protected remote access service",
        ),
        redis_prefix=_setting_text(
            product,
            "redis_prefix",
            legacy_config.PRODUCT_REDIS_PREFIX,
        ),
        cookie_prefix=_setting_text(
            product,
            "cookie_prefix",
            legacy_config.PRODUCT_COOKIE_PREFIX,
        ),
        profile_title=_setting_text(product, "profile_title", "Remote Access"),
        traffic_profile_title=_setting_text(
            product,
            "traffic_profile_title",
            "Traffic-Limited Remote Access",
        ),
        announce=_setting_text(product, "announce", ""),
        support_name=support_name,
        support_link=support_link,
        docs_links={str(key): str(value) for key, value in docs_links.items()},
    )


def _load_feature_settings() -> ProductFeatureSettings:
    features = _get_section("features")
    frontend = _get_section("frontend")

    return ProductFeatureSettings(
        commerce_enabled=_setting_bool(features, "commerce_enabled", True),
        referrals_enabled=_setting_bool(features, "referrals_enabled", True),
        promos_enabled=_setting_bool(features, "promos_enabled", True),
        web_purchase_enabled=_setting_bool(features, "web_purchase_enabled", True),
        telegram_bot_enabled=_setting_bool(features, "telegram_bot_enabled", True),
        telegram_proxy_enabled=_setting_bool(
            features,
            "telegram_proxy_enabled",
            bool(str(frontend.get("telegram_proxy_url", "")).strip()),
        ),
    )


def _load_deploy_settings() -> DeploySettings:
    deploy = _get_section("deploy")

    return DeploySettings(
        project_slug=_setting_text(deploy, "project_slug", "remote-access-service"),
        remote_app_dir=_setting_text(deploy, "remote_app_dir", "$HOME/remote-access-service"),
        backup_dir=_setting_text(deploy, "backup_dir", "$HOME/remote-access-service-backups"),
        frontend_public_dir=_setting_text(
            deploy,
            "frontend_public_dir",
            "/var/www/remote-access-service",
        ),
        container_prefix=_setting_text(deploy, "container_prefix", "remote-access"),
        image_prefix=_setting_text(
            deploy,
            "image_prefix",
            "ghcr.io/example/remote-access-service",
        ),
        config_env_var=_setting_text(
            deploy,
            "config_env_var",
            legacy_config.CONFIG_OVERRIDE_ENV_VAR,
        ),
        postgres_db=_setting_text(deploy, "postgres_db", "remote_access"),
        postgres_user=_setting_text(deploy, "postgres_user", "remote_access"),
    )


@lru_cache(maxsize=1)
def load_app_settings() -> AppSettings:
    jwt_settings = JwtSettings(
        secret=legacy_config.JWT_SECRET,
        algorithm=legacy_config.JWT_ALGORITHM,
        expire_minutes=legacy_config.JWT_EXP_MIN,
    )
    return AppSettings(
        product=_load_product_settings(),
        features=_load_feature_settings(),
        deploy=_load_deploy_settings(),
        telegram_bot=TelegramBotSettings(
            config_path=legacy_config.CONFIG_PATH,
            bot_api=legacy_config.BOT_API,
            redis_url=legacy_config.REDIS_URL,
            jwt=jwt_settings,
            reminders=ReminderRuntimeSettings(
                ready_queue_key=legacy_config.REDIS_REMINDER_READY_QUEUE_KEY,
                retry_queue_key=legacy_config.REDIS_REMINDER_RETRY_QUEUE_KEY,
                dead_letter_queue_key=legacy_config.REDIS_REMINDER_DEAD_LETTER_QUEUE_KEY,
                dedupe_prefix=legacy_config.REDIS_REMINDER_DEDUPE_PREFIX,
                dedupe_ttl_seconds=legacy_config.REDIS_REMINDER_DEDUPE_TTL_SECONDS,
                scan_interval_seconds=legacy_config.REDIS_REMINDER_SCAN_INTERVAL_SECONDS,
                lookahead_hours=legacy_config.REDIS_REMINDER_LOOKAHEAD_HOURS,
                retry_base_seconds=legacy_config.REDIS_REMINDER_RETRY_BASE_SECONDS,
                max_retries=legacy_config.REDIS_REMINDER_MAX_RETRIES,
                worker_pop_timeout_seconds=legacy_config.REDIS_REMINDER_WORKER_POP_TIMEOUT_SECONDS,
            ),
            payments=PaymentRuntimeSettings(
                ready_queue_key=legacy_config.REDIS_PAYMENT_READY_QUEUE_KEY,
                retry_queue_key=legacy_config.REDIS_PAYMENT_RETRY_QUEUE_KEY,
                dead_letter_queue_key=legacy_config.REDIS_PAYMENT_DEAD_LETTER_QUEUE_KEY,
                dedupe_prefix=legacy_config.REDIS_PAYMENT_DEDUPE_PREFIX,
                dedupe_ttl_seconds=legacy_config.REDIS_PAYMENT_DEDUPE_TTL_SECONDS,
                scan_interval_seconds=legacy_config.REDIS_PAYMENT_SCAN_INTERVAL_SECONDS,
                status_scan_interval_seconds=legacy_config.PAYMENT_STATUS_SCAN_INTERVAL_SECONDS,
                retry_base_seconds=legacy_config.REDIS_PAYMENT_RETRY_BASE_SECONDS,
                max_retries=legacy_config.REDIS_PAYMENT_MAX_RETRIES,
                worker_pop_timeout_seconds=legacy_config.REDIS_PAYMENT_WORKER_POP_TIMEOUT_SECONDS,
            ),
        ),
        backend=BackendSettings(
            config_path=legacy_config.CONFIG_PATH,
            frontend_link=legacy_config.FRONTEND_LINK,
            frontend_allowed_origins=tuple(legacy_config.get_frontend_allowed_origins()),
            backend_prefix=legacy_config.BACKEND_PREFIX,
            redis_url=legacy_config.REDIS_URL,
            jwt=jwt_settings,
            admin=AdminSettings(
                enabled=legacy_config.ADMIN_PANEL_ENABLED,
                token=legacy_config.ADMIN_TOKEN,
                default_role=legacy_config.ADMIN_DEFAULT_ROLE,
                session_ttl_minutes=legacy_config.ADMIN_SESSION_TTL_MINUTES,
                login_attempt_window_seconds=legacy_config.ADMIN_LOGIN_ATTEMPT_WINDOW_SECONDS,
                login_max_attempts=legacy_config.ADMIN_LOGIN_MAX_ATTEMPTS,
                login_lockout_seconds=legacy_config.ADMIN_LOGIN_LOCKOUT_SECONDS,
            ),
            auth=WebAuthSettings(
                web_session_ttl_minutes=legacy_config.AUTH_WEB_SESSION_TTL_MINUTES,
                email_code_ttl_minutes=legacy_config.AUTH_EMAIL_CODE_TTL_MINUTES,
                identity_link_token_ttl_minutes=legacy_config.AUTH_IDENTITY_LINK_TOKEN_TTL_MINUTES,
                challenge_resend_cooldown_seconds=legacy_config.AUTH_CHALLENGE_RESEND_COOLDOWN_SECONDS,
                challenge_request_window_seconds=legacy_config.AUTH_CHALLENGE_REQUEST_WINDOW_SECONDS,
                challenge_max_requests_per_window_per_email=legacy_config.AUTH_CHALLENGE_MAX_REQUESTS_PER_WINDOW_PER_EMAIL,
                challenge_max_requests_per_window_per_ip=legacy_config.AUTH_CHALLENGE_MAX_REQUESTS_PER_WINDOW_PER_IP,
                challenge_max_failed_attempts=legacy_config.AUTH_CHALLENGE_MAX_FAILED_ATTEMPTS,
                password_min_length=legacy_config.AUTH_PASSWORD_MIN_LENGTH,
            ),
            mail=MailSettings(
                enabled=legacy_config.MAIL_ENABLED,
                provider=legacy_config.MAIL_PROVIDER,
                from_email=legacy_config.MAIL_FROM_EMAIL,
                from_name=legacy_config.MAIL_FROM_NAME,
                reply_to=legacy_config.MAIL_REPLY_TO or None,
                smtp_host=legacy_config.MAIL_SMTP_HOST or None,
                smtp_port=legacy_config.MAIL_SMTP_PORT,
                smtp_username=legacy_config.MAIL_SMTP_USERNAME or None,
                smtp_password=legacy_config.MAIL_SMTP_PASSWORD or None,
                smtp_starttls=legacy_config.MAIL_SMTP_STARTTLS,
                smtp_ssl=legacy_config.MAIL_SMTP_SSL,
                timeout_seconds=legacy_config.MAIL_TIMEOUT_SECONDS,
            ),
        ),
    )


def load_settings() -> TelegramBotSettings:
    return load_app_settings().telegram_bot


def get_settings() -> TelegramBotSettings:
    return load_settings()


def get_backend_settings() -> BackendSettings:
    return load_app_settings().backend


def get_product_settings() -> ProductSettings:
    return load_app_settings().product


def get_product_feature_settings() -> ProductFeatureSettings:
    return load_app_settings().features


def get_deploy_settings() -> DeploySettings:
    return load_app_settings().deploy
