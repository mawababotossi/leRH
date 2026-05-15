from __future__ import annotations

import base64
import logging
import tempfile
from pathlib import Path

import httpx

from leRH.config import settings

logger = logging.getLogger(__name__)

NVIDIA_AUDIO_URL = "https://ai.api.nvidia.com/v1/audio/transcriptions"


class AudioProcessor:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.asr_model

    def transcribe(self, file_url: str) -> str:
        try:
            resp = httpx.get(file_url, timeout=30)
            resp.raise_for_status()
            return self._transcribe_bytes(resp.content)
        except Exception as exc:
            logger.error("Audio download failed: %s", exc)
            return ""

    def transcribe_file(self, file_path: str | Path) -> str:
        try:
            with open(file_path, "rb") as f:
                return self._transcribe_bytes(f.read())
        except Exception as exc:
            logger.error("Audio transcription failed: %s", exc)
            return ""

    def transcribe_base64(self, data: str, mimetype: str = "audio/ogg") -> str:
        try:
            audio_bytes = base64.b64decode(data)
            return self._transcribe_bytes(audio_bytes)
        except Exception as exc:
            logger.error("Audio transcription from base64 failed: %s", exc)
            return ""

    def _transcribe_bytes(self, audio_bytes: bytes) -> str:
        suffix = ".oga" if self._is_oga(audio_bytes) else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                mime = "audio/ogg" if suffix == ".oga" else "audio/wav"
                files = {"file": (f"audio{suffix}", f, mime)}
                headers = {"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"}
                resp = httpx.post(
                    NVIDIA_AUDIO_URL,
                    headers=headers,
                    files=files,
                    data={"model": self.model},
                    timeout=60,
                )
                resp.raise_for_status()
                return resp.json().get("text", "").strip()
        except Exception as exc:
            logger.error("NVIDIA ASR failed: %s", exc)
            return ""
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @staticmethod
    def _is_oga(data: bytes) -> bool:
        return data[:4] == b"OggS"
