from __future__ import annotations

from dataclasses import asdict, is_dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from backend.admin.auth import (
    ADMIN_SESSION_COOKIE_NAME,
    AdminPrincipal,
    attach_admin_session_cookie,
    clear_admin_session_cookie,
    create_admin_session,
    create_admin_session_for_actor,
    destroy_admin_session,
    require_superadmin,
)
from backend.bootstrap import (
    get_access_registry_service,
    get_access_request_service,
    get_admin_service,
)
from backend.schemas.admin.admin_schemas import (
    AdminActionRequest,
    AdminAccessRegistryBatchUpsertRequest,
    AdminAccessRequestReviewRequest,
    AdminAccessRegistryUpdateRequest,
    AdminAccessRegistryUpsertRequest,
    AdminLoginRequest,
    AdminPromoCreateRequest,
    AdminPromoToggleRequest,
)
from backend.services.admin.admin_service import AdminService
from shared.config.config import BOT_ADMIN_IDS, FRONTEND_ADMIN_LINK
from shared.config.settings import get_effective_product_feature_settings
from shared.utils.admin_access_link import consume_admin_bootstrap_token
from shared.services.access.access_request_service import AccessRequestService
from shared.services.access.access_registry_service import AccessRegistryService

router = APIRouter(prefix="/admin", tags=["admin"])


def _serialize_payload(value):
    if is_dataclass(value):
        return asdict(value)
    return value


def _require_promos_enabled() -> None:
    if not get_effective_product_feature_settings().promos_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo module is disabled")


def _require_access_registry_enabled() -> None:
    if not get_effective_product_feature_settings().access_registry_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access registry module is disabled")


@router.post("/session/login")
async def login_admin_session(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
):
    principal = await create_admin_session(
        request,
        token=payload.token,
        actor=payload.actor,
    )
    attach_admin_session_cookie(request, response)
    return {"status": "ok", "actor": principal.actor, "role": principal.role}


@router.post("/session/logout", status_code=204)
async def logout_admin_session(
    request: Request,
    response: Response,
):
    await destroy_admin_session(
        request,
        request.cookies.get(ADMIN_SESSION_COOKIE_NAME),
    )
    clear_admin_session_cookie(request, response)
    response.status_code = 204
    return None


@router.get("/session/me")
async def get_admin_session_me(
    principal: AdminPrincipal = Depends(require_superadmin),
):
    return {"actor": principal.actor, "role": principal.role}


@router.get("/session/bootstrap")
async def bootstrap_admin_session(
    request: Request,
    grant: str = Query(min_length=1),
):
    redis_client = getattr(request.app.state, "redis_client", None)
    deps = request.app.state.deps
    claims = await consume_admin_bootstrap_token(
        jwt_encoder=deps.jwt_encoder,
        token=grant,
        redis_client=redis_client,
    )
    if not claims:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    tg_id = int(claims.get("tg_id") or 0)
    if tg_id not in BOT_ADMIN_IDS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if not FRONTEND_ADMIN_LINK:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin frontend is unavailable")

    principal = await create_admin_session_for_actor(
        request,
        actor=str(claims.get("actor") or f"telegram-admin-{tg_id}"),
        role=deps.settings.admin.default_role,
    )
    response = RedirectResponse(url=FRONTEND_ADMIN_LINK, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    attach_admin_session_cookie(request, response)
    response.headers["cache-control"] = "no-store"
    response.headers["x-admin-actor"] = principal.actor
    return response


@router.get("/overview")
async def get_admin_overview(
    request: Request,
    principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    payload = await service.get_overview(getattr(request.app.state, "redis_client", None))
    payload["actor"] = principal.actor
    return payload


@router.get("/users")
async def search_admin_users(
    q: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    return {"items": await service.search_users(q, limit=limit)}


@router.get("/users/{user_id}")
async def get_admin_user_360(
    user_id: int,
    request: Request,
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    return await service.get_user_360(user_id, getattr(request.app.state, "redis_client", None))


@router.get("/users/{user_id}/diagnostics")
async def get_admin_user_diagnostics(
    user_id: int,
    request: Request,
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    return await service.get_user_diagnostics(user_id, getattr(request.app.state, "redis_client", None))


@router.get("/users/{user_id}/playbooks")
async def get_admin_user_playbooks(
    user_id: int,
    request: Request,
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    return {
        "items": await service.get_user_playbooks(
            user_id,
            getattr(request.app.state, "redis_client", None),
        )
    }


@router.get("/audit")
async def get_admin_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    target_tg_id: int | None = Query(default=None),
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    return {"items": await service.list_audit_logs(limit=limit, target_tg_id=target_tg_id)}


@router.post("/actions")
async def post_admin_action(
    payload: AdminActionRequest,
    request: Request,
    principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    return await service.execute_action(
        principal=principal,
        action_type=payload.action_type,
        target_user_id=payload.target_user_id,
        target_tg_id=payload.target_tg_id,
        reason=payload.reason,
        dry_run=payload.dry_run,
        params=payload.params,
        redis_client=getattr(request.app.state, "redis_client", None),
    )


@router.get("/access-requests")
async def list_access_requests(
    status_name: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AccessRequestService = Depends(get_access_request_service),
):
    return {
        "items": [_serialize_payload(item) for item in await service.list_requests(status_name=status_name, limit=limit)]
    }


@router.post("/access-requests/{request_id}/review")
async def review_access_request(
    request_id: int,
    payload: AdminAccessRequestReviewRequest,
    principal: AdminPrincipal = Depends(require_superadmin),
    service: AccessRequestService = Depends(get_access_request_service),
):
    result = await service.review_request(
        request_id=request_id,
        decision=payload.decision,
        principal=principal,
        review_note=payload.review_note,
        template_code=payload.template_code,
    )
    return _serialize_payload(result)


@router.get("/access-registry")
async def list_access_registry_entries(
    limit: int = Query(default=200, ge=1, le=500),
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AccessRegistryService = Depends(get_access_registry_service),
):
    _require_access_registry_enabled()
    return {"items": [_serialize_payload(item) for item in await service.list_entries(limit=limit)]}


@router.post("/access-registry")
async def upsert_access_registry_entry(
    payload: AdminAccessRegistryUpsertRequest,
    principal: AdminPrincipal = Depends(require_superadmin),
    service: AccessRegistryService = Depends(get_access_registry_service),
):
    _require_access_registry_enabled()
    return _serialize_payload(
        await service.upsert_entry(
            identity_type=payload.identity_type,
            identity_value=payload.identity_value,
            template_code="month_1",
            priority=100,
            auto_approve=payload.auto_approve,
            allow_auto_renew=payload.allow_auto_renew,
            is_active=payload.is_active,
            note=payload.note,
            valid_from=None,
            valid_until=None,
            principal=principal,
        )
    )


@router.post("/access-registry/batch")
async def batch_upsert_access_registry_entries(
    payload: AdminAccessRegistryBatchUpsertRequest,
    principal: AdminPrincipal = Depends(require_superadmin),
    service: AccessRegistryService = Depends(get_access_registry_service),
):
    _require_access_registry_enabled()
    return {
        "items": [
            _serialize_payload(item)
            for item in await service.batch_upsert_entries(
                identities_text=payload.identities_text,
                priority=100,
                auto_approve=payload.auto_approve,
                allow_auto_renew=payload.allow_auto_renew,
                is_active=payload.is_active,
                note=payload.note,
                valid_from=None,
                valid_until=None,
                principal=principal,
            )
        ]
    }


@router.patch("/access-registry/{entry_id}")
async def update_access_registry_entry(
    entry_id: int,
    payload: AdminAccessRegistryUpdateRequest,
    principal: AdminPrincipal = Depends(require_superadmin),
    service: AccessRegistryService = Depends(get_access_registry_service),
):
    _require_access_registry_enabled()
    return _serialize_payload(
        await service.update_entry(
            entry_id=entry_id,
            identity_type=payload.identity_type,
            identity_value=payload.identity_value,
            priority=100,
            auto_approve=payload.auto_approve,
            allow_auto_renew=payload.allow_auto_renew,
            is_active=payload.is_active,
            note=payload.note,
            valid_from=None,
            valid_until=None,
            principal=principal,
        )
    )


@router.post("/access-registry/{entry_id}/disable-and-revoke")
async def disable_access_registry_entry_and_revoke_access(
    entry_id: int,
    principal: AdminPrincipal = Depends(require_superadmin),
    registry_service: AccessRegistryService = Depends(get_access_registry_service),
    admin_service: AdminService = Depends(get_admin_service),
):
    _require_access_registry_enabled()
    entry = await registry_service.set_entry_active(
        entry_id=entry_id,
        is_active=False,
        principal=principal,
    )
    identity_type = entry.identity_type if hasattr(entry, "identity_type") else entry["identity_type"]
    identity_value = entry.identity_value if hasattr(entry, "identity_value") else entry["identity_value"]
    revoke_result = await admin_service.disable_registry_entry_and_revoke_access(
        entry_id=entry_id,
        identity_type=identity_type,
        identity_value=identity_value,
        principal=principal,
    )
    return {
        "entry": _serialize_payload(entry),
        **revoke_result,
    }


@router.delete("/access-registry/{entry_id}")
async def delete_access_registry_entry(
    entry_id: int,
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AccessRegistryService = Depends(get_access_registry_service),
):
    _require_access_registry_enabled()
    await service.delete_entry(entry_id=entry_id)
    return {"status": "ok"}


@router.get("/promos")
async def list_promo_codes(
    limit: int = Query(default=100, ge=1, le=500),
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    _require_promos_enabled()
    return {"items": await service.list_promo_codes(limit=limit)}


@router.post("/promos")
async def create_promo_code(
    payload: AdminPromoCreateRequest,
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    _require_promos_enabled()
    return await service.create_promo_code(
        code=payload.code,
        plan_id=payload.plan_id,
        duration_days_override=payload.duration_days_override,
        max_redemptions=payload.max_redemptions,
        per_user_limit=payload.per_user_limit,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
    )


@router.patch("/promos/{promo_id}")
async def toggle_promo_code(
    promo_id: int,
    payload: AdminPromoToggleRequest,
    _principal: AdminPrincipal = Depends(require_superadmin),
    service: AdminService = Depends(get_admin_service),
):
    _require_promos_enabled()
    return await service.toggle_promo_code(promo_id=promo_id, is_active=payload.is_active)
