from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.db.models import Message

logger = logging.getLogger(__name__)

MAX_HISTORY = 10


class ConversationMemory:
    def __init__(self, session: AsyncSession, user_id: str) -> None:
        self.session = session
        self.user_id = user_id

    async def add_message(self, role: str, content: str, channel: str = "whatsapp") -> Message:
        msg = Message(user_id=self.user_id, role=role, content=content, channel=channel)
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def get_history(self, limit: int = MAX_HISTORY) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.user_id == self.user_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def build_context(self, max_turns: int = MAX_HISTORY) -> list[dict]:
        history = await self.get_history(max_turns)
        context = []
        for msg in history:
            context.append({"role": msg.role, "content": msg.content})
        return context
