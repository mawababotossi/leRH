from __future__ import annotations

import logging
from io import BytesIO
from urllib.parse import unquote
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


async def _check_credits(user_id: str, cost: int, session: AsyncSession | None = None) -> None:
    cm = CreditManager()
    if not await cm.check_credits(user_id, cost, session=session):
        current = await cm.get_credits(user_id, session=session)
        raise HTTPException(
            status_code=402,
            detail=(
                f"Crédits insuffisants. Vous avez {current} crédit(s), "
                f"il en faut {cost}. Activez les alertes emploi pour recevoir 50 crédits bonus."
            ),
        )


async def _deduct_credits(
    user_id: str, cost: int, reason: str, session: AsyncSession | None = None
) -> None:
    cm = CreditManager()
    result = await cm.deduct(user_id, cost, reason, session=session)
    if not result.success:
        logger.warning("Credit deduction failed for user %s: %s", user_id, result.message)


def _validate_format(fmt: str) -> None:
    if fmt not in ("docx", "pdf"):
        raise HTTPException(status_code=400, detail="Format must be 'docx' or 'pdf'")


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
    cv_analysis = cv_record.analysis if cv_record else None
    if not cv_analysis:
        logger.info(
            "User %s has no uploaded CV — document will be generated from profile fields only",
            payload.user_id,
        )

    await _check_credits(payload.user_id, CV_COST, session=db)

    try:
        gen = DocumentGenerator()
        buf, filename = gen.generate_cv(user, job, fmt=payload.format, cv_analysis=cv_analysis)
        await _deduct_credits(payload.user_id, CV_COST, f"generate_cv_{job.id}", session=db)

        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if payload.format == "docx"
            else "application/pdf"
        )
        return _streaming_response(buf, filename, content_type)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("CV generation failed")
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
    cv_analysis = cv_record.analysis if cv_record else None

    await _check_credits(payload.user_id, COVER_LETTER_COST, session=db)

    try:
        gen = DocumentGenerator()
        buf, filename = gen.generate_cover_letter(
            user, job, fmt=payload.format, cv_analysis=cv_analysis
        )
        await _deduct_credits(
            payload.user_id, COVER_LETTER_COST, f"generate_cover_letter_{job.id}", session=db
        )

        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if payload.format == "docx"
            else "application/pdf"
        )
        return _streaming_response(buf, filename, content_type)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Cover letter generation failed")
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
    cv_analysis = cv_record.analysis if cv_record else None

    await _check_credits(payload.user_id, CV_COST + COVER_LETTER_COST, session=db)

    try:
        gen = DocumentGenerator()
        cv_buf, cv_filename = gen.generate_cv(
            user, job, fmt=payload.format, cv_analysis=cv_analysis
        )
        cl_buf, cl_filename = gen.generate_cover_letter(
            user, job, fmt=payload.format, cv_analysis=cv_analysis
        )
        await _deduct_credits(
            payload.user_id, CV_COST + COVER_LETTER_COST, f"generate_all_{job.id}", session=db
        )

        zip_buf = BytesIO()
        with ZipFile(zip_buf, "w", ZIP_DEFLATED) as zf:
            zf.writestr(cv_filename, cv_buf.getvalue())
            zf.writestr(cl_filename, cl_buf.getvalue())
        zip_buf.seek(0)

        zip_name = f"Candidature_{user.name.replace(' ', '_')}.zip"
        return _streaming_response(zip_buf, zip_name, "application/zip")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Document generation failed")
        raise HTTPException(
            status_code=500,
            detail=str(exc) or "Erreur lors de la génération des documents",
        ) from exc


@router.get("/download/{filepath:path}")
async def download_file(filepath: str):
    logger.info(f"Download request: raw={filepath}")
    decoded_path = unquote(filepath)
    logger.info(f"Download request: decoded={decoded_path}")
    file_path = GENERATED_DIR / decoded_path
    if not file_path.resolve().is_relative_to(GENERATED_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Accès refusé")
    logger.info(f"Download request: full_path={file_path} exists={file_path.exists()}")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier non trouvé")
    return StreamingResponse(
        file_path.open("rb"),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={file_path.name}"},
    )
