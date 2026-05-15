from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from leRH.core.batch import jobs
from leRH.core.credits import CreditResult
from leRH.db.models import PendingMessage


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


class FakeSubscriptionRepository:
    subscriptions: list[SimpleNamespace] = []

    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def get_active(self) -> list[SimpleNamespace]:
        return self.subscriptions


class FakeJobRepository:
    jobs: list[SimpleNamespace] = []

    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def get_recent_external(self, since_hours: int = 24) -> list[SimpleNamespace]:
        return self.jobs


class FakeUserRepository:
    users: dict[str, SimpleNamespace] = {}

    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: str) -> SimpleNamespace | None:
        return self.users.get(user_id)


class FakeCVRepository:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def get_by_user(self, user_id: str) -> list:
        return []


class FakeMatcher:
    async def match(self, user, job, cv):
        return SimpleNamespace(overall_score=82.0, recommendation="strong_match")


class FakeCreditManager:
    deduct_calls: list[tuple[str, int, str]] = []
    add_calls: list[tuple[str, int, str]] = []

    async def check_credits(self, user_id: str, amount: int, session=None) -> bool:
        return True

    async def deduct(self, user_id: str, amount: int, reason: str = "", session=None):
        self.deduct_calls.append((user_id, amount, reason))
        return CreditResult(True, 49, "ok")

    async def add(self, user_id: str, amount: int, reason: str = "", session=None):
        self.add_calls.append((user_id, amount, reason))
        return CreditResult(True, 50, "ok")


def _job(**overrides) -> SimpleNamespace:
    data = {
        "id": "job1",
        "title": "Développeur Python",
        "company": "ACME",
        "city": "Lomé",
        "source_url": "https://example.test/jobs/1",
        "created_at": datetime.now(UTC),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _subscription(**overrides) -> SimpleNamespace:
    data = {
        "id": "sub1",
        "user_id": "user1",
        "min_match_score": 60.0,
        "notify_telegram": False,
        "notify_whatsapp": True,
        "last_notified_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _user(**overrides) -> SimpleNamespace:
    data = {
        "id": "user1",
        "name": "Afi",
        "telegram_id": None,
        "whatsapp_id": "22890000000@s.whatsapp.net",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _patch_batch(session: FakeSession):
    return patch.multiple(
        jobs,
        async_session_factory=FakeSessionFactory(session),
        SubscriptionRepository=FakeSubscriptionRepository,
        JobRepository=FakeJobRepository,
        UserRepository=FakeUserRepository,
        CVRepository=FakeCVRepository,
        Matcher=FakeMatcher,
        CreditManager=FakeCreditManager,
    )


@pytest.mark.asyncio
async def test_match_and_notify_queues_whatsapp_and_deducts_credit() -> None:
    session = FakeSession()
    FakeSubscriptionRepository.subscriptions = [_subscription()]
    FakeJobRepository.jobs = [_job()]
    FakeUserRepository.users = {"user1": _user()}
    FakeCreditManager.deduct_calls = []
    FakeCreditManager.add_calls = []

    with _patch_batch(session):
        notified = await jobs.match_and_notify()

    pending_messages = [msg for msg in session.added if isinstance(msg, PendingMessage)]
    assert notified == 1
    assert len(pending_messages) == 1
    assert pending_messages[0].platform == "whatsapp"
    assert pending_messages[0].platform_chat_id == "22890000000@s.whatsapp.net"
    assert "Développeur Python" in (pending_messages[0].text or "")
    assert FakeCreditManager.deduct_calls == [("user1", 1, "notification_sub1")]


@pytest.mark.asyncio
async def test_match_and_notify_sends_telegram_and_deducts_credit() -> None:
    session = FakeSession()
    bot = SimpleNamespace(send_message=AsyncMock())
    FakeSubscriptionRepository.subscriptions = [
        _subscription(notify_telegram=True, notify_whatsapp=False)
    ]
    FakeJobRepository.jobs = [_job()]
    FakeUserRepository.users = {"user1": _user(telegram_id=123456, whatsapp_id=None)}
    FakeCreditManager.deduct_calls = []
    FakeCreditManager.add_calls = []

    with _patch_batch(session), patch.object(jobs, "get_telegram_bot", return_value=bot):
        notified = await jobs.match_and_notify()

    assert notified == 1
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == 123456
    assert "Développeur Python" in bot.send_message.await_args.kwargs["text"]
    assert FakeCreditManager.deduct_calls == [("user1", 1, "notification_sub1")]


@pytest.mark.asyncio
async def test_match_and_notify_does_not_deduct_when_no_channel_delivered() -> None:
    session = FakeSession()
    FakeSubscriptionRepository.subscriptions = [
        _subscription(notify_telegram=True, notify_whatsapp=False)
    ]
    FakeJobRepository.jobs = [_job()]
    FakeUserRepository.users = {"user1": _user(telegram_id=None, whatsapp_id=None)}
    FakeCreditManager.deduct_calls = []
    FakeCreditManager.add_calls = []

    with _patch_batch(session):
        notified = await jobs.match_and_notify()

    assert notified == 0
    assert FakeCreditManager.deduct_calls == []
    assert FakeCreditManager.add_calls == []
    assert not [msg for msg in session.added if isinstance(msg, PendingMessage)]


@pytest.mark.asyncio
async def test_match_and_notify_refunds_when_telegram_delivery_fails() -> None:
    session = FakeSession()
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("telegram down")))
    FakeSubscriptionRepository.subscriptions = [
        _subscription(notify_telegram=True, notify_whatsapp=False)
    ]
    FakeJobRepository.jobs = [_job()]
    FakeUserRepository.users = {"user1": _user(telegram_id=123456, whatsapp_id=None)}
    FakeCreditManager.deduct_calls = []
    FakeCreditManager.add_calls = []

    with _patch_batch(session), patch.object(jobs, "get_telegram_bot", return_value=bot):
        notified = await jobs.match_and_notify()

    assert notified == 0
    assert FakeCreditManager.deduct_calls == [("user1", 1, "notification_sub1")]
    assert FakeCreditManager.add_calls == [("user1", 1, "refund_notification_sub1")]
