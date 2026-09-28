import sqlite3

import pytest
from werkzeug.security import check_password_hash

from app import create_app
from app import init_db as init_db_module
from app.services import auth as auth_service
from app.services.auth import create_password_hash, create_user


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    database_path = tmp_path / "auth.db"

    def connect():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(init_db_module, "get_db_connection", connect)
    monkeypatch.setattr(auth_service, "get_db_connection", connect)
    init_db_module.init_db()
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    connection = connect()
    create_user(connection, "user", "user-password", "USER")
    create_user(connection, "admin", "admin-password", "ADMIN")
    connection.execute(
        "INSERT INTO users (username, password_hash, role, is_active) "
        "VALUES (?, ?, ?, 0)",
        ("inactive", create_password_hash("inactive-password"), "USER"),
    )
    connection.commit()
    connection.close()
    return app.test_client(), database_path


def login(client, username, password):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


def test_valid_user_login_and_me(auth_client):
    client, _ = auth_client
    response = login(client, "user", "user-password")
    assert response.status_code == 200
    assert response.json["user"]["username"] == "user"
    assert response.json["user"]["role"] == "USER"
    assert isinstance(response.json["user"]["id"], int)

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json["user"]["role"] == "USER"


def test_valid_admin_login(auth_client):
    client, _ = auth_client
    response = login(client, "admin", "admin-password")
    assert response.status_code == 200
    assert response.json["user"]["role"] == "ADMIN"


@pytest.mark.parametrize(
    ("username", "password"),
    [("user", "wrong"), ("unknown", "user-password"), ("inactive", "inactive-password")],
)
def test_invalid_unknown_and_inactive_credentials_return_401(auth_client, username, password):
    client, _ = auth_client
    response = login(client, username, password)
    assert response.status_code == 401
    assert response.json["error"] == "INVALID_CREDENTIALS"


def test_me_and_admin_route_require_authentication(auth_client):
    client, _ = auth_client
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/admin/status").status_code == 401


def test_user_is_forbidden_from_admin_route(auth_client):
    client, _ = auth_client
    assert login(client, "user", "user-password").status_code == 200
    response = client.get("/api/v1/admin/status")
    assert response.status_code == 403
    assert response.json["error"] == "FORBIDDEN"


def test_admin_can_access_admin_route(auth_client):
    client, _ = auth_client
    assert login(client, "admin", "admin-password").status_code == 200
    response = client.get("/api/v1/admin/status")
    assert response.status_code == 200
    assert response.json["success"] is True


def test_logout_invalidates_authentication(auth_client):
    client, _ = auth_client
    login(client, "user", "user-password")
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_password_hash_is_not_plaintext_and_verifies(auth_client):
    _client, database_path = auth_client
    connection = sqlite3.connect(database_path)
    row = connection.execute(
        "SELECT password_hash FROM users WHERE username = 'user'"
    ).fetchone()
    connection.close()
    assert row[0] != "user-password"
    assert check_password_hash(row[0], "user-password")


def test_role_validation_rejects_unknown_role(auth_client):
    _client, database_path = auth_client
    connection = sqlite3.connect(database_path)
    with pytest.raises(ValueError):
        create_user(connection, "bad-role", "password", "SUPERADMIN")
    connection.close()


def test_client_role_field_cannot_elevate_user(auth_client):
    client, database_path = auth_client
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "user", "password": "user-password", "role": "ADMIN"},
    )
    assert response.status_code == 200
    assert response.json["user"]["role"] == "USER"
    assert client.get("/api/v1/admin/status").status_code == 403

    connection = sqlite3.connect(database_path)
    assert connection.execute(
        "SELECT role FROM users WHERE username = 'user'"
    ).fetchone()[0] == "USER"
    connection.close()


def test_init_db_preserves_existing_tables_and_adds_users(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy-auth.db"

    def connect():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    connection = connect()
    connection.execute(
        "CREATE TABLE sensor_readings (id INTEGER PRIMARY KEY, device_id TEXT NOT NULL)"
    )
    connection.execute("INSERT INTO sensor_readings VALUES (1, 'legacy-device')")
    connection.commit()
    connection.close()
    monkeypatch.setattr(init_db_module, "get_db_connection", connect)

    init_db_module.init_db()
    connection = connect()
    assert connection.execute(
        "SELECT device_id FROM sensor_readings WHERE id = 1"
    ).fetchone()[0] == "legacy-device"
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone() is not None
    connection.close()
