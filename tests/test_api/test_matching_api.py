"""Tests des endpoints de matching."""

import pytest
from httpx import AsyncClient

from leRH.db.repository import JobRepository, UserRepository


@pytest.mark.asyncio
async def test_score_match_creates_result(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="Candidate", city="Lomé", skills=["python", "sql"])

    job_repo = JobRepository(db_session)
    job = await job_repo.create(
        recruiter_id=user.id,
        title="Dev Python",
        description="Python developer needed",
        city="Lomé",
        requirements={"skills": ["python", "sql", "fastapi"]},
    )

    resp = await client.post(f"/matching/score?candidate_id={user.id}&job_id={job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidate_id"] == user.id
    assert data["job_id"] == job.id
    assert isinstance(data["overall_score"], float)
    assert "criteria" in data
    assert data["recommendation"] in ("strong_match", "possible_match", "weak_match")


@pytest.mark.asyncio
async def test_score_match_candidate_not_found(client: AsyncClient) -> None:
    resp = await client.post("/matching/score?candidate_id=nonexistent&job_id=nonexistent")
    assert resp.status_code == 404
    assert "Candidate not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_score_match_job_not_found(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="Test")

    resp = await client.post(f"/matching/score?candidate_id={user.id}&job_id=nonexistent")
    assert resp.status_code == 404
    assert "Job not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_candidate_to_jobs(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="Candidate", city="Lomé", skills=["python"])

    job_repo = JobRepository(db_session)
    job = await job_repo.create(
        recruiter_id=user.id,
        title="Python Dev",
        description="Python dev",
    )

    resp = await client.get(f"/matching/candidate/{user.id}/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["job_id"] == job.id
    assert data[0]["candidate_id"] == user.id


@pytest.mark.asyncio
async def test_candidate_not_found(client: AsyncClient) -> None:
    resp = await client.get("/matching/candidate/nonexistent/jobs")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_job_to_candidates(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="Candidate", skills=["python"])

    job_repo = JobRepository(db_session)
    job = await job_repo.create(
        recruiter_id=user.id,
        title="Python Dev",
        description="Python dev",
    )

    resp = await client.get(f"/matching/job/{job.id}/candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["candidate_id"] == user.id


@pytest.mark.asyncio
async def test_job_not_found(client: AsyncClient) -> None:
    resp = await client.get("/matching/job/nonexistent/candidates")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_min_score_filter(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="Candidate", skills=["python"])

    job_repo = JobRepository(db_session)
    await job_repo.create(
        recruiter_id=user.id,
        title="Python Dev",
        description="Python dev",
    )

    resp = await client.get(f"/matching/candidate/{user.id}/jobs?min_score=99")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 0


@pytest.mark.asyncio
async def test_limit_param(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="Candidate", skills=["python"])

    job_repo = JobRepository(db_session)
    for i in range(5):
        await job_repo.create(
            recruiter_id=user.id,
            title=f"Job {i}",
            description="desc",
        )

    resp = await client.get(f"/matching/candidate/{user.id}/jobs?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
