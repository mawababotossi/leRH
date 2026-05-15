from __future__ import annotations

import logging
import tempfile

import httpx

from leRH.config import settings

logger = logging.getLogger(__name__)

NVIDIA_TTS_URL = "https://ai.api.nvidia.com/v1/audio/speech"


class TTSManager:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.tts_model

    def generate_audio(self, text: str) -> str:
        if not text:
            raise ValueError("Text cannot be empty")

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": text,
            "voice": "default",
            "response_format": "wav",
        }

        resp = httpx.post(NVIDIA_TTS_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(resp.content)
            fpath = tmp.name
        logger.debug("TTS saved to %s", fpath)
        return fpath
