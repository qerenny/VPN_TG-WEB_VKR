from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import backend.services.linking.linking_service as linking_module
from backend.services.linking.linking_service import LinkingService
from shared.infrastructure.identity_link_service import IdentityLinkService
from shared.models import register_models
from shared.models.users.app_user_model import AppUser
from shared.models.users.identity_link_token_model import IdentityLinkToken
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.web_session_model import WebSession
from shared.models.users.web_account_model import WebAccount


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
        session.add(
            WebAccount(
                user_id=int(user.id),
                email="user@example.com",
                password_hash="hash",
                email_verified_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                linked_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_login_at=None,
                revoked_at=None,
                created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            )
        )
        await session.commit()
        return int(user.id)


@pytest.fixture
async def seeded_telegram_only_user(session_factory):
    async with session_factory() as session:
        user = AppUser(
            created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            blocked_at=None,
            deleted_at=None,
        )
        session.add(user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(user.id),
                telegram_id=777,
                username="cat",
                linked_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        await session.commit()
        return int(user.id)


@pytest.fixture
def linking_service(session_factory, monkeypatch):
    @asynccontextmanager
    async def _test_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(linking_module, "async_session_factory", _test_db_session)
    return LinkingService(
        identity_link_service=IdentityLinkService(ttl_minutes=30),
    )


@pytest.mark.asyncio
async def test_start_telegram_link_issues_token_and_deep_link(linking_service, session_factory, seeded_user):
    result = await linking_service.start_telegram_link(user_id=seeded_user)

    assert result.status == "pending"
    assert result.deep_link is not None
    async with session_factory() as session:
        tokens = (await session.execute(select(IdentityLinkToken))).scalars().all()
    assert len(tokens) == 1
    assert tokens[0].user_id == seeded_user
    assert tokens[0].purpose == "link_telegram"


@pytest.mark.asyncio
async def test_start_telegram_link_returns_already_linked_when_present(linking_service, session_factory, seeded_user):
    async with session_factory() as session:
        session.add(
            TelegramAccount(
                user_id=seeded_user,
                telegram_id=555,
                username="cat",
                linked_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        await session.commit()

    result = await linking_service.start_telegram_link(user_id=seeded_user)

    assert result.status == "already_linked"
    assert result.telegram_id == 555


@pytest.mark.asyncio
async def test_start_web_link_issues_login_url(linking_service, seeded_telegram_only_user):
    result = await linking_service.start_web_link(telegram_id=777)

    assert result.status == "pending"
    assert "link_token=" in str(result.link_url)


@pytest.mark.asyncio
async def test_start_web_link_returns_already_linked_when_web_account_exists(
    linking_service,
    session_factory,
    seeded_user,
):
    async with session_factory() as session:
        session.add(
            TelegramAccount(
                user_id=seeded_user,
                telegram_id=888,
                username="cat",
                linked_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        await session.commit()

    result = await linking_service.start_web_link(telegram_id=888)

    assert result.status == "already_linked"
    assert result.link_url is None


@pytest.mark.asyncio
async def test_consume_web_link_moves_empty_web_shell(
    linking_service,
    session_factory,
    seeded_telegram_only_user,
):
    async with session_factory() as session:
        telegram_user = await session.get(AppUser, seeded_telegram_only_user)
        telegram_user.updated_at = datetime(2026, 4, 3, 12, 5, tzinfo=timezone.utc)
        empty_web_user = AppUser(
            created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            blocked_at=None,
            deleted_at=None,
        )
        session.add(empty_web_user)
        await session.flush()
        session.add(
            WebAccount(
                user_id=int(empty_web_user.id),
                email="fresh@example.com",
                password_hash="hash",
                email_verified_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                linked_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_login_at=None,
                revoked_at=None,
                created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            )
        )
        session.add(
            WebSession(
                user_id=int(empty_web_user.id),
                session_token_hash="hash-1",
                ip_address=None,
                user_agent=None,
                device_name=None,
                created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                expires_at=datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
                metadata_json={},
            )
        )
        issued = await linking_service.identity_link_service.issue_token(
            session,
            user_id=seeded_telegram_only_user,
            purpose="link_web",
            issued_by_channel="telegram",
            metadata={},
        )
        await session.commit()
        source_user_id = int(empty_web_user.id)

    result = await linking_service.consume_web_link(
        raw_token=issued.raw_token,
        current_user_id=source_user_id,
    )

    assert result.status == "linked"
    async with session_factory() as session:
        moved_web = (
            await session.execute(
                select(WebAccount).where(WebAccount.email == "fresh@example.com")
            )
        ).scalar_one()
        moved_session = (
            await session.execute(
                select(WebSession).where(WebSession.session_token_hash == "hash-1")
            )
        ).scalar_one()
        old_user = await session.get(AppUser, source_user_id)
    assert moved_web.user_id == seeded_telegram_only_user
    assert moved_session.user_id == seeded_telegram_only_user
    assert old_user.deleted_at is not None


@pytest.mark.asyncio
async def test_preview_web_link_stays_valid_after_consume_until_expiry(
    linking_service,
    session_factory,
    seeded_telegram_only_user,
):
    async with session_factory() as session:
        empty_web_user = AppUser(
            created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            blocked_at=None,
            deleted_at=None,
        )
        session.add(empty_web_user)
        await session.flush()
        session.add(
            WebAccount(
                user_id=int(empty_web_user.id),
                email="fresh2@example.com",
                password_hash="hash",
                email_verified_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                linked_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_login_at=None,
                revoked_at=None,
                created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            )
        )
        issued = await linking_service.identity_link_service.issue_token(
            session,
            user_id=seeded_telegram_only_user,
            purpose="link_web",
            issued_by_channel="telegram",
            metadata={},
        )
        await session.commit()
        source_user_id = int(empty_web_user.id)

    before = await linking_service.preview_web_link(raw_token=issued.raw_token)
    consumed = await linking_service.consume_web_link(
        raw_token=issued.raw_token,
        current_user_id=source_user_id,
    )
    after = await linking_service.preview_web_link(raw_token=issued.raw_token)

    assert before.status == "pending"
    assert consumed.status == "linked"
    assert after.status == "pending"
