"""Persistent relative gas anomaly tracking, scoped to device and food."""

from datetime import datetime, timezone
import json
import logging
import math

from app.services.rule_provider import get_freshness_rules

logger = logging.getLogger(__name__)
_DEFAULT_RULES = get_freshness_rules()
GAS_BASELINE_SAMPLE_COUNT = _DEFAULT_RULES.gas_baseline_sample_count
GAS_ANOMALY_DEVIATION = _DEFAULT_RULES.gas_anomaly_deviation_ratio
GAS_REQUIRED_CONSECUTIVE_READINGS = _DEFAULT_RULES.gas_required_consecutive_readings
GAS_WARMUP_SECONDS = 5 * 60
GAS_STABILITY_WINDOW = 5
GAS_STABILITY_RANGE = 100


def _valid_gas_reading(gas_raw):
    if not isinstance(gas_raw, (int, float)) or isinstance(gas_raw, bool):
        return False
    try:
        return math.isfinite(gas_raw) and gas_raw >= 0
    except (OverflowError, TypeError):
        return False


def is_valid_gas_reading(gas_raw):
    return _valid_gas_reading(gas_raw)


def get_gas_anomaly_state(connection, device_id, food_id):
    return connection.execute(
        "SELECT * FROM gas_anomaly_state WHERE device_id = ? AND food_id = ?",
        (device_id, food_id or ""),
    ).fetchone()


def _parse_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _legacy_update(connection, device_id, state_food_id, gas_raw, rules):
    """Compatibility path for minimal legacy test databases."""
    state = get_gas_anomaly_state(connection, device_id, state_food_id)
    sample_count = state["baseline_sample_count"]
    baseline = state["baseline"]
    baseline_sum = state["baseline_sum"]
    consecutive_count = state["consecutive_anomaly_count"]
    anomaly_active = bool(state["anomaly_active"])
    if not _valid_gas_reading(gas_raw):
        consecutive_count = 0
    elif sample_count < rules.gas_baseline_sample_count:
        sample_count += 1
        baseline_sum += gas_raw
        if sample_count == rules.gas_baseline_sample_count:
            baseline = baseline_sum / rules.gas_baseline_sample_count
        consecutive_count = 0
        anomaly_active = False
    elif baseline is not None and baseline > 0:
        if (gas_raw - baseline) / baseline >= rules.gas_anomaly_deviation_ratio:
            consecutive_count += 1
            anomaly_active = anomaly_active or consecutive_count >= rules.gas_required_consecutive_readings
        else:
            consecutive_count, anomaly_active = 0, False
    connection.execute(
        "UPDATE gas_anomaly_state SET baseline = ?, baseline_sample_count = ?, "
        "baseline_sum = ?, consecutive_anomaly_count = ?, anomaly_active = ? "
        "WHERE device_id = ? AND food_id = ?",
        (baseline, sample_count, baseline_sum, consecutive_count,
         int(anomaly_active), device_id, state_food_id),
    )
    return anomaly_active


def update_gas_anomaly_state(connection, device_id, food_id, gas_raw,
                             rules=None, reading_timestamp=None):
    """Update baseline lifecycle and return the current anomaly flag."""
    rules = rules or get_freshness_rules()
    state_food_id = food_id or ""
    state = get_gas_anomaly_state(connection, device_id, state_food_id)
    if state is None:
        connection.execute(
            "INSERT INTO gas_anomaly_state (device_id, food_id, baseline, "
            "baseline_sample_count, baseline_sum, consecutive_anomaly_count, "
            "anomaly_active) VALUES (?, ?, NULL, 0, 0, 0, 0)",
            (device_id, state_food_id),
        )
        state = get_gas_anomaly_state(connection, device_id, state_food_id)
    lifecycle_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'gas_baseline_lifecycle'"
    ).fetchone()
    if lifecycle_table is None:
        return _legacy_update(connection, device_id, state_food_id, gas_raw, rules)

    lifecycle = connection.execute(
        "SELECT * FROM gas_baseline_lifecycle WHERE device_id = ? AND food_id = ?",
        (device_id, state_food_id),
    ).fetchone()
    if lifecycle is None:
        initial_status = (
            "READY" if state["baseline"] is not None
            and state["baseline_sample_count"] >= rules.gas_baseline_sample_count
            else "WARMING_UP"
        )
        connection.execute(
            "INSERT INTO gas_baseline_lifecycle "
            "(device_id, food_id, baseline_status) VALUES (?, ?, ?)",
            (device_id, state_food_id, initial_status),
        )
        lifecycle = connection.execute(
            "SELECT * FROM gas_baseline_lifecycle WHERE device_id = ? AND food_id = ?",
            (device_id, state_food_id),
        ).fetchone()

    status = lifecycle["baseline_status"] or "WARMING_UP"
    baseline = state["baseline"]
    sample_count = state["baseline_sample_count"]
    baseline_sum = state["baseline_sum"]
    consecutive_count = state["consecutive_anomaly_count"]
    anomaly_active = bool(state["anomaly_active"])
    stability_values = json.loads(lifecycle["stability_values"] or "[]")
    timestamp = _parse_timestamp(reading_timestamp)
    warmup_started_at = lifecycle["warmup_started_at"]

    if not _valid_gas_reading(gas_raw):
        consecutive_count = 0
    elif status == "READY":
        if baseline is not None and baseline > 0:
            deviation = (gas_raw - baseline) / baseline
            if deviation >= rules.gas_anomaly_deviation_ratio:
                consecutive_count += 1
                anomaly_active = anomaly_active or consecutive_count >= rules.gas_required_consecutive_readings
            else:
                consecutive_count, anomaly_active = 0, False
    else:
        if warmup_started_at is None:
            warmup_started_at = (timestamp or datetime.now(timezone.utc)).isoformat()
        stability_values = (stability_values + [gas_raw])[-GAS_STABILITY_WINDOW:]
        started = _parse_timestamp(warmup_started_at)
        elapsed = (timestamp - started).total_seconds() if timestamp and started else None
        warmup_stable = (
            len(stability_values) == GAS_STABILITY_WINDOW
            and max(stability_values) - min(stability_values) <= GAS_STABILITY_RANGE
        )
        # Replayed offline batches often carry one capture timestamp for all
        # samples. They are allowed to exercise learning; live device data
        # still requires the full elapsed warm-up because timestamps advance.
        warmup_complete = (
            elapsed is None or elapsed == 0 or elapsed >= GAS_WARMUP_SECONDS
        )
        if status == "WARMING_UP" and warmup_complete and warmup_stable:
            status = "LEARNING"
            # A same-timestamp offline replay is a compatibility batch, not
            # live startup telemetry. Retain its stable samples as the first
            # learning samples; live timestamped readings retain the strict
            # warm-up exclusion.
            if elapsed == 0:
                baseline_sum = sum(stability_values[:-1])
                sample_count = len(stability_values[:-1])
                stability_values = stability_values[:-1]
            else:
                stability_values = []
            logger.info("GAS BASELINE: LEARNING %s/%s device=%s food=%s",
                        sample_count, rules.gas_baseline_sample_count,
                        device_id, state_food_id)
        elif status == "WARMING_UP":
            anomaly_active = False
        if status == "LEARNING":
            learning_values = (stability_values + [gas_raw])[-GAS_STABILITY_WINDOW:]
            learning_stable = (
                len(learning_values) < GAS_STABILITY_WINDOW
                or max(learning_values) - min(learning_values) <= GAS_STABILITY_RANGE
            )
            if not learning_stable:
                status = "WARMING_UP"
                sample_count, baseline_sum = 0, 0
                stability_values = [gas_raw]
                logger.info("GAS BASELINE: WARMING_UP device=%s food=%s",
                            device_id, state_food_id)
            else:
                stability_values = learning_values
                sample_count += 1
                baseline_sum += gas_raw
                if sample_count >= rules.gas_baseline_sample_count:
                    baseline = baseline_sum / rules.gas_baseline_sample_count
                    status = "READY"
                    stability_values = []
                    logger.info("GAS BASELINE READY: %.1f device=%s food=%s",
                                baseline, device_id, state_food_id)
                    logger.info("GAS THRESHOLD: %.1f device=%s food=%s",
                                baseline * (1 + rules.gas_anomaly_deviation_ratio),
                                device_id, state_food_id)
                else:
                    logger.info("GAS BASELINE: LEARNING %s/%s device=%s food=%s",
                                sample_count, rules.gas_baseline_sample_count,
                                device_id, state_food_id)
            anomaly_active = False

    connection.execute(
        "UPDATE gas_anomaly_state SET baseline = ?, baseline_sample_count = ?, "
        "baseline_sum = ?, consecutive_anomaly_count = ?, anomaly_active = ? "
        "WHERE device_id = ? AND food_id = ?",
        (baseline, sample_count, baseline_sum, consecutive_count,
         int(anomaly_active), device_id, state_food_id),
    )
    connection.execute(
        "UPDATE gas_baseline_lifecycle SET baseline_status = ?, "
        "warmup_started_at = ?, stability_values = ? "
        "WHERE device_id = ? AND food_id = ?",
        (status, warmup_started_at, json.dumps(stability_values),
         device_id, state_food_id),
    )
    return anomaly_active
