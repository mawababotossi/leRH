from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.db.models import CV, Application, Job, Message, Subscription, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_telegram(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_whatsapp(self, whatsapp_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.whatsapp_id == whatsapp_id))
        return result.scalar_one_or_none()

    async def get_all(self) -> list[User]:
        result = await self.session.execute(select(User))
        return list(result.scalars().all())

    async def create(self, **kwargs) -> User:
        user = User(**kwargs)
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            setattr(user, key, value)
        await self.session.flush()
        return user


class CVRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user(self, user_id: str) -> list[CV]:
        result = await self.session.execute(select(CV).where(CV.user_id == user_id))
        return list(result.scalars().all())

    async def get_latest_for_user(self, user_id: str) -> CV | None:
        """Retourne le CV le plus récemment uploadé par l'utilisateur.

        Utilisé pour récupérer l'analyse du vrai CV avant la génération
        de documents ATS (CV, lettre de motivation).
        """
        result = await self.session.execute(
            select(CV).where(CV.user_id == user_id).order_by(CV.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> CV:
        cv = CV(**kwargs)
        self.session.add(cv)
        await self.session.flush()
        return cv


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self) -> list[Job]:
        result = await self.session.execute(select(Job).where(Job.status == "active"))
        return list(result.scalars().all())

    async def get_all(self) -> list[Job]:
        result = await self.session.execute(select(Job))
        return list(result.scalars().all())

    async def get_by_id(self, job_id: str) -> Job | None:
        return await self.session.get(Job, job_id)

    async def get_by_external_id(self, external_id: str, source_name: str) -> Job | None:
        result = await self.session.execute(
            select(Job).where(Job.external_id == external_id, Job.source_name == source_name)
        )
        return result.scalar_one_or_none()

    async def get_external_active(self) -> list[Job]:
        result = await self.session.execute(
            select(Job).where(Job.status == "active", Job.is_external.is_(True))
        )
        return list(result.scalars().all())

    async def get_recent_external(self, since_hours: int = 24) -> list[Job]:
        from datetime import UTC, datetime, timedelta

        since = datetime.now(UTC) - timedelta(hours=since_hours)
        result = await self.session.execute(
            select(Job).where(
                Job.is_external.is_(True),
                Job.created_at >= since,
                Job.status == "active",
            )
        )
        return list(result.scalars().all())

    async def search(self, query: str | None = None, city: str | None = None) -> list[Job]:
        stmt = select(Job)
        if query:
            stmt = stmt.where(Job.title.ilike(f"%{query}%") | Job.description.ilike(f"%{query}%"))
        if city:
            stmt = stmt.where(Job.city.ilike(f"%{city}%"))
        stmt = stmt.order_by(Job.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> Job:
        job = Job(**kwargs)
        self.session.add(job)
        await self.session.flush()
        return job

    async def update(self, job: Job, **kwargs) -> Job:
        for key, value in kwargs.items():
            setattr(job, key, value)
        await self.session.flush()
        return job


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(Subscription.active.is_(True))
        )
        return list(result.scalars().all())

    async def get_by_user(self, user_id: str) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Subscription:
        sub = Subscription(**kwargs)
        self.session.add(sub)
        await self.session.flush()
        return sub

    async def update(self, sub: Subscription, **kwargs) -> Subscription:
        for key, value in kwargs.items():
            setattr(sub, key, value)
        await self.session.flush()
        return sub

    async def delete(self, sub: Subscription) -> None:
        await self.session.delete(sub)


class ApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, application_id: str) -> Application | None:
        return await self.session.get(Application, application_id)

    async def get_by_candidate(self, candidate_id: str) -> list[Application]:
        result = await self.session.execute(
            select(Application).where(Application.candidate_id == candidate_id)
        )
        return list(result.scalars().all())

    async def get_by_job(self, job_id: str) -> list[Application]:
        result = await self.session.execute(select(Application).where(Application.job_id == job_id))
        return list(result.scalars().all())

    async def create(self, **kwargs) -> Application:
        app = Application(**kwargs)
        self.session.add(app)
        await self.session.flush()
        return app

    async def update(self, app: Application, **kwargs) -> Application:
        for key, value in kwargs.items():
            setattr(app, key, value)
        await self.session.flush()
        return app


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_recent(self, user_id: str, limit: int = 10) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def create(self, **kwargs) -> Message:
        msg = Message(**kwargs)
        self.session.add(msg)
        await self.session.flush()
        return msg
