from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_legacy_payload
from shared.product_constants import ENTITLEMENT_KIND_TRAFFIC, PRODUCT_SCOPE_WHITELIST
from shared.utils.logging_utils import logger
from telegram_bot.services.referrals.referral_bonus_service import ReferralBonusService
from telegram_bot.services.subscriptions.subscription_flow_service import (
    SubscriptionFlowService,
)
from telegram_bot.shared.texts import messages


class PaymentProcessingService:
    def __init__(
        self,
        subscription_manager: SubscriptionFlowService,
        bonuses: ReferralBonusService,
        whitelist_traffic_service=None,
        standard_user_subscription_service=None,
        referrals_enabled: bool = True,
    ):
        self.subscription_manager = subscription_manager
        self.bonuses = bonuses
        self.whitelist_traffic_service = whitelist_traffic_service
        self.standard_user_subscription_service = standard_user_subscription_service
        self.referrals_enabled = referrals_enabled

    async def payment_processing(
        self,
        tg_id: int | None = None,
        product: str = "",
        *,
        user_id: int | None = None,
        payment_id: str | None = None,
    ) -> tuple[str, str, str | None, str | None, int | None]:
        seed = get_plan_seed_by_legacy_payload(product)
        if (
            seed is not None
            and seed.scope == PRODUCT_SCOPE_WHITELIST
            and seed.entitlement_kind == ENTITLEMENT_KIND_TRAFFIC
        ):
            if self.whitelist_traffic_service is None:
                raise ValueError("Traffic-limited configuration service is not configured")
            if not payment_id:
                raise ValueError("payment_id is required for traffic-limited payments")
            if tg_id is not None:
                result = await self.whitelist_traffic_service.activate_payment(
                    tg_id=int(tg_id),
                    product=str(product),
                    payment_id=str(payment_id),
                )
            else:
                if user_id is None:
                    raise ValueError("user_id is required for web traffic-limited payments")
                result = await self.whitelist_traffic_service.activate_payment_for_user(
                    user_id=int(user_id),
                    product=str(product),
                    payment_id=str(payment_id),
                )
            granted_gb = result.granted_bytes // (1024 * 1024 * 1024)
            remaining_gb = result.remaining_bytes // (1024 * 1024 * 1024)
            expiry_text = (
                result.expires_at.astimezone().strftime("%H:%M:%S %d-%m-%Y")
                if result.expires_at is not None
                else "без ограничения по сроку"
            )
            return (
                f"✅ Конфигурация с лимитом трафика активирована: +{granted_gb} GB",
                f"Остаток: {remaining_gb} GB\nДействует до: {expiry_text}",
                None,
                None,
                None,
            )

        grant_tg_id_text, grant_referrer_id_text = None, None
        if tg_id is None:
            if user_id is None:
                raise ValueError("user_id is required for web standard payments")
            if self.standard_user_subscription_service is None:
                raise ValueError("Standard user subscription service is not configured")
            result = await self.standard_user_subscription_service.activate_payment(
                user_id=int(user_id),
                product=str(product),
            )
            expiry_text = result.expires_at.astimezone().strftime("%H:%M:%S %d-%m-%Y")
            status_text = (
                "✅ Базовая конфигурация активирована"
                if result.was_created
                else "✅ Базовая конфигурация продлена"
            )
            return (
                status_text,
                f"Действует до: {expiry_text}",
                None,
                None,
                None,
            )

        logger.info(f"Activating or extending subscription for tg_id={tg_id}, product={product}")
        subscription_updated_text, subscription_update_date_text = await self.subscription_manager.activate_or_extend_subscription(
            tg_id=int(tg_id),
            period=product,
        )

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
            subscription_updated_text,
            subscription_update_date_text,
            grant_tg_id_text,
            grant_referrer_id_text,
            referrer_tg_id,
        )
