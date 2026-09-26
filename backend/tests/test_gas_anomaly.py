import sqlite3
import uuid
from datetime import date, timedelta

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings as readings_module
from app.services.freshness import FreshnessStatus, evaluate_freshness
from app.services.gas_anomaly import (
    GAS_ANOMALY_DEVIATION,
    GAS_BASELINE_SAMPLE_COUNT,
    GAS_REQUIRED_CONSECUTIVE_READINGS,
    update_gas_anomaly_state,
)


@pytest.fixture
def gas_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE gas_anomaly_state (
        device_id TEXT NOT NULL, food_id TEXT NOT NULL DEFAULT '',
        baseline REAL NULL, baseline_sample_count INTEGER NOT NULL DEFAULT 0,
        baseline_sum REAL NOT NULL DEFAULT 0,
        consecutive_anomaly_count INTEGER NOT NULL DEFAULT 0,
        anomaly_active INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (device_id, food_id)
    )""")
    yield connection
    connection.close()


def update(connection, gas, device="device-a", food="food-a"):
    return update_gas_anomaly_state(connection, device, food, gas)


def state(connection, device="device-a", food="food-a"):
    return connection.execute(
        "SELECT * FROM gas_anomaly_state WHERE device_id = ? AND food_id = ?",
        (device, food or ""),
    ).fetchone()


def establish_baseline(connection, value=100, device="device-a", food="food-a"):
    for _ in range(GAS_BASELINE_SAMPLE_COUNT):
        update(connection, value, device, food)


def test_baseline_is_average_of_first_ten_valid_readings_and_stays_fixed(gas_db):
    for value in range(10, 110, 10):
        update(gas_db, value)
    row = state(gas_db)
    assert row["baseline_sample_count"] == 10
    assert row["baseline"] == pytest.approx(55)
    update(gas_db, 1000)
    assert state(gas_db)["baseline"] == pytest.approx(55)


def test_incomplete_baseline_does_not_flag_anomaly(gas_db):
    for _ in range(GAS_BASELINE_SAMPLE_COUNT - 1):
        assert update(gas_db, 100) is False
    assert state(gas_db)["baseline"] is None
    assert state(gas_db)["baseline_sample_count"] == 9


def test_zero_baseline_is_not_used_for_relative_deviation(gas_db):
    establish_baseline(gas_db, value=0)
    for _ in range(5):
        assert update(gas_db, 10000) is False
    assert state(gas_db)["baseline"] == 0


@pytest.mark.parametrize(
    ("value", "candidate"),
    [(129.99, False), (130, True), (150, True), (50, False)],
)
def test_relative_deviation_candidate_threshold(gas_db, value, candidate):
    establish_baseline(gas_db)
    active = update(gas_db, value)
    assert active is False
    assert GAS_ANOMALY_DEVIATION == 0.30
    assert state(gas_db)["consecutive_anomaly_count"] == int(candidate)


def test_three_consecutive_candidates_activate_and_normal_clears(gas_db):
    establish_baseline(gas_db)
    assert [update(gas_db, 130) for _ in range(3)] == [False, False, True]
    assert state(gas_db)["anomaly_active"] == 1
    assert update(gas_db, 100) is False
    assert state(gas_db)["consecutive_anomaly_count"] == 0
    assert state(gas_db)["anomaly_active"] == 0
    assert GAS_REQUIRED_CONSECUTIVE_READINGS == 3


def test_active_anomaly_remains_active_while_readings_keep_exceeding_threshold(gas_db):
    establish_baseline(gas_db)
    for _ in range(4):
        active = update(gas_db, 130)
    assert active is True
    assert state(gas_db)["consecutive_anomaly_count"] == 4


def test_active_anomaly_survives_invalid_and_anomalous_interleaving(gas_db):
    establish_baseline(gas_db)
    for _ in range(3):
        update(gas_db, 130)
    assert state(gas_db)["anomaly_active"] == 1

    for invalid in (None, -1, None):
        assert update(gas_db, invalid) is True
        assert state(gas_db)["anomaly_active"] == 1
        assert update(gas_db, 130) is True
        assert state(gas_db)["anomaly_active"] == 1

    assert update(gas_db, 90) is False
    assert state(gas_db)["anomaly_active"] == 0


def test_anomaly_gap_resets_count_and_requires_three_again(gas_db):
    establish_baseline(gas_db)
    update(gas_db, 130)
    update(gas_db, 130)
    update(gas_db, 129)
    assert state(gas_db)["consecutive_anomaly_count"] == 0
    assert [update(gas_db, 130) for _ in range(3)] == [False, False, True]


def test_contexts_are_isolated_by_device_and_food(gas_db):
    establish_baseline(gas_db)
    assert update(gas_db, 130) is False
    assert state(gas_db, device="device-b", food="food-a") is None
    assert update(gas_db, 130, device="device-b", food="food-a") is False

    establish_baseline(gas_db, value=200, device="device-a", food="food-b")
    assert state(gas_db, device="device-a", food="food-b")["baseline"] == 200
    assert state(gas_db, device="device-a", food="food-a")["baseline"] == 100


@pytest.mark.parametrize("invalid", [None, True, False, float("nan"), float("inf"), -float("inf"), -1])
def test_invalid_gas_does_not_seed_baseline_or_activate_anomaly(gas_db, invalid):
    establish_baseline(gas_db)
    update(gas_db, 130)
    assert update(gas_db, invalid) is False
    assert state(gas_db)["baseline_sample_count"] == 10
    assert state(gas_db)["consecutive_anomaly_count"] == 0


@pytest.mark.parametrize("invalid", [None, True, False, float("nan"), float("inf"), -float("inf"), -1])
def test_invalid_gas_preserves_an_active_anomaly(gas_db, invalid):
    establish_baseline(gas_db)
    for _ in range(3):
        update(gas_db, 130)
    assert state(gas_db)["anomaly_active"] == 1
    assert update(gas_db, invalid) is True
    assert state(gas_db)["anomaly_active"] == 1
    assert state(gas_db)["consecutive_anomaly_count"] == 0
    assert update(gas_db, 100) is False
    assert state(gas_db)["anomaly_active"] == 0


def test_freshness_aggregation_keeps_gas_and_other_rules_independent():
    def result(**overrides):
        values = dict(
            temperature_c=5, humidity_pct=60, gas_raw=100,
            door_open=False, open_duration_seconds=0,
        )
        values.update(overrides)
        return evaluate_freshness(**values)

    anomaly = result(gas_anomaly_active=True)
    assert anomaly.status == FreshnessStatus.CHECK_FOOD
    assert "gas" in anomaly.reason.lower() and "baseline" in anomaly.reason.lower()
    assert result(gas_raw=-1).status == FreshnessStatus.CHECK_FOOD
    assert result(temperature_c=None, gas_anomaly_active=False).status == FreshnessStatus.CHECK_FOOD
    assert result(expiry_date="2000-01-01", gas_anomaly_active=False).status == FreshnessStatus.CHECK_FOOD
    assert result(category="MEAT", inserted_at="2000-01-01", gas_anomaly_active=False).status == FreshnessStatus.CHECK_FOOD
    today = date.today()
    assert result(category="MEAT", inserted_at=today, gas_anomaly_active=False).status == FreshnessStatus.FRESH
    assert result(expiry_date=today + timedelta(days=1)).status == FreshnessStatus.USE_SOON


def test_gas_recovery_leaves_other_rules_to_determine_final_severity(gas_db):
    establish_baseline(gas_db)
    for _ in range(3):
        update(gas_db, 130)
    assert state(gas_db)["anomaly_active"] == 1
    assert update(gas_db, 100) is False

    result = evaluate_freshness(
        temperature_c=10, temperature_exposure_hours=2.1,
        humidity_pct=60, gas_raw=100, gas_anomaly_active=False,
        door_open=False, category="MEAT", inserted_at="2000-01-01",
        expiry_date="2000-01-01",
    )
    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "temperature" in result.reason.lower()
    assert "storage duration" in result.reason.lower()
    assert "expiry date" in result.reason.lower()


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    database_path = tmp_path / "gas-anomaly-integration.db"

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


def post_gas(client, gas, food_id=None, device="FG-GAS-DEVICE", reading_id=None, timestamp=None):
    payload = {
        "device_id": device,
        "device_reading_id": reading_id or str(uuid.uuid4()),
        "timestamp": timestamp or "2026-09-26T12:00:00+07:00",
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": gas,
        "door_open": False,
    }
    if food_id is not None:
        payload["food_id"] = food_id
    return client.post("/api/v1/readings", json=payload)


def gas_events(client):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM events WHERE event_type LIKE 'GAS_%' ORDER BY id"
        )]
    finally:
        connection.close()


def gas_state(client, device="FG-GAS-DEVICE", food_id=None):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            "SELECT * FROM gas_anomaly_state WHERE device_id = ? AND food_id = ?",
            (device, food_id or ""),
        ).fetchone()
    finally:
        connection.close()


def prime_and_activate(client, food_id=None, device="FG-GAS-DEVICE"):
    for _ in range(10):
        post_gas(client, 100, food_id=food_id, device=device)
    post_gas(client, 130, food_id=food_id, device=device)
    post_gas(client, 130, food_id=food_id, device=device)
    return post_gas(client, 130, food_id=food_id, device=device)


def test_api_activates_after_ten_baseline_and_three_anomaly_readings(api_client):
    for _ in range(10):
        assert post_gas(api_client, 100).json["freshness"]["status"] == "Fresh / Normal"
    assert post_gas(api_client, 130).json["freshness"]["status"] == "Fresh / Normal"
    assert post_gas(api_client, 130).json["freshness"]["status"] == "Fresh / Normal"
    active = post_gas(api_client, 130)
    assert active.json["freshness"]["status"] == "Check Food"
    assert "gas" in active.json["freshness"]["reason"].lower()
    assert api_client.get("/api/v1/readings/latest").json["data"]["freshness"] == active.json["freshness"]


def test_api_gas_recovery_does_not_clear_other_freshness_conditions(api_client):
    for _ in range(10):
        post_gas(api_client, 100)
    for _ in range(3):
        post_gas(api_client, 130)
    recovered = post_gas(api_client, 100)
    assert recovered.json["freshness"]["status"] == "Fresh / Normal"


def test_api_gas_context_separates_devices_and_foods(api_client):
    response = api_client.post("/api/v1/foods", json={
        "food_id": "food-B", "food_name": "Food B", "category": "MEAT",
        "inserted_at": "2026-09-26", "expiry_date": "2027-09-26",
    })
    assert response.status_code == 201
    for _ in range(10):
        post_gas(api_client, 100, device="A")
    for _ in range(3):
        post_gas(api_client, 130, device="A")
    assert post_gas(api_client, 130, device="B").json["freshness"]["status"] == "Fresh / Normal"
    assert post_gas(api_client, 130, food_id="food-B", device="A").json["freshness"]["status"] == "Fresh / Normal"


def test_api_emits_only_start_and_recovery_state_transitions(api_client):
    prime_and_activate(api_client)
    for _ in range(120):
        post_gas(api_client, 130)
    events = gas_events(api_client)
    assert [event["event_type"] for event in events] == ["GAS_ANOMALY_STARTED"]

    recovered = post_gas(api_client, 100, timestamp="2026-09-26T12:30:00+07:00")
    post_gas(api_client, 100)
    post_gas(api_client, 100)
    events = gas_events(api_client)
    assert [event["event_type"] for event in events] == [
        "GAS_ANOMALY_STARTED", "GAS_ANOMALY_RECOVERED"
    ]
    assert events[1]["timestamp"] == "2026-09-26T12:30:00+07:00"
    assert recovered.status_code == 201


def test_api_invalid_gas_does_not_recover_but_valid_normal_does(api_client):
    prime_and_activate(api_client)
    for invalid in (None, -1):
        response = post_gas(api_client, invalid)
        assert response.status_code == 201
        assert gas_state(api_client)["anomaly_active"] == 1
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]
    for value in (130, None, 130):
        response = post_gas(api_client, value)
        assert response.status_code == 201
        assert gas_state(api_client)["anomaly_active"] == 1
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]
    post_gas(api_client, 100)
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED", "GAS_ANOMALY_RECOVERED"
    ]


@pytest.mark.parametrize("invalid", [True, False, float("nan"), float("inf"), -float("inf")])
def test_api_rejects_invalid_gas_values_before_state_transition(api_client, invalid):
    prime_and_activate(api_client)
    response = post_gas(api_client, invalid)
    assert response.status_code == 400
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]


def test_api_retry_and_lost_response_keep_one_reading_and_gas_event(api_client):
    for _ in range(10):
        post_gas(api_client, 100)
    post_gas(api_client, 130)
    post_gas(api_client, 130)
    reading_id = str(uuid.uuid4())
    timestamp = "2026-09-26T13:00:00+07:00"
    first = post_gas(api_client, 130, reading_id=reading_id, timestamp=timestamp)
    # Treat the committed response as lost, then retry the identical reading.
    retry = post_gas(api_client, 130, reading_id=reading_id, timestamp=timestamp)
    assert first.status_code == 201
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    connection = sqlite3.connect(api_client.application.config["TEST_DB_PATH"])
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?",
            (reading_id,),
        ).fetchone()[0] == 1
    finally:
        connection.close()
    events = gas_events(api_client)
    assert [event["event_type"] for event in events] == ["GAS_ANOMALY_STARTED"]
    assert events[0]["timestamp"] == timestamp


def test_api_gas_events_are_isolated_by_food_and_none_context(api_client):
    for food_id in ("food-A", "food-B"):
        response = api_client.post("/api/v1/foods", json={
            "food_id": food_id, "food_name": food_id, "category": "MEAT",
            "inserted_at": "2026-09-26", "expiry_date": "2027-09-26",
        })
        assert response.status_code == 201
    prime_and_activate(api_client, food_id="food-A", device="same-device")
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]
    for food_id in ("food-B", None):
        for _ in range(10):
            post_gas(api_client, 100, food_id=food_id, device="same-device")
        for _ in range(3):
            post_gas(api_client, 130, food_id=food_id, device="same-device")
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED", "GAS_ANOMALY_STARTED", "GAS_ANOMALY_STARTED"
    ]


def test_api_waits_for_third_consecutive_anomaly_before_start_event(api_client):
    for _ in range(10):
        post_gas(api_client, 100)
    post_gas(api_client, 130)
    post_gas(api_client, 130)
    assert gas_events(api_client) == []
    post_gas(api_client, 130)
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]
