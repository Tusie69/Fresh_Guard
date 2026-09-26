import ast
import sqlite3
import uuid

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings as readings_module


SENSORS = {
    "temperature": "temperature_c",
    "humidity": "humidity_pct",
    "gas": "gas_raw",
}


@pytest.fixture
def sensor_client(tmp_path, monkeypatch):
    database_path = tmp_path / "sensor-fault.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    init_db_module.init_db()
    app = create_app()
    app.config["TESTING"] = True
    app.config["TEST_DB_PATH"] = str(database_path)
    return app.test_client()


def reading_payload(seconds=0, **overrides):
    payload = {
        "device_id": "SENSOR-DEVICE",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": f"2026-09-26T10:00:{seconds:02d}+07:00",
        "temperature_c": 4.0,
        "humidity_pct": 60.0,
        "gas_raw": 300,
        "door_open": False,
    }
    payload.update(overrides)
    return payload


def post_reading(client, seconds=0, **overrides):
    return client.post("/api/v1/readings", json=reading_payload(seconds, **overrides))


def connect(client):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    return connection


def events(client):
    connection = connect(client)
    try:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM events WHERE event_type IN "
            "('SENSOR_FAULT', 'SENSOR_RECOVERED') ORDER BY id"
        )]
    finally:
        connection.close()


def fault_state(client, sensor_name, device="SENSOR-DEVICE", food_id=None):
    connection = connect(client)
    try:
        return connection.execute(
            """SELECT * FROM sensor_fault_state
               WHERE device_id = ? AND food_id IS ? AND sensor_name = ?""",
            (device, food_id, sensor_name),
        ).fetchone()
    finally:
        connection.close()


def fault_events(client):
    return [event for event in events(client) if event["event_type"] == "SENSOR_FAULT"]


def recovered_events(client):
    return [event for event in events(client) if event["event_type"] == "SENSOR_RECOVERED"]


def test_normal_reading_creates_no_events(sensor_client):
    response = post_reading(sensor_client)
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Fresh / Normal"
    assert events(sensor_client) == []


@pytest.mark.parametrize("sensor_name,field", SENSORS.items())
def test_each_numeric_sensor_null_emits_fault(sensor_client, sensor_name, field):
    response = post_reading(sensor_client, seconds=1, **{field: None})
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Check Food"
    created = fault_events(sensor_client)
    assert len(created) == 1
    assert created[0]["event_type"] == "SENSOR_FAULT"
    assert ast.literal_eval(created[0]["payload"])["sensor_name"] == sensor_name
    assert created[0]["timestamp"] == reading_payload(1)["timestamp"]
    assert fault_state(sensor_client, sensor_name)["fault_active"] == 1


def test_repeated_null_fault_does_not_spam_and_valid_recovers_once(sensor_client):
    for seconds in range(1, 6):
        post_reading(sensor_client, seconds=seconds, temperature_c=None)
    assert len(fault_events(sensor_client)) == 1
    assert recovered_events(sensor_client) == []

    post_reading(sensor_client, seconds=6, temperature_c=4.2)
    post_reading(sensor_client, seconds=7, temperature_c=4.1)
    assert len(fault_events(sensor_client)) == 1
    assert len(recovered_events(sensor_client)) == 1
    recovered = recovered_events(sensor_client)[0]
    payload = ast.literal_eval(recovered["payload"])
    assert payload["sensor_name"] == "temperature"
    assert payload["sensor_value"] == 4.2
    assert recovered["timestamp"] == reading_payload(6)["timestamp"]
    assert fault_state(sensor_client, "temperature")["fault_active"] == 0


def test_multiple_sensors_transition_and_recover_independently(sensor_client):
    post_reading(sensor_client, seconds=1, temperature_c=None)
    post_reading(sensor_client, seconds=2, temperature_c=None, humidity_pct=None)
    assert [(event["event_type"], ast.literal_eval(event["payload"])["sensor_name"])
            for event in events(sensor_client)] == [
        ("SENSOR_FAULT", "temperature"),
        ("SENSOR_FAULT", "humidity"),
    ]

    post_reading(sensor_client, seconds=3, temperature_c=4.0, humidity_pct=60.0)
    assert [(event["event_type"], ast.literal_eval(event["payload"])["sensor_name"])
            for event in events(sensor_client)] == [
        ("SENSOR_FAULT", "temperature"),
        ("SENSOR_FAULT", "humidity"),
        ("SENSOR_RECOVERED", "temperature"),
        ("SENSOR_RECOVERED", "humidity"),
    ]


def test_three_null_sensors_create_separate_fault_transitions(sensor_client):
    response = post_reading(
        sensor_client, seconds=1,
        temperature_c=None, humidity_pct=None, gas_raw=None,
    )
    assert response.status_code == 201
    assert [ast.literal_eval(event["payload"])["sensor_name"]
            for event in fault_events(sensor_client)] == [
        "temperature", "humidity", "gas"
    ]
    post_reading(sensor_client, seconds=2,
                 temperature_c=None, humidity_pct=None, gas_raw=None)
    assert len(fault_events(sensor_client)) == 3


def test_fault_state_is_isolated_by_food_device_and_null_food(sensor_client):
    for food_id in ("FOOD-A", "FOOD-B"):
        response = sensor_client.post("/api/v1/foods", json={
            "food_id": food_id,
            "food_name": food_id,
            "category": "MEAT",
            "inserted_at": "2026-09-26",
        })
        assert response.status_code == 201

    post_reading(sensor_client, seconds=1, food_id="FOOD-A", temperature_c=None)
    post_reading(sensor_client, seconds=2, food_id="FOOD-B", temperature_c=4.0)
    post_reading(sensor_client, seconds=3, device_id="OTHER-DEVICE",
                 food_id="FOOD-A", temperature_c=4.0)
    post_reading(sensor_client, seconds=4, food_id=None, temperature_c=4.0)

    assert fault_state(sensor_client, "temperature", food_id="FOOD-A")["fault_active"] == 1
    assert fault_state(sensor_client, "temperature", food_id="FOOD-B")["fault_active"] == 0
    assert fault_state(sensor_client, "temperature", "OTHER-DEVICE", "FOOD-A")["fault_active"] == 0
    assert fault_state(sensor_client, "temperature", food_id=None)["fault_active"] == 0
    assert len(fault_events(sensor_client)) == 1


@pytest.mark.parametrize("invalid", ["abc", True, {}, float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("field", list(SENSORS.values()))
def test_malformed_sensor_value_is_validation_error_not_fault(sensor_client, field, invalid):
    response = post_reading(sensor_client, seconds=1, **{field: invalid})
    assert response.status_code == 400
    assert events(sensor_client) == []
    assert fault_state(sensor_client, next(
        name for name, sensor_field in SENSORS.items() if sensor_field == field
    )) is None


def test_fault_state_and_events_survive_restart_and_recover(sensor_client):
    reading_id = str(uuid.uuid4())
    first = post_reading(sensor_client, seconds=1, temperature_c=None,
                         device_reading_id=reading_id)
    assert first.status_code == 201
    init_db_module.init_db()  # Simulate backend startup against the persisted DB.
    restarted_client = sensor_client.application.test_client()

    post_reading(restarted_client, seconds=2, temperature_c=None)
    assert len(fault_events(restarted_client)) == 1
    post_reading(restarted_client, seconds=3, temperature_c=4.0)
    assert len(recovered_events(restarted_client)) == 1
    assert fault_state(restarted_client, "temperature")["fault_active"] == 0


def test_duplicate_reading_does_not_repeat_fault_transition_and_id_is_deterministic(sensor_client):
    reading_id = str(uuid.uuid4())
    first = post_reading(sensor_client, seconds=1, temperature_c=None,
                         device_reading_id=reading_id)
    retry = post_reading(sensor_client, seconds=1, temperature_c=None,
                         device_reading_id=reading_id)
    assert first.status_code == 201
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    created = fault_events(sensor_client)
    assert len(created) == 1
    expected = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "freshguard:sensor-fault:[\"SENSOR-DEVICE\",null,\"temperature\","
        f"\"{reading_id}\",\"SENSOR_FAULT\"]",
    )
    assert created[0]["event_id"] == str(expected)
    connection = connect(sensor_client)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?",
            (reading_id,),
        ).fetchone()[0] == 1
    finally:
        connection.close()


@pytest.mark.parametrize("event_type,temperature", [("SENSOR_FAULT", None), ("SENSOR_RECOVERED", 4.0)])
def test_event_insert_failure_rolls_back_reading_and_fault_state(
    sensor_client, event_type, temperature
):
    if event_type == "SENSOR_RECOVERED":
        post_reading(sensor_client, seconds=1, temperature_c=None)
    connection = connect(sensor_client)
    try:
        connection.execute(f"""CREATE TRIGGER reject_sensor_event
            BEFORE INSERT ON events WHEN NEW.event_type = '{event_type}'
            BEGIN SELECT RAISE(ABORT, 'event insert failure'); END""")
        connection.commit()
    finally:
        connection.close()

    reading_id = str(uuid.uuid4())
    with pytest.raises(sqlite3.IntegrityError):
        post_reading(sensor_client, seconds=2, temperature_c=temperature,
                     device_reading_id=reading_id)

    state = fault_state(sensor_client, "temperature")
    if event_type == "SENSOR_RECOVERED":
        assert state["fault_active"] == 1
    else:
        assert state is None
    connection = connect(sensor_client)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?",
            (reading_id,),
        ).fetchone()[0] == 0
    finally:
        connection.close()
