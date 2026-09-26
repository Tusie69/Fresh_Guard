import sqlite3
from datetime import date, timedelta
import uuid

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings as readings_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "freshguard-test.db"

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


def food_payload(**overrides):
    payload = {
        "food_id": "FG-FOOD-001",
        "food_name": "Milk",
        "category": "DAIRY",
        "quantity": 1,
        "inserted_at": date.today().isoformat(),
        "manufacture_date": (date.today() - timedelta(days=2)).isoformat(),
        "expiry_date": (date.today() + timedelta(days=12)).isoformat(),
        "storage_location": "FRIDGE-01",
    }
    payload.update(overrides)
    return payload


def reading_payload(**overrides):
    payload = {
        "device_id": "FG-ESP32-01",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": "2026-09-25T12:00:00+07:00",
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": 300,
        "door_open": False,
    }
    payload.update(overrides)
    return payload


def test_create_food_success(client):
    response = client.post("/api/v1/foods", json=food_payload())

    assert response.status_code == 201
    assert response.json["success"] is True
    assert response.json["food"]["food_id"] == "FG-FOOD-001"
    assert response.json["food"]["category"] == "DAIRY"


@pytest.mark.parametrize(
    ("qr_code", "expected_category"),
    [
        ("FG-MEAT", "MEAT"),
        ("FG-DAIRY", "DAIRY"),
        ("FG-VEGETABLE", "VEGETABLE"),
        ("FG-FRUIT", "FRUIT"),
        ("FG-COOKED", "COOKED_FOOD"),
    ],
)
def test_create_food_maps_fixed_qr_to_category(client, qr_code, expected_category):
    payload = food_payload(qr_code=qr_code)
    payload.pop("category")
    payload.pop("food_id")
    response = client.post(
        "/api/v1/foods",
        json=payload,
    )

    assert response.status_code == 201
    assert response.json["food"]["category"] == expected_category
    assert response.json["food"]["food_id"] == "FG-FOOD-00001"
    assert "qr_code" not in response.json["food"]


def test_create_food_rejects_unknown_qr_without_saving(client):
    payload = food_payload(qr_code="FG-UNKNOWN")
    payload.pop("category")
    payload.pop("food_id")
    response = client.post(
        "/api/v1/foods",
        json=payload,
    )

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_QR_CODE"
    assert client.get("/api/v1/foods").json["data"] == []


def test_create_food_rejects_qr_category_conflict_without_saving(client):
    response = client.post(
        "/api/v1/foods",
        json=food_payload(food_id="QR-CONFLICT", qr_code="FG-MEAT", category="DAIRY"),
    )

    assert response.status_code == 400
    assert response.json["error"] == "QR_CATEGORY_CONFLICT"
    assert client.get("/api/v1/foods").json["data"] == []


def test_create_food_trims_qr_whitespace_and_allows_matching_category(client):
    response = client.post(
        "/api/v1/foods",
        json=food_payload(
            food_id="QR-TRIMMED", qr_code="  FG-MEAT  ", category=" MEAT "
        ),
    )

    assert response.status_code == 201
    assert response.json["food"]["category"] == "MEAT"


def test_qr_with_existing_food_id_derives_category_when_category_is_omitted(client):
    payload = food_payload(food_id="EXISTING-FOOD-ID", qr_code="FG-DAIRY")
    payload.pop("category")
    response = client.post("/api/v1/foods", json=payload)

    assert response.status_code == 201
    assert response.json["food"]["food_id"] == "EXISTING-FOOD-ID"
    assert response.json["food"]["category"] == "DAIRY"


def test_qr_only_food_ids_are_unique_and_increment_from_sqlite_id(client):
    first_payload = food_payload(qr_code="FG-MEAT")
    second_payload = food_payload(qr_code="FG-FRUIT")
    for payload in (first_payload, second_payload):
        payload.pop("category")
        payload.pop("food_id")

    first = client.post("/api/v1/foods", json=first_payload)
    second = client.post("/api/v1/foods", json=second_payload)

    assert first.status_code == second.status_code == 201
    assert first.json["food"]["food_id"] == "FG-FOOD-00001"
    assert second.json["food"]["food_id"] == "FG-FOOD-00002"
    assert first.json["food"]["food_id"] != second.json["food"]["food_id"]


def test_qr_only_food_id_sequence_survives_database_reinitialization(client):
    first_payload = food_payload(qr_code="FG-MEAT")
    first_payload.pop("category")
    first_payload.pop("food_id")
    first = client.post("/api/v1/foods", json=first_payload)
    assert first.json["food"]["food_id"] == "FG-FOOD-00001"

    init_db_module.init_db()
    restarted_client = create_app().test_client()
    second_payload = food_payload(qr_code="FG-DAIRY")
    second_payload.pop("category")
    second_payload.pop("food_id")
    second = restarted_client.post("/api/v1/foods", json=second_payload)

    assert second.status_code == 201
    assert second.json["food"]["food_id"] == "FG-FOOD-00002"


def test_qr_only_food_id_skips_existing_legacy_identifier(client):
    legacy = client.post(
        "/api/v1/foods", json=food_payload(food_id="FG-FOOD-00002")
    )
    payload = food_payload(qr_code="FG-MEAT")
    payload.pop("category")
    payload.pop("food_id")

    generated = client.post("/api/v1/foods", json=payload)

    assert legacy.status_code == 201
    assert generated.status_code == 201
    assert generated.json["food"]["food_id"] == "FG-FOOD-00003"


def test_food_without_id_or_qr_is_rejected(client):
    payload = food_payload()
    payload.pop("food_id")
    response = client.post("/api/v1/foods", json=payload)

    assert response.status_code == 400
    assert "food_id" in response.json["fields"]


def test_create_food_rejects_unsupported_category(client):
    response = client.post(
        "/api/v1/foods", json=food_payload(category="POULTRY")
    )

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_CATEGORY"
    assert client.get("/api/v1/foods").json["data"] == []


@pytest.mark.parametrize("missing_field", ["food_id", "food_name", "category", "inserted_at"])
def test_create_food_requires_fields(client, missing_field):
    payload = food_payload()
    payload.pop(missing_field)

    response = client.post("/api/v1/foods", json=payload)

    assert response.status_code == 400
    assert missing_field in response.json["fields"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("inserted_at", "2026-02-30"),
        ("manufacture_date", "not-a-date"),
        ("expiry_date", "2026/10/07"),
    ],
)
def test_create_food_rejects_invalid_dates(client, field, value):
    response = client.post("/api/v1/foods", json=food_payload(**{field: value}))

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_DATE"


@pytest.mark.parametrize("quantity", ["one", -1, float("inf")])
def test_create_food_rejects_invalid_quantity(client, quantity):
    response = client.post("/api/v1/foods", json=food_payload(quantity=quantity))

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_QUANTITY"


def test_create_food_rejects_boolean_quantity(client):
    response = client.post("/api/v1/foods", json=food_payload(quantity=True))

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_QUANTITY"


def test_duplicate_food_id_returns_conflict(client):
    assert client.post("/api/v1/foods", json=food_payload()).status_code == 201

    response = client.post("/api/v1/foods", json=food_payload(food_name="Another Milk"))

    assert response.status_code == 409
    assert response.json["error"] == "DUPLICATE_FOOD_ID"


def test_get_foods_returns_created_foods(client):
    client.post("/api/v1/foods", json=food_payload())

    response = client.get("/api/v1/foods")

    assert response.status_code == 200
    assert response.json["success"] is True
    assert len(response.json["data"]) == 1
    assert response.json["data"][0]["food_id"] == "FG-FOOD-001"


def test_get_existing_food(client):
    client.post("/api/v1/foods", json=food_payload())

    response = client.get("/api/v1/foods/FG-FOOD-001")

    assert response.status_code == 200
    assert response.json["food"]["food_name"] == "Milk"


def test_get_nonexistent_food_returns_404(client):
    response = client.get("/api/v1/foods/UNKNOWN")

    assert response.status_code == 404


def test_reading_without_food_id_remains_supported(client):
    response = client.post("/api/v1/readings", json=reading_payload())

    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Fresh / Normal"


def test_reading_with_registered_food_uses_food_profile(client):
    inserted_at = date.today() - timedelta(days=4)
    client.post(
        "/api/v1/foods",
        json=food_payload(
            category="MEAT",
            inserted_at=inserted_at.isoformat(),
            expiry_date=(date.today() + timedelta(days=5)).isoformat(),
        ),
    )

    response = client.post(
        "/api/v1/readings",
        json=reading_payload(food_id="FG-FOOD-001"),
    )

    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Check Food"
    assert "storage duration" in response.json["freshness"]["reason"].lower()


def test_reading_history_recomputes_freshness_from_linked_food(client):
    client.post(
        "/api/v1/foods",
        json=food_payload(
            category="MEAT",
            inserted_at=(date.today() - timedelta(days=4)).isoformat(),
            expiry_date=(date.today() + timedelta(days=5)).isoformat(),
        ),
    )
    client.post("/api/v1/readings", json=reading_payload(food_id="FG-FOOD-001"))

    history = client.get("/api/v1/readings")
    latest = client.get("/api/v1/readings/latest")

    assert history.status_code == 200
    assert history.json["data"][0]["food_id"] == "FG-FOOD-001"
    assert history.json["data"][0]["freshness"]["status"] == "Check Food"
    assert latest.status_code == 200
    assert latest.json["data"]["freshness"]["status"] == "Check Food"


def test_reading_with_unknown_food_id_is_rejected(client):
    response = client.post(
        "/api/v1/readings",
        json=reading_payload(food_id="UNKNOWN"),
    )

    assert response.status_code == 404
    assert response.json["error"] == "FOOD_NOT_FOUND"


def test_init_db_migrates_existing_readings_without_data_loss(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.db"

    def connect_to_legacy_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    legacy = connect_to_legacy_db()
    legacy.execute(
        """
        CREATE TABLE sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            temperature_c REAL,
            humidity_pct REAL,
            gas_raw INTEGER,
            door_open INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    legacy.execute(
        """CREATE TABLE food_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_id TEXT UNIQUE NOT NULL,
            food_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity REAL,
            inserted_at TEXT NOT NULL,
            manufacture_date TEXT,
            expiry_date TEXT,
            storage_location TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    legacy.execute(
        """CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT,
            door_open INTEGER NOT NULL,
            open_duration_seconds INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    legacy.execute(
        """INSERT INTO sensor_readings
           (device_id, timestamp, temperature_c, humidity_pct, gas_raw, door_open)
           VALUES ('FG-ESP32-01', '2026-09-25T12:00:00+07:00', 5, 60, 300, 0)"""
    )
    legacy.execute(
        """INSERT INTO food_items (food_id, food_name, category, inserted_at)
           VALUES ('legacy-food', 'Legacy food', 'MEAT', '2026-09-24')"""
    )
    legacy.execute(
        """INSERT INTO events (event_id, device_id, timestamp, event_type, door_open)
           VALUES ('legacy-event', 'device', '2026-09-25T12:00:00', 'door', 0)"""
    )
    legacy.commit()
    legacy.close()

    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_legacy_db)
    init_db_module.init_db()

    migrated = connect_to_legacy_db()
    columns = {row[1] for row in migrated.execute("PRAGMA table_info(sensor_readings)")}
    row = migrated.execute(
        "SELECT device_id, temperature_c, open_duration_seconds, food_id "
        "FROM sensor_readings WHERE id = 1"
    ).fetchone()
    food_table = migrated.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'food_items'"
    ).fetchone()
    index = migrated.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_sensor_readings_device_reading_id'"
    ).fetchone()
    migrated.close()

    # Re-running initialization must leave the schema and historical row intact.
    init_db_module.init_db()
    migrated = connect_to_legacy_db()
    historical = migrated.execute(
        "SELECT device_reading_id FROM sensor_readings WHERE id = 1"
    ).fetchone()
    preserved_food = migrated.execute(
        "SELECT food_name FROM food_items WHERE food_id = 'legacy-food'"
    ).fetchone()
    preserved_event = migrated.execute(
        "SELECT event_type FROM events WHERE event_id = 'legacy-event'"
    ).fetchone()
    migrated.close()

    assert {
        "open_duration_seconds", "food_id", "device_reading_id",
        "freshness_status", "freshness_reason", "freshness_evaluated_at",
    }.issubset(columns)
    assert tuple(row) == ("FG-ESP32-01", 5.0, 0, None)
    assert food_table is not None
    assert index is not None
    assert tuple(historical) == (None,)
    assert tuple(preserved_food) == ("Legacy food",)
    assert tuple(preserved_event) == ("door",)
