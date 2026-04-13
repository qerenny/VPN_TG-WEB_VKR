from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from backend.services.auth import web_auth_challenge_service as challenge_module
from backend.services.auth.web_auth_challenge_service import (
    REGISTER_EMAIL_VERIFICATION_PURPOSE,
    WebAuthChallengeService,
)
from shared.models import register_models
from shared.models.users.web_auth_challenge_model import WebAuthChallenge

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
def challenge_service(session_factory, monkeypatch):
    monkeypatch.setattr(challenge_module, "async_session_factory", session_factory)
    return WebAuthChallengeService(
        code_ttl_minutes=15,
        resend_cooldown_seconds=0,
        request_window_seconds=3600,
        max_requests_per_window_per_email=5,
        max_requests_per_window_per_ip=20,
        max_failed_attempts=2,
    )


@pytest.mark.asyncio
async def test_issue_and_consume_challenge(session_factory, challenge_service):
    issued = await challenge_service.issue_challenge(
        email="User@example.com",
        purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
        request_ip="127.0.0.1",
        request_user_agent="pytest",
    )

    assert issued.email == "user@example.com"
    assert len(issued.code) == 6

    await challenge_service.consume_challenge(
        email="user@example.com",
        purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
        code=issued.code,
    )

    async with session_factory() as session:
        row = (
            await session.execute(select(WebAuthChallenge).limit(1))
        ).scalar_one()
        assert row.consumed_at is not None


@pytest.mark.asyncio
async def test_wrong_code_increments_failed_attempts_and_revokes_after_limit(
    session_factory,
    challenge_service,
):
    issued = await challenge_service.issue_challenge(
        email="user@example.com",
        purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
        request_ip="127.0.0.1",
        request_user_agent="pytest",
    )

    with pytest.raises(Exception):
        await challenge_service.consume_challenge(
            email="user@example.com",
            purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
            code="000000",
        )
    with pytest.raises(Exception):
        await challenge_service.consume_challenge(
            email="user@example.com",
            purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
            code="111111",
        )

    async with session_factory() as session:
        row = (
            await session.execute(select(WebAuthChallenge).where(WebAuthChallenge.email == "user@example.com"))
        ).scalar_one()
        assert row.failed_attempts == 2
        assert row.revoked_at is not None
        assert row.code_hash != issued.code


@pytest.mark.asyncio
async def test_rate_limit_by_email_is_enforced(session_factory, monkeypatch):
    monkeypatch.setattr(challenge_module, "async_session_factory", session_factory)
    service = WebAuthChallengeService(
        code_ttl_minutes=15,
        resend_cooldown_seconds=0,
        request_window_seconds=3600,
        max_requests_per_window_per_email=1,
        max_requests_per_window_per_ip=20,
        max_failed_attempts=2,
    )

    await service.issue_challenge(
        email="user@example.com",
        purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
        request_ip="127.0.0.1",
        request_user_agent="pytest",
    )

    with pytest.raises(Exception):
        await service.issue_challenge(
            email="user@example.com",
            purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
            request_ip="127.0.0.1",
            request_user_agent="pytest",
        )
