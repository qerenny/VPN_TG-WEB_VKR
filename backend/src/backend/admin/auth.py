from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any

from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status

from backend.admin.types import AdminPrincipal
from backend.bootstrap import get_backend_deps
from backend.utils.async_redis_client import AsyncRedisClient, RedisClientError
from shared.config.config import PRODUCT_COOKIE_PREFIX, PRODUCT_REDIS_PREFIX


ROLE_ORDER = {
    "support": 10,
    "admin": 20,
    "tech": 30,
    "superadmin": 40,
}

ADMIN_SESSION_COOKIE_NAME = f"{PRODUCT_COOKIE_PREFIX}_admin_session"
_SESSION_KEY_PREFIX = f"{PRODUCT_REDIS_PREFIX}:admin:session"
_LOGIN_ATTEMPTS_KEY_PREFIX = f"{PRODUCT_REDIS_PREFIX}:admin:login_attempts"
_LOGIN_LOCK_KEY_PREFIX = f"{PRODUCT_REDIS_PREFIX}:admin:login_lock"
_memory_store: dict[str, tuple[dict[str, Any], float]] = {}


def _normalize_actor(actor: str | None) -> str:
    normalized = str(actor or "web-admin").strip() or "web-admin"
    return normalized[:80]


def _client_fingerprint(request: Request) -> str:
    forwarded_for = str(request.headers.get("x-forwarded-for", "")).strip()
    ip = forwarded_for.split(",")[0].strip() if forwarded_for else ""
    if not ip:
        ip = getattr(getattr(request, "client", None), "host", "") or "unknown"
    user_agent = str(request.headers.get("user-agent", "")).strip()
    raw = f"{ip}|{user_agent}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cookie_path(request: Request) -> str:
    prefix = str(get_backend_deps(request).settings.backend_prefix or "").rstrip("/")
    return f"{prefix}/admin" if prefix else "/admin"


def _cookie_secure(request: Request) -> bool:
    forwarded_proto = str(request.headers.get("x-forwarded-proto", "")).strip().lower()
    if forwarded_proto:
        return forwarded_proto == "https"
    return str(request.url.scheme).lower() == "https"


def _cookie_samesite(request: Request) -> str:
    return "none" if _cookie_secure(request) else "lax"


def _memory_get(key: str) -> dict[str, Any] | None:
    now = time.time()
    item = _memory_store.get(key)
    if item is None:
        return None
    payload, expires_at = item
    if expires_at <= now:
        _memory_store.pop(key, None)
        return None
    return payload


def _memory_set(key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    _memory_store[key] = (payload, time.time() + max(1, ttl_seconds))


def _memory_delete(key: str) -> None:
    _memory_store.pop(key, None)


async def _store_get_json(request: Request, key: str) -> dict[str, Any] | None:
    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is None:
        return _memory_get(key)

    try:
        raw_value = await redis_client.get(key)
    except RedisClientError:
        return _memory_get(key)

    if not raw_value:
        return None

    try:
        return json.loads(raw_value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


async def _store_set_json(
    request: Request,
    key: str,
    payload: dict[str, Any],
    ttl_seconds: int,
) -> None:
    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is None:
        _memory_set(key, payload, ttl_seconds)
        return

    try:
        await redis_client.set(key, json.dumps(payload), ex=max(1, ttl_seconds))
    except RedisClientError:
        _memory_set(key, payload, ttl_seconds)


async def _store_delete(request: Request, key: str) -> None:
    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is None:
        _memory_delete(key)
        return

    try:
        await redis_client.delete(key)
    except RedisClientError:
        _memory_delete(key)


async def _assert_login_not_locked(request: Request) -> None:
    settings = get_backend_deps(request).settings.admin
    fingerprint = _client_fingerprint(request)
    lock_key = f"{_LOGIN_LOCK_KEY_PREFIX}:{fingerprint}"
    lock_payload = await _store_get_json(request, lock_key)
    if not lock_payload:
        return

    locked_until = float(lock_payload.get("locked_until", 0))
    retry_after_seconds = max(1, int(locked_until - time.time()))
    if retry_after_seconds <= 0:
        await _store_delete(request, lock_key)
        return

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "message": "Too many admin login attempts",
            "retry_after_seconds": retry_after_seconds,
        },
    )


async def _record_failed_login(request: Request) -> None:
    settings = get_backend_deps(request).settings.admin
    fingerprint = _client_fingerprint(request)
    attempts_key = f"{_LOGIN_ATTEMPTS_KEY_PREFIX}:{fingerprint}"
    lock_key = f"{_LOGIN_LOCK_KEY_PREFIX}:{fingerprint}"
    now = time.time()

    attempts_payload = await _store_get_json(request, attempts_key) or {"attempts": []}
    attempts = [
        float(value)
        for value in attempts_payload.get("attempts", [])
        if now - float(value) <= max(1, settings.login_attempt_window_seconds)
    ]
    attempts.append(now)

    if len(attempts) >= max(1, settings.login_max_attempts):
        locked_until = now + max(1, settings.login_lockout_seconds)
        await _store_set_json(
            request,
            lock_key,
            {"locked_until": locked_until},
            ttl_seconds=max(1, settings.login_lockout_seconds),
        )
        await _store_delete(request, attempts_key)
        return

    await _store_set_json(
        request,
        attempts_key,
        {"attempts": attempts},
        ttl_seconds=max(1, settings.login_attempt_window_seconds),
    )


async def _clear_failed_login_state(request: Request) -> None:
    fingerprint = _client_fingerprint(request)
    await _store_delete(request, f"{_LOGIN_ATTEMPTS_KEY_PREFIX}:{fingerprint}")
    await _store_delete(request, f"{_LOGIN_LOCK_KEY_PREFIX}:{fingerprint}")


async def create_admin_session(
    request: Request,
    *,
    token: str,
    actor: str | None,
) -> AdminPrincipal:
    settings = get_backend_deps(request).settings
    admin_settings = settings.admin

    if not admin_settings.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    await _assert_login_not_locked(request)

    expected_token = str(admin_settings.token or "").strip()
    provided_token = str(token or "").strip()
    expected_token_bytes = expected_token.encode("utf-8") if expected_token else b""
    provided_token_bytes = provided_token.encode("utf-8") if provided_token else b""
    if (
        not expected_token_bytes
        or not provided_token_bytes
        or not secrets.compare_digest(provided_token_bytes, expected_token_bytes)
    ):
        await _record_failed_login(request)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    await _clear_failed_login_state(request)

    role = admin_settings.default_role if admin_settings.default_role in ROLE_ORDER else "superadmin"
    return await create_admin_session_for_actor(
        request,
        actor=_normalize_actor(actor),
        role=role,
    )


async def create_admin_session_for_actor(
    request: Request,
    *,
    actor: str,
    role: str,
) -> AdminPrincipal:
    settings = get_backend_deps(request).settings.admin
    normalized_role = role if role in ROLE_ORDER else "superadmin"
    principal = AdminPrincipal(actor=_normalize_actor(actor), role=normalized_role)
    session_id = secrets.token_urlsafe(32)
    session_key = f"{_SESSION_KEY_PREFIX}:{session_id}"
    ttl_seconds = max(300, int(settings.session_ttl_minutes) * 60)

    await _store_set_json(
        request,
        session_key,
        {
            "actor": principal.actor,
            "role": principal.role,
            "created_at": int(time.time()),
        },
        ttl_seconds=ttl_seconds,
    )
    setattr(request.state, "admin_session_id", session_id)
    return principal


async def destroy_admin_session(request: Request, session_id: str | None) -> None:
    if not session_id:
        return
    await _store_delete(request, f"{_SESSION_KEY_PREFIX}:{session_id}")


def attach_admin_session_cookie(request: Request, response: Response) -> None:
    settings = get_backend_deps(request).settings.admin
    session_id = getattr(request.state, "admin_session_id", None)
    if not session_id:
        return

    response.set_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        value=session_id,
        max_age=max(300, int(settings.session_ttl_minutes) * 60),
        httponly=True,
        secure=_cookie_secure(request),
        samesite=_cookie_samesite(request),
        path=_cookie_path(request),
    )


def clear_admin_session_cookie(request: Request, response: Response) -> None:
    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        path=_cookie_path(request),
        secure=_cookie_secure(request),
        samesite=_cookie_samesite(request),
        httponly=True,
    )


async def _require_role(
    request: Request,
    minimum_role: str,
    session_id: str | None,
) -> AdminPrincipal:
    settings = get_backend_deps(request).settings
    admin_settings = settings.admin

    if not admin_settings.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    session_payload = await _store_get_json(
        request,
        f"{_SESSION_KEY_PREFIX}:{normalized_session_id}",
    )
    if not session_payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    role = str(session_payload.get("role") or "").strip().lower()
    if role not in ROLE_ORDER:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if ROLE_ORDER[role] < ROLE_ORDER[minimum_role]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient admin role")

    return AdminPrincipal(
        actor=_normalize_actor(session_payload.get("actor")),
        role=role,
    )


async def require_superadmin(
    request: Request,
    admin_session_id: str | None = Cookie(default=None, alias=ADMIN_SESSION_COOKIE_NAME),
    _x_admin_token: str | None = Header(default=None),
) -> AdminPrincipal:
    return await _require_role(
        request=request,
        minimum_role="superadmin",
        session_id=admin_session_id,
    )


RequireSuperadmin = Depends(require_superadmin)
