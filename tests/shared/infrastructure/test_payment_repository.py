from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from shared.migration_support.repositories.payments.payment_repository import PaymentRepository
from shared.infrastructure import payment_sync_service as payment_sync_module
from shared.migration_support.models.payments.payment_model import Payment
from shared.models import register_models
from shared.models.payments.plan_model import Plan
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.product_constants import ENTITLEMENT_KIND_TIME, PRODUCT_SCOPE_STANDARD

DATABASE_URL = "sqlite+aiosqlite://"


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


async def _create_v2_user(session, *, tg_id: int) -> int:
    app_user = AppUser(
        created_at=_dt(2026, 3, 1),
        updated_at=_dt(2026, 3, 1),
        blocked_at=None,
        deleted_at=None,
    )
    session.add(app_user)
    await session.flush()
    session.add(
        TelegramAccount(
            user_id=int(app_user.id),
            telegram_id=tg_id,
            username=f"user{tg_id}",
            linked_at=_dt(2026, 3, 1),
            first_seen_at=_dt(2026, 3, 1),
            last_seen_at=_dt(2026, 3, 1),
            revoked_at=None,
        )
    )
    await session.flush()
    return int(app_user.id)


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
def payment_repo(session_factory, monkeypatch):
    @asynccontextmanager
    async def _test_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(payment_sync_module, "get_db_session", _test_db_session)

    class TestablePaymentRepository(PaymentRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    return TestablePaymentRepository()


@pytest.fixture(autouse=True)
async def seed_default_plans(session_factory):
    async with session_factory() as session:
        session.add_all(
            [
                Plan(
                    code="month_1",
                    name="1 month",
                    kind="paid",
                    legacy_payload="month1",
                    scope=PRODUCT_SCOPE_STANDARD,
                    entitlement_kind=ENTITLEMENT_KIND_TIME,
                    duration_days=30,
                    quota_bytes=None,
                    price_amount=Decimal("139"),
                    currency="RUB",
                    is_active=True,
                    metadata_json={"legacy_payload": "month1"},
                ),
                Plan(
                    code="month_3",
                    name="3 months",
                    kind="paid",
                    legacy_payload="month3",
                    scope=PRODUCT_SCOPE_STANDARD,
                    entitlement_kind=ENTITLEMENT_KIND_TIME,
                    duration_days=90,
                    quota_bytes=None,
                    price_amount=Decimal("399"),
                    currency="RUB",
                    is_active=True,
                    metadata_json={"legacy_payload": "month3"},
                ),
                Plan(
                    code="month_6",
                    name="6 months",
                    kind="paid",
                    legacy_payload="month6",
                    scope=PRODUCT_SCOPE_STANDARD,
                    entitlement_kind=ENTITLEMENT_KIND_TIME,
                    duration_days=180,
                    quota_bytes=None,
                    price_amount=Decimal("699"),
                    currency="RUB",
                    is_active=True,
                    metadata_json={"legacy_payload": "month6"},
                ),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_create_and_get_payment(payment_repo, session_factory):
    async with session_factory() as session:
        await _create_v2_user(session, tg_id=100)
        await session.commit()

    await payment_repo.create(
        Payment(
            payment_id="payment-1",
            tg_id=100,
            status="pending",
            payload="month1",
            created_at=_ms(_dt(2026, 3, 5)),
            confirmed=False,
            method="yookassa",
        )
    )

    loaded = await payment_repo.get_by_payment_id("payment-1")

    assert loaded is not None
    assert loaded.payment_id == "payment-1"
    assert loaded.tg_id == 100
    assert loaded.status == "pending"
    assert loaded.payload == "month1"
    assert loaded.confirmed is False
    assert loaded.method == "yookassa"


@pytest.mark.asyncio
async def test_update_status_confirms_payment(payment_repo, session_factory):
    async with session_factory() as session:
        await _create_v2_user(session, tg_id=200)
        await session.commit()

    await payment_repo.create(
        Payment(
            payment_id="payment-2",
            tg_id=200,
            status="pending",
            payload="month3",
            created_at=_ms(_dt(2026, 3, 5)),
            confirmed=False,
            method="cryptopay",
        )
    )

    await payment_repo.update_status("payment-2", "succeeded", True)
    loaded = await payment_repo.get_by_payment_id("payment-2")

    assert loaded is not None
    assert loaded.status == "succeeded"
    assert loaded.confirmed is True
    assert loaded.method == "cryptopay"


@pytest.mark.asyncio
async def test_get_unconfirmed_and_paid_filters(payment_repo, session_factory):
    async with session_factory() as session:
        for tg_id in (301, 302, 303):
            await _create_v2_user(session, tg_id=tg_id)
        await session.commit()

    await payment_repo.create(
        Payment(
            payment_id="pay-pending",
            tg_id=301,
            status="pending",
            payload="month1",
            created_at=_ms(_dt(2026, 3, 5)),
            confirmed=False,
            method="yookassa",
        )
    )
    await payment_repo.create(
        Payment(
            payment_id="pay-paid",
            tg_id=302,
            status="paid",
            payload="month3",
            created_at=_ms(_dt(2026, 3, 5)),
            confirmed=False,
            method="cryptopay",
        )
    )
    await payment_repo.create(
        Payment(
            payment_id="pay-fulfilled",
            tg_id=303,
            status="succeeded",
            payload="month6",
            created_at=_ms(_dt(2026, 3, 5)),
            confirmed=True,
            method="yookassa",
        )
    )

    unconfirmed = await payment_repo.get_unconfirmed()
    unconfirmed_paid = await payment_repo.get_unconfirmed_paid()

    assert {payment.payment_id for payment in unconfirmed} == {"pay-pending", "pay-paid"}
    assert [payment.payment_id for payment in unconfirmed_paid] == ["pay-paid"]


@pytest.mark.asyncio
async def test_update_status_batch(payment_repo, session_factory):
    async with session_factory() as session:
        for tg_id in (401, 402):
            await _create_v2_user(session, tg_id=tg_id)
        await session.commit()

    await payment_repo.create(
        Payment(
            payment_id="batch-1",
            tg_id=401,
            status="pending",
            payload="month1",
            created_at=_ms(_dt(2026, 3, 5)),
            confirmed=False,
            method="yookassa",
        )
    )
    await payment_repo.create(
        Payment(
            payment_id="batch-2",
            tg_id=402,
            status="pending",
            payload="month3",
            created_at=_ms(_dt(2026, 3, 5)),
            confirmed=False,
            method="cryptopay",
        )
    )

    await payment_repo.update_status_batch(
        [
            ("batch-1", "succeeded", True),
            ("batch-2", "failed", False),
        ]
    )

    first = await payment_repo.get_by_payment_id("batch-1")
    second = await payment_repo.get_by_payment_id("batch-2")

    assert first is not None and first.confirmed is True and first.status == "succeeded"
    assert second is not None and second.confirmed is False and second.status == "failed"


@pytest.mark.asyncio
async def test_has_any_for_user(payment_repo, session_factory):
    async with session_factory() as session:
        await _create_v2_user(session, tg_id=500)
        await session.commit()

    assert await payment_repo.has_any_for_user(500) is False

    await payment_repo.create(
        Payment(
            payment_id="user-500-payment",
            tg_id=500,
            status="pending",
            payload="month1",
            created_at=_ms(_dt(2026, 3, 5)),
            confirmed=False,
            method="yookassa",
        )
    )

    assert await payment_repo.has_any_for_user(500) is True
