from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from backend.services.account import account_service as account_service_module
from backend.services.account.account_service import AccountService
from shared.models import register_models
from shared.models.access.access_grant_model import AccessGrant
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.payments.plan_model import Plan
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.traffic.traffic_state_model import TrafficState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.constants.payments import PLAN_KIND_PAID
from shared.product_constants import ENTITLEMENT_KIND_TIME, PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_TRAFFIC_LIMITED
from shared.utils.timestamp_utils import TimestampUtils

DATABASE_URL = "sqlite+aiosqlite://"


def _now() -> datetime:
    return datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)


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
def account_service(session_factory, monkeypatch):
    monkeypatch.setattr(account_service_module, "get_db_session", session_factory)
    return AccountService(timestamp=TimestampUtils())


@pytest.fixture
async def seeded_user(session_factory):
    now = _now()
    async with session_factory() as session:
        user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(user)
        await session.flush()

        session.add(
            WebAccount(
                user_id=int(user.id),
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
            TelegramAccount(
                user_id=int(user.id),
                telegram_id=123456,
                username="cat_user",
                linked_at=now,
                first_seen_at=now,
                last_seen_at=now,
                revoked_at=None,
            )
        )
        session.add(
            UserProfile(
                user_id=int(user.id),
                display_name="Cat",
                timezone="Europe/Moscow",
                locale="ru",
                marketing_opt_in=True,
                preferred_contact_email="profile@example.com",
                created_at=now,
                updated_at=now,
            )
        )
        standard_plan = Plan(
            code="month_1",
            name="1 month",
            kind=PLAN_KIND_PAID,
            payload="month_1",
            scope=PRODUCT_SCOPE_STANDARD,
            entitlement_kind=ENTITLEMENT_KIND_TIME,
            duration_days=30,
            quota_bytes=None,
            price_amount=Decimal("169.00"),
            currency="RUB",
            is_active=True,
            metadata_json={},
        )
        traffic_limited_plan = Plan(
            code="traffic_limited_15gb",
            name="15 GB",
            kind=PLAN_KIND_PAID,
            payload="traffic_limited_15gb",
            scope=PRODUCT_SCOPE_TRAFFIC_LIMITED,
            entitlement_kind="traffic",
            duration_days=30,
            quota_bytes=15 * 1024 * 1024 * 1024,
            price_amount=Decimal("99.00"),
            currency="RUB",
            is_active=True,
            metadata_json={},
        )
        session.add(standard_plan)
        session.add(traffic_limited_plan)
        await session.flush()
        standard_plan_id = int(standard_plan.id)

        session.add(
            SubscriptionState(
                user_id=int(user.id),
                current_expires_at=now.replace(month=5),
                trial_activated_at=None,
                info_channel_activated_at=None,
                blocked_at=None,
                updated_at=now,
                version=1,
            )
        )
        standard_client = VpnClient(
            user_id=int(user.id),
            scope=PRODUCT_SCOPE_STANDARD,
            provider="3x-ui",
            external_client_uuid="uuid-standard",
            external_email="user@example.com",
            subscription_external_id="sub-standard",
            created_at=now,
            updated_at=now,
            deactivated_at=None,
        )
        session.add(standard_client)
        await session.flush()
        traffic_limited_client = VpnClient(
            user_id=int(user.id),
            scope=PRODUCT_SCOPE_TRAFFIC_LIMITED,
            provider="3x-ui",
            external_client_uuid="uuid-traffic_limited",
            external_email="wl-user@example.com",
            subscription_external_id="sub-traffic_limited",
            created_at=now,
            updated_at=now,
            deactivated_at=None,
        )
        session.add(traffic_limited_client)
        await session.flush()
        session.add(
            TrafficState(
                vpn_client_id=int(traffic_limited_client.id),
                scope=PRODUCT_SCOPE_TRAFFIC_LIMITED,
                allocated_bytes=15 * 1024 * 1024 * 1024,
                used_bytes=5 * 1024 * 1024 * 1024,
                remaining_bytes=10 * 1024 * 1024 * 1024,
                is_blocked=False,
                expires_at=now.replace(month=5),
                last_provider_sync_at=now,
                updated_at=now,
            )
        )
        order = PaymentOrder(
            user_id=int(user.id),
            plan_id=standard_plan_id,
            status="fulfilled",
            amount=Decimal("169.00"),
            currency="RUB",
            created_at=now,
            paid_at=now,
            fulfilled_at=now,
            idempotency_key=None,
            subscription_grant_id=None,
            metadata_json={},
        )
        session.add(order)
        await session.flush()
        session.add(
            PaymentAttempt(
                order_id=int(order.id),
                provider="external_card",
                provider_payment_id="pay_1",
                provider_status="paid",
                provider_payload_json={},
                created_at=now,
                updated_at=now,
                paid_at=now,
            )
        )
        session.add(
            AccessGrant(
                user_id=int(user.id),
                granted_by_user_id=None,
                plan_id=standard_plan_id,
                template_code="month_1",
                scope=PRODUCT_SCOPE_STANDARD,
                entitlement_kind=ENTITLEMENT_KIND_TIME,
                source_type="request_approval",
                source_ref="access_request:1",
                status="active",
                expires_at=now.replace(month=5),
                quota_bytes=None,
                created_at=now,
                activated_at=now,
                metadata_json={"approved_template_code": "month_1"},
            )
        )
        await session.commit()
        return int(user.id)


@pytest.mark.asyncio
async def test_get_profile_returns_profile_data(account_service, seeded_user):
    profile = await account_service.get_profile(user_id=seeded_user)

    assert profile.display_name == "Cat"
    assert profile.auth_email == "user@example.com"
    assert profile.email_verified is True


@pytest.mark.asyncio
async def test_update_profile_creates_and_updates_profile(session_factory, account_service):
    now = _now()
    async with session_factory() as session:
        user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(user)
        await session.flush()
        session.add(
            WebAccount(
                user_id=int(user.id),
                email="new@example.com",
                password_hash="hash",
                email_verified_at=now,
                linked_at=now,
                last_login_at=None,
                revoked_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        user_id = int(user.id)

    profile = await account_service.update_profile(
        user_id=user_id,
        display_name="New User",
        timezone_name="UTC",
        locale="en",
        marketing_opt_in=True,
        preferred_contact_email="contact@example.com",
    )

    assert profile.display_name == "New User"
    assert profile.marketing_opt_in is True
    assert profile.preferred_contact_email is None


@pytest.mark.asyncio
async def test_update_profile_keeps_preferred_email_only_without_auth_email(session_factory, account_service):
    now = _now()
    async with session_factory() as session:
        user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(user)
        await session.commit()
        user_id = int(user.id)

    profile = await account_service.update_profile(
        user_id=user_id,
        display_name="TG only",
        timezone_name=None,
        locale=None,
        marketing_opt_in=False,
        preferred_contact_email="contact@example.com",
    )

    assert profile.preferred_contact_email == "contact@example.com"


@pytest.mark.asyncio
async def test_update_profile_rejects_preferred_email_of_another_account(session_factory, account_service):
    now = _now()
    async with session_factory() as session:
        owner = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        second = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(owner)
        session.add(second)
        await session.flush()
        session.add(
            UserProfile(
                user_id=int(owner.id),
                display_name=None,
                timezone=None,
                locale=None,
                marketing_opt_in=False,
                preferred_contact_email="reserved@example.com",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        second_user_id = int(second.id)

    with pytest.raises(account_service_module.HTTPException) as exc:
        await account_service.update_profile(
            user_id=second_user_id,
            display_name=None,
            timezone_name=None,
            locale=None,
            marketing_opt_in=False,
            preferred_contact_email="reserved@example.com",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Email already attached to another account"


@pytest.mark.asyncio
async def test_update_profile_rejects_preferred_email_used_as_auth_email(session_factory, account_service):
    now = _now()
    async with session_factory() as session:
        owner = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        second = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(owner)
        session.add(second)
        await session.flush()
        session.add(
            WebAccount(
                user_id=int(owner.id),
                email="taken@example.com",
                password_hash="hash",
                email_verified_at=now,
                linked_at=now,
                last_login_at=now,
                revoked_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
        second_user_id = int(second.id)

    with pytest.raises(account_service_module.HTTPException) as exc:
        await account_service.update_profile(
            user_id=second_user_id,
            display_name=None,
            timezone_name=None,
            locale=None,
            marketing_opt_in=False,
            preferred_contact_email="taken@example.com",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Email already attached to another account"


@pytest.mark.asyncio
async def test_get_links_returns_web_and_telegram_state(account_service, seeded_user):
    links = await account_service.get_links(user_id=seeded_user)

    assert links["web"]["linked"] is True
    assert links["telegram"]["linked"] is True
    assert links["telegram"]["telegram_id"] == 123456


@pytest.mark.asyncio
async def test_get_subscriptions_returns_both_scopes(account_service, seeded_user):
    subscriptions = await account_service.get_subscriptions(user_id=seeded_user)

    assert subscriptions["standard"]["is_active"] is True
    assert subscriptions["standard"]["subscription_import_url"]
    assert subscriptions["traffic_limited"]["is_active"] is True
    assert subscriptions["traffic_limited"]["traffic_remaining_bytes"] == 10 * 1024 * 1024 * 1024


@pytest.mark.asyncio
async def test_get_subscriptions_hides_import_links_for_inactive_access(session_factory, account_service):
    now = _now()
    expired = now.replace(month=3)
    async with session_factory() as session:
        user = AppUser(created_at=now, updated_at=now, blocked_at=None, deleted_at=None)
        session.add(user)
        await session.flush()
        session.add(
            VpnClient(
                user_id=int(user.id),
                scope=PRODUCT_SCOPE_STANDARD,
                provider="3x-ui",
                external_client_uuid="uuid-standard",
                external_email="user@example.com",
                subscription_external_id="sub-standard",
                created_at=now,
                updated_at=now,
                deactivated_at=None,
            )
        )
        session.add(
            SubscriptionState(
                user_id=int(user.id),
                current_expires_at=expired,
                trial_activated_at=None,
                info_channel_activated_at=None,
                blocked_at=None,
                updated_at=now,
                version=1,
            )
        )
        await session.commit()
        user_id = int(user.id)

    subscriptions = await account_service.get_subscriptions(user_id=user_id)

    assert subscriptions["standard"]["is_active"] is False
    assert subscriptions["standard"]["subscription_import_url"] is None


@pytest.mark.asyncio
async def test_get_payments_returns_user_payment_history(account_service, seeded_user):
    payments = await account_service.get_payments(user_id=seeded_user)

    assert len(payments) == 1
    assert payments[0]["provider_payment_id"] == "pay_1"
    assert payments[0]["runtime_status"] == "paid"


@pytest.mark.asyncio
async def test_get_access_grants_returns_user_access_history(account_service, seeded_user):
    grants = await account_service.get_access_grants(user_id=seeded_user)

    assert len(grants) == 1
    assert grants[0]["template_code"] == "month_1"
    assert grants[0]["scope"] == PRODUCT_SCOPE_STANDARD
    assert grants[0]["source_type"] == "request_approval"
    assert grants[0]["metadata"]["approved_template_code"] == "month_1"


@pytest.mark.asyncio
async def test_get_plan_catalog_returns_active_paid_plans(account_service, seeded_user, monkeypatch):
    monkeypatch.setattr(
        account_service_module,
        "get_effective_product_feature_settings",
        lambda: type(
            "FeatureFlags",
            (),
            {
                "standard_config_enabled": True,
                "traffic_limited_config_enabled": True,
            },
        )(),
    )
    catalog = await account_service.get_plan_catalog()

    assert catalog["standard"]
    assert catalog["traffic_limited"]
    assert catalog["standard"][0]["scope"] == PRODUCT_SCOPE_STANDARD
    assert catalog["traffic_limited"][0]["scope"] == PRODUCT_SCOPE_TRAFFIC_LIMITED
    assert catalog["traffic_limited"][0]["human_view_traffic_quota"]


@pytest.mark.asyncio
async def test_get_plan_catalog_filters_disabled_modules(account_service, seeded_user, monkeypatch):
    monkeypatch.setattr(
        account_service_module,
        "get_effective_product_feature_settings",
        lambda: type(
            "FeatureFlags",
            (),
            {
                "standard_config_enabled": False,
                "traffic_limited_config_enabled": True,
            },
        )(),
    )

    catalog = await account_service.get_plan_catalog()

    assert catalog["standard"] == []
    assert catalog["traffic_limited"]
