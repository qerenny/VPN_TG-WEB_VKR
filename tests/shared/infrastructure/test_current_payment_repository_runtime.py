from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from shared.infrastructure.payments.payment_repository import PaymentRepository, PaymentSnapshot
from shared.models import register_models
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.plan_model import Plan
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.product_constants import ENTITLEMENT_KIND_TIME, PRODUCT_SCOPE_STANDARD

DATABASE_URL = "sqlite+aiosqlite://"


def _dt() -> datetime:
    return datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


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
def payment_repo(session_factory):
    class TestablePaymentRepository(PaymentRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    return TestablePaymentRepository()


@pytest.fixture(autouse=True)
async def seed_data(session_factory):
    async with session_factory() as session:
        user = AppUser(
            created_at=_dt(),
            updated_at=_dt(),
            blocked_at=None,
            deleted_at=None,
        )
        session.add(user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(user.id),
                telegram_id=7001,
                username="cat_user",
                linked_at=_dt(),
                first_seen_at=_dt(),
                last_seen_at=_dt(),
                revoked_at=None,
            )
        )
        session.add(
            Plan(
                code="month_1",
                name="1 month access",
                kind="paid",
                payload="month1",
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


@pytest.mark.asyncio
async def test_create_runtime_payment_creates_attempt_from_tg_id(payment_repo, session_factory):
    snapshot = PaymentSnapshot(
        payment_id="pay_runtime_1",
        user_id=None,
        tg_id=7001,
        status="pending",
        payload="month1",
        created_at=_ms(_dt()),
        confirmed=False,
        method="external_card",
    )

    await payment_repo.create(snapshot)

    async with session_factory() as session:
        attempts = (await session.execute(select(PaymentAttempt))).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].provider_payment_id == "pay_runtime_1"


@pytest.mark.asyncio
async def test_get_unconfirmed_paid_uses_paid_provider_statuses(payment_repo):
    await payment_repo.create(
        PaymentSnapshot(
            payment_id="pay_runtime_paid",
            user_id=1,
            tg_id=7001,
            status="paid",
            payload="month1",
            created_at=_ms(_dt()),
            confirmed=False,
            method="external_card",
        )
    )

    payments = await payment_repo.get_unconfirmed_paid()

    assert [payment.payment_id for payment in payments] == ["pay_runtime_paid"]
