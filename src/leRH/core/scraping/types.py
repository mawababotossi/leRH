from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScrapedJob:
    external_id: str
    title: str
    description: str
    source_url: str
    source_name: str
    company: str | None = None
    city: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    requirements: dict | None = field(default_factory=dict)
    expires_at: datetime | None = None
