from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from backend.auth.web_auth import WEB_SESSION_COOKIE_NAME
from backend.routers.auth import auth_routes
from backend.schemas.auth.auth_schemas import (
    WebEmailRequest,
    WebLoginRequest,
    WebPasswordResetRequest,
    WebPublicLinkLoginRequest,
    WebRegisterVerifyRequest,
)


def make_request(*, headers: dict[str, str] | None = None, scheme: str = "http"):
    deps = SimpleNamespace(
        settings=SimpleNamespace(
            backend_prefix="/api",
            auth=SimpleNamespace(web_session_ttl_minutes=60),
        )
    )
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(deps=deps)),
        headers={"user-agent": "pytest-agent", **(headers or {})},
        cookies={WEB_SESSION_COOKIE_NAME: "cookie-token"},
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(scheme=scheme),
    )


@pytest.mark.asyncio
async def test_login_web_session_sets_cookie_and_calls_service():
    request = make_request()
    response = Response()
    auth_service = AsyncMock()
    auth_service.login.return_value = SimpleNamespace(raw_token="raw-session-token")

    result = await auth_routes.login_web_session(
        payload=WebLoginRequest(
            email="user@example.com",
            password="secret",
            device_name="pytest-browser",
        ),
        request=request,
        response=response,
        auth_service=auth_service,
    )

    auth_service.login.assert_awaited_once_with(
        email="user@example.com",
        password="secret",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_name="pytest-browser",
    )
    assert result == {"status": "ok"}
    assert WEB_SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_login_web_session_from_telegram_link_sets_cookie_and_calls_service():
    request = make_request()
    response = Response()
    auth_service = AsyncMock()
    auth_service.login_via_telegram_link.return_value = SimpleNamespace(raw_token="raw-session-token")

    result = await auth_routes.login_web_session_from_telegram_link(
        payload=WebPublicLinkLoginRequest(
            token="token-12345678",
            device_name="telegram_link",
        ),
        request=request,
        response=response,
        auth_service=auth_service,
    )

    auth_service.login_via_telegram_link.assert_awaited_once_with(
        raw_token="token-12345678",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_name="telegram_link",
    )
    assert result == {"status": "ok"}
    assert WEB_SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_login_web_session_from_telegram_link_sets_cross_site_cookie_for_https_proxy():
    request = make_request(headers={"x-forwarded-proto": "https"}, scheme="http")
    response = Response()
    auth_service = AsyncMock()
    auth_service.login_via_telegram_link.return_value = SimpleNamespace(raw_token="raw-session-token")

    await auth_routes.login_web_session_from_telegram_link(
        payload=WebPublicLinkLoginRequest(
            token="token-12345678",
            device_name="telegram_link",
        ),
        request=request,
        response=response,
        auth_service=auth_service,
    )

    cookie_header = response.headers.get("set-cookie", "")
    assert WEB_SESSION_COOKIE_NAME in cookie_header
    assert "Secure" in cookie_header
    assert "SameSite=none" in cookie_header or "SameSite=None" in cookie_header
    assert "Path=/api" in cookie_header


@pytest.mark.asyncio
async def test_logout_web_session_revokes_cookie_session():
    request = make_request()
    response = Response()
    auth_service = AsyncMock()

    result = await auth_routes.logout_web_session(
        request=request,
        response=response,
        auth_service=auth_service,
    )

    auth_service.logout.assert_awaited_once_with("cookie-token")
    assert result == {"status": "ok"}
    assert WEB_SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_start_web_registration_calls_service():
    request = make_request()
    auth_service = AsyncMock()
    auth_service.start_registration.return_value = False

    result = await auth_routes.start_web_registration(
        payload=WebEmailRequest(email="user@example.com"),
        request=request,
        auth_service=auth_service,
    )

    auth_service.start_registration.assert_awaited_once_with(
        email="user@example.com",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
    )
    assert result == {"status": "ok", "verification_required": False}


@pytest.mark.asyncio
async def test_resend_web_registration_code_calls_service():
    request = make_request()
    auth_service = AsyncMock()
    auth_service.resend_registration.return_value = True

    result = await auth_routes.resend_web_registration_code(
        payload=WebEmailRequest(email="user@example.com"),
        request=request,
        auth_service=auth_service,
    )

    auth_service.resend_registration.assert_awaited_once_with(
        email="user@example.com",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
    )
    assert result == {"status": "ok", "verification_required": True}


@pytest.mark.asyncio
async def test_verify_web_registration_sets_cookie_and_calls_service():
    request = make_request()
    response = Response()
    auth_service = AsyncMock()
    auth_service.verify_registration.return_value = SimpleNamespace(raw_token="new-token")

    result = await auth_routes.verify_web_registration(
        payload=WebRegisterVerifyRequest(
            email="user@example.com",
            code="123456",
            password="supersecret",
            device_name="pytest-browser",
        ),
        request=request,
        response=response,
        auth_service=auth_service,
    )

    auth_service.verify_registration.assert_awaited_once_with(
        email="user@example.com",
        code="123456",
        password="supersecret",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_name="pytest-browser",
    )
    assert result == {"status": "ok"}
    assert WEB_SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_start_password_reset_calls_service():
    request = make_request()
    auth_service = AsyncMock()

    result = await auth_routes.start_password_reset(
        payload=WebEmailRequest(email="user@example.com"),
        request=request,
        auth_service=auth_service,
    )

    auth_service.start_password_reset.assert_awaited_once_with(
        email="user@example.com",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
    )
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_reset_password_calls_service():
    auth_service = AsyncMock()

    result = await auth_routes.reset_password(
        payload=WebPasswordResetRequest(
            email="user@example.com",
            code="654321",
            new_password="strong-new-password",
        ),
        auth_service=auth_service,
    )

    auth_service.reset_password.assert_awaited_once_with(
        email="user@example.com",
        code="654321",
        new_password="strong-new-password",
    )
    assert result == {"status": "ok"}
