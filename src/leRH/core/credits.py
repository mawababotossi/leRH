from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from leRH.db.base import async_session_factory
from leRH.db.models import CreditTransaction, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CV_COST = 5
COVER_LETTER_COST = 3
NOTIFICATION_COST = 1
WELCOME_CREDITS = 20
SUBSCRIPTION_BONUS = 7


@dataclass
class CreditResult:
    success: bool
    credits_remaining: int
    message: str


class CreditManager:
    @staticmethod
    def _validate_amount(amount: int) -> None:
        if amount <= 0:
            raise ValueError("Credit amount must be positive")

    async def _record_transaction(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        amount: int,
        balance_after: int,
        reason: str,
    ) -> None:
        session.add(
            CreditTransaction(
                user_id=user_id,
                amount=amount,
                balance_after=balance_after,
                reason=reason[:255],
            )
        )
        await session.flush()

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
        self,
        session: AsyncSession,
        user_id: str,
        amount: int,
        reason: str = "",
        *,
        owned: bool = False,
    ) -> CreditResult:
        self._validate_amount(amount)

        result = await session.execute(
            update(User)
            .where(User.id == user_id, User.credits >= amount)
            .values(credits=User.credits - amount)
            .execution_options(synchronize_session="fetch")
        )
        if result.rowcount == 0:
            current_result = await session.execute(select(User.credits).where(User.id == user_id))
            current = current_result.scalar_one_or_none()
            if current is None:
                return CreditResult(False, 0, "Utilisateur non trouvé")
            return CreditResult(
                False,
                current,
                f"Crédits insuffisants ({current}/{amount}). "
                f"Souscrivez à une offre pour en obtenir plus.",
            )

        balance_result = await session.execute(select(User.credits).where(User.id == user_id))
        balance = int(balance_result.scalar_one())
        await self._record_transaction(
            session,
            user_id=user_id,
            amount=-amount,
            balance_after=balance,
            reason=reason,
        )
        await session.flush()
        if owned:
            await session.commit()
        logger.info(
            "Credits deducted: user=%s amount=%d reason=%s remaining=%d",
            user_id,
            amount,
            reason,
            balance,
        )
        return CreditResult(True, balance, f"Il vous reste {balance} crédits.")

    async def deduct(
        self, user_id: str, amount: int, reason: str = "", session: AsyncSession | None = None
    ) -> CreditResult:
        if session is not None:
            return await self._deduct(session, user_id, amount, reason, owned=False)

        async with async_session_factory() as s:
            return await self._deduct(s, user_id, amount, reason, owned=True)

    async def _add(
        self,
        session: AsyncSession,
        user_id: str,
        amount: int,
        reason: str = "",
        *,
        owned: bool = False,
    ) -> CreditResult:
        self._validate_amount(amount)

        result = await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(credits=User.credits + amount)
            .execution_options(synchronize_session="fetch")
        )
        if result.rowcount == 0:
            return CreditResult(False, 0, "Utilisateur non trouvé")

        balance_result = await session.execute(select(User.credits).where(User.id == user_id))
        balance = int(balance_result.scalar_one())
        await self._record_transaction(
            session,
            user_id=user_id,
            amount=amount,
            balance_after=balance,
            reason=reason,
        )
        await session.flush()
        if owned:
            await session.commit()
        logger.info(
            "Credits added: user=%s amount=%d reason=%s total=%d",
            user_id,
            amount,
            reason,
            balance,
        )
        return CreditResult(True, balance, f"Vous avez {balance} crédits.")

    async def add(
        self, user_id: str, amount: int, reason: str = "", session: AsyncSession | None = None
    ) -> CreditResult:
        if session is not None:
            return await self._add(session, user_id, amount, reason, owned=False)
        async with async_session_factory() as s:
            return await self._add(s, user_id, amount, reason, owned=True)
