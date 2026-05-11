from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from openai import OpenAI

from leRH.config import settings
from leRH.db.models import CV, Job, User

logger = logging.getLogger(__name__)


@dataclass
class Criterion:
    name: str
    score: float
    weight: float
    details: str


@dataclass
class MatchResult:
    candidate_id: str
    job_id: str
    overall_score: float
    criteria: list[Criterion] = field(default_factory=list)
    summary: str = ""
    recommendation: str = "possible_match"
    llm_enhanced: bool = False
    job_source: str = "internal"
    job_source_url: str = ""
    is_external: bool = False


MATCH_SYSTEM_PROMPT = (
    "You are a recruitment matching AI. Analyze the compatibility "
    "between a candidate profile and a job offer. Be objective and thorough."
)

MATCH_USER_PROMPT = """Analyze the match between this candidate and job offer.

CANDIDATE:
Name: {name}
Country: {country}
City: {city}
Activity: {activity}
Diploma: {diploma}
Experience: {experience}
Skills: {skills}
Languages: {languages}
CV Analysis: {cv_analysis}

JOB OFFER:
Title: {title}
Company: {company}
City: {city_job}
Description: {description}
Requirements: {requirements}
Salary: {salary_min} - {salary_max}
Source: {source}
Source URL: {source_url}

Score each criterion 0-100:
- skills (weight 0.30): technical and soft skills match
- experience (weight 0.30): relevant work experience
- education (weight 0.15): diploma and training adequacy
- location (weight 0.10): geographic compatibility
- overall (weight 0.15): holistic assessment

Respond ONLY with a valid JSON object, no other text:
{{"criteria": [
    {{"name": "skills", "score": 0, "weight": 0.30, "details": "..."}},
    {{"name": "experience", "score": 0, "weight": 0.30, "details": "..."}},
    {{"name": "education", "score": 0, "weight": 0.15, "details": "..."}},
    {{"name": "location", "score": 0, "weight": 0.10, "details": "..."}},
    {{"name": "overall", "score": 0, "weight": 0.15, "details": "..."}}
], "summary": "...", "recommendation": "strong_match|possible_match|weak_match"}}"""


def _json_dumps(obj: object) -> str:
    if obj is None:
        return ""
    if isinstance(obj, dict | list):
        return json.dumps(obj, ensure_ascii=False)
    return str(obj)


class Matcher:
    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout,
        )

    async def match(self, user: User, job: Job, cv: CV | None = None) -> MatchResult:
        prompt = MATCH_USER_PROMPT.format(
            name=user.name or "N/A",
            country=user.country or "N/A",
            city=user.city or "N/A",
            activity=user.activity or "N/A",
            diploma=user.diploma or "N/A",
            experience=user.experience or "N/A",
            skills=_json_dumps(user.skills),
            languages=_json_dumps(user.languages),
            cv_analysis=_json_dumps(cv.analysis if cv else None),
            title=job.title,
            company=job.company or "N/A",
            city_job=job.city or "N/A",
            description=job.description,
            requirements=_json_dumps(job.requirements),
            salary_min=job.salary_min or "N/A",
            salary_max=job.salary_max or "N/A",
            source=job.source_name or "internal",
            source_url=job.source_url or "",
        )

        llm_data = await self._call_llm(prompt)
        if llm_data:
            result = self._build_result(user.id, job.id, llm_data)
            result.llm_enhanced = True
            result.job_source = job.source_name or "internal"
            result.job_source_url = job.source_url or ""
            result.is_external = job.is_external or False
            return result

        logger.info("LLM matching failed, using fallback for %s <-> %s", user.id, job.id)
        result = self._fallback_match(user, job)
        result.job_source = job.source_name or "internal"
        result.job_source_url = job.source_url or ""
        result.is_external = job.is_external or False
        return result

    async def _call_llm(self, prompt: str) -> dict | None:
        import asyncio

        try:
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=settings.llm_model_id,
                messages=[
                    {"role": "system", "content": MATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
            )
            content = response.choices[0].message.content or ""
            return self._extract_json(content)
        except Exception:
            logger.exception("LLM matching call failed")
            return None

    @staticmethod
    def _extract_json(content: str) -> dict | None:
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

    def _fallback_match(self, user: User, job: Job) -> MatchResult:
        skill_score = self._keyword_overlap(user.skills, job.requirements)
        location_score = (
            100.0 if (user.city and job.city and user.city.lower() == job.city.lower()) else 50.0
        )
        exp_score = 50.0

        criteria = [
            Criterion("skills", skill_score, 0.30, "Keyword overlap analysis"),
            Criterion("experience", exp_score, 0.30, "No structured experience data"),
            Criterion("education", 50.0, 0.15, "No structured education data"),
            Criterion(
                "location",
                location_score,
                0.10,
                "City: {}/{}".format(user.city or "?", job.city or "?"),
            ),
            Criterion(
                "overall", (skill_score + exp_score + location_score) / 3, 0.15, "Fallback estimate"
            ),
        ]
        overall = sum(c.score * c.weight for c in criteria)
        rec = self._recommendation(overall)
        return MatchResult(
            candidate_id=user.id,
            job_id=job.id,
            overall_score=round(overall, 1),
            criteria=criteria,
            summary="Fallback matching (LLM unavailable). Based on keyword and location only.",
            recommendation=rec,
        )

    @staticmethod
    def _keyword_overlap(skills: object, requirements: object) -> float:
        s_words = _extract_words(skills)
        r_words = _extract_words(requirements)
        if not s_words or not r_words:
            return 50.0
        common = s_words & r_words
        if not common:
            return 20.0
        jaccard = len(common) / len(s_words | r_words)
        return round(jaccard * 100, 1)

    @staticmethod
    def _build_result(candidate_id: str, job_id: str, data: dict) -> MatchResult:
        raw_criteria = data.get("criteria", [])
        criteria = []
        for c in raw_criteria:
            criteria.append(
                Criterion(
                    name=c.get("name", "unknown"),
                    score=float(c.get("score", 0)),
                    weight=float(c.get("weight", 0)),
                    details=c.get("details", ""),
                )
            )
        overall = sum(c.score * c.weight for c in criteria) if criteria else 0

        return MatchResult(
            candidate_id=candidate_id,
            job_id=job_id,
            overall_score=round(overall, 1),
            criteria=criteria,
            summary=data.get("summary", ""),
            recommendation=data.get("recommendation", "possible_match"),
        )

    @staticmethod
    def _recommendation(score: float) -> str:
        if score >= 70:
            return "strong_match"
        if score >= 40:
            return "possible_match"
        return "weak_match"


def _extract_words(obj: object) -> set[str]:
    text = _json_dumps(obj).lower()
    words = set(re.findall(r"[a-z]+", text))
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "in",
        "to",
        "for",
        "with",
        "on",
        "at",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "have",
        "has",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
    }
    return words - stopwords
