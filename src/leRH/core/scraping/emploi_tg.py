from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from leRH.core.scraping.base import BaseScraper
from leRH.core.scraping.types import ScrapedJob

logger = logging.getLogger(__name__)

BASE_URL = "https://www.emploi.tg"
SEARCH_URL = f"{BASE_URL}/recherche-jobs-togo"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


class EmploiTgScraper(BaseScraper):
    """Scraper for emploi.tg — the main Togolese job board."""

    def __init__(self, max_pages: int = 5) -> None:
        self.max_pages = max_pages

    @property
    def source_name(self) -> str:
        return "Emploi.tg"

    def fetch_jobs(self) -> list[ScrapedJob]:
        page = 0
        all_jobs: list[ScrapedJob] = []

        while page < self.max_pages:
            url = SEARCH_URL if page == 0 else f"{SEARCH_URL}?page={page}"
            logger.info("Fetching page %d: %s", page + 1, url)

            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
            except requests.RequestException:
                logger.exception("Failed to fetch page %d", page + 1)
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_="card-job-detail")
            if not cards:
                logger.info("No more cards found, stopping at page %d", page + 1)
                break

            for card in cards:
                job = self._parse_card(card)
                if job:
                    detail = self._fetch_detail(job.source_url)
                    if detail:
                        job = detail
                    all_jobs.append(job)

            page += 1

        logger.info("Total jobs scraped: %d", len(all_jobs))
        return all_jobs

    def _parse_card(self, card: BeautifulSoup) -> ScrapedJob | None:
        link_tag = card.find("a", href=re.compile(r"/offre-emploi-togo/"))
        if not link_tag:
            return None

        href = link_tag.get("href", "")
        full_url = urljoin(BASE_URL, href)
        external_id = self._extract_id(href)
        title = link_tag.get_text(strip=True)

        full_text = card.get_text(" ", strip=True)
        company = self._extract_company(full_text, title)
        city = self._extract_city(title)

        return ScrapedJob(
            external_id=external_id,
            title=title,
            description=full_text[:3000],
            source_url=full_url,
            source_name=self.source_name,
            company=company,
            city=city,
            expires_at=datetime.now(UTC),
        )

    def _fetch_detail(self, url: str) -> ScrapedJob | None:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException:
            logger.warning("Failed to fetch detail page: %s", url)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        meta = self._extract_meta(soup)
        description = self._extract_description(soup)
        company = self._extract_company_from_detail(soup)
        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else None
        city = self._extract_city(title) if title else None

        return ScrapedJob(
            external_id=self._extract_id(url),
            title=title or "",
            description=description or "",
            source_url=url,
            source_name=self.source_name,
            company=company,
            city=city,
            requirements=meta,
            expires_at=datetime.now(UTC),
        )

    @staticmethod
    def _extract_meta(soup: BeautifulSoup) -> dict:
        meta: dict[str, str] = {}
        for li in soup.find_all("li"):
            strong = li.find("strong")
            if not strong:
                continue
            label = strong.get_text(strip=True).rstrip(":").strip()
            span = li.find("span")
            if span:
                value = span.get_text(" ", strip=True)
                if value:
                    meta[label] = value
        return meta

    @staticmethod
    def _extract_description(soup: BeautifulSoup) -> str | None:
        desc = soup.find("div", class_="field-name-field-offre-description")
        if desc:
            text = desc.get_text(" ", strip=True)
            if len(text) > 50:
                return text

        for keyword in ["description de l'offre", "missions", "profil recherché"]:
            tag = soup.find(
                lambda t, kw=keyword: (
                    t.name in ("div", "section", "article")
                    and t.get_text(" ", strip=True).lower().startswith(kw)
                )
            )
            if tag:
                parent = tag.find_parent()
                if parent:
                    text = parent.get_text(" ", strip=True)
                    if len(text) > 50:
                        return text

        return None

    @staticmethod
    def _extract_company_from_detail(soup: BeautifulSoup) -> str | None:
        h3 = soup.find("h3")
        if h3:
            a = h3.find("a")
            if a:
                return a.get_text(strip=True)
        return None

    @staticmethod
    def _extract_id(href: str) -> str:
        match = re.search(r"(\d+)$", href)
        return match.group(1) if match else href

    @staticmethod
    def _extract_company(text: str, title: str) -> str | None:
        after_title = text.replace(title, "", 1).strip()
        after_title = re.sub(r"^-\s*", "", after_title)
        boundaries = [
            r"\s*(?:À|A)\s+propos",
            r"\s+(?:Une|une|est)\s+(?:société|entreprise|ONG|startup|filiale)",
            r"\s+(?:Notre|Nous|je|vous|elle|il|elles|ils)\s",
            r"\s+Sous",
            r"\s+Contexte",
            r"\s+Missions",
            r"\s+Et si",
            r"\s+Dans le cadre",
            r"\s+Afin",
            r"\s+Pour\s",
            r"\s+Suite",
            r"\s+Poste",
            r"\s+$",
        ]
        pattern = r"^(.+?)(?:" + "|".join(boundaries) + r")"
        match = re.match(pattern, after_title, re.DOTALL)
        if match:
            company = match.group(1).strip().rstrip(",")
            if len(company.split()) <= 5:
                return company if company else None
            first_word = company.split()[0]
            return first_word if first_word and len(first_word) > 1 else None
        return None

    @staticmethod
    def _extract_city(title: str) -> str | None:
        match = re.search(r"-\s*([A-Za-zÀ-ÿ\s,/'éèêëûüôîö]+)$", title)
        return match.group(1).strip() if match else None
