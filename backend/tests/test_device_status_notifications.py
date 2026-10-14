"""Persistent device-status transitions share the existing Telegram outbox."""

from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
import uuid

import pytest

import app as app_module
from app import database
from app.services import telegram_notifier as notifier


@pytest.fixture
def system(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "device-status.db")
    monkeypatch.setattr(app_module, "load_dotenv", lambda *a, **kw: None)
    client = app_module.create_app().test_client()
    return client


def payload(**overrides):
    value = {
        "device_id": "FG-DEVICE-STATUS-01",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": 100,
        "door_open": False,
    }
    value.update(overrides)
    return value


def rows(table):
    connection = database.get_db_connection()
    try:
        return connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    finally:
        connection.close()


def register_unactivated_food(client, food_id):
    response = client.post("/api/v1/foods", json={
        "food_id": food_id,
        "food_name": "Demo food",
        "category": "MEAT",
        "inserted_at": date.today().isoformat(),
        "expiry_date": (date.today() + timedelta(days=1)).isoformat(),
    })
    assert response.status_code == 201


def test_device_status_transitions_are_persistent_and_transactional(system):
    client = system
    food_id = "DEVICE-DEMO-FOOD"
    register_unactivated_food(client, food_id)

    assert client.post("/api/v1/readings", json=payload()).json["freshness"]["status"] == "Fresh / Normal"
    assert client.post("/api/v1/readings", json=payload(food_id=food_id)).json["freshness"]["status"] == "Use Soon"
    assert client.post(
        "/api/v1/readings",
        json=payload(door_open=True, open_duration_seconds=30),
    ).json["freshness"]["status"] == "Check Food"
    assert client.post("/api/v1/readings", json=payload()).json["freshness"]["status"] == "Fresh / Normal"

    assert [row["notification_type"] for row in rows("notification_outbox")] == [
        "DEVICE_FRESH", "DEVICE_USE_SOON", "DEVICE_CHECK_FOOD", "DEVICE_FRESH",
    ]
    snapshot = rows("device_freshness_snapshots")
    assert len(snapshot) == 1 and snapshot[0]["freshness_status"] == "Fresh / Normal"

    # Recreate the application against the same persistent database. A same
    # status after restart must not depend on in-memory state or notify again.
    app_module.create_app()
    same = client.post("/api/v1/readings", json=payload())
    assert same.status_code == 201
    assert len(rows("notification_outbox")) == 4


def test_first_fresh_same_status_and_duplicate_do_not_create_extra_events(system):
    client = system
    reading = payload()
    first = client.post("/api/v1/readings", json=reading)
    assert first.status_code == 201
    assert len(rows("notification_outbox")) == 1

    assert client.post("/api/v1/readings", json=payload()).status_code == 201
    duplicate = client.post("/api/v1/readings", json=reading)
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert len(rows("sensor_readings")) == 2
    assert len(rows("notification_outbox")) == 1


def test_device_telegram_failure_keeps_reading_ack_and_outbox(system, monkeypatch):
    client = system
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:mock")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(notifier, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(TimeoutError()))

    response = client.post("/api/v1/readings", json=payload())
    assert response.status_code == 201
    worker = notifier.TelegramNotificationWorker()
    assert worker.run_once() == 1
    outbox = rows("notification_outbox")
    assert outbox[0]["notification_type"] == "DEVICE_FRESH"
    assert outbox[0]["delivery_status"] in {"PENDING", "FAILED"}


@pytest.mark.parametrize(("notification_type", "title", "temperature"), [
    ("DEVICE_FRESH", "FreshGuard Status Changed", 5),
    ("DEVICE_USE_SOON", "FreshGuard Warning", None),
    ("DEVICE_CHECK_FOOD", "FreshGuard Alert", 15),
])
def test_device_message_format(notification_type, title, temperature):
    text = notifier.build_message({
        "notification_type": notification_type,
        "device_id": "FG-01",
        "previous_status": "Unknown / Initial",
        "current_status": "Fresh / Normal",
        "temperature_c": temperature,
        "reading_timestamp": "2026-10-05T10:00:00+07:00",
    })
    assert title in text
    assert "Device: FG-01" in text
    assert "Previous: Unknown / Initial" in text
    assert "Temperature: N/A C" in text if temperature is None else f"Temperature: {temperature} C" in text
