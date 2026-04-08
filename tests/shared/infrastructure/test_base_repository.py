from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel

from shared.infrastructure.base_repository import BaseRepository


# === Simple model ===
class DummyUser(SQLModel, table=True):
    tg_id: int = Field(primary_key=True)
    name: str


# === Test repository ===
class DummyUserRepository(BaseRepository[DummyUser]):
    def __init__(self):
        super().__init__(DummyUser)


# === In-memory SQLite setup ===
DATABASE_URL = "sqlite+aiosqlite://"


@pytest.fixture(scope="module")
async def async_engine():
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(async_engine):
    return async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def repo(session_factory):
    # patch get_db_session inside repo
    class TestableRepo(DummyUserRepository):
        @asynccontextmanager
        async def get_session(self):
            async with session_factory() as session:
                yield session

    return TestableRepo()


@pytest.mark.asyncio
async def test_create_and_get(repo: DummyUserRepository):
    user = DummyUser(tg_id=1, name="Alice")
    await repo.create(user)

    result = await repo.get(1)
    assert result is not None
    assert result.name == "Alice"


@pytest.mark.asyncio
async def test_get_all(repo: DummyUserRepository):
    await repo.create(DummyUser(tg_id=2, name="Bob"))
    await repo.create(DummyUser(tg_id=3, name="Charlie"))

    all_users = await repo.get_all()
    names = [u.name for u in all_users]
    assert "Bob" in names and "Charlie" in names


@pytest.mark.asyncio
async def test_update(repo: DummyUserRepository):
    user = await repo.get(1)
    user.name = "Updated Alice"
    await repo.update(user)

    updated = await repo.get(1)
    assert updated.name == "Updated Alice"


@pytest.mark.asyncio
async def test_delete(repo: DummyUserRepository):
    await repo.delete(2)
    deleted = await repo.get(2)
    assert deleted is None


@pytest.mark.asyncio
async def test_get_non_existing(repo: DummyUserRepository):
    result = await repo.get(9999)
    assert result is None


@pytest.mark.asyncio
async def test_delete_non_existing(repo: DummyUserRepository):
    await repo.delete(9999)
    result = await repo.get(9999)
    assert result is None
