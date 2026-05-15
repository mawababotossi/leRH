from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.db.base import get_db
from leRH.db.repository import JobRepository, UserRepository
from leRH.schemas import JobCreate, JobResponse, JobUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/", response_model=list[JobResponse])
async def list_jobs(
    query: str | None = Query(None),
    city: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[JobResponse]:
    repo = JobRepository(db)
    if query or city:
        jobs = await repo.search(query=query, city=city)
    else:
        jobs = await repo.get_all()
    return [JobResponse.model_validate(j) for j in jobs]


@router.get("/active", response_model=list[JobResponse])
async def list_active_jobs(db: AsyncSession = Depends(get_db)) -> list[JobResponse]:
    repo = JobRepository(db)
    jobs = await repo.get_active()
    return [JobResponse.model_validate(j) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)) -> JobResponse:
    repo = JobRepository(db)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@router.post("/", response_model=JobResponse, status_code=201)
async def create_job(payload: JobCreate, db: AsyncSession = Depends(get_db)) -> JobResponse:
    user_repo = UserRepository(db)
    recruiter = await user_repo.get_by_id(payload.recruiter_id)
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")

    repo = JobRepository(db)
    job = await repo.create(**payload.model_dump())
    return JobResponse.model_validate(job)


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: str, payload: JobUpdate, db: AsyncSession = Depends(get_db)
) -> JobResponse:
    repo = JobRepository(db)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        job = await repo.update(job, **updates)
        await db.refresh(job)
    return JobResponse.model_validate(job)


@router.delete("/{job_id}", status_code=200)
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    repo = JobRepository(db)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await repo.update(job, status="inactive")
    return {"message": "Job deleted"}
