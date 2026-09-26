import sqlite3
from datetime import datetime, timedelta, timezone
import uuid

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings as readings_module
from app.services.temperature_exposure import (
    TEMPERATURE_EXPOSURE_LIMIT_SECONDS,
    update_temperature_exposure,
)


@pytest.fixture
def temperature_client(tmp_path, monkeypatch):
    database_path = tmp_path / "temperature-exposure.db"

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


def iso_time(seconds=0):
    return (datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
            + timedelta(seconds=seconds)).isoformat()


def post_temperature(client, temperature, seconds=0, food_id=None, device="TEMP-DEVICE",
                     reading_id=None):
    payload = {
        "device_id": device,
        "timestamp": iso_time(seconds),
        "temperature_c": temperature,
        "humidity_pct": 60,
        "gas_raw": 100,
        "door_open": False,
    }
    if food_id is not None:
        payload["food_id"] = food_id
    payload["device_reading_id"] = reading_id or str(uuid.uuid4())
    return client.post("/api/v1/readings", json=payload)


def db_connect(client):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    return connection


def state_for(client, device="TEMP-DEVICE", food_id=None):
    connection = db_connect(client)
    try:
        return connection.execute(
            "SELECT * FROM temperature_exposure_state "
            "WHERE device_id = ? AND food_id = ?",
            (device, food_id or ""),
        ).fetchone()
    finally:
        connection.close()


def temperature_events(client):
    connection = db_connect(client)
    try:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM events WHERE event_type = "
            "'TEMPERATURE_EXPOSURE_EXCEEDED' ORDER BY id"
        )]
    finally:
        connection.close()


def prime_exposure_state(client, *, device="TEMP-DEVICE", food_id=None,
                         exposure_seconds=7200, exceeded=False, last_seconds=0):
    connection = db_connect(client)
    try:
        connection.execute(
            """INSERT INTO temperature_exposure_state (
                   device_id, food_id, exposure_seconds, exposure_active,
                   exposure_exceeded, last_valid_temperature_timestamp
               ) VALUES (?, ?, ?, 1, ?, ?)""",
            (device, food_id or "", exposure_seconds, int(exceeded), iso_time(last_seconds)),
        )
        connection.commit()
    finally:
        connection.close()


def test_at_or_below_five_resets_and_never_emits_temperature_event(temperature_client):
    for temperature in (4, 5):
        response = post_temperature(temperature_client, temperature)
        assert response.status_code == 201
        assert response.json["freshness"]["status"] == "Fresh / Normal"
        assert state_for(temperature_client)["exposure_seconds"] == 0
    assert temperature_events(temperature_client) == []


def test_first_hot_reading_starts_exposure_without_event(temperature_client):
    response = post_temperature(temperature_client, 6)
    assert response.json["freshness"]["status"] == "Fresh / Normal"
    state = state_for(temperature_client)
    assert state["exposure_active"] == 1
    assert state["exposure_seconds"] == 0
    assert temperature_events(temperature_client) == []


def test_exposure_threshold_is_strictly_greater_than_two_hours():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE temperature_exposure_state (
        device_id TEXT NOT NULL, food_id TEXT NOT NULL DEFAULT '',
        exposure_seconds REAL NOT NULL DEFAULT 0,
        exposure_active INTEGER NOT NULL DEFAULT 0,
        exposure_exceeded INTEGER NOT NULL DEFAULT 0,
        last_valid_temperature_timestamp TEXT NULL,
        continuity_broken INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(device_id, food_id)
    )""")
    try:
        update_temperature_exposure(connection, "D", None, 6, iso_time(0))
        result = None
        # Use ten-second intervals up to exactly two hours.
        for second in range(10, TEMPERATURE_EXPOSURE_LIMIT_SECONDS + 1, 10):
            result = update_temperature_exposure(connection, "D", None, 6, iso_time(second))
        assert result.exposure_seconds == TEMPERATURE_EXPOSURE_LIMIT_SECONDS
        assert result.exceeded_transition is False
        result = update_temperature_exposure(
            connection, "D", None, 6, iso_time(TEMPERATURE_EXPOSURE_LIMIT_SECONDS + 10)
        )
        assert result.exposure_seconds == TEMPERATURE_EXPOSURE_LIMIT_SECONDS + 10
        assert result.exceeded_transition is True
        result = update_temperature_exposure(
            connection, "D", None, 6, iso_time(TEMPERATURE_EXPOSURE_LIMIT_SECONDS + 20)
        )
        assert result.exceeded_transition is False
    finally:
        connection.close()


def test_backend_emits_one_event_on_threshold_transition_and_no_spam(temperature_client):
    prime_exposure_state(temperature_client)
    trigger_id = str(uuid.uuid4())
    response = post_temperature(
        temperature_client, 6, seconds=5, reading_id=trigger_id
    )
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Check Food"
    for seconds in (10, 15, 20, 25):
        post_temperature(temperature_client, 7, seconds=seconds)
    events = temperature_events(temperature_client)
    assert len(events) == 1
    assert events[0]["event_type"] == "TEMPERATURE_EXPOSURE_EXCEEDED"
    assert events[0]["timestamp"] == iso_time(5)
    assert str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"freshguard:temperature:TEMP-DEVICE:{trigger_id}:TEMPERATURE_EXPOSURE_EXCEEDED",
    )) == events[0]["event_id"]


def test_valid_normal_resets_period_and_allows_a_later_event(temperature_client):
    prime_exposure_state(temperature_client, last_seconds=0)
    post_temperature(temperature_client, 6, seconds=5)
    assert len(temperature_events(temperature_client)) == 1
    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 7205
    post_temperature(temperature_client, 5, seconds=10)
    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 0
    assert state["exposure_active"] == 0
    post_temperature(temperature_client, 6, seconds=15)
    assert state_for(temperature_client)["exposure_seconds"] == 0

    connection = db_connect(temperature_client)
    try:
        for second in range(25, 7216, 10):
            update_temperature_exposure(
                connection, "TEMP-DEVICE", None, 6, iso_time(second)
            )
        connection.commit()
    finally:
        connection.close()
    post_temperature(temperature_client, 6, seconds=7220)
    events = temperature_events(temperature_client)
    assert len(events) == 2
    assert events[0]["event_type"] == events[1]["event_type"]


def test_invalid_temperature_preserves_exposure_and_breaks_continuity(temperature_client):
    prime_exposure_state(temperature_client, exposure_seconds=400)
    invalid = post_temperature(temperature_client, None, seconds=5)
    assert invalid.status_code == 201
    after_invalid = state_for(temperature_client)
    assert after_invalid["exposure_seconds"] == 400
    assert after_invalid["continuity_broken"] == 1
    post_temperature(temperature_client, 6, seconds=10)
    assert state_for(temperature_client)["exposure_seconds"] == 400
    post_temperature(temperature_client, 6, seconds=15)
    assert state_for(temperature_client)["exposure_seconds"] == 405
    assert temperature_events(temperature_client) == []


@pytest.mark.parametrize("invalid", [True, False, float("nan"), float("inf"), -float("inf")])
def test_rejected_invalid_temperature_values_do_not_reset_exposure(temperature_client, invalid):
    prime_exposure_state(temperature_client, exposure_seconds=400)
    response = post_temperature(temperature_client, invalid, seconds=5)
    assert response.status_code == 400
    assert state_for(temperature_client)["exposure_seconds"] == 400
    assert temperature_events(temperature_client) == []


def test_long_reading_gap_is_not_counted_as_observed_exposure(temperature_client):
    post_temperature(temperature_client, 6, seconds=0)
    post_temperature(temperature_client, 6, seconds=3 * 60 * 60)
    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 0
    post_temperature(temperature_client, 6, seconds=3 * 60 * 60 + 5)
    assert state_for(temperature_client)["exposure_seconds"] == 5
    assert temperature_events(temperature_client) == []


def test_out_of_order_reading_does_not_corrupt_exposure_state(temperature_client):
    prime_exposure_state(temperature_client, exposure_seconds=100, last_seconds=20)
    post_temperature(temperature_client, 6, seconds=10)
    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 100
    assert state["last_valid_temperature_timestamp"] == iso_time(20)
    post_temperature(temperature_client, 6, seconds=25)
    assert state_for(temperature_client)["exposure_seconds"] == 105


def test_duplicate_and_lost_response_retry_update_exposure_once(temperature_client):
    prime_exposure_state(temperature_client, exposure_seconds=7200)
    reading_id = str(uuid.uuid4())
    first = post_temperature(temperature_client, 6, seconds=5, reading_id=reading_id)
    retry = post_temperature(temperature_client, 6, seconds=5, reading_id=reading_id)
    assert first.status_code == 201
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    assert state_for(temperature_client)["exposure_seconds"] == 7205
    assert len(temperature_events(temperature_client)) == 1
    connection = db_connect(temperature_client)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?",
            (reading_id,),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_post_latest_and_history_return_persisted_exposure_freshness(temperature_client):
    prime_exposure_state(temperature_client, exposure_seconds=7200, exceeded=True)
    response = post_temperature(temperature_client, 6, seconds=5)
    assert response.status_code == 201
    expected = response.json["freshness"]
    assert expected["status"] == "Check Food"

    latest = temperature_client.get("/api/v1/readings/latest")
    history = temperature_client.get("/api/v1/readings")
    assert latest.status_code == 200
    assert latest.json["data"]["freshness"] == expected
    assert history.status_code == 200
    assert history.json["data"][0]["freshness"] == expected


def test_exposure_state_survives_new_client_and_is_scoped_by_device_food(temperature_client):
    for food_id in ("food-A", "food-B"):
        response = temperature_client.post("/api/v1/foods", json={
            "food_id": food_id, "food_name": food_id, "category": "MEAT",
            "inserted_at": "2026-09-26", "expiry_date": "2027-09-26",
        })
        assert response.status_code == 201
    prime_exposure_state(
        temperature_client, device="A", food_id="food-A", exposure_seconds=90
    )
    restarted_client = temperature_client.application.test_client()
    post_temperature(restarted_client, 6, seconds=5, device="A", food_id="food-A")
    assert state_for(restarted_client, "A", "food-A")["exposure_seconds"] == 95
    assert state_for(restarted_client, "A", "food-B") is None
    assert state_for(restarted_client, "B", "food-A") is None
    assert state_for(restarted_client, "A", None) is None


def test_event_failure_rolls_back_reading_and_exposure_state(temperature_client):
    prime_exposure_state(temperature_client)
    connection = db_connect(temperature_client)
    try:
        connection.execute("""CREATE TRIGGER reject_temperature_event
            BEFORE INSERT ON events
            WHEN NEW.event_type = 'TEMPERATURE_EXPOSURE_EXCEEDED'
            BEGIN SELECT RAISE(ABORT, 'event insert failure'); END""")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(sqlite3.IntegrityError):
        post_temperature(temperature_client, 6, seconds=5, reading_id=str(uuid.uuid4()))

    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 7200
    connection = db_connect(temperature_client)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE timestamp = ?",
            (iso_time(5),),
        ).fetchone()[0] == 0
    finally:
        connection.close()
