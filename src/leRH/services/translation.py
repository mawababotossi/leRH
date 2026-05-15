from __future__ import annotations

import logging

from leRH.core.assistants.manager import Assistant

logger = logging.getLogger(__name__)


class TranslationManager:
    async def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        if not text:
            return ""
        assistant = Assistant(
            name="Translator",
            activity="translation",
            search_enabled=False,
            instructions=[
                "Tu es un traducteur. Traduis le message de l'utilisateur dans la langue demandée."
            ],
        )
        return await assistant.interact(
            f"Translate this from {src_lang} to {tgt_lang}. "
            f"Return ONLY the translation, nothing else.\n\n{text}"
        )
