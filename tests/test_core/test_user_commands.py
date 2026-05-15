from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from leRH.core import user_commands
from leRH.core.credits import SUBSCRIPTION_BONUS, WELCOME_CREDITS


class FakeSubscriptionRepository:
    subscription = None
    created = None

    def __init__(self, session) -> None:
        self.session = session

    async def get_by_user(self, user_id: str):
        return self.subscription

    async def create(self, **kwargs):
        self.created = SimpleNamespace(**kwargs)
        type(self).created = self.created
        type(self).subscription = self.created
        return self.created


class FakeCreditManager:
    add_calls: list[tuple[str, int, str]] = []

    async def add(self, user_id: str, amount: int, reason: str = "", session=None):
        self.add_calls.append((user_id, amount, reason))
        return SimpleNamespace(success=True, credits_remaining=27, message="ok")


def _user(**overrides):
    data = {
        "id": "user1",
        "name": "Afi",
        "country": "Togo",
        "activity": "Développeuse",
        "diploma": "Licence",
        "skills": ["Python", "SQL"],
        "credits": WELCOME_CREDITS,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_credit_constants_are_current() -> None:
    assert WELCOME_CREDITS == 20
    assert SUBSCRIPTION_BONUS == 7


def test_onboarding_capabilities_mentions_slash_commands() -> None:
    text = user_commands.onboarding_capabilities_text()

    assert "/statut" in text
    assert "/notifications" in text
    assert "CV adapté" in text


@pytest.mark.asyncio
async def test_build_status_text_includes_profile_credits_and_subscription() -> None:
    FakeSubscriptionRepository.subscription = None

    with patch.object(user_commands, "SubscriptionRepository", FakeSubscriptionRepository):
        text = await user_commands.build_status_text(SimpleNamespace(), _user())

    assert "Crédits restants : 20" in text
    assert "Notifications : Non activé" in text
    assert "Python, SQL" in text


@pytest.mark.asyncio
async def test_build_notifications_text_creates_subscription_and_awards_bonus() -> None:
    FakeSubscriptionRepository.subscription = None
    FakeSubscriptionRepository.created = None
    FakeCreditManager.add_calls = []

    with (
        patch.object(user_commands, "SubscriptionRepository", FakeSubscriptionRepository),
        patch("leRH.core.credits.CreditManager", FakeCreditManager),
    ):
        text = await user_commands.build_notifications_text(
            SimpleNamespace(),
            _user(),
            platform="whatsapp",
            activate=True,
        )

    assert FakeSubscriptionRepository.created is not None
    assert FakeSubscriptionRepository.created.notify_whatsapp is True
    assert FakeSubscriptionRepository.created.notify_telegram is False
    assert FakeCreditManager.add_calls == [("user1", 7, "subscription_bonus")]
    assert "Bonus ajouté : 7 crédits" in text
