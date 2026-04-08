from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

import shared.infrastructure.payment_sync_service as sync_module
from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.payment_sync_service import PaymentSyncService
from shared.migration_support.models.payments.payment_model import Payment
from shared.migration_support.models.users.user_model import User
from shared.models import register_models
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.payments.payment_webhook_event_model import PaymentWebhookEvent
from shared.models.payments.plan_model import Plan
from shared.models.subscriptions.subscription_grant_model import SubscriptionGrant
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount

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
def sync_service(session_factory, monkeypatch):
    @asynccontextmanager
    async def test_get_db_session():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(sync_module, "get_db_session", test_get_db_session)
    return PaymentSyncService(RolloutFeatureFlags(db_dual_write_payments=True))


@pytest.fixture
async def phase1_identity_state(session_factory):
    async with session_factory() as session:
        app_user = AppUser(
            created_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
        )
        session.add(app_user)
        await session.flush()
        session.add(
            TelegramAccount(
                user_id=int(app_user.id),
                telegram_id=100,
                username="alice",
                linked_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                first_seen_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                last_seen_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                revoked_at=None,
            )
        )
        session.add(
            SubscriptionState(
                user_id=int(app_user.id),
                current_expires_at=datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
                trial_activated_at=None,
                news_bonus_activated_at=None,
                blocked_at=None,
                updated_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
                version=0,
            )
        )
        session.add(
            User(
                tg_id=100,
                uuid="uuid-100",
                email="vpn-user-100@example.com",
                expiration_date=None,
                login_date=1_710_414_400_000,
                trial_date=None,
                news_channel_date=None,
                sub_id="sub-100",
            )
        )
        await session.commit()


def make_payment(**overrides) -> Payment:
    payload = dict(
        payment_id="pay-100",
        tg_id=100,
        status="pending",
        payload="month1",
        created_at=1_710_414_400_000,
        confirmed=False,
        method="cryptopay",
    )
    payload.update(overrides)
    return Payment(**payload)


@pytest.mark.asyncio
async def test_seed_default_plans_creates_expected_paid_catalog(sync_service, session_factory):
    created = await sync_service.seed_default_plans()

    async with session_factory() as session:
        plans = (await session.execute(select(Plan).order_by(Plan.code))).scalars().all()

    assert created == 10
    assert [plan.code for plan in plans] == [
        "month_1",
        "month_3",
        "month_6",
        "news_bonus_4d",
        "trial_3d",
        "whitelist_15gb",
        "whitelist_35gb",
        "whitelist_80gb",
        "whitelist_trial_2gb",
        "year_1",
    ]
    assert plans[0].price_amount == Decimal("169.00")
    assert plans[5].price_amount == Decimal("99.00")
    assert plans[5].is_active is True
    assert plans[5].legacy_payload == "whitelist15gb"
    assert plans[5].scope == "whitelist"
    assert plans[5].entitlement_kind == "traffic"
    assert plans[5].quota_bytes == 15 * 1024 * 1024 * 1024
    assert plans[5].metadata_json["scope"] == "whitelist"
    assert plans[5].metadata_json["entitlement_kind"] == "traffic"
    assert plans[6].duration_days == 45
    assert plans[7].duration_days == 60


@pytest.mark.asyncio
async def test_seed_default_plans_updates_existing_catalog_values(sync_service, session_factory):
    async with session_factory() as session:
        session.add(
            Plan(
                code="whitelist_15gb",
                name="Old name",
                kind="paid",
                legacy_payload="legacy-old",
                scope="standard",
                entitlement_kind="time",
                duration_days=7,
                quota_bytes=1,
                price_amount=Decimal("0.00"),
                currency="RUB",
                is_active=False,
                metadata_json={
                    "legacy_payload": "whitelist15gb",
                    "scope": "whitelist",
                    "entitlement_kind": "traffic",
                    "quota_bytes": 1,
                },
            )
        )
        await session.commit()

    created = await sync_service.seed_default_plans()

    async with session_factory() as session:
        plan = (
            await session.execute(select(Plan).where(Plan.code == "whitelist_15gb"))
        ).scalar_one()

    assert created == 9
    assert plan.name == "Traffic-limited access 15 GB"
    assert plan.legacy_payload == "whitelist15gb"
    assert plan.scope == "whitelist"
    assert plan.entitlement_kind == "traffic"
    assert plan.duration_days == 30
    assert plan.quota_bytes == 15 * 1024 * 1024 * 1024
    assert plan.price_amount == Decimal("99.00")
    assert plan.is_active is True
    assert plan.metadata_json["quota_bytes"] == 15 * 1024 * 1024 * 1024


@pytest.mark.asyncio
async def test_sync_legacy_payment_creates_order_attempt_and_webhook_event(
    sync_service,
    session_factory,
    phase1_identity_state,
):
    legacy_payment = make_payment(status="succeeded", method="yookassa")

    await sync_service.sync_legacy_payment(
        legacy_payment,
        provider="yookassa",
        provider_payload={"object": {"id": "pay-100", "status": "succeeded"}},
        create_webhook_event=True,
        status_changed_at=datetime(2026, 3, 14, 12, 30, tzinfo=timezone.utc),
    )

    async with session_factory() as session:
        orders = (await session.execute(select(PaymentOrder))).scalars().all()
        attempts = (await session.execute(select(PaymentAttempt))).scalars().all()
        events = (await session.execute(select(PaymentWebhookEvent))).scalars().all()

    assert len(orders) == 1
    assert len(attempts) == 1
    assert len(events) == 1
    assert orders[0].status == "paid"
    assert attempts[0].provider == "yookassa"
    assert attempts[0].provider_status == "succeeded"
    assert events[0].provider_payment_id == "pay-100"


@pytest.mark.asyncio
async def test_finalize_subscription_grant_creates_grant_for_confirmed_payment(
    sync_service,
    session_factory,
    phase1_identity_state,
):
    legacy_payment = make_payment(status="paid", confirmed=True)

    await sync_service.sync_legacy_payment(
        legacy_payment,
        provider="cryptopay",
        status_changed_at=datetime(2026, 3, 14, 12, 30, tzinfo=timezone.utc),
    )
    await sync_service.finalize_subscription_grant(
        legacy_payment,
        applied_at=datetime(2026, 3, 14, 12, 31, tzinfo=timezone.utc),
        legacy_backfill=True,
    )

    async with session_factory() as session:
        order = (await session.execute(select(PaymentOrder))).scalar_one()
        grant = (await session.execute(select(SubscriptionGrant))).scalar_one()

    assert order.status == "fulfilled"
    assert order.subscription_grant_id == grant.id
    assert grant.status == "applied"
    assert grant.source_type == "payment_order"
    assert grant.metadata_json["legacy_payment_id"] == "pay-100"
    assert grant.metadata_json["legacy_backfill"] is True
