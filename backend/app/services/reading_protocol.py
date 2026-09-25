"""Pure protocol decoding for compact FreshGuard reading payloads."""

from datetime import datetime, timedelta, timezone
import math


class ReadingProtocolError(ValueError):
    """Raised when a compact reading cannot be decoded unambiguously."""


COMPACT_REQUIRED_FIELDS = frozenset({"id", "d", "t", "tc", "h", "g", "o"})
COMPACT_OPTIONAL_FIELDS = frozenset({"od", "f"})
CANONICAL_FIELDS = frozenset(
    {
        "device_reading_id",
        "device_id",
        "timestamp",
        "temperature_c",
        "humidity_pct",
        "gas_raw",
        "door_open",
        "open_duration_seconds",
        "food_id",
    }
)
SAIGON_OFFSET = timezone(timedelta(hours=7))


def decode_compact_reading(payload):
    """Convert a compact reading object to the canonical API field names.

    This function deliberately performs protocol conversion only. Existing
    route validation remains responsible for UUID, sensor, duration, and food
    validation.
    """
    if not isinstance(payload, dict):
        raise ReadingProtocolError("Compact reading payload must be an object")

    compact_fields = COMPACT_REQUIRED_FIELDS | COMPACT_OPTIONAL_FIELDS
    if payload.keys() & compact_fields and payload.keys() & CANONICAL_FIELDS:
        raise ReadingProtocolError(
            "Compact and canonical reading fields cannot be mixed"
        )

    missing_fields = sorted(COMPACT_REQUIRED_FIELDS - payload.keys())
    if missing_fields:
        raise ReadingProtocolError(
            "Missing required compact fields: " + ", ".join(missing_fields)
        )

    if not isinstance(payload["id"], str) or not payload["id"].strip():
        raise ReadingProtocolError("Compact field 'id' must be a non-empty string")
    if not isinstance(payload["d"], str) or not payload["d"].strip():
        raise ReadingProtocolError("Compact field 'd' must be a non-empty string")

    timestamp = payload["t"]
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        raise ReadingProtocolError(
            "Compact field 't' must be a finite Unix timestamp in seconds"
        )
    if isinstance(timestamp, float) and not math.isfinite(timestamp):
        raise ReadingProtocolError(
            "Compact field 't' must be a finite Unix timestamp in seconds"
        )
    try:
        canonical_timestamp = datetime.fromtimestamp(
            timestamp, tz=SAIGON_OFFSET
        ).isoformat()
    except (OverflowError, OSError, ValueError) as error:
        raise ReadingProtocolError(
            "Compact field 't' is outside the supported timestamp range"
        ) from error

    if type(payload["o"]) is not int or payload["o"] not in (0, 1):
        raise ReadingProtocolError("Compact field 'o' must be integer 0 or 1")

    return {
        "device_reading_id": payload["id"],
        "device_id": payload["d"],
        "timestamp": canonical_timestamp,
        "temperature_c": payload["tc"],
        "humidity_pct": payload["h"],
        "gas_raw": payload["g"],
        "door_open": payload["o"] == 1,
        "open_duration_seconds": payload.get("od", 0),
        "food_id": payload.get("f"),
    }
