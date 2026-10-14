from datetime import date, datetime, timedelta, timezone
import sqlite3
import uuid

import pytest

import app as app_module
from app import database
from app.services import telegram_notifier as notifier


@pytest.fixture
def system(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "feature2.db")
    monkeypatch.setattr(app_module, "load_dotenv", lambda *a, **kw: None)
    return app_module.create_app().test_client()


def food(food_id, name, category="FRUIT", expiry_days=10, device_id=None):
    data = {
        "food_id": food_id,
        "food_name": name,
        "category": category,
        "quantity": 3,
        "inserted_at": date.today().isoformat(),
        "expiry_date": (date.today() + timedelta(days=expiry_days)).isoformat(),
    }
    if device_id is not None:
        data["device_id"] = device_id
    return data


def reading(device_id):
    return {
        "device_id": device_id,
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": 100,
        "door_open": False,
    }


def db_rows(table):
    connection = database.get_db_connection()
    try:
        return connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
    finally:
        connection.close()


def test_add_food_assigns_device_and_enqueues_food_added_once(system):
    response = system.post("/api/v1/foods", json=food("FG-APPLE-001", "Apple", device_id="FG-ESP32-01"))
    assert response.status_code == 201
    assert system.get("/api/v1/foods/active?device_id=FG-ESP32-01").json["data"][0]["food_id"] == "FG-APPLE-001"
    outbox = db_rows("notification_outbox")
    assert len(outbox) == 1 and outbox[0]["notification_type"] == "FOOD_ADDED"

    duplicate = system.post("/api/v1/foods", json=food("FG-APPLE-001", "Apple", device_id="FG-ESP32-01"))
    assert duplicate.status_code == 409
    assert len(db_rows("food_items")) == 1
    assert len(db_rows("notification_outbox")) == 1


def test_add_food_keeps_multiple_device_mappings_without_deleting_old_food(system):
    system.post("/api/v1/foods", json=food("FG-APPLE-001", "Apple", device_id="FG-ESP32-01"))
    system.post("/api/v1/foods", json=food("FG-MILK-001", "Milk", category="DAIRY", device_id="FG-ESP32-01"))
    active = system.get("/api/v1/foods/active?device_id=FG-ESP32-01").json["data"]
    assert [row["food_id"] for row in active] == ["FG-APPLE-001", "FG-MILK-001"]
    freshness = system.get("/api/v1/foods/active/freshness?device_id=FG-ESP32-01")
    assert freshness.status_code == 200
    assert [row["food_id"] for row in freshness.json["data"]] == ["FG-APPLE-001", "FG-MILK-001"]
    assert {row["food_id"] for row in db_rows("food_items")} == {"FG-APPLE-001", "FG-MILK-001"}


def test_reading_resolves_only_device_specific_food(system):
    system.post("/api/v1/foods", json=food("FG-APPLE-001", "Apple", expiry_days=10, device_id="DEVICE-A"))
    system.post("/api/v1/foods", json=food("FG-MILK-001", "Milk", category="DAIRY", expiry_days=0, device_id="DEVICE-B"))

    reading_a = system.post("/api/v1/readings", json=reading("DEVICE-A"))
    reading_b = system.post("/api/v1/readings", json=reading("DEVICE-B"))
    assert reading_a.status_code == 201
    assert reading_b.status_code == 201
    assert reading_a.json["freshness"]["status"] == "Fresh / Normal"
    assert reading_b.json["freshness"]["status"] == "Use Soon"
    latest_a = system.get("/api/v1/readings?device_id=DEVICE-A&limit=1").json["data"][0]
    assert latest_a["food_id"] == "FG-APPLE-001"

    snapshots = db_rows("food_freshness_snapshots")
    assert {row["food_id"] for row in snapshots} == {"FG-APPLE-001", "FG-MILK-001"}


def test_food_added_telegram_failure_does_not_rollback_food(system, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:mock")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(notifier, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(TimeoutError()))

    response = system.post("/api/v1/foods", json=food("FG-APPLE-001", "Apple", device_id="FG-ESP32-01"))
    assert response.status_code == 201
    worker = notifier.TelegramNotificationWorker()
    assert worker.run_once() == 1
    assert db_rows("food_items")[0]["food_id"] == "FG-APPLE-001"
    assert db_rows("notification_outbox")[0]["delivery_status"] in {"PENDING", "FAILED"}


def test_food_added_message_handles_optional_fields():
    message = notifier.build_message({
        "notification_type": "FOOD_ADDED",
        "food_id": "FG-APPLE-001",
        "food_name": "Apple",
        "category": None,
        "quantity": None,
        "device_id": "FG-ESP32-01",
        "added_at": "2026-10-05T10:00:00+00:00",
    })
    assert "Food Added" in message
    assert "Code: FG-APPLE-001" in message
    assert "Category: N/A" in message
    assert "Quantity: N/A" in message
