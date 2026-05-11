#!/usr/bin/env python3
"""Run all configured scrapers and import results into the database."""

import asyncio
import logging
import warnings
from datetime import UTC, datetime

from sqlalchemy import select

warnings.filterwarnings("ignore", category=RuntimeWarning)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKIP_ENRICH = False  # set to True to skip LLM enrichment (faster)
SYSTEM_USER_ID = "system_agg"


def get_scrapers():
    from leRH.core.scraping.emploi_tg import EmploiTgScraper

    return [EmploiTgScraper()]


async def ensure_system_user():
    from leRH.db.base import async_session_factory
    from leRH.db.models import User

    async with async_session_factory() as session:
        user = await session.get(User, SYSTEM_USER_ID)
        if not user:
            user = User(id=SYSTEM_USER_ID, name="Aggrégateur leRH", country="Togo")
            session.add(user)
            await session.flush()
            logger.info("System user created: %s", SYSTEM_USER_ID)
        await session.commit()


async def import_jobs(scraped_jobs: list) -> int:
    from leRH.db.base import async_session_factory
    from leRH.db.models import Job

    async with async_session_factory() as session:
        imported = 0
        for sj in scraped_jobs:
            existing = await session.execute(
                select(Job).where(
                    Job.external_id == sj.external_id,
                    Job.source_name == sj.source_name,
                )
            )
            if existing.scalar_one_or_none():
                continue

            job = Job(
                recruiter_id=SYSTEM_USER_ID,
                title=sj.title[:255],
                description=sj.description[:5000] or sj.title,
                company=sj.company,
                city=sj.city,
                requirements=sj.requirements,
                status="active",
                source_url=sj.source_url,
                external_id=sj.external_id,
                source_name=sj.source_name,
                is_external=True,
                last_seen_at=datetime.now(UTC),
            )
            session.add(job)
            imported += 1
            logger.info("  + [%s] %s", sj.external_id, sj.title[:60])

        await session.commit()
        return imported


async def main():
    await ensure_system_user()

    total = 0
    for scraper in get_scrapers():
        jobs = scraper.scrape()
        if not jobs:
            logger.warning("No jobs scraped from %s", scraper.source_name)
            continue

        if not SKIP_ENRICH:
            from leRH.core.pipeline.job_enricher import enrich_jobs

            logger.info("Enriching %d jobs from %s...", len(jobs), scraper.source_name)
            jobs = enrich_jobs(jobs)

        count = await import_jobs(jobs)
        total += count
        logger.info("%s: %d new / %d enriched", scraper.source_name, count, len(jobs))

    logger.info("Total new imports: %d", total)


if __name__ == "__main__":
    asyncio.run(main())
