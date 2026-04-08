from datetime import datetime, timezone
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.routers.me import me_routes


def _features(**overrides):
    values = {
        "commerce_enabled": True,
        "referrals_enabled": True,
        "promos_enabled": True,
        "web_purchase_enabled": True,
        "telegram_bot_enabled": True,
        "telegram_proxy_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@dataclass(slots=True)
class _ProfileSnapshot:
    display_name: str | None
    timezone: str | None
    locale: str | None
    marketing_opt_in: bool
    preferred_contact_email: str | None
    auth_email: str | None
    email_verified: bool


@pytest.mark.asyncio
async def test_get_web_session_me_serializes_principal():
    principal = SimpleNamespace(
        user_id=7,
        email=None,
        email_verified=False,
        telegram_linked=True,
        telegram_id=123456,
        telegram_username="cat_user",
        created_at=datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
        last_login_at=None,
    )
    account_service = SimpleNamespace(
        get_profile=AsyncMock(
            return_value=_ProfileSnapshot(
                display_name="Cat",
                timezone="Europe/Moscow",
                locale="ru",
                marketing_opt_in=True,
                preferred_contact_email="profile@example.com",
                auth_email=None,
                email_verified=False,
            )
        )
    )

    result = await me_routes.get_web_session_me(principal=principal, account_service=account_service)

    assert result.user_id == 7
    assert result.email is None
    assert result.email_verified is False
    assert result.telegram_linked is True
    assert result.telegram_id == 123456
    assert result.telegram_username == "cat_user"
    assert result.display_name == "Cat"
    assert result.timezone == "Europe/Moscow"
    assert result.locale == "ru"
    assert result.marketing_opt_in is True
    assert result.preferred_contact_email == "profile@example.com"
    assert result.created_at.endswith("+00:00")
    assert result.last_login_at is None


@pytest.mark.asyncio
async def test_get_web_profile_returns_profile_payload():
    principal = SimpleNamespace(user_id=7)
    account_service = SimpleNamespace(
        get_profile=AsyncMock(
            return_value=_ProfileSnapshot(
                display_name="Cat",
                timezone="Europe/Moscow",
                locale="ru",
                marketing_opt_in=False,
                preferred_contact_email=None,
                auth_email=None,
                email_verified=False,
            )
        )
    )

    result = await me_routes.get_web_profile(principal=principal, account_service=account_service)

    assert result.display_name == "Cat"
    assert result.auth_email is None


@pytest.mark.asyncio
async def test_patch_web_profile_updates_profile():
    principal = SimpleNamespace(user_id=7)
    account_service = SimpleNamespace(
        update_profile=AsyncMock(
            return_value=_ProfileSnapshot(
                display_name="New Cat",
                timezone="Europe/Moscow",
                locale="ru",
                marketing_opt_in=True,
                preferred_contact_email="contact@example.com",
                auth_email=None,
                email_verified=False,
            )
        )
    )

    result = await me_routes.patch_web_profile(
        payload=me_routes.WebProfileUpdateRequest(
            display_name="New Cat",
            timezone="Europe/Moscow",
            locale="ru",
            marketing_opt_in=True,
            preferred_contact_email="contact@example.com",
        ),
        principal=principal,
        account_service=account_service,
    )

    assert result.display_name == "New Cat"
    account_service.update_profile.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_web_subscriptions_returns_payload():
    principal = SimpleNamespace(user_id=7)
    account_service = SimpleNamespace(
        get_subscriptions=AsyncMock(
            return_value={"standard": {"is_active": True}, "whitelist": {"is_active": False}}
        )
    )

    result = await me_routes.get_web_subscriptions(
        principal=principal,
        account_service=account_service,
    )

    assert result.standard["is_active"] is True
    assert result.whitelist["is_active"] is False


@pytest.mark.asyncio
async def test_get_web_payments_returns_items():
    principal = SimpleNamespace(user_id=7)
    account_service = SimpleNamespace(
        get_payments=AsyncMock(
            return_value=[{"order_id": 1, "status": "fulfilled"}]
        )
    )

    result = await me_routes.get_web_payments(
        principal=principal,
        account_service=account_service,
    )

    assert result.items == [{"order_id": 1, "status": "fulfilled"}]


@pytest.mark.asyncio
async def test_get_web_payments_rejects_disabled_commerce(monkeypatch):
    monkeypatch.setattr(
        me_routes,
        "get_product_feature_settings",
        lambda: _features(commerce_enabled=False),
    )
    account_service = SimpleNamespace(get_payments=AsyncMock())

    with pytest.raises(me_routes.HTTPException) as exc_info:
        await me_routes.get_web_payments(
            principal=SimpleNamespace(user_id=7),
            account_service=account_service,
        )

    assert exc_info.value.status_code == 404
    account_service.get_payments.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_web_links_returns_payload():
    principal = SimpleNamespace(user_id=7)
    account_service = SimpleNamespace(
        get_links=AsyncMock(
            return_value={"web": {"linked": True}, "telegram": {"linked": False}}
        )
    )

    result = await me_routes.get_web_links(
        principal=principal,
        account_service=account_service,
    )

    assert result.web["linked"] is True
    assert result.telegram["linked"] is False


@pytest.mark.asyncio
async def test_get_web_plan_catalog_returns_payload():
    principal = SimpleNamespace(user_id=7)
    account_service = SimpleNamespace(
        get_plan_catalog=AsyncMock(
            return_value={
                "standard": [{"code": "month_1"}],
                "whitelist": [{"code": "whitelist_15gb"}],
            }
        )
    )

    result = await me_routes.get_web_plan_catalog(
        principal=principal,
        account_service=account_service,
    )

    assert result.standard == [{"code": "month_1"}]
    assert result.whitelist == [{"code": "whitelist_15gb"}]


@pytest.mark.asyncio
async def test_get_web_referral_stats_rejects_disabled_referrals(monkeypatch):
    monkeypatch.setattr(
        me_routes,
        "get_product_feature_settings",
        lambda: _features(referrals_enabled=False),
    )
    account_service = SimpleNamespace(get_referral_stats=AsyncMock())

    with pytest.raises(me_routes.HTTPException) as exc_info:
        await me_routes.get_web_referral_stats(
            principal=SimpleNamespace(user_id=7),
            account_service=account_service,
        )

    assert exc_info.value.status_code == 404
    account_service.get_referral_stats.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_web_checkout_uses_checkout_service():
    principal = SimpleNamespace(user_id=7)
    checkout_service = SimpleNamespace(
        create_checkout=AsyncMock(
            return_value=SimpleNamespace(
                payment_id="pay_1",
                status="pending",
                checkout_url="https://pay.example.com/1",
                provider="yookassa",
                plan_code="month_1",
                plan_name="1 month access",
                scope="standard",
                amount="169.00",
                currency="RUB",
            )
        )
    )

    result = await me_routes.create_web_checkout(
        payload=me_routes.WebCheckoutRequest(plan_code="month_1", method="yookassa"),
        principal=principal,
        checkout_service=checkout_service,
    )

    assert result.payment_id == "pay_1"
    assert result.scope == "standard"
    checkout_service.create_checkout.assert_awaited_once_with(
        user_id=7,
        plan_code="month_1",
        method="yookassa",
        expected_scope="standard",
    )


@pytest.mark.asyncio
async def test_create_web_checkout_rejects_disabled_web_purchase(monkeypatch):
    monkeypatch.setattr(
        me_routes,
        "get_product_feature_settings",
        lambda: _features(web_purchase_enabled=False),
    )
    checkout_service = SimpleNamespace(create_checkout=AsyncMock())

    with pytest.raises(me_routes.HTTPException) as exc_info:
        await me_routes.create_web_checkout(
            payload=me_routes.WebCheckoutRequest(plan_code="month_1", method="yookassa"),
            principal=SimpleNamespace(user_id=7),
            checkout_service=checkout_service,
        )

    assert exc_info.value.status_code == 404
    checkout_service.create_checkout.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_whitelist_web_checkout_uses_checkout_service():
    principal = SimpleNamespace(user_id=7)
    checkout_service = SimpleNamespace(
        create_checkout=AsyncMock(
            return_value=SimpleNamespace(
                payment_id="pay_2",
                status="pending",
                checkout_url="https://pay.example.com/2",
                provider="cryptopay",
                plan_code="whitelist_15gb",
                plan_name="Traffic-limited access 15 GB",
                scope="whitelist",
                amount="99.00",
                currency="RUB",
            )
        )
    )

    result = await me_routes.create_whitelist_web_checkout(
        payload=me_routes.WebCheckoutRequest(plan_code="whitelist_15gb", method="cryptopay"),
        principal=principal,
        checkout_service=checkout_service,
    )

    assert result.payment_id == "pay_2"
    assert result.scope == "whitelist"
    checkout_service.create_checkout.assert_awaited_once_with(
        user_id=7,
        plan_code="whitelist_15gb",
        method="cryptopay",
        expected_scope="whitelist",
    )


@pytest.mark.asyncio
async def test_apply_promo_code_rejects_disabled_promos(monkeypatch):
    monkeypatch.setattr(
        me_routes,
        "get_product_feature_settings",
        lambda: _features(promos_enabled=False),
    )
    promo_service = SimpleNamespace(apply_promo=AsyncMock())

    with pytest.raises(me_routes.HTTPException) as exc_info:
        await me_routes.apply_promo_code(
            payload=me_routes.WebPromoApplyRequest(code="TEST"),
            principal=SimpleNamespace(user_id=7),
            promo_service=promo_service,
        )

    assert exc_info.value.status_code == 404
    promo_service.apply_promo.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_telegram_link_uses_linking_service():
    principal = SimpleNamespace(user_id=7)
    linking_service = SimpleNamespace(
        start_telegram_link=AsyncMock(
            return_value=SimpleNamespace(
                status="pending",
                deep_link="https://t.me/test_bot?start=link_x",
                expires_at="2026-04-03T12:30:00+00:00",
                telegram_id=None,
                telegram_username=None,
            )
        )
    )

    result = await me_routes.start_telegram_link(
        principal=principal,
        linking_service=linking_service,
    )

    assert result.status == "pending"
    assert result.deep_link == "https://t.me/test_bot?start=link_x"
    linking_service.start_telegram_link.assert_awaited_once_with(user_id=7)
