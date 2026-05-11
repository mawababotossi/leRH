from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from leRH.core.scraping.types import ScrapedJob

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for job scrapers."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of the source (e.g. 'Emploi.tg')."""

    @abstractmethod
    def fetch_jobs(self) -> list[ScrapedJob]:
        """Fetch and parse job offers from the source."""

    def scrape(self) -> list[ScrapedJob]:
        """Scrape jobs with logging and error handling."""
        logger.info("Scraping %s...", self.source_name)
        try:
            jobs = self.fetch_jobs()
            logger.info("Scraped %d jobs from %s", len(jobs), self.source_name)
            now = datetime.now(UTC)
            for j in jobs:
                if j.expires_at is None:
                    j.expires_at = now
            return jobs
        except Exception:
            logger.exception("Failed to scrape %s", self.source_name)
            return []
