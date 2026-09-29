"""Explicit manual integration test; never drains or modifies the outbox."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from app.services.telegram_notifier import (
    TelegramDeliveryError, send_telegram_text, telegram_configured,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send-test", action="store_true",
                        help="Send one clearly labelled test message to the configured chat")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    if not telegram_configured():
        print("Telegram disabled: missing/blank or malformed config. No message sent.")
        return 1
    if not args.send_test:
        print("Telegram config is present (credentials not verified). Use --send-test to send one test message.")
        return 0
    try:
        result = send_telegram_text(
            "FreshGuard Telegram integration test\n"
            "Manual connectivity test; no food alert or sensor reading was created.\n"
            f"Sent at: {datetime.now(timezone.utc).isoformat()}"
        )
    except TelegramDeliveryError:
        print("Telegram test failed. Check credentials, chat permissions and connectivity; no secrets printed.")
        return 1
    except Exception:
        print("Telegram test failed unexpectedly; no secrets printed.")
        return 1
    print(f"Telegram API accepted the test; message_id={result['result']['message_id']}. Verify it appears in the configured chat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
