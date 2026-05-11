from __future__ import annotations

import logging

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from leRH.adapters.telegram.handlers.conversation import COUNTRIES
from leRH.core.assistants.manager import Assistant
from leRH.db.base import async_session_factory
from leRH.db.repository import JobRepository, MessageRepository, UserRepository

logger = logging.getLogger(__name__)


async def _get_user(tg_user) -> object | None:
    async with async_session_factory() as session:
        repo = UserRepository(session)
        return await repo.get_by_telegram(tg_user.id)


async def _update_conversation_state(telegram_id: int, state: str, **fields) -> None:
    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram(telegram_id)
        if user:
            for key, value in fields.items():
                setattr(user, key, value)
            user.conversation_state = state
            await session.commit()


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.message.from_user
    text = update.message.text
    logger.info("Text from %s: %.60s", tg_user.first_name, text)

    user = await _get_user(tg_user)

    if not user or user.conversation_state == "new":
        async with async_session_factory() as session:
            repo = UserRepository(session)
            user = user or await repo.create(telegram_id=tg_user.id, name=tg_user.first_name or "")
            user.conversation_state = "awaiting_country"
            await session.commit()
        await update.message.reply_text(
            "👋 Bonjour ! Je suis Koffi, votre assistant emploi.\nDans quel pays habitez-vous ?",
            reply_markup=ReplyKeyboardMarkup(
                COUNTRIES, one_time_keyboard=True, input_field_placeholder="Togo"
            ),
        )
        return

    if user.conversation_state == "awaiting_country":
        await _update_conversation_state(tg_user.id, "awaiting_activity", country=text)
        await update.message.reply_text(
            "Merci ! Quelle est votre activité ou profession ?\n(ou envoyez /skip pour passer)"
        )
        return

    if user.conversation_state == "awaiting_activity":
        await _update_conversation_state(tg_user.id, "ready", activity=text)
        await update.message.reply_text(
            "Parfait ! Envoyez-moi votre CV (PDF) pour que je l'analyse.\n"
            "Vous pouvez aussi m'envoyer un message vocal ou texte pour discuter."
        )
        return

    async with async_session_factory() as session:
        job_repo = JobRepository(session)
        local_jobs = await job_repo.get_active()
        msg_repo = MessageRepository(session)
        history_msgs = await msg_repo.get_recent(user.id, limit=10)
        history = [{"role": m.role, "content": m.content} for m in history_msgs]

    assistant = Assistant(
        name=user.name or tg_user.first_name,
        country=user.country or "Togo",
        activity=user.activity or "unknown",
        skills=user.skills,
        diploma=user.diploma,
        experience=user.experience,
        languages=user.languages,
        local_jobs=local_jobs,
        user_id=user.id,
        credits=user.credits or 0,
        platform="telegram",
        chat_id=update.effective_chat.id,
    )
    reply = await assistant.interact_with_history(text, history)

    async with async_session_factory() as session:
        msg_repo = MessageRepository(session)
        await msg_repo.create(user_id=user.id, role="user", content=text, channel="telegram")
        await msg_repo.create(user_id=user.id, role="assistant", content=reply, channel="telegram")
        await session.commit()

    await update.message.reply_text(reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.message.from_user
    chat_id = update.effective_chat.id
    logger.info("Voice from %s", tg_user.first_name)

    file_id = update.message.voice.file_id
    voice_file = await context.bot.get_file(file_id)
    file_url = voice_file.file_path

    audio_processor = context.bot_data.get("audio_processor")
    if audio_processor is None:
        await context.bot.send_message(chat_id=chat_id, text="Erreur: service audio non disponible")
        return

    transcription = audio_processor.transcribe(file_url)
    transcription = transcription.replace(
        "<|startoftranscript|><|en|><|transcribe|><|notimestamps|>", ""
    ).strip()

    await context.bot.send_message(chat_id=chat_id, text=f"📝 Transcription: {transcription}")

    translation_manager = context.bot_data.get("translation_manager")
    tts_manager = context.bot_data.get("tts_manager")

    if translation_manager:
        en_text = translation_manager.translate(transcription, "ewe_Latn", "eng_Latn")
    else:
        en_text = transcription

    user = await _get_user(tg_user)

    async with async_session_factory() as session:
        repo = JobRepository(session)
        local_jobs = await repo.get_active()

    assistant = Assistant(
        name=tg_user.first_name,
        country=user.country if user else "Togo",
        activity=(user.activity if user else None) or "unknown",
        skills=user.skills if user else None,
        diploma=user.diploma if user else None,
        experience=user.experience if user else None,
        languages=user.languages if user else None,
        local_jobs=local_jobs,
        user_id=user.id if user else None,
        credits=user.credits if user else 0,
        platform="telegram",
        chat_id=chat_id,
    )
    reply_en = await assistant.interact(en_text)

    if translation_manager:
        reply_ewe = translation_manager.translate(reply_en, "eng_Latn", "ewe_Latn")
        await context.bot.send_message(chat_id=chat_id, text=f"{reply_ewe}\n\n---\n\n{reply_en}")
    else:
        await context.bot.send_message(chat_id=chat_id, text=reply_en)

    if tts_manager and translation_manager:
        tts_text = translation_manager.translate(reply_en, "eng_Latn", "ewe_Latn")
        audio_path = tts_manager.generate_audio(tts_text)
        with open(audio_path, "rb") as f:
            await context.bot.send_voice(chat_id=chat_id, voice=f)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Audio message from %s", update.message.from_user.first_name)
    await update.message.reply_text("Je ne traite que les messages vocaux pour l'instant.")
