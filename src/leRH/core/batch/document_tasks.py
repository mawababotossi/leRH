from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from leRH.core.bot_registry import get_telegram_bot
from leRH.core.credits import CreditManager
from leRH.core.documents.generator import GENERATED_DIR, DocumentGenerator
from leRH.db.base import async_session_factory
from leRH.db.models import Job
from leRH.db.repository import UserRepository

logger = logging.getLogger(__name__)


async def generate_document_background(
    *,
    user_id: str,
    job: Job,
    func_name: str,
    cost: int,
    platform: str,
    chat_id: str | int,
) -> None:
    doc_type = "CV" if func_name == "generate_cv" else "lettre de motivation"
    logger.info("[bg] Début génération %s — user=%s job=%s", doc_type, user_id, job.title)

    try:
        async with async_session_factory() as session:
            repo = UserRepository(session)
            user = await repo.get_by_id(user_id)

        if not user:
            logger.error("[bg] Utilisateur %s introuvable", user_id)
            await _send_notification(platform, chat_id, None, "Utilisateur introuvable.")
            return

        logger.info("[bg] Utilisateur chargé — %s", user.name)

        loop = asyncio.get_running_loop()
        doc_gen = DocumentGenerator()

        logger.info("[bg] Appel LLM + génération fichier…")
        if func_name == "generate_cv":
            buf, filename = await loop.run_in_executor(
                None, lambda: doc_gen.generate_cv(user, job, fmt="docx")
            )
        else:
            buf, filename = await loop.run_in_executor(
                None, lambda: doc_gen.generate_cover_letter(user, job, fmt="docx")
            )
        logger.info("[bg] Fichier généré — %s (%d bytes)", filename, buf.getbuffer().nbytes)

        user_dir = GENERATED_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        filepath = user_dir / filename
        with open(filepath, "wb") as f:
            f.write(buf.getvalue())
        relative_path = f"{user_id}/{filename}"
        logger.info("[bg] Fichier sauvegardé — %s (relative: %s)", filepath, relative_path)

        credit_mgr = CreditManager()
        result = await credit_mgr.deduct(
            user_id, cost, reason=f"generation_{func_name}_for_{job.id}"
        )
        logger.info(
            "[bg] Crédits déduits — remaining=%d success=%s",
            result.credits_remaining,
            result.success,
        )

        caption = f"Votre {doc_type} est prêt ! 📎 Vous pouvez le télécharger maintenant."
        await _send_notification(platform, chat_id, relative_path, caption, str(filepath))
        logger.info("[bg] Notification envoyée — platform=%s", platform)

    except Exception:
        logger.exception("[bg] ÉCHEC génération %s — user=%s", doc_type, user_id)
        await _send_notification(
            platform,
            chat_id,
            None,
            "Désolé, la génération de votre document a échoué. Veuillez réessayer.",
        )


async def _send_notification(
    platform: str,
    chat_id: str | int,
    relative_path: Path | str | None,
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
    chat_id: str | int, relative_path: Path | str | None, caption: str
) -> None:
    from leRH.db.base import async_session_factory as session_factory
    from leRH.db.models import PendingMessage

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with session_factory() as session:
                session.add(
                    PendingMessage(
                        platform="whatsapp",
                        platform_chat_id=str(chat_id),
                        message_type="document" if relative_path else "text",
                        text=caption,
                        document_path=str(relative_path) if relative_path else None,
                    )
                )
                await session.commit()
            return
        except Exception as e:
            if attempt < max_retries - 1 and "database is locked" in str(e).lower():
                wait = (attempt + 1) * 0.5
                logger.warning(f"DB locked, retry in {wait}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait)
            else:
                raise
    logger.error("[bg] Failed to queue WhatsApp message after %d retries", max_retries)
