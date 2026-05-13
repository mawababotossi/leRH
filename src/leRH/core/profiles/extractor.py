from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from leRH.config import settings
from leRH.db.models import User

logger = logging.getLogger(__name__)


UNIFIED_PROMPT = """Analyze this CV and return BOTH a human-readable analysis AND structured profile data.

CV TEXT:
{cv_text}

Respond with a VALID JSON object containing:
1. "analysis": brief analysis in French (max 150 words) covering: main skills, experience level, expertise areas, strengths
2. "profile": object with:
   - skills: list of skill strings
   - diploma: highest degree (string or null)
   - experience_summary: brief professional experience summary (string)
   - experiences: list of objects: {{"company": "...", "location": "...", "title": "...", "start_date": "...", "end_date": "...", "description": "..."}}
   - education: list of objects: {{"institution": "...", "degree": "...", "field": "...", "year": "..."}}
   - languages: list of {{"language": "...", "level": "..."}}
   - social: {{"linkedin": "...", "github": "...", "website": "..."}}

Example:
{{"analysis": "Le candidat a 5 ans d'expérience...", "profile": {{"skills": ["Python"], "diploma": "Master", "experiences": [{{"company": "Google", "title": "Dev"}}]}}}}

Return ONLY the JSON object, no other text."""


class ProfileExtractor:
    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.openai_api_key,
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
                        "content": "You are a CV analysis AI. Extract structured data and write concise analysis.",
                    },
                    {
                        "role": "user",
                        "content": UNIFIED_PROMPT.format(cv_text=cv_text[:30000]),
                    },
                ],
                temperature=0.05,
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
                        "content": "You extract structured profile data from CVs. Return only valid JSON.",
                    },
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(cv_text=cv_text[:30000]),
                    },
                ],
                temperature=0.05,
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
            return self._parse_json(content)
        except Exception:
            logger.exception("Profile extraction failed")
            return None

    @staticmethod
    def _parse_json(content: str) -> dict | None:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def enrich_user(user: User, data: dict) -> User:
        from leRH.db.models import Education, Experience

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


EXTRACTION_PROMPT = """Analyze this CV text and extract structured profile information.

CV TEXT:
{cv_text}

Return ONLY a valid JSON object with these exact fields:
{{
  "skills": ["skill1", "skill2", ...],
  "diploma": "highest degree obtained",
  "experience_summary": "brief summary",
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
  "languages": [{{"language": "French", "level": "native"}}, ...],
  "social": {{"linkedin": "...", "github": "...", "website": "..."}},
  "domain": "main professional domain",
  "years_experience": 5
}}

If a field cannot be determined, use null for strings and [] for arrays."""
