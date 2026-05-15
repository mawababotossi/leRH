from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from leRH.config import settings
from leRH.db.models import User

logger = logging.getLogger(__name__)


UNIFIED_PROMPT = """Analyse ce CV et retourne à la fois une analyse lisible ET des données de profil structurées.
N'invente JAMAIS des informations qui ne sont pas dans le texte du CV.

TEXTE DU CV :
{cv_text}

Réponds avec un objet JSON VALIDE contenant :
1. "full_name": nom complet du candidat (string ou null si introuvable)
2. "email": adresse email (string ou null)
3. "phone": numéro de téléphone (string ou null)
4. "address": adresse physique (string ou null)
5. "analysis": analyse en français (max 150 mots) couvrant : compétences principales, niveau d'expérience, domaines d'expertise, points forts
6. "profile": objet avec :
   - skills: liste des compétences (strings)
   - diploma: diplôme le plus élevé (string ou null)
   - experience_summary: résumé de l'expérience professionnelle (string)
   - experiences: liste d'objets : {{"company": "...", "location": "...", "title": "...", "start_date": "...", "end_date": "...", "description": "..."}}
   - education: liste d'objets : {{"institution": "...", "degree": "...", "field": "...", "year": "..."}}
   - certifications: liste des certifications/formations certifiantes explicitement présentes dans le CV
   - languages: liste de {{"language": "...", "level": "..."}}
   - social: {{"linkedin": "...", "github": "...", "website": "..."}}

Exemple :
{{"full_name": "Jean Dupont", "email": "jean.dupont@email.com", "phone": "+22890000000", "analysis": "Développeur Python avec 5 ans d'expérience...", "profile": {{"skills": ["Python", "Django", "PostgreSQL"], "diploma": "Master en Informatique", "experience_summary": "5 ans en développement web", "experiences": [{{"company": "Tech SARL", "location": "Lomé", "title": "Développeur", "start_date": "01/2020", "end_date": "Présent", "description": "Développement d'applications web"}}], "education": [{{"institution": "Université de Lomé", "degree": "Master", "field": "Informatique", "year": "2018"}}], "certifications": ["Formation Docker avancée — Organisme — 2020"], "languages": [{{"language": "Français", "level": "Natif"}}], "social": {{"linkedin": "linkedin.com/in/jeandupont", "github": "github.com/jeandupont", "website": null}}}}}}

Retourne UNIQUEMENT l'objet JSON, pas d'autre texte."""


class ProfileExtractor:
    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout,
        )

    def analyze_cv(self, cv_text: str) -> dict | None:
        try:
            response = self._client.chat.completions.create(
                model=settings.llm_model_id,
                messages=[
                    {
                        "role": "system",
                        "content": "Tu es un expert en analyse de CV. Extrais les données structurées et rédige une analyse concise en français. N'invente jamais d'informations.",
                    },
                    {
                        "role": "user",
                        "content": UNIFIED_PROMPT.format(cv_text=cv_text[:30000]),
                    },
                ],
                temperature=0.05,  # Très basse : extraction déterministe, zéro créativité
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
            data = self._parse_json(content)
            if data and "analysis" in data:
                return data

            logger.error(
                "[Extractor] Failed to parse JSON or missing analysis key. Content snippet: %r",
                content[:500],
            )
            return None
        except Exception:
            logger.exception("CV analysis failed")
            return None

    def extract(self, cv_text: str) -> dict | None:
        try:
            response = self._client.chat.completions.create(
                model=settings.llm_model_id,
                messages=[
                    {
                        "role": "system",
                        "content": "Tu extrais des données de profil structurées à partir de CVs. Ne retourne que du JSON valide. N'invente jamais d'informations absentes du texte.",
                    },
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(cv_text=cv_text[:30000]),
                    },
                ],
                temperature=0.05,  # Très basse : extraction déterministe
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
            return self._parse_json(content)
        except Exception:
            logger.exception("Profile extraction failed")
            return None

    @staticmethod
    def _parse_json(content: str) -> dict | None:
        if not content or not content.strip():
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                text = re.sub(r",\s*([}\]])", r"\1", match.group())
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def enrich_user(user: User, data: dict) -> User:
        from leRH.db.models import Education, Experience

        # Ne mettre à jour que si ce n'est pas un prénom court (onboarding)
        # ou si le nom actuel est vide.
        if (full_name := data.get("full_name")) and (
            not user.name or len(full_name.split()) > len(user.name.split())
        ):
            user.name = full_name[:255]

        if email := data.get("email"):
            user.email = email[:255]
        if phone := data.get("phone"):
            user.phone = phone[:50]
        if address := data.get("address"):
            user.address = address

        if skills := data.get("skills"):
            user.skills = skills
        if diploma := data.get("diploma"):
            user.diploma = diploma
        if exp_summary := data.get("experience_summary") or data.get("experience"):
            user.experience = exp_summary

        # Social links
        social = data.get("social", {})
        if social.get("linkedin"):
            user.linkedin_url = social["linkedin"]
        if social.get("github"):
            user.github_url = social["github"]
        if social.get("website"):
            user.website_url = social["website"]

        if languages := data.get("languages"):
            user.languages = languages

        # Add experiences only if they don't already exist (basic deduplication)
        if experiences := data.get("experiences"):
            existing_exps = {(e.company, e.title) for e in user.experiences}
            for exp in experiences:
                if not isinstance(exp, dict):
                    continue
                company = exp.get("company", "Inconnue")
                title = exp.get("title", "Poste")
                if (company, title) not in existing_exps:
                    user.experiences.append(
                        Experience(
                            company=company,
                            location=exp.get("location"),
                            title=title,
                            start_date=exp.get("start_date"),
                            end_date=exp.get("end_date"),
                            description=exp.get("description"),
                        )
                    )

        # Add educations only if they don't already exist
        if educations := data.get("education"):
            existing_edus = {(e.institution, e.degree) for e in user.educations}
            for edu in educations:
                if not isinstance(edu, dict):
                    continue
                inst = edu.get("institution", "Inconnue")
                deg = edu.get("degree", "Diplôme")
                if (inst, deg) not in existing_edus:
                    user.educations.append(
                        Education(
                            institution=inst,
                            degree=deg,
                            field=edu.get("field"),
                            year=edu.get("year"),
                        )
                    )

        return user


EXTRACTION_PROMPT = """Analyse ce CV et extrais les informations de profil structurées.
N'invente JAMAIS des informations absentes du texte. Si un champ est introuvable, utilise null pour les chaînes et [] pour les listes.

TEXTE DU CV :
{cv_text}

Exemple de réponse :
{{
  "skills": ["Python", "Django", "PostgreSQL", "Docker"],
  "diploma": "Master en Informatique",
  "experience_summary": "Développeur full-stack avec 5 ans d'expérience",
  "experiences": [
    {{
      "company": "Tech SARL",
      "location": "Lomé, Togo",
      "title": "Développeur Full-Stack",
      "start_date": "01/2020",
      "end_date": "Présent",
      "description": "Développement d'applications web avec Django et React"
    }}
  ],
  "education": [
    {{
      "institution": "Université de Lomé",
      "degree": "Master",
      "field": "Informatique",
      "year": "2018"
    }}
  ],
  "certifications": ["Formation Docker avancée — Organisme — 2020"],
  "languages": [{{"language": "Français", "level": "natif"}}, {{"language": "Anglais", "level": "courant"}}],
  "social": {{"linkedin": "linkedin.com/in/jeandupont", "github": "github.com/jeandupont", "website": null}},
  "domain": "Développement web",
  "years_experience": 5
}}

Retourne UNIQUEMENT un objet JSON valide avec ces champs exacts :
{{
  "skills": ["compétence1", "compétence2", ...],
  "diploma": "diplôme le plus élevé ou null",
  "experience_summary": "résumé concis ou null",
  "experiences": [
    {{
      "company": "...",
      "location": "...",
      "title": "...",
      "start_date": "...",
      "end_date": "...",
      "description": "..."
    }}
  ],
  "education": [
    {{
      "institution": "...",
      "degree": "...",
      "field": "...",
      "year": "..."
    }}
  ],
  "certifications": ["certification ou formation certifiante explicitement présente dans le CV", ...],
  "languages": [{{"language": "Français", "level": "natif"}}, ...],
  "social": {{"linkedin": "...", "github": "...", "website": "..."}},
  "domain": "domaine professionnel principal ou null",
  "years_experience": 5
}}"""
