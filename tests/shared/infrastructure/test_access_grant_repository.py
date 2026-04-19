from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from shared.infrastructure.access import access_grant_repository as grant_repo_module
from shared.infrastructure.access.access_grant_repository import AccessGrantRepository
from shared.models import register_models
from shared.models.access.access_grant_model import AccessGrant
from shared.models.users.app_user_model import AppUser
from shared.product_constants import (
    ACCESS_GRANT_STATUS_ACTIVE,
    ENTITLEMENT_KIND_TIME,
    PRODUCT_SCOPE_STANDARD,
)

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
def access_grant_repository(session_factory, monkeypatch):
    @asynccontextmanager
    async def _test_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(grant_repo_module, "get_db_session", _test_db_session)
    return AccessGrantRepository()


@pytest.fixture
async def seeded_user_id(session_factory):
    async with session_factory() as session:
        user = AppUser(
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            blocked_at=None,
            deleted_at=None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return int(user.id)


@pytest.mark.asyncio
async def test_list_expiring_active_grants_uses_utc_timezone(
    access_grant_repository,
    seeded_user_id,
    session_factory,
):
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        grant = AccessGrant(
            user_id=seeded_user_id,
            granted_by_user_id=None,
            plan_id=None,
            template_code="month_1",
            scope=PRODUCT_SCOPE_STANDARD,
            entitlement_kind=ENTITLEMENT_KIND_TIME,
            source_type="test",
            source_ref="expiring",
            status=ACCESS_GRANT_STATUS_ACTIVE,
            expires_at=now + timedelta(hours=2),
            quota_bytes=None,
            created_at=now,
            activated_at=now,
            revoked_at=None,
            metadata_json={},
        )
        session.add(grant)
        await session.commit()

    rows = await access_grant_repository.list_expiring_active_grants(within_hours=24)

    assert [row.source_ref for row in rows] == ["expiring"]
