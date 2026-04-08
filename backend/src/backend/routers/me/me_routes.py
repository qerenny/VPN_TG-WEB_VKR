from __future__ import annotations

from dataclasses import asdict, is_dataclass

from fastapi import APIRouter, Depends, HTTPException

from backend.auth.web_auth import require_web_user
from backend.bootstrap import get_account_service, get_linking_service, get_web_checkout_service, get_web_promo_service
from backend.schemas.auth.auth_schemas import WebMeResponse
from backend.schemas.me.account_schemas import (
    WebLinksResponse,
    WebPaymentsResponse,
    WebPlanCatalogResponse,
    WebProfileResponse,
    WebProfileUpdateRequest,
    WebReferralStatsResponse,
    WebSubscriptionsResponse,
)
from backend.schemas.me.linking_schemas import TelegramLinkStartResponse
from backend.schemas.me.payment_checkout_schemas import (
    WebCheckoutRequest,
    WebCheckoutResponse,
)
from backend.schemas.me.promo_schemas import (
    WebPromoApplyRequest,
    WebPromoApplyResponse,
)
from backend.services.account.account_service import AccountService
from backend.services.auth.auth_service import AuthenticatedWebUser
from backend.services.linking.linking_service import LinkingService
from backend.services.payments.web_checkout_service import WebCheckoutService
from backend.services.promo.web_promo_service import WebPromoService, PromoError
from shared.config.settings import ProductFeatureSettings, get_product_feature_settings
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_WHITELIST

router = APIRouter(prefix="/me", tags=["me"])


def _serialize_payload(value):
    if is_dataclass(value):
        return asdict(value)
    return vars(value)


def _raise_feature_disabled() -> None:
    raise HTTPException(status_code=404, detail="Feature is disabled")


def _require_commerce_enabled(features: ProductFeatureSettings | None = None) -> ProductFeatureSettings:
    current = features or get_product_feature_settings()
    if not current.commerce_enabled:
        _raise_feature_disabled()
    return current


def _require_web_purchase_enabled(features: ProductFeatureSettings | None = None) -> ProductFeatureSettings:
    current = _require_commerce_enabled(features)
    if not current.web_purchase_enabled:
        _raise_feature_disabled()
    return current


def _require_referrals_enabled(features: ProductFeatureSettings | None = None) -> ProductFeatureSettings:
    current = features or get_product_feature_settings()
    if not current.referrals_enabled:
        _raise_feature_disabled()
    return current


def _require_promos_enabled(features: ProductFeatureSettings | None = None) -> ProductFeatureSettings:
    current = features or get_product_feature_settings()
    if not current.promos_enabled:
        _raise_feature_disabled()
    return current


@router.get("", response_model=WebMeResponse)
async def get_web_session_me(
    principal: AuthenticatedWebUser = Depends(require_web_user),
    account_service: AccountService = Depends(get_account_service),
):
    profile = await account_service.get_profile(user_id=principal.user_id)
    return WebMeResponse(
        user_id=principal.user_id,
        email=principal.email,
        email_verified=principal.email_verified,
        telegram_linked=principal.telegram_linked,
        telegram_id=principal.telegram_id,
        telegram_username=principal.telegram_username,
        display_name=profile.display_name,
        timezone=profile.timezone,
        locale=profile.locale,
        marketing_opt_in=profile.marketing_opt_in,
        preferred_contact_email=profile.preferred_contact_email,
        created_at=principal.created_at.isoformat(),
        last_login_at=principal.last_login_at.isoformat() if principal.last_login_at else None,
    )


@router.get("/profile", response_model=WebProfileResponse)
async def get_web_profile(
    principal: AuthenticatedWebUser = Depends(require_web_user),
    account_service: AccountService = Depends(get_account_service),
):
    profile = await account_service.get_profile(user_id=principal.user_id)
    return WebProfileResponse(**_serialize_payload(profile))


@router.patch("/profile", response_model=WebProfileResponse)
async def patch_web_profile(
    payload: WebProfileUpdateRequest,
    principal: AuthenticatedWebUser = Depends(require_web_user),
    account_service: AccountService = Depends(get_account_service),
):
    profile = await account_service.update_profile(
        user_id=principal.user_id,
        display_name=payload.display_name,
        timezone_name=payload.timezone,
        locale=payload.locale,
        marketing_opt_in=payload.marketing_opt_in,
        preferred_contact_email=payload.preferred_contact_email,
    )
    return WebProfileResponse(**_serialize_payload(profile))


@router.get("/subscriptions", response_model=WebSubscriptionsResponse)
async def get_web_subscriptions(
    principal: AuthenticatedWebUser = Depends(require_web_user),
    account_service: AccountService = Depends(get_account_service),
):
    return WebSubscriptionsResponse(**(await account_service.get_subscriptions(user_id=principal.user_id)))


@router.get("/payments", response_model=WebPaymentsResponse)
async def get_web_payments(
    principal: AuthenticatedWebUser = Depends(require_web_user),
    account_service: AccountService = Depends(get_account_service),
):
    _require_commerce_enabled()
    return WebPaymentsResponse(items=await account_service.get_payments(user_id=principal.user_id))


@router.get("/plans", response_model=WebPlanCatalogResponse)
async def get_web_plan_catalog(
    principal: AuthenticatedWebUser = Depends(require_web_user),
    account_service: AccountService = Depends(get_account_service),
):
    _require_commerce_enabled()
    return WebPlanCatalogResponse(**(await account_service.get_plan_catalog()))


@router.get("/referrals", response_model=WebReferralStatsResponse)
async def get_web_referral_stats(
    principal: AuthenticatedWebUser = Depends(require_web_user),
    account_service: AccountService = Depends(get_account_service),
):
    _require_referrals_enabled()
    stats = await account_service.get_referral_stats(user_id=principal.user_id)
    return WebReferralStatsResponse(**stats)


@router.get("/links", response_model=WebLinksResponse)
async def get_web_links(
    principal: AuthenticatedWebUser = Depends(require_web_user),
    account_service: AccountService = Depends(get_account_service),
):
    return WebLinksResponse(**(await account_service.get_links(user_id=principal.user_id)))


@router.post("/links/telegram/start", response_model=TelegramLinkStartResponse)
async def start_telegram_link(
    principal: AuthenticatedWebUser = Depends(require_web_user),
    linking_service: LinkingService = Depends(get_linking_service),
):
    result = await linking_service.start_telegram_link(user_id=principal.user_id)
    return TelegramLinkStartResponse(**_serialize_payload(result))


@router.post("/payments/checkout", response_model=WebCheckoutResponse)
async def create_web_checkout(
    payload: WebCheckoutRequest,
    principal: AuthenticatedWebUser = Depends(require_web_user),
    checkout_service: WebCheckoutService = Depends(get_web_checkout_service),
):
    _require_web_purchase_enabled()
    result = await checkout_service.create_checkout(
        user_id=principal.user_id,
        plan_code=payload.plan_code,
        method=payload.method,
        expected_scope=PRODUCT_SCOPE_STANDARD,
    )
    return WebCheckoutResponse(**_serialize_payload(result))


@router.post("/payments/checkout/whitelist", response_model=WebCheckoutResponse)
async def create_whitelist_web_checkout(
    payload: WebCheckoutRequest,
    principal: AuthenticatedWebUser = Depends(require_web_user),
    checkout_service: WebCheckoutService = Depends(get_web_checkout_service),
):
    _require_web_purchase_enabled()
    result = await checkout_service.create_checkout(
        user_id=principal.user_id,
        plan_code=payload.plan_code,
        method=payload.method,
        expected_scope=PRODUCT_SCOPE_WHITELIST,
    )
    return WebCheckoutResponse(**_serialize_payload(result))


@router.post("/promo/apply", response_model=WebPromoApplyResponse)
async def apply_promo_code(
    payload: WebPromoApplyRequest,
    principal: AuthenticatedWebUser = Depends(require_web_user),
    promo_service: WebPromoService = Depends(get_web_promo_service),
):
    _require_promos_enabled()
    try:
        result = await promo_service.apply_promo(
            user_id=principal.user_id,
            code=payload.code,
        )
        return WebPromoApplyResponse(**_serialize_payload(result))
    except PromoError as e:
        raise HTTPException(status_code=400, detail=e.detail)
