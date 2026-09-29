"""Offline replay integration tests against real temporary SQLite databases."""

from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
import uuid

import pytest

from app import create_app, database
from app.init_db import init_db
from app.routes import readings


RECEIVED = datetime(2026, 9, 28, 18, 20, tzinfo=timezone.utc)
SAIGON = timezone(timedelta(hours=7))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "ingest.db")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(readings, "utc_now", lambda: RECEIVED)
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def payload(delay=1, **overrides):
    value = {
        "device_id": "FG-ESP32-01",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": (RECEIVED - timedelta(seconds=delay)).astimezone(SAIGON).isoformat(),
        "temperature_c": 4, "humidity_pct": 60, "gas_raw": 100,
        "door_open": False, "open_duration_seconds": 0,
    }
    value.update(overrides)
    return value


def rows(table):
    connection = database.get_db_connection()
    try:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
    finally:
        connection.close()


@pytest.mark.parametrize("delay,status", [
    (0, "LIVE"), (1, "LIVE"), (10, "LIVE"), (10.001, "DELAYED"),
    (60, "DELAYED"), (120, "DELAYED"), (120.001, "OFFLINE_RECOVERED"),
    (1200, "OFFLINE_RECOVERED"), (-1, "CLOCK_SKEW"), (-30, "CLOCK_SKEW"),
])
def test_ingest_boundaries_and_get_metadata(client, delay, status, caplog):
    request = payload(delay)
    response = client.post("/api/v1/readings", json=request)
    assert response.status_code == 201
    body = response.json
    assert body["success"] is True
    assert body["device_reading_id"] == request["device_reading_id"]
    assert body["duplicate"] is False
    assert body["freshness"]["status"] == "Fresh / Normal"
    for item in [body, rows("sensor_readings")[0],
                 client.get("/api/v1/readings").json["data"][0],
                 client.get("/api/v1/readings/latest").json["data"]]:
        assert item["timestamp"] == request["timestamp"]
        assert item["received_at"] == RECEIVED.isoformat()
        assert item["delivery_delay_seconds"] == pytest.approx(delay)
        assert item["ingest_status"] == status
    assert f"[READING {status}]" in caplog.text


@pytest.mark.parametrize("timestamp", [
    "", "nonsense", None, 123, "2026-09-29", "2026-09-29T01:20:00",
    "2026-09-29T01:20:00+25:00", "2026-09-29T01:20:00+07:60",
    "2026-02-30T00:00:00Z", "0001-01-01T00:00:00+07:00",
    (RECEIVED + timedelta(seconds=30.001)).isoformat(),
    (RECEIVED + timedelta(days=1)).isoformat(),
])
def test_invalid_and_future_timestamps_do_not_insert(client, timestamp, caplog):
    response = client.post("/api/v1/readings", json=payload(timestamp=timestamp))
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_TIMESTAMP"
    assert rows("sensor_readings") == []
    assert rows("gas_anomaly_state") == []
    assert "[READING ERROR]" in caplog.text


def test_timezone_equivalence(client):
    for timestamp in ("2026-09-29T01:19:59+07:00", "2026-09-28T18:19:59Z",
                      "2026-09-28T13:19:59-05:00"):
        response = client.post("/api/v1/readings", json=payload(timestamp=timestamp))
        assert response.status_code == 201
        assert response.json["delivery_delay_seconds"] == 1
        assert response.json["timestamp"] == timestamp


def test_duplicate_preserves_first_receipt_and_all_side_effects(client, monkeypatch, caplog):
    today = date.today().isoformat()
    assert client.post("/api/v1/foods", json={
        "food_id": "FOOD-1", "food_name": "Meat", "category": "MEAT",
        "inserted_at": today,
    }).status_code == 201
    assert client.post("/api/v1/foods/FOOD-1/activate").status_code == 200
    request = payload(1200, temperature_c=None)
    first = client.post("/api/v1/readings", json=request)
    assert first.status_code == 201
    tables = ("sensor_readings", "events", "notification_outbox",
              "food_freshness_snapshots", "gas_anomaly_state",
              "temperature_exposure_state", "sensor_fault_state")
    before = {table: rows(table) for table in tables}
    assert len(before["events"]) == 1
    assert len(before["notification_outbox"]) == 1
    assert len(before["food_freshness_snapshots"]) == 1
    def unexpected(*args, **kwargs):
        pytest.fail("duplicate must not evaluate freshness or repeat side effects")
    monkeypatch.setattr(readings, "evaluate_freshness", unexpected)
    monkeypatch.setattr(readings, "_persist_food_notification", unexpected)
    monkeypatch.setattr(readings, "utc_now", lambda: RECEIVED + timedelta(hours=1))
    duplicate = client.post("/api/v1/readings", json=request)
    assert duplicate.status_code == 200
    assert duplicate.json == {**first.json, "duplicate": True, "message": "Reading already exists"}
    assert {table: rows(table) for table in tables} == before
    assert "[DUPLICATE REPLAY]" in caplog.text
    # A server clock correction must not invalidate a previously committed ACK.
    monkeypatch.setattr(readings, "utc_now", lambda: RECEIVED - timedelta(days=1))
    assert client.post("/api/v1/readings", json=request).json == duplicate.json


def test_conflict_and_composite_identity(client):
    request = payload()
    assert client.post("/api/v1/readings", json=request).status_code == 201
    conflict = client.post("/api/v1/readings", json={**request, "gas_raw": 101})
    assert conflict.status_code == 409
    assert conflict.json["error"] == "DEVICE_READING_ID_CONFLICT"
    assert client.post("/api/v1/readings", json={**request, "device_id": "OTHER"}).status_code == 201
    assert len(rows("sensor_readings")) == 2


def test_migration_preserves_legacy_rows_without_fabricating_receipt(client):
    connection = database.get_db_connection()
    connection.execute("INSERT INTO sensor_readings (device_id, timestamp, door_open) "
                       "VALUES ('legacy', '2026-01-01T00:00:00Z', 0)")
    for column in ("received_at", "delivery_delay_seconds", "ingest_status"):
        connection.execute(f"ALTER TABLE sensor_readings DROP COLUMN {column}")
    connection.commit()
    before = dict(connection.execute("SELECT * FROM sensor_readings").fetchone())
    connection.close()
    init_db()
    init_db()
    after = rows("sensor_readings")[0]
    assert after == {**before, "received_at": None, "delivery_delay_seconds": None, "ingest_status": None}
    assert client.get("/api/v1/readings/latest").json["data"]["ingest_status"] is None
    assert client.post("/api/v1/readings", json=payload()).status_code == 201


def test_database_failure_rolls_back_reading_and_state(client, caplog):
    connection = database.get_db_connection()
    connection.execute("CREATE TRIGGER fail_reading BEFORE INSERT ON sensor_readings "
                       "BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END")
    connection.close()
    response = client.post("/api/v1/readings", json=payload())
    assert response.status_code == 503
    assert response.json["error"] == "DATABASE_ERROR"
    for table in ("sensor_readings", "events", "notification_outbox", "gas_anomaly_state",
                  "temperature_exposure_state", "sensor_fault_state"):
        assert rows(table) == []
    assert "db_persistence_failure" in caplog.text


def test_database_connection_failure_is_retryable(client, monkeypatch):
    def fail():
        raise sqlite3.OperationalError("injected open failure")
    monkeypatch.setattr(readings, "get_db_connection", fail)
    assert client.post("/api/v1/readings", json=payload()).status_code == 503


def test_recorded_demo(client, caplog):
    request = payload(1200, device_reading_id="2af96931-2e7d-4c37-bca9-79c59ac576ce")
    first = client.post("/api/v1/readings", json=request)
    retry = client.post("/api/v1/readings", json=request)
    assert (first.status_code, retry.status_code) == (201, 200)
    print("\nNEW RESPONSE:", json.dumps(first.json, ensure_ascii=False))
    print("DUPLICATE RESPONSE:", json.dumps(retry.json, ensure_ascii=False))
    print("RECORDED LOGS:\n" + caplog.text)
