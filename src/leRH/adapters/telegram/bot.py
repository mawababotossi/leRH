from __future__ import annotations

import logging

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from leRH.adapters.telegram.handlers.conversation import (
    activity,
    cancel,
    country,
    diploma,
    show_profile,
    skills,
    skip_activity,
    skip_diploma,
    skip_skills,
    start,
)
from leRH.adapters.telegram.handlers.documents import handle_document
from leRH.adapters.telegram.handlers.messages import handle_audio, handle_text, handle_voice
from leRH.config import settings
from leRH.core.bot_registry import register_telegram_bot
from leRH.services.audio_processor import AudioProcessor
from leRH.services.translation import TranslationManager
from leRH.services.tts import TTSManager

logger = logging.getLogger(__name__)


def build_application():
    token = settings.telegram_token
    if not token:
        raise ValueError("TELEGRAM_TOKEN is not set")

    app = ApplicationBuilder().token(token).build()
    register_telegram_bot(app.bot)

    # Services
    app.bot_data["audio_processor"] = AudioProcessor()
    app.bot_data["translation_manager"] = TranslationManager()
    app.bot_data["tts_manager"] = TTSManager()

    # Conversation handler
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("modifier", start),
        ],
        states={
            settings.COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
            settings.ACTIVITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, activity),
                CommandHandler("skip", skip_activity),
            ],
            settings.SKILLS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, skills),
                CommandHandler("skip", skip_skills),
            ],
            settings.DIPLOMA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, diploma),
                CommandHandler("skip", skip_diploma),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("profil", show_profile))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    return app


def run_polling() -> None:
    app = build_application()
    logger.info("Starting Telegram bot polling...")
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    run_polling()
