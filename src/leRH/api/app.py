from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from leRH.api.middleware.auth import verify_api_key
from leRH.api.routers.applications import router as applications_router
from leRH.api.routers.documents import router as documents_router
from leRH.api.routers.health import router as health_router
from leRH.api.routers.jobs import router as jobs_router
from leRH.api.routers.matching import router as matching_router
from leRH.api.routers.profiles import router as profiles_router
from leRH.api.routers.subscriptions import router as subscriptions_router
from leRH.api.routers.users import router as user_router
from leRH.api.routers.whatsapp import router as whatsapp_router
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
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)

# Tous les autres routers nécessitent une clé API
protected_routers = [
    user_router,
    whatsapp_router,
    matching_router,
    jobs_router,
    profiles_router,
    subscriptions_router,
    documents_router,
    applications_router,
]

for router in protected_routers:
    app.include_router(router, dependencies=[Depends(verify_api_key)])
