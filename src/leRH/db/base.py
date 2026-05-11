from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from leRH.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"timeout": 30, "check_same_thread": False},
)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_db_write_lock = asyncio.Lock()


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class DBLock:
    """Wrapper asyncio.Lock pour sérialiser les écritures SQLite."""

    @staticmethod
    async def acquire():
        await _db_write_lock.acquire()

    @staticmethod
    def release():
        _db_write_lock.release()

    @staticmethod
    async def __aenter__():
        await _db_write_lock.acquire()

    @staticmethod
    async def __aexit__(*_args):
        _db_write_lock.release()
