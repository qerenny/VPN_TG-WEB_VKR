from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_payload
from shared.product_constants import ENTITLEMENT_KIND_TRAFFIC, PRODUCT_SCOPE_TRAFFIC_LIMITED
from shared.utils.logging_utils import logger
from telegram_bot.services.referrals.referral_bonus_service import ReferralBonusService
from telegram_bot.services.access.access_issuance_service import AccessIssuanceService
from telegram_bot.shared.texts import messages


class PaymentProcessingService:
    def __init__(
        self,
        access_issuance_service: AccessIssuanceService,
        bonuses: ReferralBonusService,
        referrals_enabled: bool = True,
    ):
        self.access_issuance_service = access_issuance_service
        self.subscription_manager = access_issuance_service.subscription_flow_service
        self.traffic_limited_service = access_issuance_service.traffic_limited_service
        self.standard_user_subscription_service = (
            access_issuance_service.standard_user_subscription_service
        )
        self.bonuses = bonuses
        self.referrals_enabled = referrals_enabled

    async def payment_processing(
        self,
        tg_id: int | None = None,
        product: str = "",
        *,
        user_id: int | None = None,
        payment_id: str | None = None,
    ) -> tuple[str, str, str | None, str | None, int | None]:
        seed = get_plan_seed_by_payload(product)
        access_result = await self.access_issuance_service.activate_from_payload(
            payload=str(product),
            source_type="payment",
            source_ref=str(payment_id or product),
            tg_id=int(tg_id) if tg_id is not None else None,
            user_id=int(user_id) if user_id is not None else None,
        )

        grant_tg_id_text, grant_referrer_id_text = None, None
        if tg_id is None:
            return (
                access_result.activation_text,
                access_result.activation_details_text,
                None,
                None,
                None,
            )
        if (
            seed is not None
            and seed.scope == PRODUCT_SCOPE_TRAFFIC_LIMITED
            and seed.entitlement_kind == ENTITLEMENT_KIND_TRAFFIC
        ):
            return (
                access_result.activation_text,
                access_result.activation_details_text,
                None,
                None,
                None,
            )

        logger.info(f"Activating or extending subscription for tg_id={tg_id}, product={product}")
        days, referrer_tg_id, referrer_days = 0, None, None
        if self.referrals_enabled:
            try:
                days, referrer_tg_id, referrer_days = await self.bonuses.grant_pending_and_referrer_bonus(int(tg_id))
            except Exception as err:
                # Bonus flow is best-effort and should not block a paid subscription activation.
                logger.error(f"Failed to process referral bonuses for tg_id={tg_id}: {err}")

        if days:
            grant_tg_id_text = messages.get_random_message("payments_charge_bonuses").format(days=days)
            logger.info(f"Granted {days} bonus days to tg_id={tg_id}")

        if referrer_tg_id:
            grant_referrer_id_text = messages.get_random_message("payments_charge_bonuses").format(days=referrer_days)
            logger.info(f"Granted {referrer_days} bonus days to referrer_tg_id={referrer_tg_id}")

        return (
            access_result.activation_text,
            access_result.activation_details_text,
            grant_tg_id_text,
            grant_referrer_id_text,
            referrer_tg_id,
        )
