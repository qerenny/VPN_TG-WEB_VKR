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
async def test_get_public_config_returns_frontend_links():
    result = await user_routes.get_public_config()

    assert result["support_link"].startswith("https://t.me/")
    assert "subscription_add_links" in result
    assert result["features"]["commerce_enabled"] is True
    assert result["features"]["referrals_enabled"] is True
    assert result["features"]["promos_enabled"] is True
    assert "app_links" in result
    assert "instruction_links" in result
    assert "happ" in result["subscription_add_links"]
    assert "happ_ios" in result["app_links"]
    assert "ios" in result["instruction_links"]
