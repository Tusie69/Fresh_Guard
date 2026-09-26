"""Persistent sensor fault transition tracking, scoped by device/food/sensor."""


SENSOR_FIELDS = (
    ("temperature", "temperature_c"),
    ("humidity", "humidity_pct"),
    ("gas", "gas_raw"),
)


def update_sensor_fault_states(connection, device_id, food_id, timestamp, values):
    """Persist sensor states and return only newly observed transitions.

    The caller owns the transaction, so state changes commit or roll back with
    the corresponding reading and events.
    """
    transitions = []
    for sensor_name, field_name in SENSOR_FIELDS:
        sensor_value = values[field_name]
        state = connection.execute(
            """SELECT fault_active FROM sensor_fault_state
               WHERE device_id = ? AND food_id IS ? AND sensor_name = ?""",
            (device_id, food_id, sensor_name),
        ).fetchone()
        was_fault_active = bool(state["fault_active"]) if state else False
        is_fault_active = sensor_value is None

        if was_fault_active != is_fault_active:
            transitions.append({
                "event_type": "SENSOR_FAULT" if is_fault_active else "SENSOR_RECOVERED",
                "sensor_name": sensor_name,
                "sensor_value": sensor_value,
                "food_id": food_id,
            })

        if state is None:
            connection.execute(
                """INSERT INTO sensor_fault_state (
                       device_id, food_id, sensor_name, fault_active, updated_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (device_id, food_id, sensor_name, int(is_fault_active), timestamp),
            )
        else:
            connection.execute(
                """UPDATE sensor_fault_state
                   SET fault_active = ?, updated_at = ?
                   WHERE device_id = ? AND food_id IS ? AND sensor_name = ?""",
                (int(is_fault_active), timestamp, device_id, food_id, sensor_name),
            )

    return transitions
