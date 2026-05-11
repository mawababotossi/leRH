from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.db.base import get_db
from leRH.db.repository import ApplicationRepository, JobRepository, UserRepository
from leRH.schemas import ApplicationCreate, ApplicationResponse

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("/", response_model=list[ApplicationResponse])
async def list_applications(
    candidate_id: str | None = None,
    job_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ApplicationResponse]:
    repo = ApplicationRepository(db)
    if candidate_id:
        apps = await repo.get_by_candidate(candidate_id)
    elif job_id:
        apps = await repo.get_by_job(job_id)
    else:
        return []
    return [ApplicationResponse.model_validate(a) for a in apps]


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str, db: AsyncSession = Depends(get_db)
) -> ApplicationResponse:
    repo = ApplicationRepository(db)
    app = await repo.get_by_id(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationResponse.model_validate(app)


@router.post("/", response_model=ApplicationResponse, status_code=201)
async def create_application(
    payload: ApplicationCreate, db: AsyncSession = Depends(get_db)
) -> ApplicationResponse:
    user_repo = UserRepository(db)
    candidate = await user_repo.get_by_id(payload.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job_repo = JobRepository(db)
    job = await job_repo.get_by_id(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    repo = ApplicationRepository(db)
    app = await repo.create(candidate_id=payload.candidate_id, job_id=payload.job_id)
    return ApplicationResponse.model_validate(app)


@router.patch("/{application_id}/status", response_model=ApplicationResponse)
async def update_application_status(
    application_id: str,
    status: str,
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    valid_statuses = {"pending", "reviewed", "accepted", "rejected"}
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    repo = ApplicationRepository(db)
    app = await repo.get_by_id(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    app = await repo.update(app, status=status)
    await db.refresh(app)
    return ApplicationResponse.model_validate(app)
