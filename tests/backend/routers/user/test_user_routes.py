from unittest.mock import MagicMock

import pytest

from backend.routers.user import user_routes


@pytest.mark.asyncio
async def test_encode_user_returns_jwt_token():
    jwt_encoder = MagicMock()
    jwt_encoder.encode.return_value = "jwt-token"

    result = await user_routes.encode_user(123, "user@example.com", jwt_encoder=jwt_encoder)

    jwt_encoder.encode.assert_called_once_with(
        {"tg_id": 123, "email": "user@example.com"}
    )
    assert result == {"token": "jwt-token"}


@pytest.mark.asyncio
async def test_get_public_config_returns_frontend_links(monkeypatch):
    monkeypatch.setattr(
        user_routes,
        "get_effective_product_feature_settings",
        lambda: type(
            "FeatureFlags",
            (),
            {
                "access_requests_enabled": True,
                "access_registry_enabled": True,
                "access_admin_override_enabled": True,
                "commerce_enabled": True,
                "referrals_enabled": True,
                "promos_enabled": True,
                "web_purchase_enabled": True,
                "telegram_bot_enabled": True,
                "mail_enabled": False,
                "standard_config_enabled": True,
                "traffic_limited_config_enabled": False,
            },
        )(),
    )
    result = await user_routes.get_public_config()

    assert result["support_link"] == result["product"]["support_link"]
    assert result["support_link"]
    assert "subscription_add_links" in result
    assert result["features"]["commerce_enabled"] is True
    assert result["features"]["referrals_enabled"] is True
    assert result["features"]["promos_enabled"] is True
    assert result["features"]["mail_enabled"] is False
    assert result["features"]["access_requests_enabled"] is True
    assert result["features"]["access_registry_enabled"] is True
    assert result["features"]["access_admin_override_enabled"] is True
    assert result["features"]["standard_config_enabled"] is True
    assert result["features"]["traffic_limited_config_enabled"] is False
    assert "app_links" in result
    assert "instruction_links" in result
    assert "happ" in result["subscription_add_links"]
    assert "happ_ios" in result["app_links"]
    assert isinstance(result["instruction_links"], dict)
    assert isinstance(result["product"]["docs_links"], dict)
