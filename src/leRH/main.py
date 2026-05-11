from __future__ import annotations

import logging
import sys

from leRH.config import settings

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)


def main() -> None:
    if not settings.telegram_token:
        logging.critical("TELEGRAM_TOKEN is not set. Create a .env file with TELEGRAM_TOKEN=...")
        sys.exit(1)

    from leRH.adapters.telegram.bot import run_polling

    run_polling()


if __name__ == "__main__":
    main()
