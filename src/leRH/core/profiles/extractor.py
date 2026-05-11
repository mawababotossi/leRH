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
   - experience: brief professional experience summary (string)
   - languages: list of {{"language": "...", "level": "..."}} (or empty list)

Example:
{{"analysis": "Le candidat a 5 ans d'expérience en développement Python...", "profile": {{"skills": ["Python", "FastAPI", "SQL"], "diploma": "Master en Informatique", "experience": "5 ans en développement web", "languages": [{{"language": "Français", "level": "natif"}}]}}}}

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
                        "content": UNIFIED_PROMPT.format(cv_text=cv_text[:8000]),
                    },
                ],
                temperature=0.05,
                max_tokens=1024,
            )
            content = response.choices[0].message.content or ""
            data = self._parse_json(content)
            if data and "analysis" in data:
                return data
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
                        "content": EXTRACTION_PROMPT.format(cv_text=cv_text[:8000]),
                    },
                ],
                temperature=0.05,
                max_tokens=1024,
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
        if skills := data.get("skills"):
            user.skills = skills
        if diploma := data.get("diploma"):
            user.diploma = diploma
        if experience := data.get("experience"):
            user.experience = experience
        if languages := data.get("languages"):
            user.languages = languages
        return user


EXTRACTION_PROMPT = """Analyze this CV text and extract structured profile information.

CV TEXT:
{cv_text}

Return ONLY a valid JSON object with these exact fields (no other text):
{{
  "skills": ["skill1", "skill2", ...],
  "diploma": "highest degree obtained",
  "experience": "brief summary of professional experience",
  "languages": [{{"language": "French", "level": "native"}}, ...],
  "domain": "main professional domain",
  "years_experience": 5
}}

If a field cannot be determined, use null for strings and [] for arrays."""
