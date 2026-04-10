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
from backend.schemas.admin.admin_schemas import (
    AdminAccessRequestReviewRequest,
    AdminAccessRegistryBatchUpsertRequest,
    AdminAccessRegistryUpdateRequest,
    AdminAccessRegistryUpsertRequest,
    AdminActionRequest,
    AdminLoginRequest,
)


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


@pytest.mark.asyncio
async def test_list_access_requests_delegates_to_service():
    service = AsyncMock()
    service.list_requests.return_value = [{"id": 1, "status": "pending"}]

    result = await admin_routes.list_access_requests(
        status_name="pending",
        limit=20,
        _principal=SimpleNamespace(actor="qa-admin", role="superadmin"),
        service=service,
    )

    service.list_requests.assert_awaited_once_with(status_name="pending", limit=20)
    assert result == {"items": [{"id": 1, "status": "pending"}]}


@pytest.mark.asyncio
async def test_review_access_request_delegates_to_service():
    service = AsyncMock()
    service.review_request.return_value = {"id": 4, "status": "approved"}
    principal = SimpleNamespace(actor="qa-admin", role="superadmin")

    result = await admin_routes.review_access_request(
        request_id=4,
        payload=AdminAccessRequestReviewRequest(
            decision="approve",
            review_note="ok",
            template_code="month_1",
        ),
        principal=principal,
        service=service,
    )

    service.review_request.assert_awaited_once_with(
        request_id=4,
        decision="approve",
        principal=principal,
        review_note="ok",
        template_code="month_1",
    )
    assert result == {"id": 4, "status": "approved"}


@pytest.mark.asyncio
async def test_list_access_registry_entries_delegates_to_service(monkeypatch):
    monkeypatch.setattr(
        admin_routes,
        "get_effective_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=True),
    )
    service = AsyncMock()
    service.list_entries.return_value = [{"id": 1, "identity_type": "telegram_id"}]

    result = await admin_routes.list_access_registry_entries(
        limit=50,
        _principal=SimpleNamespace(actor="qa-admin", role="superadmin"),
        service=service,
    )

    service.list_entries.assert_awaited_once_with(limit=50)
    assert result == {"items": [{"id": 1, "identity_type": "telegram_id"}]}


@pytest.mark.asyncio
async def test_upsert_access_registry_entry_delegates_to_service(monkeypatch):
    monkeypatch.setattr(
        admin_routes,
        "get_effective_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=True),
    )
    service = AsyncMock()
    service.upsert_entry.return_value = {"id": 2, "identity_type": "email"}
    principal = SimpleNamespace(actor="qa-admin", role="superadmin")

    result = await admin_routes.upsert_access_registry_entry(
        payload=AdminAccessRegistryUpsertRequest(
            identity_type="email",
            identity_value="user@example.com",
            auto_approve=True,
            is_active=True,
            note="corp",
        ),
        principal=principal,
        service=service,
    )

    service.upsert_entry.assert_awaited_once_with(
        identity_type="email",
        identity_value="user@example.com",
        template_code="month_1",
        priority=100,
        auto_approve=True,
        allow_auto_renew=False,
        is_active=True,
        note="corp",
        valid_from=None,
        valid_until=None,
        principal=principal,
    )
    assert result == {"id": 2, "identity_type": "email"}


@pytest.mark.asyncio
async def test_batch_upsert_access_registry_entry_delegates_to_service(monkeypatch):
    monkeypatch.setattr(
        admin_routes,
        "get_effective_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=True),
    )
    service = AsyncMock()
    service.batch_upsert_entries.return_value = [{"id": 2, "is_active": True}]
    principal = SimpleNamespace(actor="qa-admin", role="superadmin")

    result = await admin_routes.batch_upsert_access_registry_entries(
        payload=AdminAccessRegistryBatchUpsertRequest(
            identities_text="123 user@example.com",
            allow_auto_renew=True,
        ),
        principal=principal,
        service=service,
    )

    service.batch_upsert_entries.assert_awaited_once_with(
        identities_text="123 user@example.com",
        priority=100,
        auto_approve=True,
        allow_auto_renew=True,
        is_active=True,
        note=None,
        valid_from=None,
        valid_until=None,
        principal=principal,
    )
    assert result == {"items": [{"id": 2, "is_active": True}]}


@pytest.mark.asyncio
async def test_update_access_registry_entry_delegates_to_service(monkeypatch):
    monkeypatch.setattr(
        admin_routes,
        "get_effective_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=True),
    )
    service = AsyncMock()
    service.update_entry.return_value = {"id": 2, "is_active": False}
    principal = SimpleNamespace(actor="qa-admin", role="superadmin")

    result = await admin_routes.update_access_registry_entry(
        entry_id=2,
        payload=AdminAccessRegistryUpdateRequest(
            identity_type="telegram_id",
            identity_value="123",
            auto_approve=True,
            allow_auto_renew=False,
            is_active=False,
            note="corp",
        ),
        principal=principal,
        service=service,
    )

    service.update_entry.assert_awaited_once_with(
        entry_id=2,
        identity_type="telegram_id",
        identity_value="123",
        priority=100,
        auto_approve=True,
        allow_auto_renew=False,
        is_active=False,
        note="corp",
        valid_from=None,
        valid_until=None,
        principal=principal,
    )
    assert result == {"id": 2, "is_active": False}


@pytest.mark.asyncio
async def test_disable_access_registry_entry_and_revoke_access_delegates_to_services(monkeypatch):
    monkeypatch.setattr(
        admin_routes,
        "get_effective_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=True),
    )
    registry_service = AsyncMock()
    registry_service.set_entry_active.return_value = {
        "id": 2,
        "identity_type": "telegram_id",
        "identity_value": "123",
        "is_active": False,
    }
    admin_service = AsyncMock()
    admin_service.disable_registry_entry_and_revoke_access.return_value = {
        "matched_users": 1,
        "revoked_grants": 1,
        "runtime_revocations": 1,
    }
    principal = SimpleNamespace(actor="qa-admin", role="superadmin")

    result = await admin_routes.disable_access_registry_entry_and_revoke_access(
        entry_id=2,
        principal=principal,
        registry_service=registry_service,
        admin_service=admin_service,
    )

    registry_service.set_entry_active.assert_awaited_once_with(
        entry_id=2,
        is_active=False,
        principal=principal,
    )
    admin_service.disable_registry_entry_and_revoke_access.assert_awaited_once_with(
        entry_id=2,
        identity_type="telegram_id",
        identity_value="123",
        principal=principal,
    )
    assert result == {
        "entry": {
            "id": 2,
            "identity_type": "telegram_id",
            "identity_value": "123",
            "is_active": False,
        },
        "matched_users": 1,
        "revoked_grants": 1,
        "runtime_revocations": 1,
    }


@pytest.mark.asyncio
async def test_delete_access_registry_entry_delegates_to_service(monkeypatch):
    monkeypatch.setattr(
        admin_routes,
        "get_effective_product_feature_settings",
        lambda: SimpleNamespace(access_registry_enabled=True),
    )
    service = AsyncMock()

    result = await admin_routes.delete_access_registry_entry(
        entry_id=2,
        _principal=SimpleNamespace(actor="qa-admin", role="superadmin"),
        service=service,
    )

    service.delete_entry.assert_awaited_once_with(entry_id=2)
    assert result == {"status": "ok"}
