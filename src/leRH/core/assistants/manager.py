from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from openai import APIError, APITimeoutError, OpenAI

from leRH.config import settings
from leRH.core.assistants.persona import BEHAVIOR_INSTRUCTIONS, SYSTEM_PROMPT
from leRH.core.batch.document_tasks import generate_document_background
from leRH.core.credits import (
    COVER_LETTER_COST,
    CV_COST,
    SUBSCRIPTION_BONUS,
    CreditManager,
)
from leRH.core.tools.job_search import search_jobs_online
from leRH.db.base import DBLock, async_session_factory
from leRH.db.models import Job
from leRH.db.repository import SubscriptionRepository, UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_INSTRUCTIONS = BEHAVIOR_INSTRUCTIONS

MAX_TOOL_TURNS = 4


class Assistant:
    def __init__(
        self,
        *,
        name: str = "Koffi",
        country: str = settings.country,
        activity: str = settings.activity,
        instructions: list[str] | None = None,
        skills: list | None = None,
        diploma: str | None = None,
        experience: str | None = None,
        languages: list | None = None,
        search_enabled: bool = True,
        local_jobs: list[Job] | None = None,
        user_id: str | None = None,
        credits: int = 0,
        platform: str | None = None,
        chat_id: str | int | None = None,
        db_session: AsyncSession | None = None,
    ) -> None:
        self.name = name
        self.country = country
        self.activity = activity
        self.skills = skills
        self.diploma = diploma
        self.experience = experience
        self.languages = languages
        self.instructions = instructions or list(DEFAULT_INSTRUCTIONS)
        self.search_enabled = search_enabled
        self.local_jobs = local_jobs or []
        self.user_id = user_id
        self.credits = credits
        self.platform = platform
        self.chat_id = chat_id
        self._db_session = db_session

        self._client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout,
        )

    def _system_message(self) -> dict:
        parts = [SYSTEM_PROMPT]
        profile = (
            f"L'utilisateur s'appelle {self.name}. "
            f"Il habite {self.country} et travaille comme {self.activity}."
        )
        if self.skills:
            profile += f" Compétences : {', '.join(self.skills)}."
        if self.diploma:
            profile += f" Diplôme : {self.diploma}."
        if self.experience:
            profile += f" Expérience : {self.experience}."
        if self.languages:
            lang_str = ", ".join(
                f"{lang.get('language', lang)} ({lang.get('level', 'unknown')})"
                if isinstance(lang, dict)
                else str(lang)
                for lang in self.languages
            )
            profile += f" Langues : {lang_str}."
        if self.credits is not None:
            profile += f" Crédits disponibles : {self.credits}."
        parts.append(profile)
        return {"role": "system", "content": " ".join(parts)}

    def _build_messages(self, user_input: str, history: list[dict] | None = None) -> list[dict]:
        messages = [self._system_message()]

        for instruction in self.instructions:
            messages.append({"role": "system", "content": instruction})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})
        return messages

    def _build_tools(self) -> list[dict]:
        tools = []

        if self.search_enabled or self.local_jobs:
            base = []

            if self.local_jobs:
                skills_hint = ""
                if self.skills:
                    skills_hint = (
                        " Mots-clés disponibles dans le profil : "
                        + ", ".join(self.skills[:6])
                        + "."
                    )

                base.append(
                    {
                        "type": "function",
                        "function": {
                            "name": "search_local_jobs",
                            "description": (
                                "Recherche des offres d'emploi dans la base de donnees locale."
                                f"{skills_hint}"
                                " Utilise des mots-cles techniques (metiers, competences)."
                                " Exemple: 'devops', 'cloud architect', 'juriste'."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "keywords": {
                                        "type": "string",
                                        "description": (
                                            "Mots-cles techniques pour la recherche"
                                            " (metiers, competences)."
                                        ),
                                    },
                                    "city": {
                                        "type": "string",
                                        "description": (
                                            "Ville pour filtrer les resultats (optionnel)."
                                        ),
                                    },
                                },
                                "required": ["keywords"],
                            },
                        },
                    }
                )

            base.append(
                {
                    "type": "function",
                    "function": {
                        "name": "search_web_jobs",
                        "description": (
                            "Recherche des offres d'emploi sur le web en temps reel."
                            " A utiliser quand la base locale ne donne pas de resultats,"
                            " ou pour chercher sur des sites comme Emploi.tg, LinkedIn, etc."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Requete de recherche complete.",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                }
            )

            tools.extend(base)

        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "generate_cv",
                    "description": (
                        "Genere un CV personnalise et optimise ATS pour l'utilisateur"
                        " adapte a une offre d'emploi specifique."
                        " Cout: 5 credits. L'utilisateur doit avoir assez de credits."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_title": {
                                "type": "string",
                                "description": (
                                    "Titre exact ou approximatif de l'offre d'emploi"
                                    " pour laquelle generer le CV."
                                ),
                            },
                        },
                        "required": ["job_title"],
                    },
                },
            }
        )

        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "generate_cover_letter",
                    "description": (
                        "Genere une lettre de motivation personnalisee pour l'utilisateur"
                        " adaptee a une offre d'emploi specifique."
                        " Cout: 3 credits. L'utilisateur doit avoir assez de credits."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_title": {
                                "type": "string",
                                "description": (
                                    "Titre exact ou approximatif de l'offre d'emploi"
                                    " pour laquelle generer la lettre."
                                ),
                            },
                        },
                        "required": ["job_title"],
                    },
                },
            }
        )

        if self.user_id:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "check_document_status",
                        "description": (
                            "Verifie si des documents (CV, lettres de motivation) ont ete generes"
                            " pour l'utilisateur et retourne leur statut."
                            " Utilise cette fonction quand l'utilisateur demande"
                            " si son document est pret."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    },
                }
            )

        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "subscribe_job_alerts",
                    "description": (
                        "Abonne l'utilisateur aux alertes emploi quotidiennes."
                        " Il recevra automatiquement les nouvelles offres"
                        " correspondant a son profil chaque jour."
                        " Cout: gratuit, donne 50 credits bonus."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "min_score": {
                                "type": "integer",
                                "description": (
                                    "Score minimum de matching (0-100). Defaut: 60."
                                    " Plus le score est eleve, plus les offres sont"
                                    " pertinentes mais moins nombreuses."
                                ),
                            },
                        },
                        "required": [],
                    },
                },
            }
        )

        return tools

    async def interact(self, user_input: str) -> str:
        messages = self._build_messages(user_input)
        return await self._call_with_tools(messages)

    async def interact_with_history(self, user_input: str, history: list[dict]) -> str:
        messages = self._build_messages(user_input, history)
        return await self._call_with_tools(messages)

    _STOP_WORDS = frozenset(
        {
            "offre",
            "offres",
            "emploi",
            "poste",
            "postes",
            "recrute",
            "recherche",
            "trouve",
            "trouver",
            "cherche",
            "chercher",
            "liste",
            "listes",
            "montre",
            "montrer",
            "donne",
            "donner",
            "profil",
            "profils",
            "intéressant",
            "interessant",
            "correspond",
            "correspondant",
            "toutes",
            "tous",
            "tout",
            "dans",
            "pour",
            "avec",
            "sans",
            "sur",
            "mais",
            "leur",
            "être",
            "avoir",
            "faire",
            "veux",
            "vais",
            "peux",
            "moi",
            "toi",
            "quoi",
            "quel",
            "quelle",
            "quels",
            "quelles",
            "encore",
            "aussi",
            "toujours",
            "jamais",
            "bien",
            "très",
            "bon",
            "bonne",
            "merci",
            "s'il",
            "s'il vous",
            "s'il te",
        }
    )

    def _search_local_jobs(self, query: str, max_results: int = 10) -> list[Job]:
        words = [w for w in query.lower().split() if len(w) > 2 and w not in self._STOP_WORDS]
        if not words:
            return self._search_with_skills(max_results)
        matches = []
        for job in self.local_jobs:
            if job.status != "active":
                continue
            text = (f"{job.title} {job.description} {job.company or ''} {job.city or ''}").lower()
            if any(w in text for w in words):
                matches.append(job)
        if not matches:
            return self._search_with_skills(max_results)
        matches.sort(
            key=lambda j: sum(1 for w in words if w in f"{j.title} {j.description}".lower()),
            reverse=True,
        )
        return matches[:max_results]

    def _search_with_skills(self, max_results: int = 10) -> list[Job]:
        if not self.skills:
            return []
        words = [s.lower() for s in self.skills if len(s) > 2]
        if not words:
            return []
        matches = []
        for job in self.local_jobs:
            if job.status != "active":
                continue
            text = (f"{job.title} {job.description} {job.company or ''} {job.city or ''}").lower()
            if any(w in text for w in words):
                matches.append(job)
        if not matches:
            return []
        matches.sort(
            key=lambda j: sum(1 for w in words if w in f"{j.title} {j.description}".lower()),
            reverse=True,
        )
        return matches[:max_results]

    def _find_job_by_title(self, title_query: str) -> Job | None:
        words = title_query.lower().split()
        best_score = 0
        best_job = None
        for job in self.local_jobs:
            text = f"{job.title} {job.description}".lower()
            score = sum(1 for w in words if w in text and len(w) > 2)
            if score > best_score:
                best_score = score
                best_job = job
        return best_job

    async def _handle_tool_call(self, tool_call) -> str:
        func_name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            args = {}

        if func_name == "search_local_jobs":
            keywords = args.get("keywords", "")
            city = args.get("city")
            query = keywords
            if city:
                query += f" {city}"
            jobs = self._search_local_jobs(query)
            return json.dumps(
                [
                    {
                        "title": j.title,
                        "company": j.company or "",
                        "city": j.city or "",
                        "description": (j.description[:300] if j.description else ""),
                        "url": j.source_url or "",
                    }
                    for j in jobs
                ],
                ensure_ascii=False,
            )

        if func_name == "search_web_jobs":
            query = args.get("query", "")
            results = search_jobs_online(query) if query else []
            return json.dumps(
                [
                    {
                        "title": r.title,
                        "snippet": r.snippet[:300] if r.snippet else "",
                        "url": r.url,
                    }
                    for r in (results or [])
                ],
                ensure_ascii=False,
            )

        if func_name == "check_document_status":
            return self._handle_check_document_tool()

        if func_name == "generate_cv" or func_name == "generate_cover_letter":
            return await self._handle_document_tool(func_name, args)

        if func_name == "subscribe_job_alerts":
            return await self._handle_subscribe_tool(args)

        return json.dumps({"error": f"Unknown tool: {func_name}"})

    def _handle_check_document_tool(self) -> str:
        if not self.user_id:
            return json.dumps({"error": "Impossible d'identifier l'utilisateur."})
        from leRH.core.documents.generator import GENERATED_DIR

        user_dir = GENERATED_DIR / self.user_id
        if not user_dir.is_dir():
            return json.dumps({"generated": [], "message": "Aucun document genere pour l'instant."})
        files = sorted(user_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
        docs = [
            {
                "filename": f.name,
                "type": "CV" if "CV" in f.name else "Lettre de motivation",
                "generated_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                if f.stat().st_mtime
                else None,
            }
            for f in files
        ]
        return json.dumps({"generated": docs}, ensure_ascii=False)

    async def _handle_document_tool(self, func_name: str, args: dict) -> str:
        if not self.user_id:
            return json.dumps(
                {
                    "error": "Impossible d'identifier l'utilisateur. Veuillez d'abord creer votre profil."
                }
            )

        job_title = args.get("job_title", "")
        if not job_title:
            return json.dumps({"error": "Veuillez specifier le titre du poste."})

        job = self._find_job_by_title(job_title)
        if not job:
            return json.dumps(
                {
                    "error": (
                        f"Je n'ai pas trouve d'offre correspondant à « {job_title} »."
                        " Pouvez-vous etre plus precis ?"
                    )
                }
            )

        cost = CV_COST if func_name == "generate_cv" else COVER_LETTER_COST
        credit_mgr = CreditManager()

        if not await credit_mgr.check_credits(self.user_id, cost, session=self._db_session):
            current = await credit_mgr.get_credits(self.user_id, session=self._db_session)
            return json.dumps(
                {
                    "error": (
                        f"Crédits insuffisants. Vous avez {current} crédit(s), "
                        f"il en faut {cost}. Activez les alertes emploi "
                        "(gratuit) pour recevoir 50 crédits bonus !"
                    )
                }
            )

        doc_type = "CV" if func_name == "generate_cv" else "lettre de motivation"
        logger.info(
            "Background task launched: %s for user=%s job=%s", doc_type, self.user_id, job.title
        )
        asyncio.create_task(
            generate_document_background(
                user_id=self.user_id,
                job=job,
                func_name=func_name,
                cost=cost,
                platform=self.platform or "telegram",
                chat_id=self.chat_id or self.user_id,
            )
        )

        return json.dumps(
            {
                "success": True,
                "message": (
                    f"Je prépare votre {doc_type} en arrière-plan… "
                    "Vous recevrez une notification dès qu'il sera prêt !"
                ),
            }
        )

    async def _handle_subscribe_tool(self, args: dict) -> str:
        if not self.user_id:
            return json.dumps(
                {
                    "error": "Impossible d'identifier l'utilisateur. Veuillez d'abord creer votre profil."
                }
            )

        min_score = args.get("min_score", 60)
        credit_mgr = CreditManager()

        if self._db_session is not None:
            user_repo = UserRepository(self._db_session)
            user = await user_repo.get_by_id(self.user_id)
            if not user:
                return json.dumps({"error": "Utilisateur non trouvé."})

            sub_repo = SubscriptionRepository(self._db_session)
            existing = await sub_repo.get_by_user(self.user_id)
            if existing:
                existing.min_match_score = float(min_score)
                existing.active = True
            else:
                await sub_repo.create(
                    user_id=self.user_id,
                    min_match_score=float(min_score),
                    notify_telegram=True,
                    notify_whatsapp=True,
                )

            await credit_mgr.add(
                self.user_id,
                SUBSCRIPTION_BONUS,
                reason="subscription_bonus",
                session=self._db_session,
            )
        else:
            async with DBLock(), async_session_factory() as session:
                user_repo = UserRepository(session)
                user = await user_repo.get_by_id(self.user_id)
                if not user:
                    return json.dumps({"error": "Utilisateur non trouvé."})

                sub_repo = SubscriptionRepository(session)
                existing = await sub_repo.get_by_user(self.user_id)
                if existing:
                    existing.min_match_score = float(min_score)
                    existing.active = True
                else:
                    await sub_repo.create(
                        user_id=self.user_id,
                        min_match_score=float(min_score),
                        notify_telegram=True,
                        notify_whatsapp=True,
                    )

                await credit_mgr.add(
                    self.user_id, SUBSCRIPTION_BONUS, reason="subscription_bonus", session=session
                )

        return json.dumps(
            {
                "success": True,
                "message": (
                    f"Vous êtes abonné aux alertes emploi (score minimum: {min_score}/100) ! "
                    f"Vous recevrez les offres chaque jour. "
                    f"Vous avez reçu {SUBSCRIPTION_BONUS} crédits bonus !"
                ),
                "credits_awarded": SUBSCRIPTION_BONUS,
            }
        )

    async def _call_with_tools(self, messages: list[dict]) -> str:
        tools = self._build_tools()

        for _turn in range(MAX_TOOL_TURNS):
            try:
                kwargs = {
                    "model": settings.llm_model_id,
                    "messages": messages,
                    "temperature": 0.5,
                    "max_tokens": 1024,
                }
                if tools:
                    kwargs["tools"] = tools
                response = await asyncio.to_thread(self._client.chat.completions.create, **kwargs)
            except APITimeoutError:
                logger.error("LLM API timeout after %ds", settings.openai_timeout)
                return "Désolé, le service IA met trop de temps à répondre. Veuillez réessayer dans quelques instants."
            except APIError as exc:
                logger.error("LLM API error (code=%s): %s", exc.status_code, exc.message)
                return "Désolé, le service IA est temporairement indisponible. Veuillez réessayer."
            except Exception:
                logger.exception("LLM call failed")
                return "Désolé, une erreur est survenue. Veuillez réessayer."

            if not tools:
                return response.choices[0].message.content or ""

            finish_reason = response.choices[0].finish_reason
            if finish_reason != "tool_calls":
                return response.choices[0].message.content or ""

            assistant_msg = response.choices[0].message
            messages.append(assistant_msg)

            for tool_call in assistant_msg.tool_calls:
                result = await self._handle_tool_call(tool_call)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        return response.choices[0].message.content or ""
