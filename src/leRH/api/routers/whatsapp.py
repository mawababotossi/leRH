from __future__ import annotations

import io
import logging
from contextlib import suppress

import PyPDF2
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.core.assistants.manager import Assistant
from leRH.core.conversation import ConversationMemory
from leRH.db.base import get_db
from leRH.db.repository import CVRepository, JobRepository, UserRepository
from leRH.utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def _clean_jid(raw: str) -> str:
    """Extrait le numéro de téléphone d'un JID WhatsApp."""
    return raw.split("@")[0].strip()


WELCOME_INTRO = (
    "Bienvenue sur leRH ! 🎯 Je suis Koffi, votre assistant emploi.\n\nQuel est votre prénom ?"
)

COUNTRY_QUESTION = "Merci ! Dans quel pays habitez-vous ?"
ACTIVITY_QUESTION = "Parfait ! Quelle est votre profession ou activité ?"
READY_MESSAGE = (
    "Super ! Votre profil est complet. Vous pouvez maintenant :\n"
    "• M'envoyer un message pour discuter\n"
    "• M'envoyer un CV (PDF) pour analyse\n\n"
    "Comment puis-je vous aider ?"
)


class StartRequest(BaseModel):
    from_: str
    text: str
    model_config = {"alias_generator": lambda s: s.rstrip("_"), "populate_by_name": True}


class MessageRequest(BaseModel):
    from_: str
    text: str
    model_config = {"alias_generator": lambda s: s.rstrip("_"), "populate_by_name": True}


class VoiceRequest(BaseModel):
    from_: str
    audio_base64: str
    mimetype: str = "audio/ogg"


class DocumentRequest(BaseModel):
    from_: str
    document_base64: str
    mimetype: str = "application/pdf"
    filename: str = "document.pdf"
    model_config = {"alias_generator": lambda s: s.rstrip("_"), "populate_by_name": True}


class ReplyResponse(BaseModel):
    reply: str


async def get_or_create_user(db: AsyncSession, whatsapp_id: str) -> tuple:
    clean_id = _clean_jid(whatsapp_id)
    repo = UserRepository(db)
    user = await repo.get_by_whatsapp(clean_id)
    created = False
    if not user:
        user = await repo.create(whatsapp_id=clean_id, name="")
        created = True
        logger.info("New WhatsApp user: %s (%s)", user.id, clean_id)
    return user, created


async def _get_local_jobs(db: AsyncSession) -> list:
    repo = JobRepository(db)
    return await repo.get_active()


async def process_conversation(
    db: AsyncSession,
    whatsapp_id: str,
    text: str,
    channel: str = "whatsapp",
) -> str:
    user, _ = await get_or_create_user(db, whatsapp_id)
    memory = ConversationMemory(db, user.id)
    state = user.conversation_state

    ratelimit = get_rate_limiter()
    if not ratelimit.check(whatsapp_id):
        return "Vous envoyez trop de messages. Veuillez ralentir."

    try:
        match state:
            case "new":
                await memory.add_message("user", text)
                user.name = text.strip()
                user.conversation_state = "awaiting_country"
                await db.flush()
                await memory.add_message("assistant", COUNTRY_QUESTION)
                return COUNTRY_QUESTION

            case "awaiting_country":
                user.country = text.strip()
                user.conversation_state = "awaiting_activity"
                await db.flush()
                await memory.add_message("assistant", ACTIVITY_QUESTION)
                return ACTIVITY_QUESTION

            case "awaiting_activity":
                user.activity = text.strip()
                user.conversation_state = "ready"
                await db.flush()
                await memory.add_message("assistant", READY_MESSAGE)
                return READY_MESSAGE

            case "ready":
                await memory.add_message("user", text)
                history = await memory.build_context()
                local_jobs = await _get_local_jobs(db)
                assistant = Assistant(
                    name=user.name or "User",
                    country=user.country,
                    activity=user.activity or "job seeker",
                    skills=user.skills,
                    diploma=user.diploma,
                    experience=user.experience,
                    languages=user.languages,
                    local_jobs=local_jobs,
                    user_id=user.id,
                    credits=user.credits or 0,
                    platform="whatsapp",
                    chat_id=_clean_jid(whatsapp_id),
                    db_session=db,
                )
                reply = await assistant.interact_with_history(text, history)
                await memory.add_message("assistant", reply)
                return reply

            case _:
                user.conversation_state = "new"
                await db.flush()
                return WELCOME_INTRO

    except Exception:
        logger.exception("Conversation error for %s", whatsapp_id)
        return "Désolé, une erreur s'est produite. Veuillez réessayer dans quelques instants."


@router.post("/document", response_model=ReplyResponse)
async def whatsapp_document(
    payload: DocumentRequest,
    db: AsyncSession = Depends(get_db),
) -> ReplyResponse:
    clean_id = _clean_jid(payload.from_)
    repo = UserRepository(db)
    user = await repo.get_by_whatsapp(clean_id)
    if not user:
        return ReplyResponse(reply="Veuillez d'abord envoyer /start pour créer votre profil.")

    if user.conversation_state != "ready":
        return ReplyResponse(
            reply="Veuillez d'abord compléter votre inscription (nom, pays, activité)."
        )

    try:
        import base64

        pdf_bytes = base64.b64decode(payload.document_base64)
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        cv_text = ""
        for page in reader.pages:
            if text := page.extract_text():
                cv_text += text + "\n"
        cv_text = cv_text.strip()

        if not cv_text:
            return ReplyResponse(reply="Impossible d'extraire le texte de ce PDF.")

        from leRH.core.profiles.extractor import ProfileExtractor

        extractor = ProfileExtractor()
        result = extractor.analyze_cv(cv_text)

        if result:
            analysis = result.get("analysis", "")
            profile = result.get("profile", {})
            if profile:
                user = extractor.enrich_user(user, profile)
            cv_analysis = result
        else:
            analysis = "Analyse non disponible."
            cv_analysis = {"analysis": "Extraction failed"}

        cv_repo = CVRepository(db)
        await cv_repo.create(
            user_id=user.id,
            original_name=payload.filename,
            extracted_text=cv_text[:5000],
            analysis=cv_analysis,
        )

        return ReplyResponse(reply=f"Analyse du CV:\n\n{analysis}")
    except Exception as exc:
        logger.exception("WhatsApp document processing failed")
        return ReplyResponse(reply=f"Erreur lors de l'analyse du document: {exc}")


@router.post("/start", response_model=ReplyResponse)
async def whatsapp_start(
    payload: StartRequest,
    db: AsyncSession = Depends(get_db),
) -> ReplyResponse:
    return ReplyResponse(reply=await process_conversation(db, payload.from_, payload.text))


@router.post("/message", response_model=ReplyResponse)
async def whatsapp_message(
    payload: MessageRequest,
    db: AsyncSession = Depends(get_db),
) -> ReplyResponse:
    return ReplyResponse(reply=await process_conversation(db, payload.from_, payload.text))


@router.post("/voice", response_model=ReplyResponse)
async def whatsapp_voice(
    payload: VoiceRequest,
    db: AsyncSession = Depends(get_db),
) -> ReplyResponse:
    from leRH.services.audio_processor import AudioProcessor

    user, _ = await get_or_create_user(db, payload.from_)
    memory = ConversationMemory(db, user.id)

    ap = AudioProcessor()
    transcription = ap.transcribe_base64(payload.audio_base64, payload.mimetype)
    if not transcription:
        return ReplyResponse(reply="Je n'ai pas compris le message audio. Pouvez-vous réessayer ?")

    await memory.add_message("user", f"[voice] {transcription}")

    if user.conversation_state != "ready":
        reply = await process_conversation(db, payload.from_, transcription)
    else:
        from leRH.services.translation import TranslationManager

        tl = TranslationManager()
        en_text = transcription
        with suppress(Exception):
            en_text = tl.translate(transcription, "ewe_Latn", "eng_Latn")

        history = await memory.build_context()
        local_jobs = await _get_local_jobs(db)
        assistant = Assistant(
            name=user.name or "User",
            country=user.country or "Togo",
            activity=user.activity or "job seeker",
            skills=user.skills,
            diploma=user.diploma,
            experience=user.experience,
            languages=user.languages,
            local_jobs=local_jobs,
            user_id=user.id,
            credits=user.credits or 0,
            platform="whatsapp",
            chat_id=_clean_jid(payload.from_),
            db_session=db,
        )
        reply_en = await assistant.interact_with_history(en_text, history)
        try:
            reply_ewe = tl.translate(reply_en, "eng_Latn", "ewe_Latn")
            reply = f"{reply_ewe}\n\n---\n\n{reply_en}"
        except Exception:
            reply = reply_en

        await memory.add_message("assistant", reply)

    return ReplyResponse(reply=reply)


class PendingMessageResponse(BaseModel):
    id: str
    message_type: str
    text: str | None = None
    document_path: str | None = None
    platform_chat_id: str | None = None


@router.get("/pending", response_model=list[PendingMessageResponse])
async def get_pending_messages(
    db: AsyncSession = Depends(get_db),
) -> list[PendingMessageResponse]:
    from sqlalchemy import select

    from leRH.db.models import PendingMessage

    result = await db.execute(
        select(PendingMessage)
        .where(PendingMessage.platform == "whatsapp", ~PendingMessage.sent)
        .order_by(PendingMessage.created_at)
        .limit(50)
    )
    msgs = result.scalars().all()
    for msg in msgs:
        msg.sent = True
    await db.commit()
    return [
        PendingMessageResponse(
            id=msg.id,
            message_type=msg.message_type,
            text=msg.text,
            document_path=msg.document_path,
            platform_chat_id=msg.platform_chat_id,
        )
        for msg in msgs
    ]
