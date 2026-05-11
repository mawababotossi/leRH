from __future__ import annotations

import logging

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from leRH.config import settings
from leRH.db.base import async_session_factory
from leRH.db.repository import UserRepository

logger = logging.getLogger(__name__)

COUNTRIES = [["Togo", "Bénin", "Ghana"], ["Côte d'Ivoire", "Burkina Faso", "Sénégal"]]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user
    logger.info("User %s (%s) started", tg_user.first_name, tg_user.id)

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if not user:
            user = await repo.create(telegram_id=tg_user.id, name=tg_user.first_name or "")
            logger.info("Created DB user %s for Telegram %s", user.id, tg_user.id)
        user.conversation_state = "awaiting_country"
        await session.commit()

    await update.message.reply_text(
        "👋 Bonjour ! Je suis Koffi, votre assistant emploi.\nDans quel pays habitez-vous ?",
        reply_markup=ReplyKeyboardMarkup(
            COUNTRIES, one_time_keyboard=True, input_field_placeholder="Togo"
        ),
    )
    return settings.COUNTRY


async def country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user
    country_text = update.message.text

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if user:
            user.country = country_text
            user.conversation_state = "awaiting_activity"
            await session.commit()
            logger.info("User %s country set to %s", tg_user.id, country_text)

    await update.message.reply_text(
        "Merci ! Quelle est votre activité ou profession ?\n(ou envoyez /skip pour passer)"
    )
    return settings.ACTIVITY


async def activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if user:
            user.activity = update.message.text
            user.conversation_state = "ready"
            await session.commit()
            logger.info("User %s activity set to %s", tg_user.id, user.activity)

    await update.message.reply_text(
        "Parfait ! Envoyez-moi votre CV (PDF) pour que je l'analyse.\n"
        "Vous pouvez aussi m'envoyer un message vocal ou texte pour discuter."
    )
    return ConversationHandler.END


async def skip_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("User %s skipped activity", update.message.from_user.first_name)

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(update.message.from_user.id)
        if user:
            user.conversation_state = "ready"
            await session.commit()

    await update.message.reply_text("Pas de problème. Je reste disponible pour vous aider.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("User %s cancelled", update.message.from_user.first_name)

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(update.message.from_user.id)
        if user:
            user.conversation_state = "new"
            await session.commit()

    await update.message.reply_text("À bientôt !")
    return ConversationHandler.END
