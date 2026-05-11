from __future__ import annotations

import logging
from datetime import UTC, datetime

from leRH.core.credits import NOTIFICATION_COST, CreditManager
from leRH.core.matching.engine import Matcher
from leRH.core.pipeline.job_enricher import enrich_jobs
from leRH.core.scraping.emploi_tg import EmploiTgScraper
from leRH.db.base import async_session_factory
from leRH.db.repository import CVRepository, JobRepository, SubscriptionRepository, UserRepository

SYSTEM_USER_ID = "system_agg"

logger = logging.getLogger(__name__)


async def scrape_and_store() -> int:
    scraper = EmploiTgScraper()
    raw_jobs = scraper.scrape()
    if not raw_jobs:
        logger.info("No jobs scraped")
        return 0

    enriched = enrich_jobs(raw_jobs)
    stored = 0

    async with async_session_factory() as session:
        repo = JobRepository(session)
        for job in enriched:
            existing = await repo.get_by_external_id(job.external_id, job.source_name)
            if existing:
                existing.last_seen_at = datetime.now(UTC)
                existing.status = "active"
                continue

            await repo.create(
                recruiter_id=SYSTEM_USER_ID,
                title=job.title,
                description=job.description[:5000],
                company=job.company,
                city=job.city,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                requirements=job.requirements or {},
                source_url=job.source_url,
                external_id=job.external_id,
                source_name=job.source_name,
                is_external=True,
                status="active",
            )
            stored += 1
        await session.commit()

    logger.info("Stored %d new external jobs", stored)
    return stored


async def match_and_notify() -> int:
    async with async_session_factory() as session:
        sub_repo = SubscriptionRepository(session)
        subs = await sub_repo.get_active()
        if not subs:
            logger.info("No active subscriptions to notify")
            return 0

        job_repo = JobRepository(session)
        new_jobs = await job_repo.get_recent_external(since_hours=24)

        if not new_jobs:
            logger.info("No recent external jobs to match")
            return 0

        user_repo = UserRepository(session)
        cv_repo = CVRepository(session)
        matcher = Matcher()
        credit_mgr = CreditManager()
        notified = 0

        for sub in subs:
            user = await user_repo.get_by_id(sub.user_id)
            if not user:
                continue

            if not await credit_mgr.check_credits(sub.user_id, NOTIFICATION_COST, session=session):
                logger.info("User %s has insufficient credits for notification", sub.user_id)
                continue

            cvs = await cv_repo.get_by_user(sub.user_id)
            cv = cvs[0] if cvs else None
            matches = []

            for job in new_jobs:
                result = await matcher.match(user, job, cv)
                if result.overall_score >= sub.min_match_score:
                    matches.append((job, result))

            if not matches:
                continue

            messages = _build_notification_messages(user, matches)
            for msg in messages:
                logger.info(
                    "Match notification for user %s: %s",
                    user.id,
                    msg[:100],
                )

            result = await credit_mgr.deduct(
                sub.user_id, NOTIFICATION_COST, reason=f"notification_{sub.id}", session=session
            )
            if not result.success:
                logger.warning("Credit deduction failed for %s: %s", sub.user_id, result.message)
                continue
            sub.last_notified_at = datetime.now(UTC)
            notified += 1

        try:
            await session.commit()
        except Exception:
            logger.exception("Failed to commit notifications")
            return notified
        logger.info("Notified %d subscribers", notified)
        return notified


def _build_notification_messages(user, matches: list) -> list[str]:
    from_date = matches[0][0].created_at.strftime("%d/%m/%Y")
    header = f"Nouvelles offres pour vous ({from_date})\n"
    parts = [header]

    for job, result in matches:
        score = result.overall_score
        rec = _emoji(result.recommendation)
        parts.append(
            f"{rec} {job.title}\n"
            f"  {job.company or 'N/A'} — {job.city or 'N/A'}\n"
            f"  Score: {score}/100\n"
        )

    return ["\n".join(parts)]


def _emoji(recommendation: str) -> str:
    return {"strong_match": "🔥", "possible_match": "✅", "weak_match": "👀"}.get(
        recommendation, "📌"
    )


async def daily_batch() -> dict[str, int]:
    logger.info("=== Daily batch started ===")
    stored = await scrape_and_store()
    notified = await match_and_notify()
    logger.info("=== Daily batch done: %d new jobs, %d notifications ===", stored, notified)
    return {"stored": stored, "notified": notified}
