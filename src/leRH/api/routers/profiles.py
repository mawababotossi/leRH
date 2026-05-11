from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.core.profiles.extractor import ProfileExtractor
from leRH.db.base import get_db
from leRH.db.repository import CVRepository, UserRepository
from leRH.schemas import CVResponse, UserResponse

router = APIRouter(prefix="/profiles", tags=["profiles"])


class AnalyzeCVRequest(BaseModel):
    user_id: str
    cv_text: str
    original_name: str = "cv.pdf"


class ProfileResponse(BaseModel):
    user: UserResponse
    skills: list | None = None
    diploma: str | None = None
    experience: str | None = None
    languages: list | None = None


@router.post("/analyze-cv", response_model=ProfileResponse)
async def analyze_cv(
    payload: AnalyzeCVRequest, db: AsyncSession = Depends(get_db)
) -> ProfileResponse:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    extractor = ProfileExtractor()
    result = extractor.analyze_cv(payload.cv_text)
    profile = result.get("profile", {}) if result else {}

    cv_repo = CVRepository(db)
    await cv_repo.create(
        user_id=user.id,
        original_name=payload.original_name,
        extracted_text=payload.cv_text[:5000],
        analysis=result,
    )

    if profile:
        user = extractor.enrich_user(user, profile)
        await db.flush()

    return ProfileResponse(
        user=UserResponse.model_validate(user),
        skills=profile.get("skills") if profile else None,
        diploma=profile.get("diploma") if profile else None,
        experience=profile.get("experience") if profile else None,
        languages=profile.get("languages") if profile else None,
    )


@router.get("/{user_id}", response_model=ProfileResponse)
async def get_profile(user_id: str, db: AsyncSession = Depends(get_db)) -> ProfileResponse:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    cv_repo = CVRepository(db)
    cvs = await cv_repo.get_by_user(user_id)

    analysis = cvs[0].analysis if cvs else None

    return ProfileResponse(
        user=UserResponse.model_validate(user),
        skills=user.skills or (analysis.get("skills") if analysis else None),
        diploma=user.diploma or (analysis.get("diploma") if analysis else None),
        experience=user.experience or (analysis.get("experience") if analysis else None),
        languages=user.languages or (analysis.get("languages") if analysis else None),
    )


@router.get("/{user_id}/cvs", response_model=list[CVResponse])
async def list_cvs(user_id: str, db: AsyncSession = Depends(get_db)) -> list[CVResponse]:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    cv_repo = CVRepository(db)
    cvs = await cv_repo.get_by_user(user_id)
    return [CVResponse.model_validate(cv) for cv in cvs]
