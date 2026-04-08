from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from backend.auth.web_auth import WEB_SESSION_COOKIE_NAME, attach_web_session_cookie, clear_web_session_cookie
from backend.bootstrap import get_auth_service
from backend.schemas.auth.auth_schemas import (
    WebEmailRequest,
    WebLoginRequest,
    WebPasswordResetRequest,
    WebPublicLinkLoginRequest,
    WebRegisterVerifyRequest,
)
from backend.services.auth.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    forwarded_for = str(request.headers.get("x-forwarded-for", "")).strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    return getattr(getattr(request, "client", None), "host", None)


@router.post("/login")
async def login_web_session(
    payload: WebLoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    session = await auth_service.login(
        email=payload.email,
        password=payload.password,
        ip_address=_client_ip(request),
        user_agent=str(request.headers.get("user-agent", "")).strip() or None,
        device_name=payload.device_name,
    )
    attach_web_session_cookie(
        request,
        response,
        session_token=session.raw_token,
        ttl_minutes=getattr(request.app.state.deps.settings.auth, "web_session_ttl_minutes", 43200),
    )
    return {"status": "ok"}


@router.post("/link/telegram/login")
async def login_web_session_from_telegram_link(
    payload: WebPublicLinkLoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    session = await auth_service.login_via_telegram_link(
        raw_token=payload.token,
        ip_address=_client_ip(request),
        user_agent=str(request.headers.get("user-agent", "")).strip() or None,
        device_name=payload.device_name,
    )
    attach_web_session_cookie(
        request,
        response,
        session_token=session.raw_token,
        ttl_minutes=getattr(request.app.state.deps.settings.auth, "web_session_ttl_minutes", 43200),
    )
    return {"status": "ok"}


@router.post("/register/start", status_code=status.HTTP_200_OK)
async def start_web_registration(
    payload: WebEmailRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    verification_required = await auth_service.start_registration(
        email=payload.email,
        ip_address=_client_ip(request),
        user_agent=str(request.headers.get("user-agent", "")).strip() or None,
    )
    return {"status": "ok", "verification_required": verification_required}


@router.post("/register/resend", status_code=status.HTTP_200_OK)
async def resend_web_registration_code(
    payload: WebEmailRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    verification_required = await auth_service.resend_registration(
        email=payload.email,
        ip_address=_client_ip(request),
        user_agent=str(request.headers.get("user-agent", "")).strip() or None,
    )
    return {"status": "ok", "verification_required": verification_required}


@router.post("/register/verify", status_code=status.HTTP_200_OK)
async def verify_web_registration(
    payload: WebRegisterVerifyRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    session = await auth_service.verify_registration(
        email=payload.email,
        code=payload.code,
        password=payload.password,
        ip_address=_client_ip(request),
        user_agent=str(request.headers.get("user-agent", "")).strip() or None,
        device_name=payload.device_name,
    )
    attach_web_session_cookie(
        request,
        response,
        session_token=session.raw_token,
        ttl_minutes=getattr(request.app.state.deps.settings.auth, "web_session_ttl_minutes", 43200),
    )
    return {"status": "ok"}


@router.post("/password/forgot", status_code=status.HTTP_200_OK)
async def start_password_reset(
    payload: WebEmailRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    await auth_service.start_password_reset(
        email=payload.email,
        ip_address=_client_ip(request),
        user_agent=str(request.headers.get("user-agent", "")).strip() or None,
    )
    return {"status": "ok"}


@router.post("/password/reset", status_code=status.HTTP_200_OK)
async def reset_password(
    payload: WebPasswordResetRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    await auth_service.reset_password(
        email=payload.email,
        code=payload.code,
        new_password=payload.new_password,
    )
    return {"status": "ok"}


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout_web_session(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    await auth_service.logout(request.cookies.get(WEB_SESSION_COOKIE_NAME))
    clear_web_session_cookie(request, response)
    return {"status": "ok"}
