"""Cross-service reliability integration checks using a temporary SQLite DB."""

import ast
from datetime import datetime, timedelta, timezone
import sqlite3
import uuid

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import events as events_module
from app.routes import readings as readings_module
from firmware import simulator


@pytest.fixture
def system(tmp_path, monkeypatch):
    database_path = tmp_path / "cross-system.db"

    def connect():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect)
    monkeypatch.setattr(events_module, "get_db_connection", connect)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect)
    init_db_module.init_db()
    app = create_app()
    app.config.update(TESTING=True, TEST_DB_PATH=str(database_path))
    return app.test_client()


def timestamp(second):
    return (datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
            + timedelta(seconds=second)).isoformat()


def post_reading(client, second, *, reading_id=None, device="CROSS-DEVICE",
                 food_id=None, temperature=5, humidity=60, gas=100, door=False,
                 duration=0):
    payload = {
        "device_id": device,
        "device_reading_id": reading_id or str(uuid.uuid4()),
        "timestamp": timestamp(second),
        "temperature_c": temperature,
        "humidity_pct": humidity,
        "gas_raw": gas,
        "door_open": door,
        "open_duration_seconds": duration,
    }
    if food_id is not None:
        payload["food_id"] = food_id
    return client.post("/api/v1/readings", json=payload)


def rows(client, sql, params=()):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql, params)]
    finally:
        connection.close()


def event_types(client):
    return [row["event_type"] for row in rows(
        client, "SELECT event_type FROM events ORDER BY id"
    )]


def test_gas_anomaly_and_gas_sensor_fault_are_independent(system):
    for index in range(10):
        assert post_reading(system, index * 5, gas=100).status_code == 201
    for index in range(3):
        response = post_reading(system, 50 + index * 5, gas=130)
    assert response.status_code == 201
    assert event_types(system) == ["GAS_ANOMALY_STARTED"]

    invalid_id = str(uuid.uuid4())
    invalid = post_reading(system, 65, reading_id=invalid_id, gas=None)
    assert invalid.status_code == 201
    assert rows(system, "SELECT anomaly_active FROM gas_anomaly_state")[0]["anomaly_active"] == 1
    assert event_types(system) == ["GAS_ANOMALY_STARTED", "SENSOR_FAULT"]

    retry = post_reading(system, 65, reading_id=invalid_id, gas=None)
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    assert event_types(system) == ["GAS_ANOMALY_STARTED", "SENSOR_FAULT"]

    post_reading(system, 70, gas=130)
    assert "GAS_ANOMALY_RECOVERED" not in event_types(system)
    assert "SENSOR_RECOVERED" in event_types(system)
    post_reading(system, 75, gas=100)
    assert event_types(system)[-1] == "GAS_ANOMALY_RECOVERED"
    gas_events = rows(system, "SELECT event_id FROM events WHERE event_type LIKE 'GAS_%'")
    assert len({event["event_id"] for event in gas_events}) == len(gas_events)


def test_temperature_fault_breaks_continuity_without_resetting_exposure(system):
    post_reading(system, 0, temperature=6)
    post_reading(system, 5, temperature=6)
    fault = post_reading(system, 10, temperature=None)
    assert fault.status_code == 201
    state = rows(system, "SELECT * FROM temperature_exposure_state")[0]
    assert state["exposure_seconds"] == 5
    assert state["continuity_broken"] == 1
    assert "TEMPERATURE_EXPOSURE_EXCEEDED" not in event_types(system)

    recovery = post_reading(system, 15, temperature=6)
    assert recovery.status_code == 201
    state = rows(system, "SELECT * FROM temperature_exposure_state")[0]
    assert state["exposure_seconds"] == 5
    assert state["continuity_broken"] == 0
    post_reading(system, 20, temperature=6)
    assert rows(system, "SELECT * FROM temperature_exposure_state")[0]["exposure_seconds"] == 10
    sensor_events = rows(system,
        "SELECT event_type, timestamp FROM events WHERE event_type LIKE 'SENSOR_%' ORDER BY id")
    assert [(event["event_type"], event["timestamp"]) for event in sensor_events] == [
        ("SENSOR_FAULT", timestamp(10)), ("SENSOR_RECOVERED", timestamp(15))
    ]


def test_gas_and_temperature_transition_events_coexist_and_freshness_is_consistent(system):
    for index in range(10):
        post_reading(system, index * 5, temperature=4, gas=100)
    connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
    connection.execute(
        """UPDATE temperature_exposure_state
           SET exposure_seconds = 7190, exposure_active = 1,
               exposure_exceeded = 0, last_valid_temperature_timestamp = ?,
               continuity_broken = 0
           WHERE device_id = ? AND food_id = ''""",
        (timestamp(45), "CROSS-DEVICE"),
    )
    connection.commit()
    connection.close()

    post_reading(system, 50, temperature=6, gas=130)
    post_reading(system, 55, temperature=6, gas=130)
    trigger = post_reading(system, 60, temperature=6, gas=130)
    assert trigger.status_code == 201
    assert set(event_types(system)) == {
        "GAS_ANOMALY_STARTED", "TEMPERATURE_EXPOSURE_EXCEEDED"
    }
    assert rows(system, "SELECT COUNT(*) AS n FROM sensor_readings")[0]["n"] == 13
    assert "FRESHNESS_CHANGED" not in event_types(system)
    assert trigger.json["freshness"]["status"] == "Check Food"
    latest = system.get("/api/v1/readings/latest").json["data"]
    history = system.get("/api/v1/readings?limit=1").json["data"][0]
    assert latest["freshness"] == history["freshness"] == trigger.json["freshness"]


def test_three_sensor_faults_and_recoveries_remain_separate(system):
    first = post_reading(system, 0, temperature=None, humidity=None, gas=None)
    assert first.status_code == 201
    faults = rows(system,
        "SELECT event_type, payload FROM events WHERE event_type = 'SENSOR_FAULT' ORDER BY id")
    assert [ast.literal_eval(event["payload"])["sensor_name"] for event in faults] == [
        "temperature", "humidity", "gas"
    ]
    post_reading(system, 5, temperature=None, humidity=None, gas=None)
    assert len(rows(system, "SELECT id FROM events WHERE event_type = 'SENSOR_FAULT'")) == 3

    post_reading(system, 10, temperature=4, humidity=None, gas=None)
    assert [ast.literal_eval(event["payload"])["sensor_name"] for event in rows(
        system, "SELECT payload FROM events WHERE event_type = 'SENSOR_RECOVERED' ORDER BY id"
    )] == ["temperature"]
    post_reading(system, 15, temperature=4, humidity=60, gas=None)
    post_reading(system, 20, temperature=4, humidity=60, gas=100)
    recovered = rows(system,
        "SELECT payload FROM events WHERE event_type = 'SENSOR_RECOVERED' ORDER BY id")
    assert [ast.literal_eval(event["payload"])["sensor_name"] for event in recovered] == [
        "temperature", "humidity", "gas"
    ]


@pytest.mark.parametrize("event_type", [
    "GAS_ANOMALY_STARTED", "TEMPERATURE_EXPOSURE_EXCEEDED", "SENSOR_FAULT"
])
def test_lost_reading_response_does_not_replay_transition(system, event_type):
    reading_id = str(uuid.uuid4())
    second = 5
    if event_type == "GAS_ANOMALY_STARTED":
        connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
        connection.execute(
            """INSERT INTO gas_anomaly_state (
                   device_id, food_id, baseline, baseline_sample_count,
                   baseline_sum, consecutive_anomaly_count, anomaly_active
               ) VALUES ('CROSS-DEVICE', '', 100, 10, 1000, 2, 0)"""
        )
        connection.commit()
        connection.close()
    elif event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
        connection.execute(
            """INSERT INTO temperature_exposure_state (
                   device_id, food_id, exposure_seconds, exposure_active,
                   exposure_exceeded, last_valid_temperature_timestamp,
                   continuity_broken
               ) VALUES ('CROSS-DEVICE', '', 7200, 1, 0, ?, 0)""",
            (timestamp(0),),
        )
        connection.commit()
        connection.close()

    kwargs = {"gas": 130} if event_type == "GAS_ANOMALY_STARTED" else {}
    if event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        kwargs["temperature"] = 6
    if event_type == "SENSOR_FAULT":
        kwargs["temperature"] = None
    first = post_reading(system, second, reading_id=reading_id, **kwargs)
    retry = post_reading(system, second, reading_id=reading_id, **kwargs)
    changed = post_reading(system, second, reading_id=reading_id,
                           **{**kwargs, "humidity": 61})
    assert first.status_code == 201
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    assert changed.status_code == 409
    assert rows(system, "SELECT COUNT(*) AS n FROM sensor_readings")[0]["n"] == 1
    assert event_types(system) == [event_type]


def test_backend_reinitialization_preserves_active_gas_exposure_and_fault(system):
    for index in range(10):
        post_reading(system, index * 5, gas=100, temperature=6)
    connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
    connection.execute(
        """UPDATE temperature_exposure_state
           SET exposure_seconds = 7200, exposure_exceeded = 0,
               last_valid_temperature_timestamp = ?
           WHERE device_id = 'CROSS-DEVICE' AND food_id = ''""",
        (timestamp(45),),
    )
    connection.commit()
    connection.close()
    for index in range(3):
        post_reading(system, 50 + index * 5, gas=130, temperature=6)
    assert event_types(system).count("TEMPERATURE_EXPOSURE_EXCEEDED") == 1
    post_reading(system, 65, gas=None, temperature=None)
    init_db_module.init_db()
    restarted = system.application.test_client()

    assert rows(restarted, "SELECT anomaly_active FROM gas_anomaly_state")[0]["anomaly_active"] == 1
    exposure = rows(restarted, "SELECT * FROM temperature_exposure_state")[0]
    assert exposure["exposure_seconds"] == 7215
    assert exposure["exposure_exceeded"] == 1
    assert event_types(restarted).count("TEMPERATURE_EXPOSURE_EXCEEDED") == 1
    assert rows(restarted, "SELECT fault_active FROM sensor_fault_state WHERE sensor_name='gas'")[0]["fault_active"] == 1
    assert rows(restarted, "SELECT fault_active FROM sensor_fault_state WHERE sensor_name='temperature'")[0]["fault_active"] == 1
    before = event_types(restarted)
    post_reading(restarted, 70, gas=None, temperature=None)
    assert event_types(restarted) == before
    assert event_types(restarted).count("TEMPERATURE_EXPOSURE_EXCEEDED") == 1
    post_reading(restarted, 75, gas=100, temperature=6)
    assert event_types(restarted).count("GAS_ANOMALY_RECOVERED") == 1
    assert event_types(restarted).count("SENSOR_RECOVERED") == 2


def test_food_and_null_food_contexts_do_not_share_transition_state(system):
    for food_id in ("FOOD-A", "FOOD-B"):
        response = system.post("/api/v1/foods", json={
            "food_id": food_id, "food_name": food_id, "category": "MEAT",
            "inserted_at": "2026-09-26", "expiry_date": "2027-09-26",
        })
        assert response.status_code == 201
    for index in range(10):
        post_reading(system, index * 5, food_id="FOOD-A", gas=100)
    for index in range(3):
        post_reading(system, 50 + index * 5, food_id="FOOD-A", gas=130,
                     temperature=None if index == 2 else 5)
    post_reading(system, 70, food_id="FOOD-B", gas=100, temperature=6)
    post_reading(system, 72, food_id="FOOD-B", gas=100, temperature=None)
    post_reading(system, 75, food_id=None, gas=100, temperature=4)
    post_reading(system, 80, food_id="FOOD-A", gas=130, temperature=4)

    states = rows(system, "SELECT device_id, food_id, anomaly_active FROM gas_anomaly_state")
    assert {(state["food_id"], state["anomaly_active"]) for state in states} == {
        ("FOOD-A", 1), ("FOOD-B", 0), ("", 0)
    }
    events = rows(system, "SELECT event_type FROM events WHERE event_type LIKE 'GAS_%'")
    assert [event["event_type"] for event in events] == ["GAS_ANOMALY_STARTED"]

    faults = rows(system,
        "SELECT food_id, sensor_name, fault_active FROM sensor_fault_state "
        "WHERE sensor_name = 'temperature'")
    assert {(fault["food_id"], fault["fault_active"]) for fault in faults} == {
        ("FOOD-A", 0), ("FOOD-B", 1), (None, 0)
    }
    exposure_contexts = rows(system,
        "SELECT food_id, exposure_seconds FROM temperature_exposure_state "
        "WHERE device_id = 'CROSS-DEVICE'")
    assert {context["food_id"] for context in exposure_contexts} == {
        "FOOD-A", "FOOD-B", ""
    }


class _Response:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body or {}

    def json(self):
        return self.body


def test_door_events_and_sensor_faults_coexist_through_event_queue(system, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    producer = simulator.DoorEventProducer()
    assert producer.observe({"device_id": "CROSS-DEVICE", "timestamp": timestamp(0),
                             "door_open": False, "open_duration_seconds": 0}) == []
    opened = {"device_id": "CROSS-DEVICE", "timestamp": timestamp(5),
              "door_open": True, "open_duration_seconds": 5}
    door_open_events = producer.observe(opened)
    assert [event["event_type"] for event in door_open_events] == ["DOOR_OPENED"]
    simulator.enqueue_event(door_open_events[0], queue_file)
    fault = post_reading(system, 5, door=True, duration=5, temperature=None)
    assert fault.status_code == 201

    timed_out = {**opened, "timestamp": timestamp(35), "open_duration_seconds": 30}
    timeout_events = producer.observe(timed_out)
    assert [event["event_type"] for event in timeout_events] == ["DOOR_TIMEOUT"]
    simulator.enqueue_event(timeout_events[0], queue_file)
    recovered = post_reading(system, 40, door=True, duration=35, temperature=4)
    assert recovered.status_code == 201

    closed = {**opened, "timestamp": timestamp(45), "door_open": False,
              "open_duration_seconds": 0}
    close_events = producer.observe(closed)
    assert [event["event_type"] for event in close_events] == ["DOOR_CLOSED"]
    simulator.enqueue_event(close_events[0], queue_file)
    queued = simulator.load_pending_events(queue_file)
    stable_ids = [event["event_id"] for event in queued]

    first_response_was_lost = {"done": False}

    def post_to_flask(url, *, json, timeout):
        response = system.post("/api/v1/events", json=json)
        result = _Response(response.status_code, response.json)
        if not first_response_was_lost["done"]:
            first_response_was_lost["done"] = True
            raise simulator.requests.Timeout("response lost after backend commit")
        return result

    monkeypatch.setattr(simulator.requests, "post", post_to_flask)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert simulator.load_pending_events(queue_file) == []
    stored_door = rows(system,
        "SELECT event_id, event_type FROM events WHERE event_type LIKE 'DOOR_%' ORDER BY id")
    assert [event["event_id"] for event in stored_door] == stable_ids
    assert [event["event_type"] for event in stored_door] == [
        "DOOR_OPENED", "DOOR_TIMEOUT", "DOOR_CLOSED"
    ]
    assert event_types(system).count("SENSOR_FAULT") == 1
    assert event_types(system).count("SENSOR_RECOVERED") == 1


@pytest.mark.parametrize("event_type", [
    "GAS_ANOMALY_STARTED", "TEMPERATURE_EXPOSURE_EXCEEDED", "SENSOR_FAULT"
])
def test_event_insert_failure_rolls_back_combined_reading_and_transition(system, event_type):
    reading_id = str(uuid.uuid4())
    if event_type == "GAS_ANOMALY_STARTED":
        connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
        connection.execute(
            """INSERT INTO gas_anomaly_state (
                   device_id, food_id, baseline, baseline_sample_count,
                   baseline_sum, consecutive_anomaly_count, anomaly_active
               ) VALUES ('CROSS-DEVICE', '', 100, 10, 1000, 2, 0)"""
        )
        connection.commit()
        connection.close()
    elif event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
        connection.execute(
            """INSERT INTO temperature_exposure_state (
                   device_id, food_id, exposure_seconds, exposure_active,
                   exposure_exceeded, last_valid_temperature_timestamp,
                   continuity_broken
               ) VALUES ('CROSS-DEVICE', '', 7200, 1, 0, ?, 0)""",
            (timestamp(0),),
        )
        connection.commit()
        connection.close()

    connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
    connection.execute(f"""CREATE TRIGGER reject_transition_event BEFORE INSERT ON events
        WHEN NEW.event_type = '{event_type}'
        BEGIN SELECT RAISE(ABORT, 'event insert failure'); END""")
    connection.commit()
    connection.close()

    kwargs = {"gas": 130}
    if event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        kwargs["temperature"] = 6
    elif event_type == "SENSOR_FAULT":
        kwargs["temperature"] = None
    with pytest.raises(sqlite3.IntegrityError):
        post_reading(system, 5, reading_id=reading_id, **kwargs)
    assert rows(system, "SELECT COUNT(*) AS n FROM sensor_readings")[0]["n"] == 0
    assert rows(system, "SELECT event_type FROM events") == []

    if event_type == "GAS_ANOMALY_STARTED":
        state = rows(system, "SELECT * FROM gas_anomaly_state")[0]
        assert state["anomaly_active"] == 0 and state["consecutive_anomaly_count"] == 2
    elif event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        state = rows(system, "SELECT * FROM temperature_exposure_state")[0]
        assert state["exposure_seconds"] == 7200 and state["exposure_exceeded"] == 0
    else:
        assert rows(system, "SELECT * FROM sensor_fault_state") == []
