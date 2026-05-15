"""Fixtures partagées pour tous les tests."""

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from leRH.api.app import app
from leRH.config import settings
from leRH.db.base import Base, get_db

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "mysql+aiomysql://user:pass@localhost:3306/lerh_test",
)
_TABLES_CREATED = False


@pytest_asyncio.fixture
async def engine():
    global _TABLES_CREATED
    eng = create_async_engine(TEST_DB_URL, echo=False)
    if not _TABLES_CREATED:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _TABLES_CREATED = True
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": settings.internal_api_key.get_secret_value()},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
