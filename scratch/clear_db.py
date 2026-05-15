import asyncio
import logging

from sqlalchemy import delete

from leRH.db.base import async_session_factory, engine
from leRH.db.models import (
    CV,
    Application,
    Base,
    Education,
    Experience,
    Message,
    PendingMessage,
    RateLimitEntry,
    Subscription,
    User,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def clear_db():
    async with engine.begin() as conn:
        logger.info("Ensuring all tables exist...")
        await conn.run_sync(Base.metadata.create_all)

    tables_to_clear = [
        Application,
        CV,
        Experience,
        Education,
        Subscription,
        Message,
        PendingMessage,
        RateLimitEntry,
        User,
    ]

    async with async_session_factory() as session:
        for table in tables_to_clear:
            try:
                logger.info(f"Clearing table: {table.__tablename__}")
                await session.execute(delete(table))
            except Exception as e:
                logger.warning(f"Could not clear table {table.__tablename__}: {e}")

        await session.commit()
        logger.info("Database cleared (except jobs)!")


if __name__ == "__main__":
    asyncio.run(clear_db())
