from shared.config import config as legacy_config
from shared.config.settings import (
    get_backend_settings,
    get_deploy_settings,
    get_product_feature_settings,
    get_product_settings,
    get_settings,
    load_app_settings,
    load_settings,
)


def test_load_app_settings_maps_legacy_config():
    app_settings = load_app_settings()

    assert app_settings.telegram_bot.config_path == legacy_config.CONFIG_PATH
    assert app_settings.telegram_bot.bot_api == legacy_config.BOT_API
    assert app_settings.telegram_bot.redis_url == legacy_config.REDIS_URL
    assert app_settings.telegram_bot.jwt.secret == legacy_config.JWT_SECRET
    assert (
        app_settings.telegram_bot.reminders.ready_queue_key
        == legacy_config.REDIS_REMINDER_READY_QUEUE_KEY
    )
    assert (
        app_settings.telegram_bot.payments.status_scan_interval_seconds
        == legacy_config.PAYMENT_STATUS_SCAN_INTERVAL_SECONDS
    )

    assert app_settings.backend.config_path == legacy_config.CONFIG_PATH
    assert app_settings.backend.frontend_link == legacy_config.FRONTEND_LINK
    assert app_settings.backend.frontend_allowed_origins == tuple(
        legacy_config.get_frontend_allowed_origins()
    )
    assert app_settings.backend.backend_prefix == legacy_config.BACKEND_PREFIX
    assert app_settings.backend.redis_url == legacy_config.REDIS_URL
    assert app_settings.backend.jwt.algorithm == legacy_config.JWT_ALGORITHM
    assert (
        app_settings.backend.auth.web_session_ttl_minutes
        == legacy_config.AUTH_WEB_SESSION_TTL_MINUTES
    )
    assert (
        app_settings.backend.auth.email_code_ttl_minutes
        == legacy_config.AUTH_EMAIL_CODE_TTL_MINUTES
    )
    assert (
        app_settings.backend.auth.identity_link_token_ttl_minutes
        == legacy_config.AUTH_IDENTITY_LINK_TOKEN_TTL_MINUTES
    )
    assert (
        app_settings.backend.auth.challenge_max_failed_attempts
        == legacy_config.AUTH_CHALLENGE_MAX_FAILED_ATTEMPTS
    )
    assert (
        app_settings.backend.auth.password_min_length
        == legacy_config.AUTH_PASSWORD_MIN_LENGTH
    )
    assert app_settings.backend.mail.enabled == legacy_config.MAIL_ENABLED
    assert app_settings.backend.mail.provider == legacy_config.MAIL_PROVIDER
    assert app_settings.backend.mail.from_email == legacy_config.MAIL_FROM_EMAIL
    assert app_settings.backend.mail.smtp_port == legacy_config.MAIL_SMTP_PORT
    assert app_settings.product.name == "Remote Access Service"
    assert app_settings.product.redis_prefix == "remote_access"
    assert app_settings.product.docs_links["faq"] == ""
    assert app_settings.features.commerce_enabled == legacy_config._as_bool(
        legacy_config.config.get("features", {}).get("commerce_enabled"),
        default=True,
    )
    assert app_settings.features.telegram_bot_enabled == legacy_config._as_bool(
        legacy_config.config.get("features", {}).get("telegram_bot_enabled"),
        default=True,
    )
    assert app_settings.features.mail_enabled == legacy_config.MAIL_ENABLED
    assert app_settings.deploy.project_slug == "remote-access-service"
    assert app_settings.deploy.config_env_var == legacy_config.CONFIG_OVERRIDE_ENV_VAR


def test_settings_accessors_return_cached_subsettings():
    app_settings = load_app_settings()

    assert load_settings() is app_settings.telegram_bot
    assert get_settings() is app_settings.telegram_bot
    assert get_backend_settings() is app_settings.backend
    assert get_product_settings() is app_settings.product
    assert get_product_feature_settings() is app_settings.features
    assert get_deploy_settings() is app_settings.deploy


def test_load_env_config_applies_override_file_and_process_env(tmp_path, monkeypatch):
    base_path = tmp_path / ".env.local"
    override_path = tmp_path / ".env.override"
    base_path.write_text(
        'PRODUCT__NAME="Base Product"\nPRODUCT__DESCRIPTION="Base Description"\n',
        encoding="utf-8",
    )
    override_path.write_text(
        'PRODUCT__DESCRIPTION="Override Description"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PRODUCT__NAME", "Process Override")

    config_data = legacy_config._load_env_config(base_path)

    assert config_data["product"]["name"] == "Process Override"
    assert config_data["product"]["description"] == "Override Description"
