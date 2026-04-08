from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from shared.config.settings import RolloutFeatureFlags
from shared.migration_support.models.payments.payment_model import Payment
from shared.migration_support.models.users.user_model import User
from shared.migration_support.repositories.payments.payment_repository import PaymentRepository
from shared.models import register_models
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.payments.plan_model import Plan
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.product_constants import ENTITLEMENT_KIND_TIME, PRODUCT_SCOPE_STANDARD

DATABASE_URL = "sqlite+aiosqlite://"


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


def _dt_to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


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
def payment_repo(session_factory):
    class TestablePaymentRepository(PaymentRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    return TestablePaymentRepository(
        features=RolloutFeatureFlags()
    )


async def _seed_v2_payment(
    session,
    *,
    telegram_id: int,
    payment_id: str,
    provider: str,
    provider_status: str,
    order_status: str,
    legacy_payload: str,
    fulfilled: bool = False,
) -> None:
    app_user = AppUser(
        created_at=_dt(2026, 3, 1),
        updated_at=_dt(2026, 3, 1),
    )
    session.add(app_user)
    await session.flush()

    plan = Plan(
        code=f"plan_{payment_id}",
        name=f"Plan {payment_id}",
        kind="paid",
        legacy_payload=legacy_payload,
        scope=PRODUCT_SCOPE_STANDARD,
        entitlement_kind=ENTITLEMENT_KIND_TIME,
        duration_days=30,
        quota_bytes=None,
        price_amount=Decimal("9.99"),
        currency="RUB",
        is_active=True,
        metadata_json={"legacy_payload": legacy_payload},
    )
    session.add(plan)
    await session.flush()

    session.add(
        TelegramAccount(
            user_id=int(app_user.id),
            telegram_id=telegram_id,
            username=f"user{telegram_id}",
            linked_at=_dt(2026, 3, 1),
            first_seen_at=_dt(2026, 3, 1),
            last_seen_at=_dt(2026, 3, 1),
            revoked_at=None,
        )
    )
    await session.flush()

    order = PaymentOrder(
        user_id=int(app_user.id),
        plan_id=int(plan.id),
        status=order_status,
        amount=Decimal("9.99"),
        currency="RUB",
        created_at=_dt(2026, 3, 5),
        paid_at=_dt(2026, 3, 6) if order_status in {"paid", "fulfilled"} else None,
        fulfilled_at=_dt(2026, 3, 7) if fulfilled else None,
        idempotency_key=f"legacy_payment:{payment_id}",
        subscription_grant_id=None,
        metadata_json={"legacy_payment_id": payment_id, "legacy_payload": legacy_payload},
    )
    session.add(order)
    await session.flush()

    session.add(
        PaymentAttempt(
            order_id=int(order.id),
            provider=provider,
            provider_payment_id=payment_id,
            provider_status=provider_status,
            provider_payload_json={"legacy_payload": legacy_payload},
            created_at=_dt(2026, 3, 5),
            updated_at=_dt(2026, 3, 6),
            paid_at=_dt(2026, 3, 6) if provider_status in {"paid", "succeeded"} else None,
        )
    )


@pytest.mark.asyncio
async def test_get_by_payment_id_prefers_v2_projection(payment_repo, session_factory):
    async with session_factory() as session:
        session.add(
            User(
                tg_id=100,
                email="user100@example.com",
                login_date=1_600_000_000_000,
                expiration_date=None,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-100",
            )
        )
        session.add(
            Payment(
                payment_id="pay-1",
                tg_id=100,
                status="pending",
                payload="stale_payload",
                created_at=1_700_000_000_000,
                confirmed=False,
                method="yookassa",
            )
        )
        await _seed_v2_payment(
            session,
            telegram_id=100,
            payment_id="pay-1",
            provider="yookassa",
            provider_status="succeeded",
            order_status="fulfilled",
            legacy_payload="month1",
            fulfilled=True,
        )
        await session.commit()

    payment = await payment_repo.get_by_payment_id("pay-1")

    assert payment is not None
    assert payment.payment_id == "pay-1"
    assert payment.tg_id == 100
    assert payment.status == "succeeded"
    assert payment.payload == "month1"
    assert payment.confirmed is True
    assert payment.method == "yookassa"
    assert payment.created_at == _dt_to_ms(_dt(2026, 3, 5))


@pytest.mark.asyncio
async def test_get_by_payment_id_returns_none_when_v2_row_missing(
    payment_repo,
    session_factory,
):
    async with session_factory() as session:
        session.add(
            User(
                tg_id=200,
                email="user200@example.com",
                login_date=1_600_000_000_000,
                expiration_date=None,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-200",
            )
        )
        session.add(
            Payment(
                payment_id="legacy-only",
                tg_id=200,
                status="processing",
                payload="month3",
                created_at=1_700_000_000_000,
                confirmed=False,
                method="cryptopay",
            )
        )
        await session.commit()

    payment = await payment_repo.get_by_payment_id("legacy-only")

    assert payment is None


@pytest.mark.asyncio
async def test_get_unconfirmed_uses_v2_projection_only(
    payment_repo,
    session_factory,
):
    async with session_factory() as session:
        session.add_all(
            [
                User(
                    tg_id=301,
                    email="user301@example.com",
                    login_date=1_600_000_000_000,
                    expiration_date=None,
                    trial_date=None,
                    news_channel_date=None,
                    sub_id="sub-301",
                ),
                User(
                    tg_id=302,
                    email="user302@example.com",
                    login_date=1_600_000_000_000,
                    expiration_date=None,
                    trial_date=None,
                    news_channel_date=None,
                    sub_id="sub-302",
                ),
                User(
                    tg_id=303,
                    email="user303@example.com",
                    login_date=1_600_000_000_000,
                    expiration_date=None,
                    trial_date=None,
                    news_channel_date=None,
                    sub_id="sub-303",
                ),
            ]
        )
        session.add_all(
            [
                Payment(
                    payment_id="pay-pending",
                    tg_id=301,
                    status="pending",
                    payload="month1",
                    created_at=1_700_000_000_000,
                    confirmed=False,
                    method="yookassa",
                ),
                Payment(
                    payment_id="pay-paid",
                    tg_id=302,
                    status="pending",
                    payload="month3",
                    created_at=1_700_000_000_000,
                    confirmed=False,
                    method="cryptopay",
                ),
            ]
        )
        await _seed_v2_payment(
            session,
            telegram_id=301,
            payment_id="pay-pending",
            provider="yookassa",
            provider_status="pending",
            order_status="pending_payment",
            legacy_payload="month1",
            fulfilled=False,
        )
        await _seed_v2_payment(
            session,
            telegram_id=302,
            payment_id="pay-paid",
            provider="cryptopay",
            provider_status="paid",
            order_status="paid",
            legacy_payload="month3",
            fulfilled=False,
        )
        await _seed_v2_payment(
            session,
            telegram_id=304,
            payment_id="v2-only",
            provider="yookassa",
            provider_status="pending",
            order_status="pending_payment",
            legacy_payload="year1",
            fulfilled=False,
        )
        await _seed_v2_payment(
            session,
            telegram_id=305,
            payment_id="fulfilled",
            provider="yookassa",
            provider_status="succeeded",
            order_status="fulfilled",
            legacy_payload="month1",
            fulfilled=True,
        )
        await session.commit()

    payments = await payment_repo.get_unconfirmed()

    payment_ids = {payment.payment_id for payment in payments}
    assert payment_ids == {"pay-pending", "pay-paid", "v2-only"}


@pytest.mark.asyncio
async def test_get_unconfirmed_paid_filters_paid_but_not_fulfilled_payments(
    payment_repo,
    session_factory,
):
    async with session_factory() as session:
        await _seed_v2_payment(
            session,
            telegram_id=402,
            payment_id="v2-paid",
            provider="yookassa",
            provider_status="succeeded",
            order_status="paid",
            legacy_payload="year1",
            fulfilled=False,
        )
        await _seed_v2_payment(
            session,
            telegram_id=403,
            payment_id="v2-fulfilled",
            provider="yookassa",
            provider_status="succeeded",
            order_status="fulfilled",
            legacy_payload="month1",
            fulfilled=True,
        )
        await session.commit()

    payments = await payment_repo.get_unconfirmed_paid()

    payment_ids = {payment.payment_id for payment in payments}
    assert payment_ids == {"v2-paid"}
