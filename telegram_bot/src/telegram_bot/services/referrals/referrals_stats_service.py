from shared.config.config import BOT_REFERRAL_LINK
from shared.infrastructure.referrals.referral_repository import (
    ReferralRepository,
)
from shared.utils.logging_utils import logger
from telegram_bot.shared.texts import messages


class ReferralStatsService:
    def __init__(self, repo: ReferralRepository):
        self.repo = repo

    async def get_stats(self, tg_id: int) -> dict:
        users = await self.repo.get_users_by_referrer(tg_id)
        user = await self.repo.get(tg_id)
        invited = len(users)
        paid_count = int(user.paid_count or 0)
        pending = int(user.days_pending or 0)
        awaiting_paid_count = max(invited - paid_count, 0)
        awaiting_bonus_days = self._project_bonus_days(
            paid_count=paid_count,
            awaiting_paid_count=awaiting_paid_count,
        )

        logger.info(
            "Retrieved referral stats for tg_id=%s, invited=%s, paid_count=%s, "
            "pending_days=%s, awaiting_paid_count=%s, awaiting_bonus_days=%s",
            tg_id,
            invited,
            paid_count,
            pending,
            awaiting_paid_count,
            awaiting_bonus_days,
        )

        return {
            "invited": invited,
            "paid_count": paid_count,
            "pending_days": pending,
            "awaiting_paid_count": awaiting_paid_count,
            "awaiting_bonus_days": awaiting_bonus_days,
        }

    async def send_referral_link(self, tg_id) -> str:
        """
        Sends personal referral link to the user.
        """
        link = BOT_REFERRAL_LINK + str(tg_id)
        text = messages.get_random_message("referral_link") + f"\n```{link}```"
        logger.info(f"Referral link sent to tg_id={tg_id}: {link}")

        return text
    async def send_rules(self, tg_id) -> str:
        """
        Sends referral program rules.
        """
        text = messages.get_random_message("referral_rules")
        logger.info(f"Referral rules sent to tg_id={tg_id}")

        return text

    @staticmethod
    def _project_bonus_days(*, paid_count: int, awaiting_paid_count: int) -> int:
        projected = 0
        for next_paid_count in range(paid_count + 1, paid_count + awaiting_paid_count + 1):
            projected += ReferralStatsService._calc_referrer_bonus(next_paid_count)
        return projected

    @staticmethod
    def _calc_referrer_bonus(count: int) -> int:
        match count:
            case 3:
                return 10
            case 5:
                return 15
            case 10:
                return 31
            case 15:
                return 62
            case _:
                return 7
