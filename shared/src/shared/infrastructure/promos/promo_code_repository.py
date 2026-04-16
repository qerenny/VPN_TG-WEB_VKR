from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa
from sqlmodel import select

from shared.infrastructure.base_repository import BaseRepository
from shared.models.growth.promo_code_model import PromoCode as PromoCodeV2
from shared.models.growth.promo_redemption_model import PromoRedemption
from shared.models.payments.plan_model import Plan
from shared.utils.logging_utils import log_function_call, setup_logger

logger = setup_logger("promo-code.repository", "database.log")


@dataclass(slots=True)
class PromoCodeSnapshot:
    code: str
    duration: str
    remaining_uses: int | None = None


class PromoCodeRepository(BaseRepository[PromoCodeSnapshot]):
    def __init__(self):
        super().__init__(PromoCodeSnapshot)

    @log_function_call(logger)
    async def get_by_code(self, code: str) -> PromoCodeSnapshot | None:
        async with self.get_session() as session:
            return await self._get_v2_promo_by_code(session, code)

    async def _get_v2_promo_by_code(self, session, code: str) -> PromoCodeSnapshot | None:
        promo_v2 = (
            await session.execute(select(PromoCodeV2).where(PromoCodeV2.code == code))
        ).scalar_one_or_none()
        if promo_v2 is None:
            return None

        plan = None
        redemptions_count = (
            await session.execute(
                select(sa.func.count(PromoRedemption.id)).where(
                    PromoRedemption.promo_code_id == promo_v2.id
                )
            )
        ).scalar_one()

        plan_metadata = {}
        if promo_v2.plan_id is not None:
            plan = await session.get(Plan, promo_v2.plan_id)
            if plan is not None:
                plan_metadata = dict(getattr(plan, "metadata_json", {}) or {})

        metadata = dict(promo_v2.metadata_json or {})
        legacy_duration = (
            str(metadata.get("legacy_duration") or "").strip()
            or str(getattr(plan, "payload", "") or "").strip()
            or str(plan_metadata.get("plan_payload") or "").strip()
        )
        if not legacy_duration:
            legacy_duration = f"day{int(promo_v2.duration_days_override or 0)}"

        remaining_uses = None
        if promo_v2.max_redemptions is not None:
            remaining_uses = max(0, int(promo_v2.max_redemptions) - int(redemptions_count or 0))

        return PromoCodeSnapshot(
            code=str(promo_v2.code),
            duration=legacy_duration,
            remaining_uses=remaining_uses,
        )
