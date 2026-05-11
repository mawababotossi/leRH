#!/usr/bin/env python3
"""Backfill: enrich existing external jobs with LLM-extracted fields."""

import asyncio
import logging
import warnings

from sqlalchemy import select

warnings.filterwarnings("ignore", category=RuntimeWarning)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    from leRH.core.pipeline.job_enricher import JobEnricher
    from leRH.core.scraping.types import ScrapedJob
    from leRH.db.base import async_session_factory
    from leRH.db.models import Job

    enricher = JobEnricher()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Job).where(
                Job.is_external,
                Job.requirements.is_(None),
            )
        )
        jobs = result.scalars().all()
        logger.info("Found %d jobs to enrich", len(jobs))

        for i, job in enumerate(jobs):
            sj = ScrapedJob(
                external_id=job.external_id or job.id,
                title=job.title,
                description=job.description,
                source_url=job.source_url or "",
                source_name=job.source_name or "unknown",
                company=job.company,
                city=job.city,
            )
            enriched = enricher.enrich(sj)

            job.title = enriched.title
            job.company = enriched.company
            job.city = enriched.city
            job.requirements = enriched.requirements

            if (i + 1) % 5 == 0:
                logger.info("Enriched %d/%d", i + 1, len(jobs))
                await session.flush()

        await session.commit()
        logger.info("Backfill complete: %d jobs enriched", len(jobs))


if __name__ == "__main__":
    asyncio.run(main())
