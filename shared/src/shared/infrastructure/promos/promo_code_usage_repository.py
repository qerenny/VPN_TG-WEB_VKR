from __future__ import annotations

from shared.config.settings import RuntimeSyncFlags
from shared.infrastructure.base_repository import BaseRepository
from shared.infrastructure.growth_service import GrowthService
from shared.models.growth.promo_code_model import PromoCode as PromoCodeV2
from shared.models.growth.promo_redemption_model import PromoRedemption
from shared.models.users.telegram_account_model import TelegramAccount
from shared.utils.logging_utils import log_function_call, setup_logger
from sqlmodel import select

logger = setup_logger("promo-code-usage.repository", "database.log")


class PromoCodeUsageRepository(BaseRepository[PromoRedemption]):
    def __init__(self):
        super().__init__(PromoRedemption)
        self.growth_service = GrowthService(
            RuntimeSyncFlags(growth_sync_enabled=True)
        )

    @log_function_call(logger)
    async def is_used(self, tg_id: int, code: str) -> bool:
        async with self.get_session() as session:
            result = await session.execute(
                select(PromoRedemption.id)
                .join(PromoCodeV2, PromoCodeV2.id == PromoRedemption.promo_code_id)
                .join(TelegramAccount, TelegramAccount.user_id == PromoRedemption.user_id)
                .where(
                    TelegramAccount.telegram_id == int(tg_id),
                    TelegramAccount.revoked_at.is_(None),
                    PromoCodeV2.code == code,
                )
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    @log_function_call(logger)
    async def mark_used(self, tg_id: int, code: str) -> None:
        await self.growth_service.sync_promo_redemption(
            tg_id=int(tg_id),
            promo_code=str(code),
        )

    @log_function_call(logger)
    async def has_any_for_user(self, tg_id: int) -> bool:
        async with self.get_session() as session:
            result = await session.execute(
                select(PromoRedemption.id)
                .join(TelegramAccount, TelegramAccount.user_id == PromoRedemption.user_id)
                .where(
                    TelegramAccount.telegram_id == int(tg_id),
                    TelegramAccount.revoked_at.is_(None),
                )
                .limit(1)
            )
            return result.scalar_one_or_none() is not None
