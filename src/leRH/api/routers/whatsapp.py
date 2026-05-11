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
    "Bienvenue sur leRH ! 🎯 Je suis Koffi, votre assistant emploi personnalisé.\n\n"
    "Je vais vous aider à trouver des offres d'emploi et à générer des CV et lettres "
    "de motivation adaptés à votre profil.\n\n"
    "Pour commencer, quel est votre *prénom* ?"
)

# Salutations courantes à ne pas interpréter comme un prénom
_GREETINGS = {
    "bonjour",
    "bonsoir",
    "salut",
    "hello",
    "hi",
    "hey",
    "allo",
    "allô",
    "coucou",
    "yo",
    "bjr",
    "bsr",
    "slt",
    "salu",
    "wesh",
    "hola",
}


def _looks_like_greeting(text: str) -> bool:
    """Retourne True si le texte ressemble à une salutation plutôt qu'un prénom."""
    normalized = text.strip().lower().rstrip("!?.")
    if normalized in _GREETINGS:
        return True
    # Un prénom ne devrait pas dépasser 50 caractères ni contenir plusieurs mots
    # de type salutation
    words = normalized.split()
    if len(text) > 50:
        return True
    return len(words) > 1 and all(w in _GREETINGS for w in words)


COUNTRY_QUESTION = (
    "Merci *{name}* ! Dans quel pays habitez-vous ?\n(ex: Togo, Bénin, Côte d'Ivoire)"
)
ACTIVITY_QUESTION = "Parfait ! Quelle est votre profession ou domaine d'activité ?"
SKILLS_QUESTION = (
    "Très bien. Quelles sont vos 3 compétences principales ?\n"
    "(ex: Python, Vente, Comptabilité, Gestion d'équipe)"
)
DIPLOMA_QUESTION = "D'accord. Quel est votre dernier diplôme ou niveau d'études ?"
READY_MESSAGE = (
    "Super *{name}*, votre profil de base est prêt ! 🎉\n\n"
    "Vous pouvez maintenant :\n"
    "• Envoyer votre *CV en PDF* pour que je l'analyse et personnalise vos documents\n"
    "• Me poser des questions sur les offres d'emploi\n"
    "• Demander la génération d'un CV ou d'une lettre de motivation\n\n"
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
    """Récupère ou crée un utilisateur WhatsApp.

    Un nouvel utilisateur est créé avec l'état 'new' (non 'awaiting_name') pour
    que le premier message entrant déclenche l'envoi de WELCOME_INTRO sans
    consommer le texte comme prénom.
    """
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
                # Premier contact : envoyer le message de bienvenue.
                # Ne pas sauvegarder le texte reçu comme prénom — c'est
                # probablement une salutation ("Bonjour", "Salut"...).
                user.conversation_state = "awaiting_name"
                await db.flush()
                await memory.add_message("assistant", WELCOME_INTRO)
                return WELCOME_INTRO

            case "awaiting_name":
                # L'utilisateur répond au "Quel est votre prénom ?"
                name_candidate = text.strip()
                if _looks_like_greeting(name_candidate):
                    retry = (
                        "Je n'ai pas bien compris votre prénom 😊\n"
                        "Pouvez-vous me donner juste votre prénom ? "
                        "(ex: Kofi, Amina, Jean-Pierre)"
                    )
                    await memory.add_message("assistant", retry)
                    return retry
                user.name = name_candidate
                user.conversation_state = "awaiting_country"
                await db.flush()
                country_q = COUNTRY_QUESTION.format(name=name_candidate)
                await memory.add_message("assistant", country_q)
                return country_q

            case "awaiting_country":
                user.country = text.strip()
                user.conversation_state = "awaiting_activity"
                await db.flush()
                await memory.add_message("assistant", ACTIVITY_QUESTION)
                return ACTIVITY_QUESTION

            case "awaiting_activity":
                user.activity = text.strip()
                user.conversation_state = "awaiting_skills"
                await db.flush()
                await memory.add_message("assistant", SKILLS_QUESTION)
                return SKILLS_QUESTION

            case "awaiting_skills":
                # On parse les compétences séparées par des virgules
                raw_skills = text.strip()
                skills_list = [s.strip() for s in raw_skills.split(",") if s.strip()]
                user.skills = skills_list
                user.conversation_state = "awaiting_diploma"
                await db.flush()
                await memory.add_message("assistant", DIPLOMA_QUESTION)
                return DIPLOMA_QUESTION

            case "awaiting_diploma":
                user.diploma = text.strip()
                user.conversation_state = "ready"
                await db.flush()
                ready_msg = READY_MESSAGE.format(name=user.name or "")
                await memory.add_message("assistant", ready_msg)
                return ready_msg

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
                # État inconnu ou corrompu : repartir à zéro proprement.
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
