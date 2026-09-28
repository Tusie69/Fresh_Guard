"""Persistent relative gas anomaly tracking, scoped to device and food."""

import math

from app.services.rule_provider import get_freshness_rules


# Compatibility aliases for existing callers/tests. The provider owns values.
_DEFAULT_RULES = get_freshness_rules()
GAS_BASELINE_SAMPLE_COUNT = _DEFAULT_RULES.gas_baseline_sample_count
GAS_ANOMALY_DEVIATION = _DEFAULT_RULES.gas_anomaly_deviation_ratio
GAS_REQUIRED_CONSECUTIVE_READINGS = _DEFAULT_RULES.gas_required_consecutive_readings


def _valid_gas_reading(gas_raw):
    if not isinstance(gas_raw, (int, float)) or isinstance(gas_raw, bool):
        return False
    try:
        return math.isfinite(gas_raw) and gas_raw >= 0
    except (OverflowError, TypeError):
        return False


def is_valid_gas_reading(gas_raw):
    """Expose the service's validity rule to transition/event callers."""
    return _valid_gas_reading(gas_raw)


def get_gas_anomaly_state(connection, device_id, food_id):
    """Return the persisted state for this device/food context, if present."""
    return connection.execute(
        "SELECT * FROM gas_anomaly_state WHERE device_id = ? AND food_id = ?",
        (device_id, food_id or ""),
    ).fetchone()


def update_gas_anomaly_state(connection, device_id, food_id, gas_raw, rules=None):
    """Update and return the persisted anomaly flag for one reading.

    The caller owns the transaction so state and its sensor_readings row can
    commit or roll back together.
    """
    rules = rules or get_freshness_rules()
    state_food_id = food_id or ""
    state = connection.execute(
        "SELECT * FROM gas_anomaly_state WHERE device_id = ? AND food_id = ?",
        (device_id, state_food_id),
    ).fetchone()

    if state is None:
        connection.execute(
            """INSERT INTO gas_anomaly_state (
                device_id, food_id, baseline, baseline_sample_count,
                baseline_sum, consecutive_anomaly_count, anomaly_active
            ) VALUES (?, ?, NULL, 0, 0, 0, 0)""",
            (device_id, state_food_id),
        )
        state = connection.execute(
            "SELECT * FROM gas_anomaly_state WHERE device_id = ? AND food_id = ?",
            (device_id, state_food_id),
        ).fetchone()

    sample_count = state["baseline_sample_count"]
    baseline = state["baseline"]
    baseline_sum = state["baseline_sum"]
    consecutive_count = state["consecutive_anomaly_count"]
    anomaly_active = bool(state["anomaly_active"])

    if not _valid_gas_reading(gas_raw):
        consecutive_count = 0
        # Missing/invalid sensor data cannot prove that an active anomaly ended.
    elif sample_count < rules.gas_baseline_sample_count:
        sample_count += 1
        baseline_sum += gas_raw
        if sample_count == rules.gas_baseline_sample_count:
            baseline = baseline_sum / rules.gas_baseline_sample_count
        consecutive_count = 0
        anomaly_active = False
    elif baseline is not None and baseline > 0:
        deviation = (gas_raw - baseline) / baseline
        if deviation >= rules.gas_anomaly_deviation_ratio:
            consecutive_count += 1
            anomaly_active = (
                anomaly_active
                or consecutive_count >= rules.gas_required_consecutive_readings
            )
        else:
            consecutive_count = 0
            anomaly_active = False

    connection.execute(
        """UPDATE gas_anomaly_state
           SET baseline = ?, baseline_sample_count = ?, baseline_sum = ?,
               consecutive_anomaly_count = ?, anomaly_active = ?
           WHERE device_id = ? AND food_id = ?""",
        (
            baseline,
            sample_count,
            baseline_sum,
            consecutive_count,
            int(anomaly_active),
            device_id,
            state_food_id,
        ),
    )
    return anomaly_active
