import sqlite3

import pytest
from werkzeug.security import check_password_hash

from app import create_app
from app import init_db as init_db_module
from app.routes import admin as admin_route
from app.services import auth as auth_service
from app.services.auth import create_user


@pytest.fixture
def user_client(tmp_path, monkeypatch):
    path = tmp_path / "users.db"

    def connect():
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        return db

    monkeypatch.setattr(init_db_module, "get_db_connection", connect)
    monkeypatch.setattr(auth_service, "get_db_connection", connect)
    monkeypatch.setattr(admin_route, "get_db_connection", connect)
    init_db_module.init_db()
    db = connect()
    admin_id = create_user(db, "admin", "admin-password", "ADMIN")
    user_id = create_user(db, "user", "user-password", "USER")
    db.commit(); db.close()
    app = create_app(); app.config.update(TESTING=True, SECRET_KEY="users-test")
    return app.test_client(), connect, admin_id, user_id


def login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_user_management_authorization(user_client):
    client, _, _, _ = user_client
    assert client.get("/api/v1/admin/users").status_code == 401
    login(client, "user", "user-password")
    assert client.get("/api/v1/admin/users").status_code == 403
    login(client, "admin", "admin-password")
    assert client.get("/api/v1/admin/users").status_code == 200


def test_create_list_detail_and_duplicate(user_client):
    client, connect, _, _ = user_client
    login(client, "admin", "admin-password")
    created = client.post("/api/v1/admin/users", json={"username": "new-user", "password": "secret", "role": "USER"})
    assert created.status_code == 201
    user = created.json["user"]
    assert "password_hash" not in user
    db = connect(); row = db.execute("SELECT password_hash FROM users WHERE username = 'new-user'").fetchone(); db.close()
    assert check_password_hash(row[0], "secret")
    assert client.post("/api/v1/admin/users", json={"username": "new-user", "password": "secret", "role": "USER"}).status_code == 409
    assert client.get(f"/api/v1/admin/users/{user['id']}").json["user"]["username"] == "new-user"
    assert client.get("/api/v1/admin/users/9999").status_code == 404
    assert all("password_hash" not in item for item in client.get("/api/v1/admin/users").json["users"])


@pytest.mark.parametrize("payload,error", [
    ({"username": "", "password": "x", "role": "USER"}, "INVALID_USERNAME"),
    ({"username": "x", "password": "", "role": "USER"}, "INVALID_PASSWORD"),
    ({"username": "x", "password": "x", "role": "ROOT"}, "INVALID_ROLE"),
    ({"username": "x", "password": "x", "role": "USER", "is_active": True}, "UNSUPPORTED_FIELD"),
])
def test_create_validation(user_client, payload, error):
    client, _, _, _ = user_client; login(client, "admin", "admin-password")
    response = client.post("/api/v1/admin/users", json=payload)
    assert response.status_code == 400 and response.json["error"] == error


def test_update_status_role_and_invalid_fields(user_client):
    client, _, admin_id, user_id = user_client; login(client, "admin", "admin-password")
    assert client.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": False, "reason": "status"}).status_code == 200
    assert client.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": True, "role": "ADMIN", "reason": "promote"}).status_code == 200
    assert client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "USER", "reason": "demote"}).status_code == 200
    assert client.patch(f"/api/v1/admin/users/{user_id}", json={"password_hash": "x"}).status_code == 400
    assert client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "ROOT"}).status_code == 400


def test_self_and_last_admin_protection(user_client):
    client, connect, admin_id, user_id = user_client; login(client, "admin", "admin-password")
    assert client.patch(f"/api/v1/admin/users/{admin_id}", json={"is_active": False, "reason": "test"}).json["error"] == "LAST_ACTIVE_ADMIN"
    assert client.patch(f"/api/v1/admin/users/{admin_id}", json={"role": "USER", "reason": "test"}).json["error"] == "LAST_ACTIVE_ADMIN"
    assert client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "ADMIN", "reason": "promote"}).status_code == 200
    # There are now two active admins, so the other admin can safely be deactivated.
    second_admin = client.application.test_client()
    login(second_admin, "user", "user-password")
    assert second_admin.patch(f"/api/v1/admin/users/{admin_id}", json={"is_active": False, "reason": "cleanup"}).status_code == 200
    # The remaining admin cannot be demoted or deactivated.
    assert second_admin.patch(f"/api/v1/admin/users/{user_id}", json={"role": "USER", "reason": "test"}).json["error"] == "LAST_ACTIVE_ADMIN"
    assert second_admin.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": False, "reason": "test"}).json["error"] == "LAST_ACTIVE_ADMIN"


def test_deactivated_user_loses_session_and_role_change_is_live(user_client):
    client, _, _, user_id = user_client; login(client, "user", "user-password")
    admin = client.application.test_client()
    login(admin, "admin", "admin-password")
    assert admin.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": False, "reason": "disable"}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    # Reactivate and promote, then a fresh session sees the database role.
    assert admin.patch(f"/api/v1/admin/users/{user_id}", json={"is_active": True, "role": "ADMIN", "reason": "restore"}).status_code == 200
    login(client, "user", "user-password")
    assert client.get("/api/v1/auth/me").json["user"]["role"] == "ADMIN"


def test_user_audit_history_records_mutations_without_passwords(user_client):
    client, _, _, user_id = user_client
    assert client.get("/api/v1/admin/users/history").status_code == 401
    login(client, "user", "user-password")
    assert client.get("/api/v1/admin/users/history").status_code == 403
    login(client, "admin", "admin-password")
    created = client.post("/api/v1/admin/users", json={"username": "audited", "password": "secret", "role": "USER"})
    assert created.status_code == 201
    target_id = created.json["user"]["id"]
    client.patch(f"/api/v1/admin/users/{target_id}", json={"role": "ADMIN", "reason": "promotion"})
    client.patch(f"/api/v1/admin/users/{target_id}", json={"is_active": False, "reason": "offboarding"})
    history = client.get("/api/v1/admin/users/history").json["history"]
    assert [item["action"] for item in history[:3]] == ["USER_DEACTIVATED", "ROLE_CHANGED", "CREATE_USER"]
    assert history[0]["target_user_id"] == target_id
    assert history[0]["actor_username"] == "admin"
    assert all("password" not in str(item).lower() for item in history)


def test_user_audit_noop_and_rejected_mutations_create_no_rows(user_client):
    client, connect, admin_id, user_id = user_client
    login(client, "admin", "admin-password")
    assert client.patch(f"/api/v1/admin/users/{admin_id}", json={"role": "USER"}).status_code == 400
    assert client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "ADMIN", "reason": "promote"}).status_code == 200
    before = connect().execute("SELECT COUNT(*) FROM user_management_audit").fetchone()[0]
    assert client.patch(f"/api/v1/admin/users/{user_id}", json={"role": "ADMIN"}).status_code == 200
    after = connect().execute("SELECT COUNT(*) FROM user_management_audit").fetchone()[0]
    assert before == after
