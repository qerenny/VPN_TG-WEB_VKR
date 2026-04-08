from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.config.config import DB_SQL_ECHO, DB_URL
from shared.utils.logging_utils import setup_logger

logger = setup_logger("engine", "database.log")


DATABASE_URL = DB_URL

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=DB_SQL_ECHO,
    future=True,
    pool_pre_ping=True,
    pool_recycle=300,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
