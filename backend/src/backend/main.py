from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.bootstrap import BackendDeps, build_backend_deps
from backend.routers.admin import admin_routes
from backend.routers.auth import auth_routes
from backend.routers.me import me_routes
from backend.routers.payments import payment_webhook_routes
from backend.routers.public_link import public_link_routes
from backend.routers.subscription import subscription_routes
from backend.routers.user import user_routes
from backend.utils.async_redis_client import AsyncRedisClient, RedisClientError

from shared.config.settings import (
    BackendSettings,
    get_backend_settings,
    get_product_settings,
)
from shared.utils.logging_utils import logger


def _create_lifespan(
    settings: BackendSettings,
):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # verify=False is maintained to match existing behavior in subscription_routes.py
        app.state.http_client = httpx.AsyncClient(verify=False)
        app.state.redis_client = None

        try:
            redis_client = AsyncRedisClient(settings.redis_url)
            await redis_client.ping()
            app.state.redis_client = redis_client
            logger.info("Redis cache is connected")
        except RedisClientError as err:
            logger.warning(f"Redis is unavailable, fallback to in-memory cache: {err}")

        yield

        await app.state.http_client.aclose()
        if app.state.redis_client is not None:
            await app.state.redis_client.aclose()

    return lifespan


def create_app(
    settings: BackendSettings | None = None,
    deps: BackendDeps | None = None,
) -> FastAPI:
    runtime_settings = settings or get_backend_settings()
    runtime_deps = deps or build_backend_deps(runtime_settings)

    app = FastAPI(
        title=f"{get_product_settings().name} API",
        lifespan=_create_lifespan(runtime_settings),
    )
    app.state.settings = runtime_settings
    app.state.deps = runtime_deps

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.frontend_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(user_routes.router, prefix=runtime_settings.backend_prefix)
    app.include_router(auth_routes.router, prefix=runtime_settings.backend_prefix)
    app.include_router(me_routes.router, prefix=runtime_settings.backend_prefix)
    app.include_router(public_link_routes.router, prefix=runtime_settings.backend_prefix)
    app.include_router(subscription_routes.router, prefix=runtime_settings.backend_prefix)
    app.include_router(payment_webhook_routes.router, prefix=runtime_settings.backend_prefix)
    app.include_router(admin_routes.router, prefix=runtime_settings.backend_prefix)

    return app


app = create_app()
