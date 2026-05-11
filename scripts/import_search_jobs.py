#!/usr/bin/env python3
"""Search for job offers online and import them into the database."""

import asyncio
import logging
import warnings

from sqlalchemy import select

warnings.filterwarnings("ignore", category=RuntimeWarning)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SYSTEM_USER_ID = "system_agg"
SYSTEM_USER_NAME = "Aggrégateur leRH"


async def ensure_system_user():
    from leRH.db.base import async_session_factory
    from leRH.db.models import User

    async with async_session_factory() as session:
        user = await session.get(User, SYSTEM_USER_ID)
        if not user:
            user = User(id=SYSTEM_USER_ID, name=SYSTEM_USER_NAME, country="Togo")
            session.add(user)
            await session.flush()
            logger.info("System user created: %s", SYSTEM_USER_ID)
        await session.commit()
        return user


async def import_offers(queries: list[str], max_per_query: int = 5):
    from leRH.core.tools.job_search import search_jobs_online
    from leRH.db.base import async_session_factory
    from leRH.db.models import Job

    await ensure_system_user()
    async with async_session_factory() as session:
        imported = 0
        for query in queries:
            logger.info("Searching: %s", query)
            results = search_jobs_online(query, max_results=max_per_query)
            for res in results:
                existing = await session.execute(select(Job).where(Job.title == res.title[:255]))
                if existing.scalar_one_or_none():
                    continue
                job = Job(
                    recruiter_id=SYSTEM_USER_ID,
                    title=res.title[:255],
                    description=res.snippet[:2000] or res.title,
                    company="Offre externe",
                    city="Togo",
                    status="active",
                    source_url=res.url,
                    source_name="Web",
                    is_external=True,
                )
                session.add(job)
                imported += 1
                logger.info("  + %s", res.title[:60])

        await session.commit()
        logger.info("Importé %d offres sur %d requêtes.", imported, len(queries))
        return imported


async def list_offres():
    from leRH.db.base import async_session_factory
    from leRH.db.models import Job

    async with async_session_factory() as session:
        result = await session.execute(select(Job).where(Job.recruiter_id == SYSTEM_USER_ID))
        jobs = result.scalars().all()
        print(f"\n=== {len(jobs)} offres importées ===")
        for j in jobs:
            src = j.requirements.get("source_url", "") if j.requirements else ""
            print(f"  [{j.id}] {j.title}")
            print(f"       {j.description[:100]}...")
            print(f"       {src}")
            print()


if __name__ == "__main__":
    queries = [
        "offre emploi Togo 2026",
        "recrutement Lomé Togo",
        "offre emploi developpeur Togo",
    ]

    asyncio.run(import_offers(queries))
    asyncio.run(list_offres())
