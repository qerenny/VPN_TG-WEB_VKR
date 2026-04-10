from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import telegram_bot.services.linking.telegram_link_service as telegram_link_module
from shared.infrastructure.identity_link_service import IdentityLinkService
from shared.models import register_models
from shared.models.users.web_account_model import WebAccount
from shared.models.users.web_session_model import WebSession
from shared.models.users.app_user_model import AppUser
from shared.models.users.identity_link_token_model import IdentityLinkToken
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from telegram_bot.services.linking.telegram_link_service import TelegramLinkService


DATABASE_URL = "sqlite+aiosqlite://"


@pytest.fixture
async def session_factory():
    register_models()
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
async def seeded_user(session_factory):
    async with session_factory() as session:
        user = AppUser(
            created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            blocked_at=None,
            deleted_at=None,
        )
        session.add(user)
        await session.flush()
        await session.commit()
        return int(user.id)


@pytest.fixture
def service(session_factory, monkeypatch):
    @asynccontextmanager
    async def _test_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(telegram_link_module, "get_db_session", _test_db_session)
    identity = IdentityLinkService(ttl_minutes=30)
    return TelegramLinkService(identity_link_service=identity, secret="secret-key"), identity


@pytest.mark.asyncio
async def test_consume_start_token_links_telegram_to_target_user(service, session_factory, seeded_user):
    telegram_link_service, identity = service
    async with session_factory() as session:
        issued = await identity.issue_token(
            session,
            user_id=seeded_user,
            purpose="link_telegram",
            issued_by_channel="web",
            metadata={},
        )
        await session.commit()

    result = await telegram_link_service.consume_start_token(
        tg_id=999,
        telegram_username="cat",
        raw_token=issued.raw_token,
    )

    assert result.status == "linked"
    async with session_factory() as session:
        account = (
            await session.execute(
                select(TelegramAccount).where(TelegramAccount.telegram_id == 999)
            )
        ).scalar_one_or_none()
        token = (await session.execute(select(IdentityLinkToken))).scalar_one()
    assert account is not None
    assert account.user_id == seeded_user
    assert token.used_at is None


@pytest.mark.asyncio
async def test_consume_start_token_detects_conflict(service, session_factory, seeded_user):
    telegram_link_service, identity = service
    async with session_factory() as session:
        other_user = AppUser(
            created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            blocked_at=None,
            deleted_at=None,
        )
        session.add(other_user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(other_user.id),
                telegram_id=999,
                username="other",
                linked_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        issued = await identity.issue_token(
            session,
            user_id=seeded_user,
            purpose="link_telegram",
            issued_by_channel="web",
            metadata={},
        )
        await session.commit()

    result = await telegram_link_service.consume_start_token(
        tg_id=999,
        telegram_username="cat",
        raw_token=issued.raw_token,
    )

    assert result.status == "conflict"


@pytest.mark.asyncio
async def test_consume_start_token_merges_empty_web_shell_into_existing_telegram_user(service, session_factory):
    telegram_link_service, identity = service
    now = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)

    async with session_factory() as session:
        web_user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        telegram_user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(web_user)
        session.add(telegram_user)
        await session.flush()
        session.add(
            WebAccount(
                user_id=int(web_user.id),
                email="user@example.com",
                password_hash="hash",
                email_verified_at=now,
                linked_at=now,
                last_login_at=now,
                revoked_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            UserProfile(
                user_id=int(web_user.id),
                display_name="Meow",
                timezone=None,
                locale=None,
                marketing_opt_in=False,
                preferred_contact_email="user@example.com",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            WebSession(
                user_id=int(web_user.id),
                session_token_hash="hash-1",
                ip_address=None,
                user_agent=None,
                device_name=None,
                created_at=now,
                last_seen_at=now,
                expires_at=datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
                metadata_json={},
            )
        )
        session.add(
            TelegramAccount(
                user_id=int(telegram_user.id),
                telegram_id=999,
                username="oldcat",
                linked_at=now,
                first_seen_at=now,
                last_seen_at=now,
                revoked_at=None,
            )
        )
        issued = await identity.issue_token(
            session,
            user_id=int(web_user.id),
            purpose="link_telegram",
            issued_by_channel="web",
            metadata={},
        )
        await session.commit()
        web_user_id = int(web_user.id)
        telegram_user_id = int(telegram_user.id)

    result = await telegram_link_service.consume_start_token(
        tg_id=999,
        telegram_username="cat",
        raw_token=issued.raw_token,
    )

    assert result.status == "linked"
    async with session_factory() as session:
        web_account = (
            await session.execute(select(WebAccount).where(WebAccount.email == "user@example.com"))
        ).scalar_one()
        telegram_account = (
            await session.execute(select(TelegramAccount).where(TelegramAccount.telegram_id == 999))
        ).scalar_one()
        profile = await session.get(UserProfile, telegram_user_id)
        web_session = (
            await session.execute(select(WebSession).where(WebSession.session_token_hash == "hash-1"))
        ).scalar_one()
        old_web_user = await session.get(AppUser, web_user_id)
    assert int(web_account.user_id) == telegram_user_id
    assert int(telegram_account.user_id) == telegram_user_id
    assert telegram_account.username == "cat"
    assert profile is not None
    assert int(profile.user_id) == telegram_user_id
    assert int(web_session.user_id) == telegram_user_id
    assert old_web_user is not None and old_web_user.deleted_at is not None


@pytest.mark.asyncio
async def test_create_web_link_is_stable_for_same_telegram_user(service, session_factory, seeded_user):
    telegram_link_service, _ = service
    now = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)
    telegram_link_module.FRONTEND_TELEGRAM_LINK = "https://cabinet.example.org"

    async with session_factory() as session:
        session.add(
            TelegramAccount(
                user_id=seeded_user,
                telegram_id=777,
                username="cat",
                linked_at=now,
                first_seen_at=now,
                last_seen_at=now,
                revoked_at=None,
            )
        )
        await session.commit()

    first_link = await telegram_link_service.create_web_link(tg_id=777)
    second_link = await telegram_link_service.create_web_link(tg_id=777)

    assert first_link is not None
    assert first_link == second_link
    assert first_link.startswith("https://cabinet.example.org/auth/login?link_token=")


@pytest.mark.asyncio
async def test_create_web_link_returns_none_without_public_telegram_frontend(service, session_factory, seeded_user):
    telegram_link_service, _ = service
    now = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)
    telegram_link_module.FRONTEND_TELEGRAM_LINK = ""

    async with session_factory() as session:
        session.add(
            TelegramAccount(
                user_id=seeded_user,
                telegram_id=778,
                username="cat",
                linked_at=now,
                first_seen_at=now,
                last_seen_at=now,
                revoked_at=None,
            )
        )
        await session.commit()

    assert await telegram_link_service.create_web_link(tg_id=778) is None
