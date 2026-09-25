import sqlite3
from datetime import date, timedelta

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings as readings_module


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    database_path = tmp_path / "food-freshness-integration.db"

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


def register_food(client, food_id, category="MEAT", stored_days=0, expiry_days=10):
    today = date.today()
    response = client.post(
        "/api/v1/foods",
        json={
            "food_id": food_id,
            "food_name": f"Test {category.title()}",
            "category": category,
            "quantity": 1,
            "inserted_at": (today - timedelta(days=stored_days)).isoformat(),
            "manufacture_date": today.isoformat(),
            "expiry_date": (today + timedelta(days=expiry_days)).isoformat(),
            "storage_location": "TEST",
        },
    )
    assert response.status_code == 201
    return response.json["food"]


def post_reading(client, **overrides):
    reading = {
        "device_id": "FG-TEST-DEVICE",
        "timestamp": "2026-09-25T12:00:00+07:00",
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": 100,
        "door_open": False,
        "open_duration_seconds": 0,
    }
    reading.update(overrides)
    return client.post("/api/v1/readings", json=reading)


def test_tc01_registered_food_and_normal_environment(api_client):
    register_food(api_client, "FG-TEST-001", "MEAT", 0, 10)

    response = post_reading(api_client, food_id="FG-TEST-001")

    # POST /readings has historically returned 201 for a created reading.
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Fresh / Normal"


@pytest.mark.parametrize(
    ("stored_days", "expected_status"),
    [
        (1, "Fresh / Normal"),
        (2, "Use Soon"),
        (3, "Use Soon"),
        (4, "Check Food"),
    ],
)
def test_storage_duration_flows_from_food_record(
    api_client, stored_days, expected_status
):
    register_food(api_client, "FG-STORAGE", "MEAT", stored_days, 10)

    response = post_reading(api_client, food_id="FG-STORAGE")

    assert response.status_code == 201
    assert response.json["freshness"]["status"] == expected_status


@pytest.mark.parametrize(
    ("expiry_days", "expected_status"),
    [
        (5, "Fresh / Normal"),
        (1, "Use Soon"),
        (0, "Use Soon"),
        (-1, "Check Food"),
    ],
)
def test_expiry_flows_from_food_record(api_client, expiry_days, expected_status):
    register_food(api_client, "FG-EXPIRY", "MEAT", 0, expiry_days)

    response = post_reading(api_client, food_id="FG-EXPIRY")

    assert response.status_code == 201
    assert response.json["freshness"]["status"] == expected_status


def test_tc10_food_use_soon_and_fresh_temperature(api_client):
    register_food(api_client, "FG-AGG-10", stored_days=2, expiry_days=10)

    response = post_reading(api_client, food_id="FG-AGG-10", temperature_c=5)

    assert response.json["freshness"]["status"] == "Use Soon"
    assert "storage duration" in response.json["freshness"]["reason"].lower()


def test_tc11_fresh_food_and_check_food_temperature(api_client):
    register_food(api_client, "FG-AGG-11", stored_days=0, expiry_days=10)

    response = post_reading(api_client, food_id="FG-AGG-11", temperature_c=15)

    assert response.json["freshness"]["status"] == "Check Food"
    assert "temperature" in response.json["freshness"]["reason"].lower()


def test_tc12_check_food_temperature_wins_over_food_use_soon(api_client):
    register_food(api_client, "FG-AGG-12", stored_days=2, expiry_days=10)

    response = post_reading(api_client, food_id="FG-AGG-12", temperature_c=15)

    assert response.json["freshness"]["status"] == "Check Food"
    assert "temperature" in response.json["freshness"]["reason"].lower()
    assert "storage duration" in response.json["freshness"]["reason"].lower()


def test_storage_expiry_and_door_reasons_are_all_preserved(api_client):
    register_food(api_client, "FG-MULTI", stored_days=2, expiry_days=1)

    response = post_reading(
        api_client,
        food_id="FG-MULTI",
        door_open=True,
        open_duration_seconds=10,
    )

    assert response.json["freshness"]["status"] == "Use Soon"
    reason = response.json["freshness"]["reason"].lower()
    assert "storage duration" in reason
    assert "expiry date" in reason
    assert "door" in reason


def test_unknown_food_returns_404_without_saving_reading(api_client):
    response = post_reading(api_client, food_id="DOES-NOT-EXIST")

    assert response.status_code == 404
    assert response.json["error"] == "FOOD_NOT_FOUND"
    assert api_client.get("/api/v1/readings").json["count"] == 0


def test_reading_without_food_id_keeps_response_contract(api_client):
    response = post_reading(api_client)

    assert response.status_code == 201
    assert response.json["success"] is True
    assert "freshness" in response.json
    assert set(response.json["freshness"]) == {"status", "reason"}
    assert isinstance(response.json["freshness"]["reason"], str)
    assert response.json["freshness"]["status"] == "Fresh / Normal"


def test_food_id_selects_the_registered_category(api_client):
    register_food(api_client, "FG-MEAT-001", "MEAT", 5, 10)
    register_food(api_client, "FG-VEG-001", "VEGETABLE", 5, 10)

    meat = post_reading(api_client, food_id="FG-MEAT-001")
    vegetable = post_reading(api_client, food_id="FG-VEG-001")

    assert meat.json["freshness"]["status"] == "Check Food"
    assert vegetable.json["freshness"]["status"] == "Fresh / Normal"


def test_latest_and_history_reload_linked_food_for_freshness(api_client):
    register_food(api_client, "FG-LATEST", "MEAT", 4, 10)
    post_reading(api_client, food_id="FG-LATEST")

    latest = api_client.get("/api/v1/readings/latest")
    history = api_client.get("/api/v1/readings")

    assert latest.status_code == 200
    assert latest.json["data"]["food_id"] == "FG-LATEST"
    assert latest.json["data"]["freshness"]["status"] == "Check Food"
    assert history.status_code == 200
    assert history.json["data"][0]["food_id"] == "FG-LATEST"
    assert history.json["data"][0]["freshness"]["status"] == "Check Food"
