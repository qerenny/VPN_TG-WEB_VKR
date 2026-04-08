from typing import Tuple

from shared.infrastructure.referrals.referral_repository import (
    ReferralRepository,
)
from shared.utils.logging_utils import logger


class ReferralValidatorService:
    def __init__(self, repo: ReferralRepository):
        self.repo = repo
    async def is_valid_referral(self, tg_id: int, referrer_id: str) -> bool:
        if not referrer_id.isdigit():
            logger.info(f"Invalid referrer_id format: {referrer_id}")
            return False

        referrer_id = int(referrer_id)
        if tg_id == referrer_id:
            logger.info(f"User {tg_id} referred themselves.")
            return False

        if not await self.repo.get(referrer_id):
            logger.info(f"Referrer not found in DB: referrer_id={referrer_id}")
            return False

        if await self.repo.is_symmetrical_referral(tg_id=tg_id, referrer_tg_id=referrer_id):
            logger.info(f"Symmetrical referral detected: tg_id={tg_id}, referrer_id={referrer_id}")
            return False

        return True
    async def is_code_new(self, tg_id: int, referrer_tg_id: int) -> Tuple[bool, str]:
        user = await self.repo.get(tg_id)
        code_applied = user.referrer_tg_id

        is_new = code_applied is None

        if is_new:
            logger.info(f"Code is new: tg_id={tg_id}, referrer_id={referrer_tg_id}")
            return True, "code_activated"
        else:
            logger.info(f"Code was already used or updated: tg_id={tg_id}, referrer_id={referrer_tg_id}")
            return False, "code_updated"
