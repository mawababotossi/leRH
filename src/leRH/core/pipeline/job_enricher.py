from __future__ import annotations

import json
import logging
import re

from openai import OpenAI

from leRH.config import settings
from leRH.core.scraping.types import ScrapedJob

logger = logging.getLogger(__name__)

ENRICH_PROMPT = """Analyse cette offre d'emploi et retourne UNIQUEMENT un objet JSON.

Titre: {title}
Entreprise: {company}
Ville: {city}
Description:
{description}

Réponds UNIQUEMENT avec ce JSON (pas d'autre texte):
{{
  "title_clean": "titre nettoyé (corrige les espaces, majuscules, tirets)",
  "company_clean": "nom entreprise extrait ou null",
  "city_clean": "ville extraite ou null",
  "skills": ["compétence1", "compétence2"],
  "diploma_required": "diplôme requis ou null",
  "experience_level": "debutant|intermediaire|confirme|senior|non_specifie",
  "sector": "secteur d'activité ou null",
  "contract_type": "CDI|CDD|stage|freelance|non_specifie",
  "description_clean": "description courte (2-3 phrases) ou null"
}}"""


class JobEnricher:
    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout,
        )

    def enrich(self, job: ScrapedJob) -> ScrapedJob:
        try:
            prompt = ENRICH_PROMPT.format(
                title=job.title,
                company=job.company or "",
                city=job.city or "",
                description=job.description[:3000],
            )
            response = self._client.chat.completions.create(
                model=settings.llm_model_id,
                messages=[
                    {
                        "role": "system",
                        "content": "Tu extrais des informations structurées d'offres d'emploi. Réponds uniquement en JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.05,
                max_tokens=512,
            )
            content = response.choices[0].message.content or ""
            data = self._parse_json(content)
            if data:
                job = self._apply(job, data)
        except Exception:
            logger.exception("Enrichment failed for %s", job.title[:60])
        return job

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
    def _apply(job: ScrapedJob, data: dict) -> ScrapedJob:
        if data.get("title_clean"):
            job.title = data["title_clean"][:255]
        if data.get("company_clean"):
            job.company = data["company_clean"][:255]
        if data.get("city_clean"):
            job.city = data["city_clean"][:100]

        enriched = {}
        if data.get("skills"):
            enriched["skills"] = data["skills"]
        if data.get("diploma_required"):
            enriched["diploma_required"] = data["diploma_required"]
        if data.get("experience_level"):
            enriched["experience_level"] = data["experience_level"]
        if data.get("sector"):
            enriched["sector"] = data["sector"]
        if data.get("contract_type"):
            enriched["contract_type"] = data["contract_type"]
        if data.get("description_clean"):
            enriched["description_clean"] = data["description_clean"]

        if enriched:
            if job.requirements:
                job.requirements.update(enriched)
            else:
                job.requirements = enriched

        return job


def enrich_jobs(jobs: list[ScrapedJob]) -> list[ScrapedJob]:
    enricher = JobEnricher()
    enriched = []
    for i, job in enumerate(jobs):
        result = enricher.enrich(job)
        enriched.append(result)
        if (i + 1) % 5 == 0:
            logger.info("Enriched %d/%d jobs", i + 1, len(jobs))
    logger.info("Enrichment complete: %d jobs", len(jobs))
    return enriched
