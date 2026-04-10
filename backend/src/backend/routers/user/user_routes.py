from fastapi import APIRouter, Depends

from backend.bootstrap import get_jwt_encoder
from shared.config.config import (
    BOT_SUPPORT_TG_LINK,
    FRONTEND_APP_LINK_HAPP_ANDROID,
    FRONTEND_APP_LINK_HAPP_ANDROID_APK,
    FRONTEND_APP_LINK_HAPP_ANDROID_TV,
    FRONTEND_APP_LINK_HAPP_APPLE_TV,
    FRONTEND_APP_LINK_HAPP_IOS,
    FRONTEND_APP_LINK_HAPP_IOS_GLOBAL,
    FRONTEND_APP_LINK_HAPP_LINUX,
    FRONTEND_APP_LINK_HAPP_LINUX_RPM,
    FRONTEND_APP_LINK_HAPP_MACOS,
    FRONTEND_APP_LINK_HAPP_MACOS_DMG,
    FRONTEND_APP_LINK_HAPP_WINDOWS,
    FRONTEND_APP_LINK_WINDOWS_NEKORAY,
    FRONTEND_HAPP_SUBSCRIPTION_ADD_LINK,
    FRONTEND_INSTRUCTION_LINK_ANDROID,
    FRONTEND_INSTRUCTION_LINK_IOS,
    FRONTEND_INSTRUCTION_LINK_LINUX,
    FRONTEND_INSTRUCTION_LINK_MACOS,
    FRONTEND_INSTRUCTION_LINK_WINDOWS,
    FRONTEND_INSTRUCTION_LINK_WINDOWS_NEKORAY,
    FRONTEND_SUBSCRIPTION_CLIENT_NAME,
    PAYMENT_PROVIDER_CARD_CODE,
    PAYMENT_PROVIDER_CARD_LABEL,
    PAYMENT_PROVIDER_WALLET_CODE,
    PAYMENT_PROVIDER_WALLET_LABEL,
)
from shared.config.settings import get_effective_product_feature_settings, get_product_settings
from shared.utils.jwt_encoder import JWTEncoder

router = APIRouter(prefix="/user", tags=["user"])


def _truthy_links(value: dict[str, str]) -> dict[str, str]:
    return {key: link for key, link in value.items() if isinstance(link, str) and link.strip()}


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
    features = get_effective_product_feature_settings()
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
            "docs_links": _truthy_links(product.docs_links),
        },
        "features": {
            "access_requests_enabled": features.access_requests_enabled,
            "access_registry_enabled": features.access_registry_enabled,
            "access_admin_override_enabled": features.access_admin_override_enabled,
            "commerce_enabled": features.commerce_enabled,
            "referrals_enabled": features.referrals_enabled,
            "promos_enabled": features.promos_enabled,
            "web_purchase_enabled": features.web_purchase_enabled,
            "telegram_bot_enabled": features.telegram_bot_enabled,
            "mail_enabled": features.mail_enabled,
            "standard_config_enabled": features.standard_config_enabled,
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
        "subscription_add_links": {
            "happ": FRONTEND_HAPP_SUBSCRIPTION_ADD_LINK,
        },
        "subscription_client": {
            "name": FRONTEND_SUBSCRIPTION_CLIENT_NAME,
        },
        "app_links": {
            "happ_ios_global": FRONTEND_APP_LINK_HAPP_IOS_GLOBAL,
            "happ_ios": FRONTEND_APP_LINK_HAPP_IOS,
            "happ_android": FRONTEND_APP_LINK_HAPP_ANDROID,
            "happ_android_apk": FRONTEND_APP_LINK_HAPP_ANDROID_APK,
            "happ_windows": FRONTEND_APP_LINK_HAPP_WINDOWS,
            "happ_macos": FRONTEND_APP_LINK_HAPP_MACOS,
            "happ_macos_dmg": FRONTEND_APP_LINK_HAPP_MACOS_DMG,
            "happ_linux": FRONTEND_APP_LINK_HAPP_LINUX,
            "happ_linux_rpm": FRONTEND_APP_LINK_HAPP_LINUX_RPM,
            "happ_apple_tv": FRONTEND_APP_LINK_HAPP_APPLE_TV,
            "happ_android_tv": FRONTEND_APP_LINK_HAPP_ANDROID_TV,
            "windows_nekoray": FRONTEND_APP_LINK_WINDOWS_NEKORAY,
        },
        "instruction_links": {
            key: value
            for key, value in {
                "ios": FRONTEND_INSTRUCTION_LINK_IOS,
                "android": FRONTEND_INSTRUCTION_LINK_ANDROID,
                "windows": FRONTEND_INSTRUCTION_LINK_WINDOWS,
                "macos": FRONTEND_INSTRUCTION_LINK_MACOS,
                "linux": FRONTEND_INSTRUCTION_LINK_LINUX,
                "windows_nekoray": FRONTEND_INSTRUCTION_LINK_WINDOWS_NEKORAY,
            }.items()
            if value
        },
    }
