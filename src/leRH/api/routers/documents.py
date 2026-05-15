from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.core.credits import COVER_LETTER_COST, CV_COST, CreditManager
from leRH.core.documents.generator import GENERATED_DIR, DocumentGenerator
from leRH.db.base import get_db
from leRH.db.repository import CVRepository, JobRepository, UserRepository
from leRH.schemas import DocumentGenerateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


async def _reserve_credits(
    user_id: str, cost: int, reason: str, session: AsyncSession | None = None
) -> None:
    cm = CreditManager()
    result = await cm.deduct(user_id, cost, reason, session=session)
    if not result.success:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Crédits insuffisants. Vous avez {result.credits_remaining} crédit(s), "
                f"il en faut {cost}. Activez les alertes emploi pour recevoir 7 crédits bonus."
            ),
        )


async def _refund_credits(
    user_id: str, cost: int, reason: str, session: AsyncSession | None = None
) -> None:
    cm = CreditManager()
    result = await cm.add(user_id, cost, reason, session=session)
    if not result.success:
        logger.warning("Credit refund failed for user %s: %s", user_id, result.message)


def _validate_format(fmt: str) -> None:
    if fmt not in ("docx", "pdf"):
        raise HTTPException(status_code=400, detail="Format must be 'docx' or 'pdf'")


def _cv_analysis_with_source(cv_record) -> dict | None:
    if not cv_record or not cv_record.analysis:
        return None
    analysis = dict(cv_record.analysis)
    analysis["source_text"] = cv_record.extracted_text or ""
    return analysis


def _streaming_response(buf: BytesIO, filename: str, content_type: str) -> StreamingResponse:
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(buf.getvalue())),
        },
    )


@router.post("/generate-cv")
async def generate_cv(
    payload: DocumentGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    _validate_format(payload.format)

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    job_repo = JobRepository(db)
    job = await job_repo.get_by_id(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

    # Charger le dernier CV analysé pour enrichir la génération
    cv_repo = CVRepository(db)
    cv_record = await cv_repo.get_latest_for_user(payload.user_id)
    cv_analysis = _cv_analysis_with_source(cv_record)
    if not cv_analysis:
        logger.info(
            "User %s has no uploaded CV — document will be generated from profile fields only",
            payload.user_id,
        )

    await _reserve_credits(payload.user_id, CV_COST, f"reserve_generate_cv_{job.id}")

    try:
        gen = DocumentGenerator()
        buf, filename = await asyncio.to_thread(
            gen.generate_cv, user, job, fmt=payload.format, cv_analysis=cv_analysis
        )

        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if payload.format == "docx"
            else "application/pdf"
        )
        return _streaming_response(buf, filename, content_type)
    except HTTPException:
        await _refund_credits(payload.user_id, CV_COST, f"refund_generate_cv_{job.id}")
        raise
    except Exception as exc:
        logger.exception("CV generation failed")
        await _refund_credits(payload.user_id, CV_COST, f"refund_generate_cv_{job.id}")
        raise HTTPException(
            status_code=500,
            detail=str(exc) or "Erreur lors de la génération du CV",
        ) from exc


@router.post("/generate-cover-letter")
async def generate_cover_letter(
    payload: DocumentGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    _validate_format(payload.format)

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    job_repo = JobRepository(db)
    job = await job_repo.get_by_id(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

    # Charger le dernier CV analysé pour enrichir la génération
    cv_repo = CVRepository(db)
    cv_record = await cv_repo.get_latest_for_user(payload.user_id)
    cv_analysis = _cv_analysis_with_source(cv_record)

    await _reserve_credits(
        payload.user_id,
        COVER_LETTER_COST,
        f"reserve_generate_cover_letter_{job.id}",
    )

    try:
        gen = DocumentGenerator()
        buf, filename = await asyncio.to_thread(
            gen.generate_cover_letter, user, job, fmt=payload.format, cv_analysis=cv_analysis
        )

        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if payload.format == "docx"
            else "application/pdf"
        )
        return _streaming_response(buf, filename, content_type)
    except HTTPException:
        await _refund_credits(
            payload.user_id,
            COVER_LETTER_COST,
            f"refund_generate_cover_letter_{job.id}",
        )
        raise
    except Exception as exc:
        logger.exception("Cover letter generation failed")
        await _refund_credits(
            payload.user_id,
            COVER_LETTER_COST,
            f"refund_generate_cover_letter_{job.id}",
        )
        raise HTTPException(
            status_code=500,
            detail=str(exc) or "Erreur lors de la génération de la lettre de motivation",
        ) from exc


@router.post("/generate-all")
async def generate_all(
    payload: DocumentGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    _validate_format(payload.format)

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    job_repo = JobRepository(db)
    job = await job_repo.get_by_id(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

    # Charger le dernier CV analysé (une seule requête pour les deux documents)
    cv_repo = CVRepository(db)
    cv_record = await cv_repo.get_latest_for_user(payload.user_id)
    cv_analysis = _cv_analysis_with_source(cv_record)

    total_cost = CV_COST + COVER_LETTER_COST
    await _reserve_credits(payload.user_id, total_cost, f"reserve_generate_all_{job.id}")

    try:
        gen = DocumentGenerator()
        cv_buf, cv_filename = await asyncio.to_thread(
            gen.generate_cv, user, job, fmt=payload.format, cv_analysis=cv_analysis
        )
        cl_buf, cl_filename = await asyncio.to_thread(
            gen.generate_cover_letter, user, job, fmt=payload.format, cv_analysis=cv_analysis
        )

        zip_buf = BytesIO()
        with ZipFile(zip_buf, "w", ZIP_DEFLATED) as zf:
            zf.writestr(cv_filename, cv_buf.getvalue())
            zf.writestr(cl_filename, cl_buf.getvalue())
        zip_buf.seek(0)

        zip_name = f"Candidature_{user.name.replace(' ', '_')}.zip"
        return _streaming_response(zip_buf, zip_name, "application/zip")
    except HTTPException:
        await _refund_credits(payload.user_id, total_cost, f"refund_generate_all_{job.id}")
        raise
    except Exception as exc:
        logger.exception("Document generation failed")
        await _refund_credits(payload.user_id, total_cost, f"refund_generate_all_{job.id}")
        raise HTTPException(
            status_code=500,
            detail=str(exc) or "Erreur lors de la génération des documents",
        ) from exc


MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".zip": "application/zip",
}


@router.get("/download/{filepath:path}")
async def download_file(filepath: str):
    logger.info("Download request: raw=%s", filepath)

    # Rejeter tout chemin contenant des séquences suspectes
    if ".." in filepath or filepath.startswith("/"):
        logger.warning("Invalid path attempt: %s", filepath)
        raise HTTPException(status_code=400, detail="Chemin invalide")

    # GENERATED_DIR doit être résolu
    safe_base = GENERATED_DIR.resolve()
    file_path = (safe_base / filepath).resolve()

    # Vérification stricte que le chemin résolu commence par le préfixe autorisé
    if not str(file_path).startswith(str(safe_base) + "/"):
        logger.warning("Path traversal attempt blocked: %s", filepath)
        raise HTTPException(status_code=403, detail="Accès refusé")

    logger.info("Download request: full_path=%s exists=%s", file_path, file_path.exists())
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier non trouvé")
    file_size = file_path.stat().st_size
    logger.info("Download serving: %s (%d bytes)", file_path.name, file_size)
    if file_size == 0:
        logger.error("File is empty (0 bytes): %s", file_path)
        raise HTTPException(status_code=500, detail="Le fichier généré est vide")
    media_type = MIME_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
    return StreamingResponse(
        file_path.open("rb"),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"',
            "Content-Length": str(file_size),
        },
    )
