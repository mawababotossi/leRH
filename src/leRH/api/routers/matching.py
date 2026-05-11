from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.core.matching.engine import Matcher, MatchResult
from leRH.db.base import get_db
from leRH.db.repository import CVRepository, JobRepository, UserRepository

router = APIRouter(prefix="/matching", tags=["matching"])


@router.get("/candidate/{candidate_id}/jobs", response_model=list[dict])
async def match_candidate_to_jobs(
    candidate_id: str,
    limit: int = 10,
    min_score: float = 0,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(candidate_id)
    if not user:
        raise HTTPException(status_code=404, detail="Candidate not found")

    cv_repo = CVRepository(db)
    cvs = await cv_repo.get_by_user(candidate_id)
    cv = cvs[0] if cvs else None

    job_repo = JobRepository(db)
    jobs = await job_repo.get_active()

    matcher = Matcher()
    results: list[MatchResult] = []
    for job in jobs:
        result = await matcher.match(user, job, cv)
        if result.overall_score >= min_score:
            results.append(result)

    results.sort(key=lambda r: r.overall_score, reverse=True)
    return [_result_to_dict(r) for r in results[:limit]]


@router.get("/job/{job_id}/candidates", response_model=list[dict])
async def match_job_to_candidates(
    job_id: str,
    limit: int = 10,
    min_score: float = 0,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    job_repo = JobRepository(db)
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    user_repo = UserRepository(db)
    users = await user_repo.get_all()
    cv_repo = CVRepository(db)

    matcher = Matcher()
    results: list[MatchResult] = []
    for user in users:
        cvs = await cv_repo.get_by_user(user.id)
        cv = cvs[0] if cvs else None
        result = await matcher.match(user, job, cv)
        if result.overall_score >= min_score:
            results.append(result)

    results.sort(key=lambda r: r.overall_score, reverse=True)
    return [_result_to_dict(r) for r in results[:limit]]


@router.post("/score", response_model=dict)
async def score_match(
    candidate_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(candidate_id)
    if not user:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job_repo = JobRepository(db)
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    cv_repo = CVRepository(db)
    cvs = await cv_repo.get_by_user(candidate_id)
    cv = cvs[0] if cvs else None

    matcher = Matcher()
    result = await matcher.match(user, job, cv)
    return _result_to_dict(result)


def _result_to_dict(r: MatchResult) -> dict:
    return {
        "candidate_id": r.candidate_id,
        "job_id": r.job_id,
        "overall_score": r.overall_score,
        "criteria": [
            {"name": c.name, "score": c.score, "weight": c.weight, "details": c.details}
            for c in r.criteria
        ],
        "summary": r.summary,
        "recommendation": r.recommendation,
        "llm_enhanced": r.llm_enhanced,
        "job_source": r.job_source,
        "job_source_url": r.job_source_url,
        "is_external": r.is_external,
    }
