from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def search_jobs_online(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search for job offers using DuckDuckGo."""
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results, region="wt-wt")
            return [
                SearchResult(title=r["title"], url=r["href"], snippet=r["body"]) for r in results
            ]
    except ImportError:
        logger.error("duckduckgo_search not installed")
        return []
    except Exception:
        logger.exception("Web search failed for query: %s", query)
        return []
