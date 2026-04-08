from contextlib import asynccontextmanager
from typing import Generic, List, Optional, Type, TypeVar

from sqlmodel import SQLModel, select

from shared.config.database.session import get_db_session
from shared.utils.logging_utils import log_function_call, setup_logger

logger = setup_logger("base.repository", "database.log")

T = TypeVar("T", bound=SQLModel)


class BaseRepository(Generic[T]):
    def __init__(self, model: Type[T]):
        self.model = model

    @asynccontextmanager
    async def get_session(self):
        async with get_db_session() as session:
            yield session

    @log_function_call(logger)
    async def get(self, id: int) -> Optional[T]:
        async with self.get_session() as session:
            result = await session.execute(select(self.model).where(self.model.tg_id == id))
            return result.scalar_one_or_none()

    @log_function_call(logger)
    async def get_all(self) -> List[T]:
        async with self.get_session() as session:
            result = await session.execute(select(self.model))
            return result.scalars().all()

    @log_function_call(logger)
    async def create(self, obj: T) -> T:
        async with self.get_session() as session:
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj

    @log_function_call(logger)
    async def update(self, obj: T) -> T:
        async with self.get_session() as session:
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj

    @log_function_call(logger)
    async def delete(self, id: int) -> None:
        async with self.get_session() as session:
            result = await session.execute(select(self.model).where(self.model.tg_id == id))
            obj = result.scalar_one_or_none()
            if obj:
                await session.delete(obj)
                await session.commit()
