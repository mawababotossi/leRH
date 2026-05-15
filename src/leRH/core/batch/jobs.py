from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from leRH.core.bot_registry import get_telegram_bot
from leRH.core.credits import NOTIFICATION_COST, CreditManager
from leRH.core.matching.engine import Matcher
from leRH.core.pipeline.job_enricher import enrich_jobs
from leRH.core.scraping.emploi_tg import EmploiTgScraper
from leRH.db.base import async_session_factory
from leRH.db.models import PendingMessage
from leRH.db.repository import CVRepository, JobRepository, SubscriptionRepository, UserRepository

SYSTEM_USER_ID = "system_agg"

logger = logging.getLogger(__name__)


async def scrape_and_store() -> int:
    loop = asyncio.get_running_loop()
    scraper = EmploiTgScraper()
    raw_jobs = await loop.run_in_executor(None, scraper.scrape)
    if not raw_jobs:
        logger.info("No jobs scraped")
        return 0

    enriched = await loop.run_in_executor(None, lambda: enrich_jobs(raw_jobs))
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
            candidate_jobs = [job for job in new_jobs if _is_new_for_subscription(job, sub)]
            if not candidate_jobs:
                continue

            matches = []

            for job in candidate_jobs:
                result = await matcher.match(user, job, cv)
                if result.overall_score >= sub.min_match_score:
                    matches.append((job, result))

            if not matches:
                continue

            messages = _build_notification_messages(user, matches)
            if not _has_notification_channel(user, sub):
                logger.warning("No notification channel available for user %s", user.id)
                continue

            result = await credit_mgr.deduct(
                sub.user_id, NOTIFICATION_COST, reason=f"notification_{sub.id}", session=session
            )
            if not result.success:
                logger.warning("Credit deduction failed for %s: %s", sub.user_id, result.message)
                continue

            delivered = await _deliver_notification(user, sub, messages, session)
            if not delivered:
                logger.warning("No notification channel delivered for user %s", user.id)
                await credit_mgr.add(
                    sub.user_id,
                    NOTIFICATION_COST,
                    reason=f"refund_notification_{sub.id}",
                    session=session,
                )
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


def _has_notification_channel(user, sub) -> bool:
    if sub.notify_whatsapp and user.whatsapp_id:
        return True
    return bool(sub.notify_telegram and user.telegram_id and get_telegram_bot())


async def _deliver_notification(user, sub, messages: list[str], session: AsyncSession) -> bool:
    delivered = False

    if sub.notify_telegram:
        if user.telegram_id:
            for msg in messages:
                delivered = await _send_telegram_notification(user.telegram_id, msg) or delivered
        else:
            logger.info("User %s has Telegram notifications enabled but no telegram_id", user.id)

    if sub.notify_whatsapp:
        if user.whatsapp_id:
            for msg in messages:
                await _queue_whatsapp_notification(session, user.whatsapp_id, msg)
                delivered = True
        else:
            logger.info("User %s has WhatsApp notifications enabled but no whatsapp_id", user.id)

    return delivered


async def _send_telegram_notification(telegram_id: int, message: str) -> bool:
    bot = get_telegram_bot()
    if not bot:
        logger.error("No Telegram bot registered for job notification")
        return False

    try:
        await bot.send_message(chat_id=int(telegram_id), text=message)
    except Exception:
        logger.exception("Failed to send job notification via Telegram to chat_id=%s", telegram_id)
        return False

    logger.info("Job notification sent via Telegram to chat_id=%s", telegram_id)
    return True


async def _queue_whatsapp_notification(
    session: AsyncSession,
    whatsapp_id: str,
    message: str,
) -> None:
    session.add(
        PendingMessage(
            platform="whatsapp",
            platform_chat_id=whatsapp_id,
            message_type="text",
            text=message,
            document_path=None,
        )
    )
    await session.flush()
    logger.info("Job notification queued for WhatsApp chat_id=%s", whatsapp_id)


def _build_notification_messages(user, matches: list) -> list[str]:
    from_date = matches[0][0].created_at.strftime("%d/%m/%Y")
    name = user.name or "vous"
    header = f"Bonjour {name},\n\nNouvelles offres pour vous ({from_date})\n"
    parts = [header]

    for job, result in matches:
        score = result.overall_score
        rec = _emoji(result.recommendation)
        link = f"  Lien: {job.source_url}\n" if getattr(job, "source_url", None) else ""
        parts.append(
            f"{rec} {job.title}\n"
            f"  {job.company or 'N/A'} — {job.city or 'N/A'}\n"
            f"  Score: {score}/100\n"
            f"{link}"
        )

    parts.append(
        f"\nCette notification a consommé {NOTIFICATION_COST} crédit. "
        "Répondez si vous voulez préparer un CV ou une lettre pour une offre."
    )
    return ["\n".join(parts)]


def _emoji(recommendation: str) -> str:
    return {"strong_match": "🔥", "possible_match": "✅", "weak_match": "👀"}.get(
        recommendation, "📌"
    )


def _is_new_for_subscription(job, sub) -> bool:
    if not sub.last_notified_at:
        return True
    if not job.created_at:
        return True
    return _to_utc(job.created_at) > _to_utc(sub.last_notified_at)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def cleanup_stale_jobs(days: int = 30) -> int:
    """Nettoie les offres externes périmées.

    Args:
        days: Âge maximum des offres en jours.

    Returns:
        Nombre d'offres supprimées.
    """
    async with async_session_factory() as session:
        repo = JobRepository(session)
        deleted = await repo.cleanup_stale_external_jobs(days)
        await session.commit()
        return deleted


async def daily_batch() -> dict[str, int]:
    logger.info("=== Daily batch started ===")
    stored = await scrape_and_store()
    notified = await match_and_notify()
    logger.info("=== Daily batch done: %d new jobs, %d notifications ===", stored, notified)
    return {"stored": stored, "notified": notified}
