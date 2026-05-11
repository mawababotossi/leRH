from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Bot as TelegramBot

logger = logging.getLogger(__name__)

_telegram_bot: TelegramBot | None = None


def register_telegram_bot(bot: TelegramBot) -> None:
    global _telegram_bot
    _telegram_bot = bot
    logger.info("Telegram bot registered for background notifications")


def get_telegram_bot() -> TelegramBot | None:
    return _telegram_bot
