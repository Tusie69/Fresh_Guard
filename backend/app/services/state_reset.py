"""State reset primitives for future stateful FreshRule updates.

These functions only mutate the processor state tables inside a caller-owned
transaction. They never write events or historical reading snapshots.
"""


def reset_temperature_state(connection):
    cursor = connection.execute(
        "UPDATE temperature_exposure_state SET "
        "exposure_seconds = 0, exposure_active = 0, exposure_exceeded = 0, "
        "last_valid_temperature_timestamp = NULL, continuity_broken = 0"
    )
    return cursor.rowcount


def reset_gas_state(connection):
    cursor = connection.execute(
        "UPDATE gas_anomaly_state SET "
        "baseline = NULL, baseline_sample_count = 0, baseline_sum = 0, "
        "consecutive_anomaly_count = 0, anomaly_active = 0"
    )
    return cursor.rowcount


def reset_state_for_rule_keys(connection, changed_rule_keys):
    """Reset each affected global state table once for a rule change batch."""
    keys = tuple(changed_rule_keys)
    reset = set()
    if any(key.startswith("temperature.") for key in keys):
        reset_temperature_state(connection)
        reset.add("temperature")
    if any(key.startswith("gas.") for key in keys):
        reset_gas_state(connection)
        reset.add("gas")
    if any(key.startswith("door.") for key in keys):
        raise ValueError("Door state reset is unsupported")
    return frozenset(reset)


def apply_stateful_rule_transaction(connection, update, audit, changed_rule_keys):
    """Apply future rule/audit/state changes atomically.

    ``update`` and ``audit`` are callbacks receiving the open connection.
    The caller remains responsible for choosing and validating rule values.
    """
    connection.execute("BEGIN")
    try:
        update(connection)
        audit(connection)
        reset_state_for_rule_keys(connection, changed_rule_keys)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
