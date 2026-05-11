from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from leRH.db.base import DBLock, async_session_factory
from leRH.db.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CV_COST = 5
COVER_LETTER_COST = 3
NOTIFICATION_COST = 1
WELCOME_CREDITS = 10
SUBSCRIPTION_BONUS = 50


@dataclass
class CreditResult:
    success: bool
    credits_remaining: int
    message: str


class CreditManager:
    async def _get_user(self, user_id: str, session: AsyncSession | None = None) -> User | None:
        if session is not None:
            return await session.get(User, user_id)
        async with async_session_factory() as s:
            return await s.get(User, user_id)

    async def check_credits(
        self, user_id: str, amount: int = 1, session: AsyncSession | None = None
    ) -> bool:
        user = await self._get_user(user_id, session)
        if not user:
            return False
        return (user.credits or 0) >= amount

    async def get_credits(self, user_id: str, session: AsyncSession | None = None) -> int:
        user = await self._get_user(user_id, session)
        return user.credits if user else 0

    async def _deduct(
        self, session: AsyncSession, user_id: str, amount: int, reason: str = ""
    ) -> CreditResult:
        user = await session.get(User, user_id)
        if not user:
            return CreditResult(False, 0, "Utilisateur non trouvé")

        current = user.credits or 0
        if current < amount:
            return CreditResult(
                False,
                current,
                f"Crédits insuffisants ({current}/{amount}). "
                f"Souscrivez à une offre pour en obtenir plus.",
            )

        user.credits = current - amount
        await session.flush()
        await session.commit()
        logger.info(
            "Credits deducted: user=%s amount=%d reason=%s remaining=%d",
            user_id,
            amount,
            reason,
            user.credits,
        )
        return CreditResult(True, user.credits, f"Il vous reste {user.credits} crédits.")

    async def deduct(
        self, user_id: str, amount: int, reason: str = "", session: AsyncSession | None = None
    ) -> CreditResult:
        if session is not None:
            return await self._deduct(session, user_id, amount, reason)
        async with DBLock(), async_session_factory() as s:
            return await self._deduct(s, user_id, amount, reason)

    async def _add(
        self, session: AsyncSession, user_id: str, amount: int, reason: str = ""
    ) -> CreditResult:
        user = await session.get(User, user_id)
        if not user:
            return CreditResult(False, 0, "Utilisateur non trouvé")

        user.credits = (user.credits or 0) + amount
        await session.flush()
        await session.commit()
        logger.info(
            "Credits added: user=%s amount=%d reason=%s total=%d",
            user_id,
            amount,
            reason,
            user.credits,
        )
        return CreditResult(True, user.credits, f"Vous avez {user.credits} crédits.")

    async def add(
        self, user_id: str, amount: int, reason: str = "", session: AsyncSession | None = None
    ) -> CreditResult:
        if session is not None:
            return await self._add(session, user_id, amount, reason)
        async with DBLock(), async_session_factory() as s:
            return await self._add(s, user_id, amount, reason)
