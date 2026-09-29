"""Send one bounded batch of pending notifications for development use."""

import logging
from pathlib import Path

from dotenv import load_dotenv
from app.init_db import init_db
from app.services.telegram_notifier import TelegramNotificationWorker


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    logging.basicConfig(level=logging.INFO)
    init_db()
    TelegramNotificationWorker().run_once()
