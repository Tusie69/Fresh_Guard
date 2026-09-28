import sqlite3
from datetime import date

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings as readings_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "freshguard-active-foods.db"

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


def food_payload(food_id, name, category):
    return {
        "food_id": food_id,
        "food_name": name,
        "category": category,
        "inserted_at": date.today().isoformat(),
        "expiry_date": date.today().isoformat(),
        "storage_location": "FRIDGE-01",
    }


def create_food(client, food_id, name, category):
    response = client.post("/api/v1/foods", json=food_payload(food_id, name, category))
    assert response.status_code == 201
    return response.json["food"]


def test_active_foods_table_is_idempotent_and_existing_foods_stay_inactive(client):
    create_food(client, "F1", "Beef", "MEAT")
    active = client.get("/api/v1/foods/active")
    assert active.status_code == 200
    assert active.json["data"] == []


def test_activate_multiple_foods_is_idempotent(client):
    create_food(client, "F1", "Beef", "MEAT")
    create_food(client, "F2", "Apple", "FRUIT")

    first = client.post("/api/v1/foods/F1/activate")
    second = client.post("/api/v1/foods/F2/activate")
    duplicate = client.post("/api/v1/foods/F1/activate")

    assert first.status_code == second.status_code == duplicate.status_code == 200
    active = client.get("/api/v1/foods/active").json["data"]
    assert [food["food_id"] for food in active] == ["F1", "F2"]
    assert all(food["activated_at"] for food in active)


def test_activate_unknown_food_fails(client):
    response = client.post("/api/v1/foods/UNKNOWN/activate")
    assert response.status_code == 404
    assert response.json["error"] == "FOOD_NOT_FOUND"


def test_deactivate_only_removes_membership_and_preserves_food(client):
    create_food(client, "F1", "Beef", "MEAT")
    create_food(client, "F2", "Apple", "FRUIT")
    client.post("/api/v1/foods/F1/activate")
    client.post("/api/v1/foods/F2/activate")

    removed = client.post("/api/v1/foods/F1/deactivate")
    assert removed.status_code == 200
    assert removed.json["active"] is False
    active = client.get("/api/v1/foods/active").json["data"]
    assert [food["food_id"] for food in active] == ["F2"]

    food = client.get("/api/v1/foods/F1")
    assert food.status_code == 200
    assert food.json["food"]["food_id"] == "F1"
    assert client.post("/api/v1/foods/F1/deactivate").status_code == 200


def test_active_foods_survive_app_restart(client, tmp_path, monkeypatch):
    create_food(client, "F1", "Beef", "MEAT")
    client.post("/api/v1/foods/F1/activate")
    database_path = tmp_path / "freshguard-active-foods.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    restarted = create_app().test_client()
    active = restarted.get("/api/v1/foods/active")
    assert active.status_code == 200
    assert [food["food_id"] for food in active.json["data"]] == ["F1"]
