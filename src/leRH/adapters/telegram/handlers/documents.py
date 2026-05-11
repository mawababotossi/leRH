from __future__ import annotations

import io
import logging

import PyPDF2
from telegram import Update
from telegram.ext import ContextTypes

from leRH.core.profiles.extractor import ProfileExtractor
from leRH.db.base import async_session_factory
from leRH.db.repository import CVRepository, UserRepository

logger = logging.getLogger(__name__)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.message.from_user
    doc = update.message.document

    if not doc or doc.mime_type != "application/pdf":
        await update.message.reply_text("Veuillez envoyer votre CV au format PDF.")
        return

    logger.info("PDF from %s: %s", tg_user.first_name, doc.file_name)
    await update.message.reply_text("Analyse de votre CV en cours...")

    try:
        pdf_file = await context.bot.get_file(doc.file_id)
        buf = io.BytesIO()
        await pdf_file.download_to_memory(buf)
        buf.seek(0)

        reader = PyPDF2.PdfReader(buf)
        cv_text = ""
        for page in reader.pages:
            if text := page.extract_text():
                cv_text += text + "\n"
        cv_text = cv_text.strip()

        if not cv_text:
            await update.message.reply_text("Impossible d'extraire le texte de ce PDF.")
            return

        logger.info("CV text extracted (%d chars)", len(cv_text))

        extractor = ProfileExtractor()
        result = extractor.analyze_cv(cv_text)

        async with async_session_factory() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram(tg_user.id)

            analysis_text = "Analyse non disponible."
            if result:
                analysis_text = result.get("analysis", "")
                profile = result.get("profile", {})
                if profile and user:
                    user = extractor.enrich_user(user, profile)

            if user:
                cv_repo = CVRepository(session)
                await cv_repo.create(
                    user_id=user.id,
                    original_name=doc.file_name or "cv.pdf",
                    extracted_text=cv_text[:5000],
                    analysis=result or {"analysis": "Extraction failed"},
                )

            await session.commit()

        await update.message.reply_text(f"Analyse du CV:\n\n{analysis_text}")
    except Exception as exc:
        logger.exception("Error processing CV")
        await update.message.reply_text(f"Desole, une erreur s'est produite: {exc}")
