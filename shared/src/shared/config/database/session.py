from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.database.engine import async_session_factory
from shared.utils.logging_utils import setup_logger

logger = setup_logger("session.lifecycle", "database.log")


@asynccontextmanager
async def get_db_session() -> AsyncSession:
    session = async_session_factory()
    logger.debug("🔵 Opened new AsyncSession")
    try:
        yield session
    finally:
        await session.close()
        logger.debug("⚪ Closed AsyncSession")
