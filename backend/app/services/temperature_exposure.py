"""Persistent, reading-timestamp-based temperature exposure tracking."""

from dataclasses import dataclass
from datetime import datetime, timezone
import math


TEMPERATURE_LIMIT_C = 5.0
TEMPERATURE_EXPOSURE_LIMIT_SECONDS = 2 * 60 * 60
# The simulator samples every five seconds. Do not infer unobserved exposure
# when a reading gap exceeds two expected sample periods.
MAX_CONTIGUOUS_READING_GAP_SECONDS = 10


@dataclass(frozen=True)
class ExposureUpdate:
    exposure_seconds: float
    exceeded_transition: bool


def _parse_reading_timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _valid_temperature(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def update_temperature_exposure(connection, device_id, food_id, temperature_c,
                                timestamp):
    """Update one persisted context inside the caller's transaction.

    Exposure accumulates only between consecutive observed hot readings no
    more than ten seconds apart. Gaps and invalid temperatures never add time.
    Out-of-order readings leave the state untouched.
    """
    state = connection.execute(
        "SELECT * FROM temperature_exposure_state "
        "WHERE device_id = ? AND food_id = ?",
        (device_id, food_id or ""),
    ).fetchone()

    if not _valid_temperature(temperature_c):
        if state is not None:
            last_timestamp = state["last_valid_temperature_timestamp"]
            if (
                last_timestamp is None
                or _parse_reading_timestamp(timestamp)
                > _parse_reading_timestamp(last_timestamp)
            ):
                connection.execute(
                    "UPDATE temperature_exposure_state "
                    "SET continuity_broken = 1 WHERE device_id = ? AND food_id = ?",
                    (device_id, food_id or ""),
                )
        return ExposureUpdate(
            float(state["exposure_seconds"]) if state else 0.0, False
        )

    reading_time = _parse_reading_timestamp(timestamp)
    old_seconds = float(state["exposure_seconds"]) if state else 0.0
    old_active = bool(state["exposure_active"]) if state else False
    old_exceeded = bool(state["exposure_exceeded"]) if state else False
    continuity_broken = bool(state["continuity_broken"]) if state else False
    old_timestamp = state["last_valid_temperature_timestamp"] if state else None

    if old_timestamp is not None:
        previous_time = _parse_reading_timestamp(old_timestamp)
        if reading_time <= previous_time:
            return ExposureUpdate(old_seconds, False)
    else:
        previous_time = None

    if temperature_c <= TEMPERATURE_LIMIT_C:
        exposure_seconds = 0.0
        exposure_active = False
        exposure_exceeded = False
    else:
        exposure_seconds = old_seconds
        exposure_active = True
        if old_active and not continuity_broken and previous_time is not None:
            gap = (reading_time - previous_time).total_seconds()
            if 0 < gap <= MAX_CONTIGUOUS_READING_GAP_SECONDS:
                exposure_seconds += gap
        exposure_exceeded = old_exceeded or (
            exposure_seconds > TEMPERATURE_EXPOSURE_LIMIT_SECONDS
        )

    connection.execute(
        """INSERT INTO temperature_exposure_state (
               device_id, food_id, exposure_seconds, exposure_active,
               exposure_exceeded, last_valid_temperature_timestamp,
               continuity_broken
           ) VALUES (?, ?, ?, ?, ?, ?, 0)
           ON CONFLICT(device_id, food_id) DO UPDATE SET
               exposure_seconds = excluded.exposure_seconds,
               exposure_active = excluded.exposure_active,
               exposure_exceeded = excluded.exposure_exceeded,
               last_valid_temperature_timestamp =
                   excluded.last_valid_temperature_timestamp,
               continuity_broken = 0""",
        (
            device_id, food_id or "", exposure_seconds, int(exposure_active),
            int(exposure_exceeded), timestamp,
        ),
    )
    return ExposureUpdate(
        exposure_seconds,
        not old_exceeded and exposure_exceeded,
    )
