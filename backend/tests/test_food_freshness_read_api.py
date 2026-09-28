import sqlite3
from datetime import date, timedelta
import uuid

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings as readings_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "freshguard-phase3b.db"

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


def add_food(client, food_id, name="Beef", expiry=None):
    response = client.post("/api/v1/foods", json={
        "food_id": food_id,
        "food_name": name,
        "category": "MEAT",
        "inserted_at": date.today().isoformat(),
        "expiry_date": expiry or (date.today() + timedelta(days=10)).isoformat(),
        "storage_location": "FRIDGE-01",
    })
    assert response.status_code == 201
    assert client.post(f"/api/v1/foods/{food_id}/activate").status_code == 200


def post_reading(client, **overrides):
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
    response = client.post("/api/v1/readings", json=payload)
    assert response.status_code == 201
    return response


def test_active_freshness_returns_latest_and_waiting_foods(client):
    add_food(client, "F1", "Beef")
    add_food(client, "F2", "Apple")
    post_reading(client)

    result = client.get("/api/v1/foods/active/freshness")
    assert result.status_code == 200
    assert {item["food_id"] for item in result.json["data"]} == {"F1", "F2"}
    assert all(item["freshness_status"] == "Fresh / Normal" for item in result.json["data"])

    add_food(client, "F3", "Milk")
    waiting = client.get("/api/v1/foods/active/freshness").json["data"]
    item = next(food for food in waiting if food["food_id"] == "F3")
    assert item["freshness_status"] is None
    assert item["freshness_reason"] is None
    assert item["reading_id"] is None
    assert item["evaluated_at"] is None


def test_latest_selection_history_limit_and_deactivation(client):
    add_food(client, "F1")
    post_reading(client, temperature_c=4)
    post_reading(client, temperature_c=15)

    latest = client.get("/api/v1/foods/active/freshness").json["data"][0]
    assert latest["freshness_status"] == "Check Food"
    history = client.get("/api/v1/foods/F1/freshness-history?limit=1")
    assert history.status_code == 200
    assert len(history.json["data"]) == 1
    assert history.json["data"][0]["freshness_status"] == "Check Food"

    assert client.post("/api/v1/foods/F1/deactivate").status_code == 200
    assert client.get("/api/v1/foods/active/freshness").json["data"] == []
    assert client.get("/api/v1/foods/F1/freshness-history").json["data"]


def test_unknown_food_history_is_not_found_and_get_does_not_create_snapshot(client):
    add_food(client, "F1")
    before = client.get("/api/v1/foods/F1/freshness-history").json["data"]
    assert before == []
    assert client.get("/api/v1/foods/UNKNOWN/freshness-history").status_code == 404
    assert client.get("/api/v1/foods/UNKNOWN/freshness-history").json["error"] == "FOOD_NOT_FOUND"
    after = client.get("/api/v1/foods/F1/freshness-history").json["data"]
    assert after == []
