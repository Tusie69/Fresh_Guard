"""Delivery metadata only; never an input to the freshness engine."""

from datetime import datetime, timezone
import re


LIVE_DELAY_THRESHOLD_SECONDS = 10
OFFLINE_DELAY_THRESHOLD_SECONDS = 120
MAX_FUTURE_SKEW_SECONDS = 30

# Require an explicit, valid offset rather than guessing the device timezone.
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)"
)


def utc_now():
    return datetime.now(timezone.utc)


def parse_device_timestamp(value):
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise ValueError("timestamp must be an ISO datetime with seconds and timezone")
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise ValueError("timestamp must be a valid timezone-aware ISO datetime") from error


def delivery_metadata(captured_at, received_at):
    delay = (received_at - captured_at).total_seconds()
    if delay < -MAX_FUTURE_SKEW_SECONDS:
        raise ValueError("timestamp exceeds the allowed future clock skew")
    if delay < 0:
        status = "CLOCK_SKEW"
    elif delay <= LIVE_DELAY_THRESHOLD_SECONDS:
        status = "LIVE"
    elif delay <= OFFLINE_DELAY_THRESHOLD_SECONDS:
        status = "DELAYED"
    else:
        # Inferred from latency, not proof of a WiFi outage.
        status = "OFFLINE_RECOVERED"
    return {
        "received_at": received_at.isoformat(),
        "delivery_delay_seconds": delay,
        "ingest_status": status,
    }
