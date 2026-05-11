"""Tests des endpoints Applications."""

import pytest
from httpx import AsyncClient

from leRH.db.repository import JobRepository, UserRepository


@pytest.mark.asyncio
async def test_create_application(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    candidate = await user_repo.create(name="Candidate")
    recruiter = await user_repo.create(name="Recruiter")
    job_repo = JobRepository(db_session)
    job = await job_repo.create(recruiter_id=recruiter.id, title="Dev", description="Python")

    resp = await client.post(
        "/applications/",
        json={
            "candidate_id": candidate.id,
            "job_id": job.id,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["candidate_id"] == candidate.id
    assert data["job_id"] == job.id
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_create_application_candidate_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        "/applications/",
        json={
            "candidate_id": "nonexistent",
            "job_id": "nonexistent",
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_application(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    candidate = await user_repo.create(name="Candidate")
    recruiter = await user_repo.create(name="Recruiter")
    job_repo = JobRepository(db_session)
    job = await job_repo.create(recruiter_id=recruiter.id, title="Dev", description="Python")

    create = await client.post(
        "/applications/",
        json={
            "candidate_id": candidate.id,
            "job_id": job.id,
        },
    )
    app_id = create.json()["id"]

    resp = await client.get(f"/applications/{app_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_get_application_not_found(client: AsyncClient) -> None:
    resp = await client.get("/applications/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_by_candidate(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    candidate = await user_repo.create(name="Candidate")
    recruiter = await user_repo.create(name="Recruiter")
    job_repo = JobRepository(db_session)
    job1 = await job_repo.create(recruiter_id=recruiter.id, title="Job 1", description="desc")
    job2 = await job_repo.create(recruiter_id=recruiter.id, title="Job 2", description="desc")

    await client.post("/applications/", json={"candidate_id": candidate.id, "job_id": job1.id})
    await client.post("/applications/", json={"candidate_id": candidate.id, "job_id": job2.id})

    resp = await client.get(f"/applications/?candidate_id={candidate.id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_list_by_job(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    c1 = await user_repo.create(name="C1")
    c2 = await user_repo.create(name="C2")
    recruiter = await user_repo.create(name="Recruiter")
    job_repo = JobRepository(db_session)
    job = await job_repo.create(recruiter_id=recruiter.id, title="Job", description="desc")

    await client.post("/applications/", json={"candidate_id": c1.id, "job_id": job.id})
    await client.post("/applications/", json={"candidate_id": c2.id, "job_id": job.id})

    resp = await client.get(f"/applications/?job_id={job.id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_update_status(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    candidate = await user_repo.create(name="Candidate")
    recruiter = await user_repo.create(name="Recruiter")
    job_repo = JobRepository(db_session)
    job = await job_repo.create(recruiter_id=recruiter.id, title="Dev", description="Python")

    create = await client.post(
        "/applications/",
        json={
            "candidate_id": candidate.id,
            "job_id": job.id,
        },
    )
    app_id = create.json()["id"]

    resp = await client.patch(f"/applications/{app_id}/status?status=reviewed")
    assert resp.status_code == 200
    assert resp.json()["status"] == "reviewed"


@pytest.mark.asyncio
async def test_update_status_invalid(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    candidate = await user_repo.create(name="Candidate")
    recruiter = await user_repo.create(name="Recruiter")
    job_repo = JobRepository(db_session)
    job = await job_repo.create(recruiter_id=recruiter.id, title="Dev", description="Python")

    create = await client.post(
        "/applications/",
        json={
            "candidate_id": candidate.id,
            "job_id": job.id,
        },
    )
    app_id = create.json()["id"]

    resp = await client.patch(f"/applications/{app_id}/status?status=invalid")
    assert resp.status_code == 400
