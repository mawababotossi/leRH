from __future__ import annotations

import logging

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from leRH.config import settings
from leRH.core.user_commands import (
    build_notifications_text,
    build_status_text,
    onboarding_capabilities_text,
)
from leRH.db.base import async_session_factory
from leRH.db.repository import UserRepository

logger = logging.getLogger(__name__)

COUNTRIES = [["Togo", "Bénin", "Ghana"], ["Côte d'Ivoire", "Burkina Faso", "Sénégal"]]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user
    first_name = tg_user.first_name or ""
    logger.info("User %s (%s) started", first_name, tg_user.id)

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if not user:
            # Telegram fournit le vrai prénom via l'API — pas besoin de le demander.
            user = await repo.create(telegram_id=tg_user.id, name=first_name)
            logger.info("Created DB user %s for Telegram %s", user.id, tg_user.id)
        else:
            # Mise à jour du prénom Telegram en cas de changement
            if first_name and user.name != first_name:
                user.name = first_name
        user.conversation_state = "awaiting_country"
        await session.commit()

    await update.message.reply_text(
        f"👋 Bonjour *{first_name}* ! Je suis Koffi, votre assistant emploi.\n"
        f"Dans quel pays habitez-vous ?",
        parse_mode="Markdown",
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
            user.country = country_text[:255] if country_text else None
            user.conversation_state = "awaiting_activity"
            await session.commit()
            logger.info("User %s country set to %s", tg_user.id, country_text)

    await update.message.reply_text(
        "Merci ! Quelle est votre activité ou profession ?\n(ou envoyez /skip pour passer)"
    )
    return settings.ACTIVITY


async def activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user
    text = update.message.text

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if user:
            user.activity = text[:255] if text else None
            user.conversation_state = "awaiting_skills"
            await session.commit()
            logger.info("User %s activity set to %s", tg_user.id, text)

    await update.message.reply_text(
        "Super ! Quelles sont vos 3 compétences principales ?\n"
        "(Séparez-les par des virgules, ex: Python, Marketing, Gestion de projet)\n"
        "Envoyez /skip pour passer."
    )
    return settings.SKILLS


async def skip_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user
    logger.info("User %s skipped activity", tg_user.id)

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if user:
            user.conversation_state = "awaiting_skills"
            await session.commit()

    await update.message.reply_text(
        "Pas de souci. Quelles sont vos compétences principales ?\nEnvoyez /skip pour passer."
    )
    return settings.SKILLS


async def skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user
    text = update.message.text or ""
    skills_list = [s.strip()[:100] for s in text.split(",") if s.strip()][:20]

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if user:
            user.skills = skills_list
            user.conversation_state = "awaiting_diploma"
            await session.commit()
            logger.info("User %s skills set to %s", tg_user.id, skills_list)

    await update.message.reply_text(
        "Bien reçu. Quel est votre dernier diplôme ou niveau d'études ?\n"
        "Envoyez /skip pour terminer."
    )
    return settings.DIPLOMA


async def skip_skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user
    logger.info("User %s skipped skills", tg_user.id)

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if user:
            user.conversation_state = "awaiting_diploma"
            await session.commit()

    await update.message.reply_text(
        "D'accord. Quel est votre dernier diplôme ou niveau d'études ?\n"
        "Envoyez /skip pour terminer."
    )
    return settings.DIPLOMA


async def diploma(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user
    text = update.message.text
    first_name = tg_user.first_name or ""

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if user:
            user.diploma = text[:255] if text else None
            user.conversation_state = "ready"
            await session.commit()
            logger.info("User %s diploma set to %s", tg_user.id, text)

    await update.message.reply_text(
        f"Parfait *{first_name}* ! Votre profil est maintenant complet. 🎉\n\n"
        f"{onboarding_capabilities_text()}",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def skip_diploma(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.message.from_user
    first_name = tg_user.first_name or ""
    logger.info("User %s skipped diploma", tg_user.id)

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if user:
            user.conversation_state = "ready"
            await session.commit()

    await update.message.reply_text(
        f"C'est noté *{first_name}* !\n\n{onboarding_capabilities_text()}",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le profil actuel de l'utilisateur Telegram."""
    tg_user = update.message.from_user

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)

    if not user:
        await update.message.reply_text(
            "Vous n'avez pas encore de profil. Tapez /start pour créer votre compte."
        )
        return

    skills_str = ""
    if user.skills:
        skills_list = user.skills if isinstance(user.skills, list) else []
        skills_str = ", ".join(skills_list[:8]) if skills_list else str(user.skills)

    lines = [
        "*📄 Votre profil*",
        f"👤 Nom : {user.name or '—'}",
        f"🌍 Pays : {user.country or '—'}",
        f"💼 Activité : {user.activity or '—'}",
        f"🎓 Diplôme : {user.diploma or '—'}",
        f"📊 Compétences : {skills_str or '—'}",
        f"💰 Crédits : {user.credits or 0}",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le statut complet du compte Telegram."""
    tg_user = update.message.from_user

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if not user:
            await update.message.reply_text(
                "Vous n'avez pas encore de profil. Tapez /start pour créer votre compte."
            )
            return
        text = await build_status_text(session, user)

    await update.message.reply_text(text)


async def manage_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Active ou affiche les notifications emploi pour Telegram."""
    tg_user = update.message.from_user

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(tg_user.id)
        if not user:
            await update.message.reply_text(
                "Vous n'avez pas encore de profil. Tapez /start pour créer votre compte."
            )
            return
        text = await build_notifications_text(session, user, platform="telegram", activate=True)
        await session.commit()

    await update.message.reply_text(text)


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
