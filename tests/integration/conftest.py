from __future__ import annotations

import asyncio
import os
import warnings

import pytest
import pytest_asyncio
from sqlalchemy.exc import DBAPIError
from sqlalchemy import text
from sqlmodel import SQLModel

from backend.main import create_app
from backend.routers.subscription import subscription_routes
from shared.config.config import CONFIG_PATH, DB_NAME, REDIS_URL
from shared.config.database.engine import engine
from shared.models.admin.admin_audit_log_model import AdminAuditLog
from shared.models import register_models as register_models
from shared.utils.async_redis_client import AsyncRedisClient


INTEGRATION_ENABLED = os.getenv("REMOTE_ACCESS_RUN_INTEGRATION") == "1"

ACTIVE_SCHEMA_TABLE_NAMES = (
    "admin_audit_log",
    "payment_webhook_events",
    "payment_attempts",
    "payment_orders",
    "subscription_grants",
    "plans",
    "referral_rewards",
    "referral_reward_rules",
    "referral_edges",
    "promo_redemptions",
    "promo_codes",
    "vpn_client_deployments",
    "vpn_access_points",
    "vpn_locations",
    "vpn_control_planes",
    "subscription_state",
    "vpn_clients",
    "identity_link_tokens",
    "user_profiles",
    "web_auth_challenges",
    "web_sessions",
    "web_accounts",
    "telegram_accounts",
    "users",
)


def _active_schema_tables():
    return [
        SQLModel.metadata.tables[name]
        for name in ACTIVE_SCHEMA_TABLE_NAMES
        if name in SQLModel.metadata.tables
    ]


def _assert_safe_integration_target() -> None:
    config_path = str(CONFIG_PATH)
    if not config_path.endswith("tests/integration/.env.ci"):
        raise RuntimeError(
            "Integration tests require REMOTE_ACCESS_CONFIG_PATH=<repo>/tests/integration/.env.ci "
            f"to avoid mutating the default database. Current config: {config_path}"
        )
    if DB_NAME == "remote_access" or "integration" not in DB_NAME:
        raise RuntimeError(
            "Integration tests require a dedicated database name containing 'integration'. "
            f"Current database: {DB_NAME}"
        )


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def run_async_fn(event_loop):
    def _run(coro):
        event_loop.run_until_complete(engine.dispose())
        try:
            return event_loop.run_until_complete(coro)
        finally:
            event_loop.run_until_complete(engine.dispose())

    return _run


async def _create_schema() -> None:
    await engine.dispose()
    _assert_safe_integration_target()
    register_models()
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: SQLModel.metadata.create_all(sync_conn, tables=_active_schema_tables()))


async def _drop_schema() -> None:
    await engine.dispose()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: SQLModel.metadata.drop_all(sync_conn, tables=_active_schema_tables()))
    except DBAPIError as err:
        warnings.warn(
            f"integration schema cleanup skipped: {err}",
            RuntimeWarning,
            stacklevel=2,
        )
    await engine.dispose()


async def _truncate_database() -> None:
    await engine.dispose()
    truncate_sql = text(
        "TRUNCATE TABLE "
        + ", ".join(ACTIVE_SCHEMA_TABLE_NAMES)
        + " RESTART IDENTITY CASCADE"
    )
    async with engine.begin() as conn:
        await conn.execute(truncate_sql)
    await engine.dispose()


async def _flush_redis() -> None:
    redis_client = AsyncRedisClient(REDIS_URL)
    try:
        await redis_client._execute("FLUSHDB")
    finally:
        await redis_client.aclose()


def pytest_collection_modifyitems(config, items):
    try:
        __import__("fastapi.testclient")
        has_fastapi_testclient = True
    except ModuleNotFoundError:
        has_fastapi_testclient = False

    if INTEGRATION_ENABLED and has_fastapi_testclient:
        return

    reason = (
        "integration tests are disabled; set REMOTE_ACCESS_RUN_INTEGRATION=1"
        if not INTEGRATION_ENABLED
        else "fastapi.testclient is not installed"
    )
    skip_marker = pytest.mark.skip(reason=reason)
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def integration_schema():
    if not INTEGRATION_ENABLED:
        yield
        return
    await _create_schema()
    yield
    await _drop_schema()


@pytest_asyncio.fixture(autouse=True)
async def clean_integration_state():
    if not INTEGRATION_ENABLED:
        yield
        return
    subscription_routes.subscription_cache.clear()
    subscription_routes.subscription_info_cache.clear()
    subscription_routes.subscription_inflight.clear()
    await _truncate_database()
    await _flush_redis()
    yield
    subscription_routes.subscription_cache.clear()
    subscription_routes.subscription_info_cache.clear()
    subscription_routes.subscription_inflight.clear()
    await _truncate_database()
    await _flush_redis()


@pytest.fixture
def client():
    if not INTEGRATION_ENABLED:
        pytest.skip("integration tests are disabled; set REMOTE_ACCESS_RUN_INTEGRATION=1")
    try:
        from fastapi.testclient import TestClient
    except ModuleNotFoundError as err:
        pytest.skip(f"fastapi.testclient is not installed: {err}")

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def redis_client():
    if not INTEGRATION_ENABLED:
        pytest.skip("integration tests are disabled; set REMOTE_ACCESS_RUN_INTEGRATION=1")
    client = AsyncRedisClient(REDIS_URL)
    await client.ping()
    yield client
    await client.aclose()
