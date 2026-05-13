from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from leRH.core.batch.jobs import cleanup_stale_jobs, daily_batch, scrape_and_store

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    if scheduler.running:
        logger.warning("Scheduler already running")
        return

    scheduler.add_job(
        daily_batch,
        trigger="cron",
        hour=2,
        minute=0,
        id="daily_batch",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        cleanup_stale_jobs,
        trigger="cron",
        hour=3,
        minute=0,
        id="cleanup_stale_jobs",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        scrape_and_store,
        trigger=CronTrigger(hour="6-22", minute=0),
        id="hourly_scrape",
        replace_existing=True,
        misfire_grace_time=600,
    )
    scheduler.start()
    logger.info("Batch scheduler started (daily at 02:00, cleanup at 03:00, hourly scrape 06:00-22:00)")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Batch scheduler stopped")
