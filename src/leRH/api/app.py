from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from leRH.db.base import Base, engine

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting leRH API")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")

    from leRH.core.batch.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    yield
    stop_scheduler()
    await engine.dispose()
    logger.info("Shutting down leRH API")


app = FastAPI(
    title="leRH API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from leRH.api.routers.applications import router as applications_router  # noqa: E402
from leRH.api.routers.documents import router as documents_router  # noqa: E402
from leRH.api.routers.health import router as health_router  # noqa: E402
from leRH.api.routers.jobs import router as jobs_router  # noqa: E402
from leRH.api.routers.matching import router as matching_router  # noqa: E402
from leRH.api.routers.profiles import router as profiles_router  # noqa: E402
from leRH.api.routers.subscriptions import router as subscriptions_router  # noqa: E402
from leRH.api.routers.users import router as user_router  # noqa: E402
from leRH.api.routers.whatsapp import router as whatsapp_router  # noqa: E402

app.include_router(health_router)
app.include_router(user_router)
app.include_router(whatsapp_router)
app.include_router(matching_router)
app.include_router(jobs_router)
app.include_router(profiles_router)
app.include_router(subscriptions_router)
app.include_router(documents_router)
app.include_router(applications_router)
