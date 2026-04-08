from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Response

from backend.admin.auth import (
    ADMIN_SESSION_COOKIE_NAME,
    attach_admin_session_cookie,
    create_admin_session,
    require_superadmin,
)
from backend.routers.admin import admin_routes
from backend.schemas.admin.admin_schemas import AdminActionRequest, AdminLoginRequest


def make_request(*, token: str = "secret-token", role: str = "superadmin", enabled: bool = True):
    settings = SimpleNamespace(
        backend_prefix="/test-api",
        admin=SimpleNamespace(
            enabled=enabled,
            token=token,
            default_role=role,
            session_ttl_minutes=60,
            login_attempt_window_seconds=300,
            login_max_attempts=3,
            login_lockout_seconds=600,
        ),
    )
    deps = SimpleNamespace(settings=settings)
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(deps=deps, redis_client=None)),
        state=SimpleNamespace(),
        headers={"user-agent": f"pytest-{id(settings)}"},
        cookies={},
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(scheme="http"),
    )


def make_https_request(*, token: str = "secret-token", role: str = "superadmin", enabled: bool = True):
    request = make_request(token=token, role=role, enabled=enabled)
    request.headers["x-forwarded-proto"] = "https"
    request.url = SimpleNamespace(scheme="https")
    return request


@pytest.mark.asyncio
async def test_create_admin_session_and_require_superadmin_accept_valid_cookie():
    request = make_request()

    principal = await create_admin_session(
        request,
        token="secret-token",
        actor="qa-admin",
    )
    response = Response()
    attach_admin_session_cookie(request, response)
    cookie_header = response.headers.get("set-cookie", "")
    session_id = cookie_header.split(f"{ADMIN_SESSION_COOKIE_NAME}=", 1)[1].split(";", 1)[0]

    resolved = await require_superadmin(
        request=request,
        admin_session_id=session_id,
    )

    assert principal.actor == "qa-admin"
    assert resolved.actor == "qa-admin"
    assert resolved.role == "superadmin"


@pytest.mark.asyncio
async def test_create_admin_session_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        await create_admin_session(
            make_request(),
            token="wrong-token",
            actor="qa-admin",
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_admin_session_accepts_non_ascii_token():
    request = make_request(token="админ-пароль")

    principal = await create_admin_session(
        request,
        token="админ-пароль",
        actor="qa-admin",
    )

    assert principal.actor == "qa-admin"
    assert principal.role == "superadmin"


@pytest.mark.asyncio
async def test_create_admin_session_locks_after_repeated_failures():
    request = make_request()

    for _ in range(3):
        with pytest.raises(HTTPException):
            await create_admin_session(
                request,
                token="wrong-token",
                actor="qa-admin",
            )

    with pytest.raises(HTTPException) as exc_info:
        await create_admin_session(
            request,
            token="secret-token",
            actor="qa-admin",
        )

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_login_admin_session_sets_cookie():
    request = make_request()
    response = Response()

    result = await admin_routes.login_admin_session(
        payload=AdminLoginRequest(token="secret-token", actor="qa-admin"),
        request=request,
        response=response,
    )

    assert result == {"status": "ok", "actor": "qa-admin", "role": "superadmin"}
    assert ADMIN_SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_login_admin_session_sets_cross_site_cookie_for_https():
    request = make_https_request()
    response = Response()

    await admin_routes.login_admin_session(
        payload=AdminLoginRequest(token="secret-token", actor="qa-admin"),
        request=request,
        response=response,
    )

    cookie_header = response.headers.get("set-cookie", "")
    assert "SameSite=none" in cookie_header or "SameSite=None" in cookie_header
    assert "Secure" in cookie_header


@pytest.mark.asyncio
async def test_get_admin_overview_includes_actor():
    service = AsyncMock()
    service.get_overview.return_value = {"stats": {"total_users": 10}}
    principal = SimpleNamespace(actor="qa-admin", role="superadmin")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis_client=None)))

    result = await admin_routes.get_admin_overview(
        request=request,
        principal=principal,
        service=service,
    )

    service.get_overview.assert_awaited_once_with(None)
    assert result["stats"]["total_users"] == 10
    assert result["actor"] == "qa-admin"


@pytest.mark.asyncio
async def test_post_admin_action_delegates_to_service():
    service = AsyncMock()
    service.execute_action.return_value = {"status": "success", "summary": "done"}
    principal = SimpleNamespace(actor="qa-admin", role="superadmin")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis_client=None)))
    payload = AdminActionRequest(
        action_type="extend_subscription",
        target_user_id=77,
        target_tg_id=123,
        reason="support",
        dry_run=True,
        params={"period": "month1"},
    )

    result = await admin_routes.post_admin_action(
        payload=payload,
        request=request,
        principal=principal,
        service=service,
    )

    service.execute_action.assert_awaited_once_with(
        principal=principal,
        action_type="extend_subscription",
        target_user_id=77,
        target_tg_id=123,
        reason="support",
        dry_run=True,
        params={"period": "month1"},
        redis_client=None,
    )
    assert result == {"status": "success", "summary": "done"}
