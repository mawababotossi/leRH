from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from leRH.api.middleware.auth import verify_api_key
from leRH.api.middleware.logging import CorrelationIdMiddleware, get_correlation_id
from leRH.api.routers.applications import router as applications_router
from leRH.api.routers.documents import router as documents_router
from leRH.api.routers.health import router as health_router
from leRH.api.routers.jobs import router as jobs_router
from leRH.api.routers.matching import router as matching_router
from leRH.api.routers.profiles import router as profiles_router
from leRH.api.routers.subscriptions import router as subscriptions_router
from leRH.api.routers.users import router as user_router
from leRH.api.routers.whatsapp import router as whatsapp_router
from leRH.config import settings
from leRH.db.base import Base, engine


class CorrelationIdFormatter(logging.Formatter):
    def format(self, record):
        record.correlation_id = get_correlation_id() or "-"
        return super().format(record)


handler = logging.StreamHandler()
handler.setFormatter(
    CorrelationIdFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s"
    )
)
logging.basicConfig(level=logging.INFO, handlers=[handler])
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

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
