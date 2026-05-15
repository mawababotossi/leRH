from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from leRH.core.bot_registry import get_telegram_bot
from leRH.core.credits import CreditManager
from leRH.core.documents.generator import GENERATED_DIR, DocumentGenerator
from leRH.db.base import async_session_factory
from leRH.db.models import DocumentJob, Job, User
from leRH.db.repository import CVRepository, UserRepository

logger = logging.getLogger(__name__)

_db_lock = asyncio.Lock()


def _cv_analysis_with_source(cv_record) -> dict | None:
    if not cv_record or not cv_record.analysis:
        return None
    analysis = dict(cv_record.analysis)
    analysis["source_text"] = cv_record.extracted_text or ""
    return analysis


async def _mark_document_job(
    document_job_id: str | None,
    *,
    status: str,
    file_path: str | None = None,
    error: str | None = None,
) -> None:
    if not document_job_id:
        return

    async with async_session_factory() as session:
        document_job = await session.get(DocumentJob, document_job_id)
        if not document_job:
            return

        document_job.status = status
        if file_path is not None:
            document_job.file_path = file_path
        if error is not None:
            document_job.error = error[:4000]
        if status in {"completed", "failed"}:
            document_job.completed_at = datetime.now(UTC)
        await session.commit()


async def generate_document_background(
    *,
    user_id: str,
    job: Job,
    func_name: str,
    cost: int,
    platform: str,
    chat_id: str | int,
    skip_deduction: bool = False,
    target_profile: dict | None = None,
) -> None:
    doc_type = "CV" if func_name == "generate_cv" else "lettre de motivation"
    document_kind = "cv" if func_name == "generate_cv" else "cover_letter"
    document_job_id: str | None = None
    logger.info("[bg] Début génération %s — user=%s job=%s", doc_type, user_id, job.title)

    try:
        async with async_session_factory() as session:
            repo = UserRepository(session)
            user = await repo.get_by_id(user_id)

            # Charger le dernier CV analysé dans la même session
            cv_repo = CVRepository(session)
            cv_record = await cv_repo.get_latest_for_user(user_id)
            cv_analysis = _cv_analysis_with_source(cv_record)
            if cv_analysis:
                logger.info(
                    "[bg] CV analysé trouvé pour %s — les données du vrai CV seront utilisées",
                    user_id,
                )
            else:
                logger.info(
                    "[bg] Aucun CV uploadé pour %s — génération depuis le profil seulement",
                    user_id,
                )
            if user:
                document_job = DocumentJob(
                    user_id=user_id,
                    job_id=job.id,
                    document_type=document_kind,
                    status="running",
                    platform=platform,
                    chat_id=str(chat_id),
                    target_profile=target_profile,
                )
                session.add(document_job)
                await session.flush()
                document_job_id = document_job.id
                await session.commit()

        if not user:
            logger.error("[bg] Utilisateur %s introuvable", user_id)
            await _send_notification(
                platform=platform,
                chat_id=chat_id,
                relative_path=None,
                caption="Utilisateur introuvable.",
                absolute_path=None,
            )
            return

        logger.info("[bg] Utilisateur chargé — %s", user.name)
        doc_user = user
        doc_cv_analysis = cv_analysis
        if target_profile:
            doc_user = User(
                name=target_profile.get("name") or "Candidat",
                country=user.country,
                activity=target_profile.get("activity"),
                skills=target_profile.get("skills") or [],
                diploma=target_profile.get("diploma"),
                experience=target_profile.get("experience"),
                languages=target_profile.get("languages") or [],
                phone=target_profile.get("phone") or None,
                email=target_profile.get("email") or None,
            )
            doc_cv_analysis = None
            logger.info(
                "[bg] Document généré pour un bénéficiaire tiers — %s",
                doc_user.name,
            )

        loop = asyncio.get_running_loop()
        doc_gen = DocumentGenerator()

        logger.info("[bg] Appel LLM + génération fichier…")
        if func_name == "generate_cv":
            buf, filename = await loop.run_in_executor(
                None,
                lambda: doc_gen.generate_cv(doc_user, job, fmt="pdf", cv_analysis=doc_cv_analysis),
            )
        else:
            buf, filename = await loop.run_in_executor(
                None,
                lambda: doc_gen.generate_cover_letter(
                    doc_user, job, fmt="pdf", cv_analysis=doc_cv_analysis
                ),
            )
        logger.info("[bg] Fichier généré — %s (%d bytes)", filename, buf.getbuffer().nbytes)

        # Save file under GENERATED_DIR / user_id / filename
        user_dir = GENERATED_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        filepath = user_dir / filename
        with open(filepath, "wb") as f:
            f.write(buf.getvalue())

        # relative_path is what the download endpoint expects after /documents/download/
        # It must match the {filepath:path} parameter, i.e. "user_id/filename.docx"
        relative_path = f"{user_id}/{filename}"
        logger.info("[bg] Fichier sauvegardé — %s (relative: %s)", filepath, relative_path)
        await _mark_document_job(
            document_job_id,
            status="completed",
            file_path=relative_path,
        )

        # Deduct credits AFTER successful generation (if not already deducted)
        if not skip_deduction:
            credit_mgr = CreditManager()
            result = await credit_mgr.deduct(
                user_id, cost, reason=f"generation_{func_name}_for_{job.id}"
            )
            logger.info(
                "[bg] Crédits déduits — remaining=%d success=%s",
                result.credits_remaining,
                result.success,
            )
        else:
            logger.info("[bg] Crédits déjà déduits par l'appelant")

        if doc_type == "CV":
            ready_line = "Ton CV est prêt."
            next_line = "Tu veux que je l'ajuste davantage ?"
        else:
            ready_line = "Ta lettre de motivation est prête."
            next_line = "Tu veux que je l'adapte davantage ?"

        job_context = f"Poste : {job.title}"
        if job.company:
            job_context += f"\nEntreprise : {job.company}"
        if target_profile:
            job_context += f"\nBénéficiaire : {doc_user.name}"

        caption = (
            f"{ready_line}\n\n"
            f"{job_context}\n\n"
            "Je viens de te l'envoyer en PDF.\n"
            "C'est une proposition générée automatiquement : relis-la avant de l'envoyer.\n"
            f"{next_line}"
        )
        await _send_notification(
            platform=platform,
            chat_id=chat_id,
            relative_path=relative_path,
            caption=caption,
            absolute_path=str(filepath),
        )
        logger.info("[bg] Notification envoyée — platform=%s", platform)

    except Exception as exc:
        logger.exception("[bg] ÉCHEC génération %s — user=%s", doc_type, user_id)
        await _mark_document_job(document_job_id, status="failed", error=str(exc))

        # Rembourser les crédits si la déduction a été faite à l'avance
        if skip_deduction:
            try:
                credit_mgr = CreditManager()
                await credit_mgr.add(user_id, cost, reason=f"refund_{func_name}_failure")
                logger.info("[bg] Crédits remboursés — user=%s amount=%d", user_id, cost)
            except Exception:
                logger.exception("[bg] ÉCHEC remboursement crédits — user=%s", user_id)

        await _send_notification(
            platform=platform,
            chat_id=chat_id,
            relative_path=None,
            caption=(
                "Désolé, la génération du document a échoué.\n\n"
                "Tes crédits ont été remboursés. Tu peux réessayer avec la même offre."
            ),
            absolute_path=None,
        )


async def _send_notification(
    platform: str,
    chat_id: str | int,
    relative_path: str | None,
    caption: str,
    absolute_path: str | None = None,
) -> None:
    if platform == "telegram":
        await _send_telegram(chat_id, absolute_path, caption)
    elif platform == "whatsapp":
        await _queue_whatsapp(chat_id, relative_path, caption)


async def _send_telegram(chat_id: str | int, filepath: str | None, caption: str) -> None:
    bot = get_telegram_bot()
    if not bot:
        logger.error("No Telegram bot registered")
        return
    try:
        chat_id_int = int(chat_id)
        if filepath and Path(filepath).exists():
            await bot.send_document(
                chat_id=chat_id_int,
                document=filepath,
                caption=caption,
                filename=Path(filepath).name,
            )
            logger.info(
                "Document sent via Telegram to chat_id=%s: %s", chat_id, Path(filepath).name
            )
        else:
            await bot.send_message(chat_id=chat_id_int, text=caption)
            logger.info("Notification sent via Telegram to chat_id=%s", chat_id)
    except Exception:
        logger.exception("Failed to send Telegram notification to chat_id=%s", chat_id)
        try:
            chat_id_int = int(chat_id)
            await bot.send_message(chat_id=chat_id_int, text=caption)
        except Exception:
            logger.exception("Text fallback also failed for chat_id=%s", chat_id)


async def _queue_whatsapp(
    chat_id: str | int,
    relative_path: str | None,
    caption: str,
) -> None:
    from leRH.db.base import async_session_factory as session_factory
    from leRH.db.models import PendingMessage

    async with _db_lock, session_factory() as session:
        session.add(
            PendingMessage(
                platform="whatsapp",
                platform_chat_id=str(chat_id),
                message_type="document" if relative_path else "text",
                text=caption,
                document_path=relative_path,
            )
        )
        await session.commit()
    logger.info(
        "[bg] WhatsApp pending message queued — chat_id=%s path=%s",
        chat_id,
        relative_path,
    )
