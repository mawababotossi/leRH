"""Tests des endpoints Profiles."""

import pytest
from httpx import AsyncClient

from leRH.db.repository import UserRepository


@pytest.mark.asyncio
async def test_get_profile(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="Test User", city="Lomé")

    resp = await client.get(f"/profiles/{user.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["name"] == "Test User"
    assert data["user"]["city"] == "Lomé"


@pytest.mark.asyncio
async def test_get_profile_not_found(client: AsyncClient) -> None:
    resp = await client.get("/profiles/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_cvs(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="CV Owner")

    resp = await client.get(f"/profiles/{user.id}/cvs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_cvs_not_found(client: AsyncClient) -> None:
    resp = await client.get("/profiles/nonexistent/cvs")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analyze_cv_creates_cv(client: AsyncClient, db_session) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="Candidate")

    resp = await client.post(
        "/profiles/analyze-cv",
        json={
            "user_id": user.id,
            "cv_text": "Experienced Python developer with 5 years in web development",
            "original_name": "cv.pdf",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["id"] == user.id

    cvs_resp = await client.get(f"/profiles/{user.id}/cvs")
    assert len(cvs_resp.json()) == 1


@pytest.mark.asyncio
async def test_analyze_cv_user_not_found(client: AsyncClient) -> None:
    resp = await client.post(
        "/profiles/analyze-cv",
        json={
            "user_id": "nonexistent",
            "cv_text": "Some CV text",
        },
    )
    assert resp.status_code == 404
