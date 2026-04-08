from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func as sa_func, select

from shared.config.database.session import get_db_session
from shared.models.growth.promo_code_model import PromoCode
from shared.models.growth.promo_redemption_model import PromoRedemption
from shared.models.subscriptions.subscription_grant_model import SubscriptionGrant
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.payments.plan_model import Plan
from shared.utils.logging_utils import logger
from telegram_bot.services.subscriptions.standard_user_subscription_service import (
    StandardUserSubscriptionService,
)


@dataclass(frozen=True, slots=True)
class PromoApplyResult:
    status: str
    granted_days: int
    message: str


class WebPromoService:
    def __init__(
        self,
        *,
        standard_user_subscription_service: StandardUserSubscriptionService,
    ) -> None:
        self.standard_user_subscription_service = standard_user_subscription_service

    async def apply_promo(self, *, user_id: int, code: str) -> PromoApplyResult:
        normalized_code = code.strip()
        if not normalized_code:
            raise PromoError("Введите промокод")

        now = datetime.now(timezone.utc)

        # Step 1: validate + claim redemption slot via unique constraint.
        async with get_db_session() as session:
            promo = (
                await session.execute(
                    select(PromoCode).where(PromoCode.code == normalized_code)
                )
            ).scalar_one_or_none()
            if promo is None or not promo.is_active:
                raise PromoError("Промокод не найден или неактивен")

            if promo.valid_from and now < promo.valid_from:
                raise PromoError("Промокод ещё не активен")
            if promo.valid_until and now > promo.valid_until:
                raise PromoError("Срок действия промокода истёк")

            if promo.max_redemptions is not None:
                redemption_count = (
                    await session.execute(
                        select(sa_func.count(PromoRedemption.id)).where(
                            PromoRedemption.promo_code_id == promo.id
                        )
                    )
                ).scalar_one()
                if int(redemption_count) >= int(promo.max_redemptions):
                    raise PromoError("Промокод исчерпан")

            existing = (
                await session.execute(
                    select(PromoRedemption).where(
                        and_(
                            PromoRedemption.promo_code_id == promo.id,
                            PromoRedemption.user_id == int(user_id),
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise PromoError("Вы уже использовали этот промокод")

            duration_days = promo.duration_days_override
            if duration_days is None and promo.plan_id is not None:
                plan = await session.get(Plan, promo.plan_id)
                if plan is not None:
                    duration_days = plan.duration_days
            if not duration_days or int(duration_days) <= 0:
                raise PromoError("Промокод не содержит срока подписки")
            duration_days = int(duration_days)

            sub_state = await session.get(SubscriptionState, int(user_id))
            current_expires = getattr(sub_state, "current_expires_at", None)
            if current_expires is not None and current_expires.tzinfo is None:
                current_expires = current_expires.replace(tzinfo=timezone.utc)

            redemption = PromoRedemption(
                promo_code_id=promo.id,
                user_id=int(user_id),
                redeemed_at=now,
            )
            session.add(redemption)
            await session.commit()
            redemption_id = int(redemption.id)
            promo_id = int(promo.id)
            promo_plan_id = promo.plan_id

        # Step 2: push new expiration to 3x-ui + update SubscriptionState.
        try:
            activation = await self.standard_user_subscription_service.activate_days(
                user_id=int(user_id),
                duration_days=duration_days,
            )
        except Exception as exc:
            # Roll back the claim so the user can retry.
            logger.exception(
                f"Promo activation failed for user_id={user_id}, code={normalized_code}: {exc}"
            )
            async with get_db_session() as session:
                stale = await session.get(PromoRedemption, redemption_id)
                if stale is not None:
                    await session.delete(stale)
                    await session.commit()
            raise PromoError("Не удалось активировать промокод, попробуйте ещё раз")

        new_expires = activation.expires_at

        # Step 3: record SubscriptionGrant and link it to the redemption.
        async with get_db_session() as session:
            grant = SubscriptionGrant(
                user_id=int(user_id),
                plan_id=promo_plan_id,
                source_type="promo_redemption",
                source_ref=str(redemption_id),
                status="applied",
                duration_days=duration_days,
                expires_before=current_expires,
                expires_after=new_expires,
                created_at=now,
                applied_at=now,
                metadata_json={"promo_code": normalized_code},
            )
            session.add(grant)
            await session.flush()

            redemption = await session.get(PromoRedemption, redemption_id)
            if redemption is not None:
                redemption.subscription_grant_id = int(grant.id)

            await session.commit()

        logger.info(
            f"Promo {normalized_code!r} applied for user_id={user_id}, "
            f"granted_days={duration_days}, promo_id={promo_id}, "
            f"redemption_id={redemption_id}"
        )
        return PromoApplyResult(
            status="ok",
            granted_days=duration_days,
            message=f"Промокод активирован! +{duration_days} дн.",
        )


class PromoError(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)
