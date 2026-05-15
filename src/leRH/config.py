from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_token: str = ""
    openai_api_key: SecretStr = SecretStr("")
    internal_api_key: SecretStr = SecretStr("")
    openai_base_url: str = "http://127.0.0.1:1337/v1"
    openai_timeout: int = 120
    llm_model_id: str = "mistralai/mistral-small-4-119b-2603"
    asr_model: str = "nvidia/nemostt-whisper"
    tts_model: str = "nvidia/parakeet-tts"

    country: str = "Togo"
    activity: str = "job seeker"

    database_url: str = "mysql+aiomysql://user:pass@localhost:3306/lerh"
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    auto_create_tables: bool = True
    enable_scheduler: bool = True

    search_enabled: bool = True
    search_max_results: int = 5
    search_region: str = "wt-wt"

    src_dir: Path = Path(__file__).resolve().parent

    COUNTRY: ClassVar[int] = 0
    ACTIVITY: ClassVar[int] = 1
    SKILLS: ClassVar[int] = 2
    DIPLOMA: ClassVar[int] = 3


settings = Settings()
