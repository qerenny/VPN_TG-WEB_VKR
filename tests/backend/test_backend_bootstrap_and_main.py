from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bootstrap import (
    build_backend_deps,
    get_backend_deps,
    get_access_registry_service,
    get_linking_service,
    get_jwt_encoder,
    get_subscription_manager_service,
    get_user_manager_service,
    get_web_checkout_service,
)
from backend.main import _create_lifespan, create_app
from backend.utils.async_redis_client import RedisClientError
from shared.config.settings import BackendSettings, JwtSettings


def make_backend_settings() -> BackendSettings:
    return BackendSettings(
        config_path=Path("/tmp/.env.local"),
        frontend_link="https://frontend.example.com",
        frontend_allowed_origins=(
            "https://frontend.example.com",
            "https://frontend-alt.example.com",
        ),
        backend_prefix="/api",
        redis_url="redis://localhost:6379/0",
        jwt=JwtSettings(
            secret="secret",
            algorithm="HS256",
            expire_minutes=30,
        ),
    )


def test_build_backend_deps_wires_shared_dependencies():
    settings = make_backend_settings()

    deps = build_backend_deps(settings)

    assert deps.settings is settings
    assert deps.user_manager_service.repo is deps.user_repository
    assert deps.user_manager_service.jwt_encoder is deps.jwt_encoder
    assert deps.subscription_manager_service.repo is deps.user_repository
    assert deps.subscription_manager_service.jwt_encoder is deps.jwt_encoder
    assert deps.subscription_manager_service.timestamp is deps.timestamp_utils


def test_backend_dependency_accessors_read_from_app_state():
    deps = build_backend_deps(make_backend_settings())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(deps=deps)))

    assert get_backend_deps(request) is deps
    assert get_jwt_encoder(request) is deps.jwt_encoder
    assert get_linking_service(request) is deps.linking_service
    assert get_access_registry_service(request) is deps.access_registry_service
    assert get_user_manager_service(request) is deps.user_manager_service
    assert get_subscription_manager_service(request) is deps.subscription_manager_service
    assert get_web_checkout_service(request) is deps.web_checkout_service


def test_get_backend_deps_raises_when_not_initialized():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    with pytest.raises(RuntimeError, match="Backend dependencies are not initialized"):
        get_backend_deps(request)


def test_create_app_uses_supplied_settings_and_deps():
    settings = make_backend_settings()
    deps = build_backend_deps(settings)

    app = create_app(settings=settings, deps=deps)

    assert app.state.settings is settings
    assert app.state.deps is deps

    route_paths = {route.path for route in app.routes}
    assert "/health" in route_paths
    assert "/api/user/encode" in route_paths
    assert "/api/user/public-config" in route_paths
    assert "/api/auth/login" in route_paths
    assert "/api/auth/register/start" in route_paths
    assert "/api/auth/register/resend" in route_paths
    assert "/api/auth/register/verify" in route_paths
    assert "/api/auth/password/forgot" in route_paths
    assert "/api/auth/password/reset" in route_paths
    assert "/api/auth/logout" in route_paths
    assert "/api/me" in route_paths
    assert "/api/me/profile" in route_paths
    assert "/api/me/subscriptions" in route_paths
    assert "/api/me/payments" in route_paths
    assert "/api/me/payments/checkout" in route_paths
    assert "/api/me/payments/checkout/traffic-limited" in route_paths
    assert "/api/me/links" in route_paths
    assert "/api/me/links/telegram/start" in route_paths
    assert "/api/public/link/telegram/{token}" in route_paths
    assert "/api/public/link/consume" in route_paths
    assert "/api/subscription/build" in route_paths
    assert "/api/subscription/{user_token}" in route_paths
    assert "/api/payments/webhook/external/{method}/{token}" in route_paths

    cors_middleware = next(
        middleware for middleware in app.user_middleware if middleware.cls.__name__ == "CORSMiddleware"
    )
    assert cors_middleware.kwargs["allow_origins"] == list(settings.frontend_allowed_origins)


@pytest.mark.asyncio
async def test_lifespan_initializes_and_closes_shared_clients():
    settings = make_backend_settings()
    app = SimpleNamespace(state=SimpleNamespace())
    http_client = MagicMock(aclose=AsyncMock())
    redis_client = MagicMock(ping=AsyncMock(), aclose=AsyncMock())

    with (
        patch("backend.main.httpx.AsyncClient", return_value=http_client) as client_class,
        patch("backend.main.AsyncRedisClient", return_value=redis_client) as redis_class,
    ):
        async with _create_lifespan(settings)(app):
            assert app.state.http_client is http_client
            assert app.state.redis_client is redis_client

    client_class.assert_called_once_with(verify=False)
    redis_class.assert_called_once_with(settings.redis_url)
    redis_client.ping.assert_awaited_once_with()
    http_client.aclose.assert_awaited_once_with()
    redis_client.aclose.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_lifespan_falls_back_when_redis_is_unavailable():
    settings = make_backend_settings()
    app = SimpleNamespace(state=SimpleNamespace())
    http_client = MagicMock(aclose=AsyncMock())
    redis_client = MagicMock(
        ping=AsyncMock(side_effect=RedisClientError("down")),
        aclose=AsyncMock(),
    )

    with (
        patch("backend.main.httpx.AsyncClient", return_value=http_client),
        patch("backend.main.AsyncRedisClient", return_value=redis_client),
        patch("backend.main.logger") as logger,
    ):
        async with _create_lifespan(settings)(app):
            assert app.state.http_client is http_client
            assert app.state.redis_client is None

    logger.warning.assert_called_once()
    http_client.aclose.assert_awaited_once_with()
    redis_client.aclose.assert_not_called()
