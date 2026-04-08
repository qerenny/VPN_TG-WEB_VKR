from __future__ import annotations

from shared.config.config import BOT_BONUS_NEW_USER_INT
from shared.constants.referrals import (
    REFERRAL_REWARD_SOURCE_TELEGRAM_START,
    REFERRAL_TRIGGER_INVITE_REGISTERED,
)
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
)
from shared.infrastructure.promos.promo_code_usage_repository import (
    PromoCodeUsageRepository,
)
from shared.infrastructure.referrals.referral_repository import (
    ReferralRepository,
    ReferralSnapshot,
)
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.infrastructure.growth_sync_service import (
    ReferralRewardContext,
)
from shared.utils.logging_utils import logger
from telegram_bot.services.referrals.referral_bonus_service import ReferralBonusService
from telegram_bot.services.referrals.referral_validator_service import (
    ReferralValidatorService,
)


class ReferralRegistrationService:
    def __init__(
        self,
        repo: ReferralRepository,
        user_repo: TelegramUserRepository,
        payment_repo: PaymentRepository,
        promo_usage_repo: PromoCodeUsageRepository,
        validator: ReferralValidatorService,
        bonuses: ReferralBonusService,
        sync_service=None,
    ):
        self.repo = repo
        self.user_repo = user_repo
        self.payment_repo = payment_repo
        self.promo_usage_repo = promo_usage_repo
        self.validator = validator
        self.bonuses = bonuses

    async def register_user(
        self,
        tg_id: int,
        referral_code: list[str],
        *,
        user_created: bool,
    ) -> tuple[bool, str]:
        """
        Registers a user in the referral system, optionally with a referral code.
        """
        referral_exists = await self.repo.get(tg_id)

        if len(referral_code) > 1:
            if not await self._can_apply_referral_code(
                tg_id=tg_id,
                user_created=user_created,
                referral_exists=referral_exists,
            ):
                logger.info(
                    f"Rejected referral code for ineligible user tg_id={tg_id}: "
                    f"referral_code={referral_code}"
                )
                return False, "existing_user"

            referrer_id = int(referral_code[1])
            if await self.validator.is_valid_referral(tg_id, str(referrer_id)):
                code_is_new, action = await self.validator.is_code_new(tg_id, referrer_id)
                await self.repo.update_referrer(tg_id, referrer_id)

                if code_is_new:
                    await self.bonuses.grant_bonus_to_user(
                        tg_id,
                        BOT_BONUS_NEW_USER_INT,
                        reward_context=ReferralRewardContext(
                            referred_tg_id=tg_id,
                            referrer_tg_id=referrer_id,
                            trigger_type=REFERRAL_TRIGGER_INVITE_REGISTERED,
                            trigger_ref=str(tg_id),
                            source=REFERRAL_REWARD_SOURCE_TELEGRAM_START,
                            metadata={"legacy_new_user_bonus": BOT_BONUS_NEW_USER_INT},
                        ),
                    )

                logger.info(
                    f"Referral code processed: tg_id={tg_id}, referrer_id={referrer_id}, "
                    f"action={action}"
                )
                return True, action

            logger.info(f"Invalid referral code: {referrer_id} for tg_id={tg_id}")
            return False, "invalid_code"

        logger.info(f"Registration complete without referral code for tg_id={tg_id}")
        return True, "no_code"

    async def _can_apply_referral_code(
        self,
        *,
        tg_id: int,
        user_created: bool,
        referral_exists: ReferralSnapshot | None,
    ) -> bool:
        if user_created:
            return True

        user = await self.user_repo.get(tg_id)
        if user is None:
            return False

        if user.expiration_date is not None:
            return False
        if user.trial_date is not None:
            return False
        if user.news_channel_date is not None:
            return False

        if referral_exists is not None and referral_exists.referrer_tg_id is not None:
            return False

        if await self.payment_repo.has_any_for_user(tg_id):
            return False

        if await self.promo_usage_repo.has_any_for_user(tg_id):
            return False

        return True
