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


async def get_user(db: AsyncSession, whatsapp_id: str) -> User | None:
    """Récupère un utilisateur WhatsApp s'il existe."""
    clean_id = _clean_jid(whatsapp_id)
    repo = UserRepository(db)
    return await repo.get_by_whatsapp(clean_id)


async def _get_local_jobs(db: AsyncSession) -> list:
    repo = JobRepository(db)
    return await repo.get_active()


async def process_conversation(
    db: AsyncSession,
    whatsapp_id: str,
    text: str,
    channel: str = "whatsapp",
) -> str:
    from leRH.db.repository import OnboardingRepository
    from leRH.utils.rate_limiter import check_rate_limit

    clean_id = _clean_jid(whatsapp_id)

    if not await check_rate_limit(whatsapp_id):
        return "Vous envoyez trop de messages. Veuillez ralentir."

    # 1. Vérifier si l'utilisateur existe déjà
    user = await get_user(db, whatsapp_id)
    if user:
        memory = ConversationMemory(db, user.id)
        # Si l'utilisateur est déjà prêt, on utilise l'assistant
        if user.conversation_state == "ready":
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
                platform="whatsapp",
                chat_id=clean_id,
                db_session=db,
            )
            # Commit avant l'appel LLM pour libérer le verrou SQLite
            await db.commit()
            reply = await assistant.interact_with_history(text, history)
            await memory.add_message("assistant", reply)
            return reply
        
        # Sinon, on continue l'onboarding (cas rare où un User existe mais n'est pas ready)
        state = user.conversation_state
    else:
        # 2. Gestion de l'onboarding via session temporaire
        onboarding_repo = OnboardingRepository(db)
        session = await onboarding_repo.get(clean_id, "whatsapp")
        
        if not session:
            # Premier contact : créer la session et envoyer Bienvenue
            await onboarding_repo.create(clean_id, "whatsapp")
            return WELCOME_INTRO

        state = session.state
        data = session.data or {}

    try:
        match state:
            case "new":
                # On vient de recevoir le premier message après le WELCOME_INTRO
                # On traite ce message comme le prénom (sauf si c'est une salutation)
                name_candidate = text.strip()
                if _looks_like_greeting(name_candidate):
                    return (
                        "Enchanté ! 😊 Pour commencer, pouvez-vous me donner votre *prénom* ?"
                    )
                
                if user:
                    user.name = name_candidate[:255]
                    user.conversation_state = "awaiting_country"
                else:
                    session.data = {**data, "name": name_candidate[:255]}
                    session.state = "awaiting_country"
                
                await db.flush()
                return COUNTRY_QUESTION.format(name=name_candidate)

            case "awaiting_country":
                country = text.strip()[:255]
                if user:
                    user.country = country
                    user.conversation_state = "awaiting_activity"
                else:
                    session.data = {**data, "country": country}
                    session.state = "awaiting_activity"
                
                await db.flush()
                return ACTIVITY_QUESTION

            case "awaiting_activity":
                activity = text.strip()[:255]
                if user:
                    user.activity = activity
                    user.conversation_state = "awaiting_skills"
                else:
                    session.data = {**data, "activity": activity}
                    session.state = "awaiting_skills"
                
                await db.flush()
                return SKILLS_QUESTION

            case "awaiting_skills":
                raw_skills = text.strip()
                skills_list = [s.strip()[:100] for s in raw_skills.split(",") if s.strip()][:20]
                if user:
                    user.skills = skills_list
                    user.conversation_state = "awaiting_diploma"
                else:
                    session.data = {**data, "skills": skills_list}
                    session.state = "awaiting_diploma"
                
                await db.flush()
                return DIPLOMA_QUESTION

            case "awaiting_diploma":
                diploma = text.strip()[:255]
                
                if user:
                    user.diploma = diploma
                    user.conversation_state = "ready"
                    user_name = user.name
                else:
                    # FIN DE L'ONBOARDING : Création de l'utilisateur réel
                    user_repo = UserRepository(db)
                    user = await user_repo.create(
                        whatsapp_id=clean_id,
                        name=data.get("name", ""),
                        country=data.get("country", "Togo"),
                        activity=data.get("activity"),
                        skills=data.get("skills"),
                        diploma=diploma,
                        conversation_state="ready",
                        credits=10
                    )
                    user_name = user.name
                    # Supprimer la session temporaire
                    await onboarding_repo.delete(clean_id, "whatsapp")
                
                await db.flush()
                ready_msg = READY_MESSAGE.format(name=user_name or "")
                
                # Initialiser la mémoire avec le message de bienvenue prêt
                memory = ConversationMemory(db, user.id)
                await memory.add_message("assistant", ready_msg)
                
                return ready_msg

            case _:
                # État inconnu : reset
                if user:
                    user.conversation_state = "new"
                else:
                    session.state = "new"
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
                user = extractor.enrich_user(user, {**result, **profile})
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

    clean_id = _clean_jid(payload.from_)
    user = await get_user(db, payload.from_)
    
    ap = AudioProcessor()
    transcription = ap.transcribe_base64(payload.audio_base64, payload.mimetype)
    if not transcription:
        return ReplyResponse(reply="Je n'ai pas compris le message audio. Pouvez-vous réessayer ?")

    if not user:
        # En onboarding
        reply = await process_conversation(db, payload.from_, transcription)
        return ReplyResponse(reply=reply)

    memory = ConversationMemory(db, user.id)
    await memory.add_message("user", f"[voice] {transcription}")

    if user.conversation_state != "ready":
        reply = await process_conversation(db, payload.from_, transcription)
    else:
        from leRH.services.translation import TranslationManager

        tl = TranslationManager()
        en_text = transcription
        with suppress(Exception):
            en_text = await tl.translate(transcription, "ewe_Latn", "eng_Latn")

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
            chat_id=clean_id,
            db_session=db,
        )
        # Commit avant l'appel LLM pour libérer le verrou SQLite
        await db.commit()
        reply_en = await assistant.interact_with_history(en_text, history)
        try:
            reply_ewe = await tl.translate(reply_en, "eng_Latn", "ewe_Latn")
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


class AckRequest(BaseModel):
    ids: list[str]


@router.get("/pending", response_model=list[PendingMessageResponse])
async def get_pending_messages(
    db: AsyncSession = Depends(get_db),
) -> list[PendingMessageResponse]:
    """Retourne les messages en attente SANS les marquer comme envoyés.

    Le bot doit appeler POST /pending/ack avec les IDs une fois l'envoi confirmé.
    """
    from sqlalchemy import select

    from leRH.db.models import PendingMessage

    result = await db.execute(
        select(PendingMessage)
        .where(PendingMessage.platform == "whatsapp", ~PendingMessage.sent)
        .order_by(PendingMessage.created_at)
        .limit(50)
    )
    msgs = result.scalars().all()
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


@router.post("/pending/ack")
async def ack_pending_messages(
    payload: AckRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Marque les messages comme envoyés après confirmation du bot WhatsApp.

    Le bot appelle cet endpoint avec la liste des IDs qu'il a réussi à envoyer.
    """
    from sqlalchemy import select

    from leRH.db.models import PendingMessage

    if not payload.ids:
        return {"acked": 0}

    result = await db.execute(select(PendingMessage).where(PendingMessage.id.in_(payload.ids)))
    msgs = result.scalars().all()
    for msg in msgs:
        msg.sent = True
    await db.commit()
    logger.info("Acked %d pending messages: %s", len(msgs), payload.ids)
    return {"acked": len(msgs)}
