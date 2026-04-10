from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from backend.services.auth import auth_service as auth_service_module
from backend.services.auth import web_auth_challenge_service as challenge_module
from backend.services.auth import web_session_service as web_session_service_module
from backend.services.auth.auth_service import AuthService
from backend.services.auth.password_hasher import PasswordHasher
from backend.services.auth.web_auth_challenge_service import (
    PASSWORD_RESET_PURPOSE,
    REGISTER_EMAIL_VERIFICATION_PURPOSE,
    WebAuthChallengeService,
)
from backend.services.auth.web_session_service import WebSessionService
from shared.infrastructure.identity_link_service import IdentityLinkService
from shared.models import register_models
from shared.models.users.app_user_model import AppUser
from shared.models.users.identity_link_token_model import IdentityLinkToken
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount
from shared.models.users.web_session_model import WebSession
from shared.utils.telegram_web_login_token import issue_telegram_web_login_token

DATABASE_URL = "sqlite+aiosqlite://"


@pytest.fixture
async def async_engine():
    register_models()
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session_factory(async_engine):
    return async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def auth_service(session_factory, monkeypatch):
    monkeypatch.setattr(auth_service_module, "async_session_factory", session_factory)
    monkeypatch.setattr(challenge_module, "async_session_factory", session_factory)
    monkeypatch.setattr(web_session_service_module, "async_session_factory", session_factory)

    challenge_service = WebAuthChallengeService(
        code_ttl_minutes=15,
        resend_cooldown_seconds=0,
        request_window_seconds=3600,
        max_requests_per_window_per_email=5,
        max_requests_per_window_per_ip=20,
        max_failed_attempts=5,
    )
    transactional_email_service = AsyncMock()
    service = AuthService(
        password_hasher=PasswordHasher(),
        session_service=WebSessionService(ttl_minutes=60),
        challenge_service=challenge_service,
        transactional_email_service=transactional_email_service,
        identity_link_service=IdentityLinkService(ttl_minutes=30),
        email_code_ttl_minutes=15,
        password_min_length=8,
        telegram_web_login_secret="secret-key",
    )
    return service, challenge_service, transactional_email_service


@pytest.mark.asyncio
async def test_start_registration_issues_challenge_and_sends_email(auth_service):
    service, _, transactional_email_service = auth_service

    await service.start_registration(
        email="User@example.com",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
    )

    transactional_email_service.send_verification_code.assert_awaited_once()
    kwargs = transactional_email_service.send_verification_code.await_args.kwargs
    assert kwargs["to_email"] == "user@example.com"
    assert len(kwargs["code"]) == 6


@pytest.mark.asyncio
async def test_verify_registration_creates_account_and_session(session_factory, auth_service):
    service, challenge_service, _ = auth_service
    issued = await challenge_service.issue_challenge(
        email="user@example.com",
        purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
        request_ip="127.0.0.1",
        request_user_agent="pytest-agent",
    )

    session_snapshot = await service.verify_registration(
        email="user@example.com",
        code=issued.code,
        password="supersecret",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_name="pytest-browser",
    )

    assert session_snapshot.user_id > 0
    assert session_snapshot.raw_token

    async with session_factory() as session:
        web_account = (
            await session.execute(select(WebAccount).where(WebAccount.email == "user@example.com"))
        ).scalar_one()
        assert web_account.email_verified_at is not None
        assert PasswordHasher().verify_password("supersecret", web_account.password_hash) is True
        web_sessions = (
            await session.execute(select(WebSession).where(WebSession.user_id == web_account.user_id))
        ).scalars().all()
        assert len(web_sessions) == 1


@pytest.mark.asyncio
async def test_login_via_telegram_link_keeps_link_token_valid_until_expiry(session_factory, auth_service):
    service, _, _ = auth_service
    now = auth_service_module.datetime.now(auth_service_module.timezone.utc)

    async with session_factory() as session:
        user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(user)
        await session.flush()
        issued = await service.identity_link_service.issue_token(
            session,
            user_id=int(user.id),
            purpose="link_web",
            issued_by_channel="telegram",
            metadata={},
        )
        await session.commit()

    first_session = await service.login_via_telegram_link(
        raw_token=issued.raw_token,
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_name="telegram-link",
    )
    second_session = await service.login_via_telegram_link(
        raw_token=issued.raw_token,
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_name="telegram-link",
    )

    assert first_session.raw_token
    assert second_session.raw_token

    async with session_factory() as session:
        token = (await session.execute(select(IdentityLinkToken))).scalar_one()
    assert token.used_at is None


@pytest.mark.asyncio
async def test_login_via_telegram_permanent_link_token(session_factory, auth_service):
    service, _, _ = auth_service
    now = auth_service_module.datetime.now(auth_service_module.timezone.utc)

    async with session_factory() as session:
        user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(user.id),
                telegram_id=6884511529,
                username="remote_access_support",
                linked_at=now,
                first_seen_at=now,
                last_seen_at=now,
                revoked_at=None,
            )
        )
        await session.commit()
        raw_token = issue_telegram_web_login_token(
            tg_id=6884511529,
            user_id=int(user.id),
            secret="secret-key",
        )

    session_snapshot = await service.login_via_telegram_link(
        raw_token=raw_token,
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_name="telegram-link",
    )

    assert session_snapshot.user_id > 0
    assert session_snapshot.raw_token


@pytest.mark.asyncio
async def test_login_via_telegram_link_rejects_blocked_user(session_factory, auth_service):
    service, _, _ = auth_service
    now = auth_service_module.datetime.now(auth_service_module.timezone.utc)

    async with session_factory() as session:
        user = AppUser(created_at=now, updated_at=now, blocked_at=now, deleted_at=None)
        session.add(user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(user.id),
                telegram_id=6884511529,
                username="remote_access_support",
                linked_at=now,
                first_seen_at=now,
                last_seen_at=now,
                revoked_at=None,
            )
        )
        await session.commit()
        raw_token = issue_telegram_web_login_token(
            tg_id=6884511529,
            user_id=int(user.id),
            secret="secret-key",
        )

    with pytest.raises(auth_service_module.HTTPException) as exc_info:
        await service.login_via_telegram_link(
            raw_token=raw_token,
            ip_address="127.0.0.1",
            user_agent="pytest-agent",
            device_name="telegram-link",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "User is blocked"


@pytest.mark.asyncio
async def test_reset_password_updates_hash_and_revokes_existing_sessions(session_factory, auth_service):
    service, challenge_service, _ = auth_service
    hasher = PasswordHasher()

    async with session_factory() as session:
        user = AppUser(created_at=auth_service_module.datetime.now(auth_service_module.timezone.utc), updated_at=auth_service_module.datetime.now(auth_service_module.timezone.utc), blocked_at=None, deleted_at=None)
        session.add(user)
        await session.flush()
        session.add(
            WebAccount(
                user_id=int(user.id),
                email="user@example.com",
                password_hash=hasher.hash_password("oldpassword"),
                email_verified_at=auth_service_module.datetime.now(auth_service_module.timezone.utc),
                linked_at=auth_service_module.datetime.now(auth_service_module.timezone.utc),
                last_login_at=None,
                revoked_at=None,
                created_at=auth_service_module.datetime.now(auth_service_module.timezone.utc),
                updated_at=auth_service_module.datetime.now(auth_service_module.timezone.utc),
            )
        )
        await session.commit()

    old_session = await service.session_service.create_session(
        user_id=1,
        ip_address="127.0.0.1",
        user_agent="pytest",
        device_name="pytest-browser",
    )
    assert old_session.raw_token

    issued = await challenge_service.issue_challenge(
        email="user@example.com",
        purpose=PASSWORD_RESET_PURPOSE,
        request_ip="127.0.0.1",
        request_user_agent="pytest-agent",
    )

    await service.reset_password(
        email="user@example.com",
        code=issued.code,
        new_password="newpassword",
    )

    async with session_factory() as session:
        web_account = (
            await session.execute(select(WebAccount).where(WebAccount.email == "user@example.com"))
        ).scalar_one()
        assert hasher.verify_password("newpassword", web_account.password_hash) is True
        sessions = (
            await session.execute(select(WebSession).where(WebSession.user_id == web_account.user_id))
        ).scalars().all()
        assert sessions
        assert all(row.revoked_at is not None for row in sessions)


@pytest.mark.asyncio
async def test_verify_registration_attaches_existing_telegram_first_user(session_factory, auth_service):
    service, challenge_service, _ = auth_service
    now = auth_service_module.datetime.now(auth_service_module.timezone.utc)

    async with session_factory() as session:
        user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(user.id),
                telegram_id=6884511529,
                username="remote_access_support",
                linked_at=now,
                first_seen_at=now,
                last_seen_at=now,
                revoked_at=None,
            )
        )
        session.add(
            UserProfile(
                user_id=int(user.id),
                display_name=None,
                timezone=None,
                locale=None,
                marketing_opt_in=False,
                preferred_contact_email="user@example.com",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    issued = await challenge_service.issue_challenge(
        email="user@example.com",
        purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
        request_ip="127.0.0.1",
        request_user_agent="pytest-agent",
    )

    session_snapshot = await service.verify_registration(
        email="user@example.com",
        code=issued.code,
        password="supersecret",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_name="pytest-browser",
    )

    async with session_factory() as session:
        web_account = (
            await session.execute(select(WebAccount).where(WebAccount.email == "user@example.com"))
        ).scalar_one()
        assert int(web_account.user_id) == int(session_snapshot.user_id)
        users = (await session.execute(select(AppUser))).scalars().all()
        assert len(users) == 1


@pytest.mark.asyncio
async def test_verify_registration_without_email_confirmation_when_noop_mail(monkeypatch, session_factory):
    monkeypatch.setattr(auth_service_module, "async_session_factory", session_factory)
    monkeypatch.setattr(challenge_module, "async_session_factory", session_factory)
    monkeypatch.setattr(web_session_service_module, "async_session_factory", session_factory)

    challenge_service = WebAuthChallengeService(
        code_ttl_minutes=15,
        resend_cooldown_seconds=0,
        request_window_seconds=3600,
        max_requests_per_window_per_email=5,
        max_requests_per_window_per_ip=20,
        max_failed_attempts=5,
    )
    transactional_email_service = SimpleNamespace(
        delivery_service=SimpleNamespace(
            settings=SimpleNamespace(enabled=False, provider="noop"),
        ),
        send_verification_code=AsyncMock(),
    )
    service = AuthService(
        password_hasher=PasswordHasher(),
        session_service=WebSessionService(ttl_minutes=60),
        challenge_service=challenge_service,
        transactional_email_service=transactional_email_service,
        identity_link_service=IdentityLinkService(ttl_minutes=30),
        email_code_ttl_minutes=15,
        password_min_length=8,
        telegram_web_login_secret="secret-key",
    )

    verification_required = await service.start_registration(
        email="user@example.com",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
    )

    assert verification_required is False
    transactional_email_service.send_verification_code.assert_not_awaited()

    session_snapshot = await service.verify_registration(
        email="user@example.com",
        code="",
        password="supersecret",
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_name="pytest-browser",
    )

    assert session_snapshot.user_id > 0

    async with session_factory() as session:
        web_account = (
            await session.execute(select(WebAccount).where(WebAccount.email == "user@example.com"))
        ).scalar_one()
        assert web_account.email_verified_at is not None
