from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_token: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://integrate.api.nvidia.com/v1"
    openai_timeout: int = 120
    llm_model_id: str = "nvidia/nemotron-4-340b-instruct"
    asr_model: str = "nvidia/nemostt-whisper"
    tts_model: str = "nvidia/parakeet-tts"

    country: str = "Togo"
    activity: str = "job seeker"

    database_url: str = "sqlite+aiosqlite:///data/lerh.db"

    search_enabled: bool = True
    search_max_results: int = 5
    search_region: str = "wt-wt"

    src_dir: Path = Path(__file__).resolve().parent

    COUNTRY: ClassVar[int] = 0
    ACTIVITY: ClassVar[int] = 1
    SKILLS: ClassVar[int] = 2
    DIPLOMA: ClassVar[int] = 3


settings = Settings()
