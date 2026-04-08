from __future__ import annotations

from fastapi import Cookie, Depends, Request, Response

from backend.bootstrap import get_auth_service, get_backend_deps
from backend.services.auth.auth_service import AuthService, AuthenticatedWebUser
from shared.config.config import PRODUCT_COOKIE_PREFIX


WEB_SESSION_COOKIE_NAME = f"{PRODUCT_COOKIE_PREFIX}_web_session"


def _cookie_path(request: Request) -> str:
    prefix = str(get_backend_deps(request).settings.backend_prefix or "").rstrip("/")
    return prefix or "/"


def _cookie_secure(request: Request) -> bool:
    forwarded_proto = str(request.headers.get("x-forwarded-proto", "")).strip().lower()
    if forwarded_proto:
        return forwarded_proto == "https"
    return str(request.url.scheme).lower() == "https"


def _cookie_samesite(request: Request) -> str:
    return "none" if _cookie_secure(request) else "lax"


def attach_web_session_cookie(
    request: Request,
    response: Response,
    *,
    session_token: str,
    ttl_minutes: int,
) -> None:
    response.set_cookie(
        key=WEB_SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=_cookie_secure(request),
        samesite=_cookie_samesite(request),
        path=_cookie_path(request),
        max_age=max(300, int(ttl_minutes) * 60),
    )


def clear_web_session_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(
        key=WEB_SESSION_COOKIE_NAME,
        path=_cookie_path(request),
        secure=_cookie_secure(request),
        samesite=_cookie_samesite(request),
    )


async def require_web_user(
    request: Request,
    web_session_id: str | None = Cookie(default=None, alias=WEB_SESSION_COOKIE_NAME),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedWebUser:
    return await auth_service.get_current_user(web_session_id)


RequireWebUser = Depends(require_web_user)
