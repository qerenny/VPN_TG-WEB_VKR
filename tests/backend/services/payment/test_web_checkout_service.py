from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from backend.services.payments.web_checkout_service import WebCheckoutService
from shared.models import register_models
from shared.models.payments.plan_model import Plan
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount
from shared.product_constants import ENTITLEMENT_KIND_TIME, ENTITLEMENT_KIND_TRAFFIC, PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_WHITELIST
from shared.utils.timestamp_utils import TimestampUtils
import backend.services.payments.web_checkout_service as checkout_module


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
        session.add(
            TelegramAccount(
                user_id=int(user.id),
                telegram_id=7001,
                username="cat_user",
                linked_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        session.add_all(
            [
                Plan(
                    code="month_1",
                    name="1 month access",
                    kind="paid",
                    legacy_payload="month1",
                    scope=PRODUCT_SCOPE_STANDARD,
                    entitlement_kind=ENTITLEMENT_KIND_TIME,
                    duration_days=30,
                    quota_bytes=None,
                    price_amount=Decimal("169.00"),
                    currency="RUB",
                    is_active=True,
                    metadata_json={},
                ),
                Plan(
                    code="whitelist_15gb",
                    name="Traffic-limited access 15 GB",
                    kind="paid",
                    legacy_payload="whitelist15gb",
                    scope=PRODUCT_SCOPE_WHITELIST,
                    entitlement_kind=ENTITLEMENT_KIND_TRAFFIC,
                    duration_days=30,
                    quota_bytes=15 * 1024 * 1024 * 1024,
                    price_amount=Decimal("99.00"),
                    currency="RUB",
                    is_active=True,
                    metadata_json={},
                ),
            ]
        )
        await session.commit()
        return int(user.id)


@pytest.fixture
def checkout_service(session_factory, monkeypatch):
    @asynccontextmanager
    async def _test_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(checkout_module, "get_db_session", _test_db_session)
    repo = SimpleNamespace(create=AsyncMock())
    gateway = SimpleNamespace(
        create_payment=AsyncMock(
            return_value={
                "id": "pay_123",
                "status": "pending",
                "url": "https://pay.example.com/123",
                "confirmed": False,
            }
        )
    )
    service = WebCheckoutService(
        payment_repository=repo,
        gateways={"yookassa": gateway},
        timestamp=TimestampUtils(),
    )
    return service, repo, gateway


@pytest.mark.asyncio
async def test_create_checkout_builds_standard_order(checkout_service, seeded_user):
    service, repo, gateway = checkout_service

    result = await service.create_checkout(
        user_id=seeded_user,
        plan_code="month_1",
        method="yookassa",
        expected_scope="standard",
    )

    assert result.plan_code == "month_1"
    assert result.scope == "standard"
    gateway.create_payment.assert_awaited_once()
    repo.create.assert_awaited_once()
    snapshot = repo.create.await_args.args[0]
    assert snapshot.user_id == seeded_user
    assert snapshot.tg_id == 7001
    assert snapshot.payload == "month1"


@pytest.mark.asyncio
async def test_create_checkout_builds_whitelist_order(checkout_service, seeded_user):
    service, repo, gateway = checkout_service

    result = await service.create_checkout(
        user_id=seeded_user,
        plan_code="whitelist_15gb",
        method="yookassa",
        expected_scope="whitelist",
    )

    assert result.plan_code == "whitelist_15gb"
    assert result.scope == "whitelist"
    snapshot = repo.create.await_args.args[0]
    assert snapshot.payload == "whitelist15gb"


@pytest.mark.asyncio
async def test_create_checkout_works_for_telegram_first_user_without_web_account(session_factory, monkeypatch):
    @asynccontextmanager
    async def _test_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(checkout_module, "get_db_session", _test_db_session)

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
                telegram_id=7002,
                username="tg_only_user",
                linked_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
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
                preferred_contact_email="tg-only@example.com",
                created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            )
        )
        session.add(
            Plan(
                code="month_1",
                name="1 month access",
                kind="paid",
                legacy_payload="month1",
                scope=PRODUCT_SCOPE_STANDARD,
                entitlement_kind=ENTITLEMENT_KIND_TIME,
                duration_days=30,
                quota_bytes=None,
                price_amount=Decimal("169.00"),
                currency="RUB",
                is_active=True,
                metadata_json={},
            )
        )
        await session.commit()
        user_id = int(user.id)

    repo = SimpleNamespace(create=AsyncMock())
    gateway = SimpleNamespace(
        create_payment=AsyncMock(
            return_value={
                "id": "pay_telegram_first",
                "status": "pending",
                "url": "https://pay.example.com/tg-first",
                "confirmed": False,
            }
        )
    )
    service = WebCheckoutService(
        payment_repository=repo,
        gateways={"yookassa": gateway},
        timestamp=TimestampUtils(),
    )

    result = await service.create_checkout(
        user_id=user_id,
        plan_code="month_1",
        method="yookassa",
        expected_scope="standard",
    )

    assert result.checkout_url == "https://pay.example.com/tg-first"
    gateway.create_payment.assert_awaited_once()
    assert gateway.create_payment.await_args.kwargs["customer_email"] == "tg-only@example.com"
