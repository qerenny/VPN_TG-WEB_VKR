from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from shared.config.database.session import get_db_session


@dataclass(frozen=True, slots=True)
class RolloutCheck:
    name: str
    ok: bool
    details: str = ""


async def execute_scalar(sql: str, **params: Any) -> Any:
    async with get_db_session() as session:
        result = await session.execute(text(sql), params)
        return result.scalar_one_or_none()


async def execute_sql(sql: str, **params: Any) -> None:
    async with get_db_session() as session:
        await session.execute(text(sql), params)
        await session.commit()


def print_checks(checks: list[RolloutCheck]) -> None:
    for check in checks:
        status = "OK" if check.ok else "FAIL"
        suffix = f": {check.details}" if check.details else ""
        print(f"[{status}] {check.name}{suffix}")


def run_async(main_coro: Any) -> None:
    asyncio.run(main_coro)
