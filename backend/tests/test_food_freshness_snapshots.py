import sqlite3
from datetime import date, timedelta
import uuid

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings as readings_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "freshguard-snapshots.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    init_db_module.init_db()
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def add_food(client, food_id, name, expiry):
    response = client.post("/api/v1/foods", json={
        "food_id": food_id,
        "food_name": name,
        "category": "MEAT",
        "inserted_at": date.today().isoformat(),
        "expiry_date": expiry,
    })
    assert response.status_code == 201
    assert client.post(f"/api/v1/foods/{food_id}/activate").status_code == 200


def reading_payload(**overrides):
    payload = {
        "device_id": "FG-ESP32-01",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": "2026-09-28T12:00:00+07:00",
        "temperature_c": 4,
        "humidity_pct": 50,
        "gas_raw": 100,
        "door_open": False,
    }
    payload.update(overrides)
    return payload


def test_one_raw_reading_creates_one_snapshot_per_active_food(client):
    today = date.today()
    add_food(client, "FRESH", "Fresh Beef", (today + timedelta(days=10)).isoformat())
    add_food(client, "SOON", "Soon Beef", today.isoformat())
    add_food(client, "EXPIRED", "Expired Beef", (today - timedelta(days=1)).isoformat())

    response = client.post("/api/v1/readings", json=reading_payload())
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Check Food"

    connection = readings_module.get_db_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0] == 1
        rows = connection.execute(
            "SELECT food_id, freshness_status FROM food_freshness_snapshots ORDER BY food_id"
        ).fetchall()
        assert [(row["food_id"], row["freshness_status"]) for row in rows] == [
            ("EXPIRED", "Check Food"),
            ("FRESH", "Fresh / Normal"),
            ("SOON", "Use Soon"),
        ]
    finally:
        connection.close()


def test_zero_active_foods_preserves_foodless_reading_behavior(client):
    response = client.post("/api/v1/readings", json=reading_payload())
    assert response.status_code == 201
    connection = readings_module.get_db_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM food_freshness_snapshots").fetchone()[0] == 0
    finally:
        connection.close()


def test_duplicate_does_not_create_snapshots_again(client):
    today = date.today()
    add_food(client, "F1", "Beef", (today + timedelta(days=10)).isoformat())
    payload = reading_payload(device_reading_id=str(uuid.uuid4()))
    first = client.post("/api/v1/readings", json=payload)
    duplicate = client.post("/api/v1/readings", json=payload)
    assert first.status_code == 201
    assert duplicate.status_code == 200
    connection = readings_module.get_db_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM food_freshness_snapshots").fetchone()[0] == 1
    finally:
        connection.close()


def test_activation_after_reading_is_not_retroactive_and_deactivation_keeps_snapshot(client):
    today = date.today()
    create = client.post("/api/v1/foods", json={
        "food_id": "F1", "food_name": "Beef", "category": "MEAT",
        "inserted_at": today.isoformat(), "expiry_date": today.isoformat(),
    })
    assert create.status_code == 201
    reading = client.post("/api/v1/readings", json=reading_payload())
    assert reading.status_code == 201
    assert client.get("/api/v1/foods/active").json["data"] == []

    client.post("/api/v1/foods/F1/activate")
    connection = readings_module.get_db_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM food_freshness_snapshots").fetchone()[0] == 0
    finally:
        connection.close()

    second = client.post("/api/v1/readings", json=reading_payload())
    assert second.status_code == 201
    assert client.post("/api/v1/foods/F1/deactivate").status_code == 200
    connection = readings_module.get_db_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM food_freshness_snapshots").fetchone()[0] == 1
    finally:
        connection.close()
