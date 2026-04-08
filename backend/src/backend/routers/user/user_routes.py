from fastapi import APIRouter, Depends

from backend.bootstrap import get_jwt_encoder
from shared.config.config import (
    BOT_SUPPORT_TG_LINK,
    FRONTEND_APP_LINK_HAPP_ANDROID,
    FRONTEND_APP_LINK_HAPP_IOS,
    FRONTEND_APP_LINK_HAPP_LINUX,
    FRONTEND_APP_LINK_HAPP_MACOS,
    FRONTEND_APP_LINK_HAPP_WINDOWS,
    FRONTEND_APP_LINK_WINDOWS_NEKORAY,
    FRONTEND_HAPP_SUBSCRIPTION_ADD_LINK,
    FRONTEND_INSTRUCTION_LINK_ANDROID,
    FRONTEND_INSTRUCTION_LINK_IOS,
    FRONTEND_INSTRUCTION_LINK_LINUX,
    FRONTEND_INSTRUCTION_LINK_MACOS,
    FRONTEND_INSTRUCTION_LINK_WINDOWS,
    FRONTEND_INSTRUCTION_LINK_WINDOWS_NEKORAY,
    FRONTEND_TELEGRAM_PROXY_URL,
    PAYMENT_PROVIDER_CARD_CODE,
    PAYMENT_PROVIDER_CARD_LABEL,
    PAYMENT_PROVIDER_WALLET_CODE,
    PAYMENT_PROVIDER_WALLET_LABEL,
)
from shared.config.settings import get_product_feature_settings, get_product_settings
from shared.utils.jwt_encoder import JWTEncoder

router = APIRouter(prefix="/user", tags=["user"])


@router.post("/encode")
async def encode_user(
    tg_id: int,
    email: str,
    jwt_encoder: JWTEncoder = Depends(get_jwt_encoder),
):
    token = jwt_encoder.encode({"tg_id": tg_id, "email": email})
    return {"token": token}


@router.get("/public-config")
async def get_public_config():
    features = get_product_feature_settings()
    product = get_product_settings()
    return {
        "product": {
            "name": product.name,
            "short_name": product.short_name,
            "description": product.description,
            "profile_title": product.profile_title,
            "traffic_profile_title": product.traffic_profile_title,
            "support_name": product.support_name,
            "support_link": product.support_link,
            "docs_links": product.docs_links,
        },
        "features": {
            "commerce_enabled": features.commerce_enabled,
            "referrals_enabled": features.referrals_enabled,
            "promos_enabled": features.promos_enabled,
            "web_purchase_enabled": features.web_purchase_enabled,
            "telegram_bot_enabled": features.telegram_bot_enabled,
            "telegram_proxy_enabled": features.telegram_proxy_enabled,
            "traffic_limited_config_enabled": features.traffic_limited_config_enabled,
        },
        "support_link": product.support_link or BOT_SUPPORT_TG_LINK,
        "payment_methods": {
            "primary": PAYMENT_PROVIDER_CARD_CODE,
            "items": [
                {
                    "code": PAYMENT_PROVIDER_CARD_CODE,
                    "label": PAYMENT_PROVIDER_CARD_LABEL,
                },
                {
                    "code": PAYMENT_PROVIDER_WALLET_CODE,
                    "label": PAYMENT_PROVIDER_WALLET_LABEL,
                },
            ],
        },
        "telegram_proxy_url": (
            FRONTEND_TELEGRAM_PROXY_URL if features.telegram_proxy_enabled else ""
        ),
        "subscription_add_links": {
            "happ": FRONTEND_HAPP_SUBSCRIPTION_ADD_LINK,
        },
        "app_links": {
            "happ_ios": FRONTEND_APP_LINK_HAPP_IOS,
            "happ_android": FRONTEND_APP_LINK_HAPP_ANDROID,
            "happ_windows": FRONTEND_APP_LINK_HAPP_WINDOWS,
            "happ_macos": FRONTEND_APP_LINK_HAPP_MACOS,
            "happ_linux": FRONTEND_APP_LINK_HAPP_LINUX,
            "windows_nekoray": FRONTEND_APP_LINK_WINDOWS_NEKORAY,
        },
        "instruction_links": {
            "ios": FRONTEND_INSTRUCTION_LINK_IOS,
            "android": FRONTEND_INSTRUCTION_LINK_ANDROID,
            "windows": FRONTEND_INSTRUCTION_LINK_WINDOWS,
            "macos": FRONTEND_INSTRUCTION_LINK_MACOS,
            "linux": FRONTEND_INSTRUCTION_LINK_LINUX,
            "windows_nekoray": FRONTEND_INSTRUCTION_LINK_WINDOWS_NEKORAY,
        },
    }
