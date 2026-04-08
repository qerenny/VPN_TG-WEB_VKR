from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]

for relative_path in ("backend/src", "shared/src", "telegram_bot/src"):
    src_path = str(ROOT / relative_path)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _install_fastapi_stub() -> None:
    try:
        __import__("fastapi")
        return
    except ModuleNotFoundError:
        pass

    module = ModuleType("fastapi")
    responses_module = ModuleType("fastapi.responses")
    middleware_module = ModuleType("fastapi.middleware")
    cors_module = ModuleType("fastapi.middleware.cors")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str | None = None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _Route:
        def __init__(self, path: str, endpoint):
            self.path = path
            self.endpoint = endpoint

    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.routes = []

        def _decorate(self, path: str, **kwargs):
            def decorator(func):
                self.routes.append(_Route(path, func))
                return func

            return decorator

        get = post = put = patch = delete = _decorate

    class FastAPI:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.routes = []
            self.state = SimpleNamespace()
            self.user_middleware = []

        def _decorate(self, path: str, **kwargs):
            def decorator(func):
                self.routes.append(_Route(path, func))
                return func

            return decorator

        get = post = put = patch = delete = _decorate

        def include_router(self, router, prefix: str = "", **kwargs) -> None:
            router_prefix = getattr(router, "kwargs", {}).get("prefix", "")
            for route in getattr(router, "routes", []):
                self.routes.append(
                    _Route(f"{prefix}{router_prefix}{route.path}", route.endpoint)
                )
            return None

        def add_middleware(self, *args, **kwargs) -> None:
            if args:
                self.user_middleware.append(
                    SimpleNamespace(cls=args[0], kwargs=kwargs)
                )
            return None

    def Depends(dependency):
        return dependency

    def Query(default=None, **kwargs):
        return default

    class PlainTextResponse(str):
        pass

    class CORSMiddleware:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    module.HTTPException = HTTPException
    module.APIRouter = APIRouter
    module.FastAPI = FastAPI
    module.Depends = Depends
    module.Query = Query
    module.Request = SimpleNamespace
    responses_module.PlainTextResponse = PlainTextResponse
    cors_module.CORSMiddleware = CORSMiddleware
    sys.modules["fastapi"] = module
    sys.modules["fastapi.responses"] = responses_module
    sys.modules["fastapi.middleware"] = middleware_module
    sys.modules["fastapi.middleware.cors"] = cors_module


_install_fastapi_stub()

from shared.config import config as shared_config

shared_config.SENTRY_DSN = None
shared_config.TELEGRAM_LOGGER_TOKEN = None
shared_config.TELEGRAM_LOGGER_CHAT_ID = None
