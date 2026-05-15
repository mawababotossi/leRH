"""Tests des endpoints Jobs."""

import pytest
from httpx import AsyncClient

from leRH.db.repository import UserRepository


@pytest.mark.asyncio
async def test_create_job(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    recruiter = await user_repo.create(name="Recruiter")

    payload = {
        "recruiter_id": recruiter.id,
        "title": "Commercial terrain",
        "description": "Vente de produits agro-alimentaires",
        "company": "AgriCo",
        "city": "Kara",
        "salary_min": 80000,
        "salary_max": 120000,
        "requirements": {"skills": ["vente", "négociation", "terrain"]},
    }
    resp = await client.post("/jobs/", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Commercial terrain"
    assert data["company"] == "AgriCo"
    assert data["city"] == "Kara"
    assert data["status"] == "active"
    assert "id" in data
    assert data["recruiter_id"] == recruiter.id


@pytest.mark.asyncio
async def test_create_job_recruiter_not_found(client: AsyncClient) -> None:
    payload = {
        "recruiter_id": "nonexistent",
        "title": "Test",
        "description": "Test job",
    }
    resp = await client.post("/jobs/", json=payload)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    recruiter = await user_repo.create(name="Recruiter")

    create = await client.post(
        "/jobs/",
        json={
            "recruiter_id": recruiter.id,
            "title": "Dev",
            "description": "Python dev",
        },
    )
    job_id = create.json()["id"]

    resp = await client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Dev"


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient) -> None:
    resp = await client.get("/jobs/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    recruiter = await user_repo.create(name="Recruiter")

    for i in range(3):
        await client.post(
            "/jobs/",
            json={
                "recruiter_id": recruiter.id,
                "title": f"Job {i}",
                "description": f"Description {i}",
            },
        )

    resp = await client.get("/jobs/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_list_active_jobs(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    recruiter = await user_repo.create(name="Recruiter")

    await client.post(
        "/jobs/",
        json={
            "recruiter_id": recruiter.id,
            "title": "Active Job",
            "description": "desc",
        },
    )
    create = await client.post(
        "/jobs/",
        json={
            "recruiter_id": recruiter.id,
            "title": "Inactive Job",
            "description": "desc",
        },
    )
    job_id = create.json()["id"]
    await client.patch(f"/jobs/{job_id}", json={"status": "inactive"})

    resp = await client.get("/jobs/active")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_search_jobs(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    recruiter = await user_repo.create(name="Recruiter")

    await client.post(
        "/jobs/",
        json={
            "recruiter_id": recruiter.id,
            "title": "Commercial terrain",
            "description": "Vente de produits",
            "city": "Kara",
        },
    )
    await client.post(
        "/jobs/",
        json={
            "recruiter_id": recruiter.id,
            "title": "Développeur Python",
            "description": "Développement web",
            "city": "Lomé",
        },
    )

    resp = await client.get("/jobs/?query=Commercial")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = await client.get("/jobs/?city=Kara")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_update_job(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    recruiter = await user_repo.create(name="Recruiter")

    create = await client.post(
        "/jobs/",
        json={
            "recruiter_id": recruiter.id,
            "title": "Old Title",
            "description": "Old description",
        },
    )
    job_id = create.json()["id"]

    resp = await client.patch(f"/jobs/{job_id}", json={"title": "New Title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "New Title"
    assert resp.json()["description"] == "Old description"


@pytest.mark.asyncio
async def test_update_job_not_found(client: AsyncClient) -> None:
    resp = await client.patch("/jobs/nonexistent", json={"title": "New"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_job(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    recruiter = await user_repo.create(name="Recruiter")

    create = await client.post(
        "/jobs/",
        json={
            "recruiter_id": recruiter.id,
            "title": "To Delete",
            "description": "desc",
        },
    )
    job_id = create.json()["id"]

    resp = await client.delete(f"/jobs/{job_id}")
    assert resp.status_code == 200

    get_resp = await client.get(f"/jobs/{job_id}")
    assert get_resp.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_delete_job_not_found(client: AsyncClient) -> None:
    resp = await client.delete("/jobs/nonexistent")
    assert resp.status_code == 404
