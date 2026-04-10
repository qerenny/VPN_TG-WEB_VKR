from __future__ import annotations

import asyncio

from sqlalchemy import select

from shared.config.database.session import get_db_session
from shared.infrastructure.payment_plan_catalog import iter_default_plan_seeds
from shared.models.payments.plan_model import Plan


async def main() -> None:
    async with get_db_session() as session:
        existing_codes = {
            str(code)
            for code in (
                await session.execute(select(Plan.code))
            ).scalars().all()
        }
        created = 0
        for seed in iter_default_plan_seeds():
            if seed.code in existing_codes:
                continue
            session.add(
                Plan(
                    code=seed.code,
                    name=seed.name,
                    kind=seed.kind,
                    payload=seed.payload,
                    scope=seed.scope,
                    entitlement_kind=seed.entitlement_kind,
                    duration_days=seed.duration_days,
                    quota_bytes=seed.quota_bytes,
                    price_amount=seed.price_amount,
                    currency=seed.currency,
                    is_active=True,
                    metadata_json={},
                )
            )
            created += 1
        await session.commit()
    print(f"Seed plans completed: created {created} plan rows.")


if __name__ == "__main__":
    asyncio.run(main())
