"""Feature 3 offline replay checks across simulator, backend and dashboard APIs."""

from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
import uuid

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import events as events_module
from app.routes import readings as readings_module
from app.services import telegram_notifier as notifier
from firmware import simulator



def timestamp(second):
    return (datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
            + timedelta(seconds=second)).isoformat()


def measured_epoch(value):
    return datetime.fromisoformat(value).timestamp()


class Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    def json(self):
        return self.body


def _reading(device, second, **overrides):
    value = {
        "device_id": device,
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": timestamp(second),
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": 100,
        "door_open": False,
        "open_duration_seconds": 0,
    }
    value.update(overrides)
    return value


def _db(client):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    return connection


@pytest.fixture
def system(tmp_path, monkeypatch):
    database_path = tmp_path / "feature3.db"

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


def test_offline_replay_resolves_device_food_and_food_notifications(system, tmp_path, monkeypatch):
    device = "FG-ESP32-01"
    food = system.post("/api/v1/foods", json={
        "food_id": "FG-OFFLINE-APPLE",
        "food_name": "Apple",
        "category": "FRUIT",
        "quantity": 3,
        "inserted_at": date.today().isoformat(),
        "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
        "device_id": device,
    })
    assert food.status_code == 201

    # Isolate reading transitions from the initial Food Added event.
    connection = _db(system)
    connection.execute("DELETE FROM notification_outbox")
    connection.commit()
    connection.close()

    first = system.post("/api/v1/readings", json=_reading(device, 0))
    assert first.status_code == 201
    assert first.json["freshness"]["status"] == "Fresh / Normal"

    connection = _db(system)
    connection.execute(
        "UPDATE food_items SET expiry_date=? WHERE food_id=?",
        (date.today().isoformat(), "FG-OFFLINE-APPLE"),
    )
    connection.commit()
    connection.close()

    queue_file = tmp_path / "pending_readings.jsonl"
    queued = [
        _reading(device, 60),
        _reading(device, 120, door_open=True, open_duration_seconds=30),
    ]
    for item in queued:
        assert simulator.enqueue_reading(item, queue_file)

    online = {"value": False}

    def post_to_backend(_url, *, json, timeout):
        if not online["value"]:
            raise simulator.requests.ConnectionError("backend stopped")
        response = system.post("/api/v1/readings", json=json)
        return Response(response.status_code, response.json)

    monkeypatch.setattr(simulator.requests, "post", post_to_backend)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)
    assert simulator.load_pending_readings(queue_file) == queued

    online["value"] = True
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)
    assert simulator.load_pending_readings(queue_file) == []

    history = system.get(f"/api/v1/readings?device_id={device}&limit=20").json["data"]
    assert [measured_epoch(item["timestamp"]) for item in history] == [
        measured_epoch(timestamp(120)), measured_epoch(timestamp(60)), measured_epoch(timestamp(0)),
    ]
    assert all(item["food_id"] == "FG-OFFLINE-APPLE" for item in history)
    assert history[1]["ingest_status"] == "OFFLINE_RECOVERED"
    assert history[2]["ingest_status"] == "OFFLINE_RECOVERED"

    connection = _db(system)
    try:
        outbox = connection.execute(
            "SELECT notification_type, payload_json FROM notification_outbox ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    assert [row["notification_type"] for row in outbox] == [
        "FOOD_USE_SOON", "FOOD_CHECK_FOOD",
    ]
    payload = json.loads(outbox[0]["payload_json"])
    message = notifier.build_message(payload)
    assert "Measured at: " + json.loads(outbox[0]["payload_json"])["reading_timestamp"] in message
    assert "DEVICE_USE_SOON" not in message


def test_realtime_insert_before_replay_still_has_measured_timestamp_order(system, tmp_path, monkeypatch):
    device = "FG-MIXED-OFFLINE"
    queue_file = tmp_path / "mixed.jsonl"
    old = [_reading(device, 60), _reading(device, 120), _reading(device, 180)]
    for item in old:
        simulator.enqueue_reading(item, queue_file)

    realtime = _reading(device, 600)
    assert system.post("/api/v1/readings", json=realtime).status_code == 201

    def post_to_backend(_url, *, json, timeout):
        response = system.post("/api/v1/readings", json=json)
        return Response(response.status_code, response.json)

    monkeypatch.setattr(simulator.requests, "post", post_to_backend)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    history = system.get(f"/api/v1/readings?device_id={device}&limit=20").json["data"]
    assert [measured_epoch(item["timestamp"]) for item in history] == [
        measured_epoch(timestamp(600)), measured_epoch(timestamp(180)),
        measured_epoch(timestamp(120)), measured_epoch(timestamp(60))
    ]
