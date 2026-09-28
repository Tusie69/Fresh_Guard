import sqlite3

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import admin as admin_route
from app.services import auth as auth_service
from app.services.auth import create_user


@pytest.fixture
def overview_client(tmp_path, monkeypatch):
    path = tmp_path / "overview.db"

    def connect():
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        return db

    monkeypatch.setattr(init_db_module, "get_db_connection", connect)
    monkeypatch.setattr(auth_service, "get_db_connection", connect)
    monkeypatch.setattr(admin_route, "get_db_connection", connect)
    init_db_module.init_db()
    db = connect()
    create_user(db, "admin", "admin-password", "ADMIN")
    create_user(db, "user", "user-password", "USER")
    db.execute("INSERT INTO food_items (food_id, food_name, category, inserted_at) VALUES ('F1', 'Apple', 'FRUIT', '2026-01-01')")
    db.execute("INSERT INTO sensor_readings (device_id, timestamp, door_open, freshness_status) VALUES ('D1', '2026-09-27T10:00:00Z', 0, 'Fresh / Normal')")
    db.execute("INSERT INTO events (event_id, device_id, timestamp, event_type, door_open) VALUES ('E1', 'D1', '2026-09-27T10:00:00Z', 'TEST', 0)")
    db.commit(); db.close()
    app = create_app(); app.config.update(TESTING=True, SECRET_KEY="overview-test")
    return app.test_client(), connect


def login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_overview_authorization(overview_client):
    client, _ = overview_client
    assert client.get("/api/v1/admin/overview").status_code == 401
    login(client, "user", "user-password")
    assert client.get("/api/v1/admin/overview").status_code == 403
    login(client, "admin", "admin-password")
    assert client.get("/api/v1/admin/overview").status_code == 200


def test_overview_aggregates_supported_data_without_passwords(overview_client):
    client, _ = overview_client
    login(client, "admin", "admin-password")
    data = client.get("/api/v1/admin/overview").json
    assert data["users"] == {"total": 2, "active": 2, "inactive": 0, "admins": 1, "regular_users": 1}
    assert data["readings"] == {"total": 1, "latest_timestamp": "2026-09-27T10:00:00Z", "latest_freshness_status": "Fresh / Normal"}
    assert data["foods"] == {"total": 1}
    assert data["events"] == {"total": 1}
    assert data["freshness_rules"]["total"] == 23
    assert data["freshness_rules"]["editable"] == 17
    assert data["freshness_rules"]["locked"] == 6
    assert "password_hash" not in str(data)


def test_overview_handles_empty_data(overview_client):
    client, connect = overview_client
    db = connect()
    db.execute("DELETE FROM sensor_readings"); db.execute("DELETE FROM food_items"); db.execute("DELETE FROM events")
    db.commit(); db.close()
    login(client, "admin", "admin-password")
    data = client.get("/api/v1/admin/overview").json
    assert data["readings"] == {"total": 0, "latest_timestamp": None, "latest_freshness_status": None}
    assert data["foods"]["total"] == 0
    assert data["events"]["total"] == 0
    assert data["freshness_rules"]["latest_change_at"] is None
