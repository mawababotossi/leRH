"""Tests des modèles et repositories."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.db.repository import ApplicationRepository, CVRepository, JobRepository, UserRepository


@pytest.mark.asyncio
async def test_create_user_repo(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    user = await repo.create(name="Test", country="Togo", telegram_id=999)
    assert user.id
    assert user.name == "Test"
    assert user.telegram_id == 999


@pytest.mark.asyncio
async def test_get_user_by_telegram_repo(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    await repo.create(name="User1", telegram_id=111)
    await repo.create(name="User2", telegram_id=222)

    found = await repo.get_by_telegram(111)
    assert found is not None
    assert found.name == "User1"

    missing = await repo.get_by_telegram(333)
    assert missing is None


@pytest.mark.asyncio
async def test_create_cv(db_session: AsyncSession) -> None:
    user_repo = UserRepository(db_session)
    user = await user_repo.create(name="CV Owner")

    cv_repo = CVRepository(db_session)
    cv = await cv_repo.create(user_id=user.id, original_name="cv.pdf", extracted_text="Hello world")
    assert cv.id
    assert cv.user_id == user.id


@pytest.mark.asyncio
async def test_job_lifecycle(db_session: AsyncSession) -> None:
    user_repo = UserRepository(db_session)
    recruiter = await user_repo.create(name="Recruiter")

    job_repo = JobRepository(db_session)
    job = await job_repo.create(
        recruiter_id=recruiter.id,
        title="Commercial terrain",
        description="Vente de produits",
        city="Kara",
        salary_min=80000,
        salary_max=120000,
    )
    assert job.status == "active"

    active_jobs = await job_repo.get_active()
    assert len(active_jobs) == 1


@pytest.mark.asyncio
async def test_application(db_session: AsyncSession) -> None:
    user_repo = UserRepository(db_session)
    candidate = await user_repo.create(name="Candidate")
    recruiter = await user_repo.create(name="Recruiter")

    job_repo = JobRepository(db_session)
    job = await job_repo.create(recruiter_id=recruiter.id, title="Dev", description="Python")

    app_repo = ApplicationRepository(db_session)
    application = await app_repo.create(candidate_id=candidate.id, job_id=job.id, match_score=85.0)
    assert application.status == "pending"
    assert application.match_score == 85.0


@pytest.mark.asyncio
async def test_user_update(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    user = await repo.create(name="UpdateMe", city="Lomé")

    updated = await repo.update(user, city="Kara")
    assert updated.city == "Kara"

    reloaded = await repo.get_by_id(user.id)
    assert reloaded is not None
    assert reloaded.city == "Kara"
