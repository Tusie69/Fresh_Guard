import sqlite3

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import admin as admin_route
from app.services import auth as auth_service
from app.services.auth import create_user


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    path = tmp_path / "admin-rules.db"

    def connect():
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(init_db_module, "get_db_connection", connect)
    monkeypatch.setattr(auth_service, "get_db_connection", connect)
    monkeypatch.setattr(admin_route, "get_db_connection", connect)
    init_db_module.init_db()
    connection = connect()
    create_user(connection, "user", "user-password", "USER")
    create_user(connection, "admin", "admin-password", "ADMIN")
    connection.commit()
    connection.close()
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="admin-rules-secret")
    return app.test_client(), connect


def login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_admin_read_endpoint_exposes_editable_metadata_and_history(admin_client):
    client, _ = admin_client
    assert login(client, "admin", "admin-password").status_code == 200
    response = client.get("/api/v1/admin/freshness-rules")
    assert response.status_code == 200
    assert response.json["rules"]["humidity"]["vegetable"]["min_pct"]["editable"] is True
    assert response.json["rules"]["temperature"]["hot_threshold_c"]["editable"] is True
    assert response.json["rules"]["temperature"]["critical_threshold_c"]["editable"] is False
    assert client.get("/api/v1/admin/freshness-rules/history").json["history"] == []


def test_user_and_unauthenticated_cannot_update(admin_client):
    client, _ = admin_client
    assert client.put("/api/v1/admin/freshness-rules", json={"reason": "x", "rules": {}}).status_code == 401
    assert login(client, "user", "user-password").status_code == 200
    assert client.put("/api/v1/admin/freshness-rules", json={"reason": "x", "rules": {"expiry.use_soon_window_days": 2}}).status_code == 403
    assert client.get("/api/v1/admin/freshness-rules/history").status_code == 403


def test_admin_can_update_safe_rules_and_audit_actor(admin_client):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    response = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "prototype validation",
        "rules": {
            "humidity.vegetable.min_pct": 82,
            "storage.MEAT.max_duration_days": 4,
            "expiry.use_soon_window_days": 2,
        },
    })
    assert response.status_code == 200
    assert response.json["changed_count"] == 3
    connection = connect()
    values = dict(connection.execute("SELECT rule_key, rule_value FROM freshness_rules" ).fetchall())
    assert values["humidity.vegetable.min_pct"] == "82.0"
    audit = connection.execute("SELECT * FROM freshness_rule_audit ORDER BY id DESC").fetchall()
    assert len(audit) == 3
    assert audit[0]["actor_username"] == "admin"
    assert audit[0]["actor_role"] == "ADMIN"
    assert audit[0]["reason"] == "prototype validation"
    connection.close()
    history = client.get("/api/v1/admin/freshness-rules/history").json["history"]
    assert history[0]["id"] > history[-1]["id"]


@pytest.mark.parametrize("key", [
    "temperature.continuity_gap_seconds", "temperature.critical_threshold_c", "gas.anomaly_increase_pct", "door.open_duration_seconds", "unknown.rule",
])
def test_locked_or_unknown_rule_rejected(admin_client, key):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    response = client.put("/api/v1/admin/freshness-rules", json={"reason": "test", "rules": {key: 2}})
    assert response.status_code == 400
    assert response.json["error"] in {"RULE_NOT_EDITABLE", "UNKNOWN_RULE"}
    connection = connect()
    assert connection.execute("SELECT COUNT(*) FROM freshness_rule_audit").fetchone()[0] == 0
    connection.close()


@pytest.mark.parametrize("changes", [
    {"humidity.vegetable.min_pct": -1},
    {"humidity.vegetable.max_pct": 101},
    {"humidity.vegetable.min_pct": 95},
    {"humidity.vegetable.min_pct": True},
    {"storage.MEAT.max_duration_days": 2.5},
    {"storage.MEAT.warning_days": 4},
    {"expiry.use_soon_window_days": -1},
    {"expiry.use_soon_window_days": "2"},
])
def test_invalid_values_are_rejected(admin_client, changes):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    response = client.put("/api/v1/admin/freshness-rules", json={"reason": "test", "rules": changes})
    assert response.status_code == 400
    connection = connect()
    assert connection.execute("SELECT COUNT(*) FROM freshness_rule_audit").fetchone()[0] == 0
    connection.close()


def test_batch_validation_is_atomic_and_noop_has_no_audit(admin_client):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    invalid = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "atomic", "rules": {"expiry.use_soon_window_days": 2, "temperature.continuity_gap_seconds": 7},
    })
    assert invalid.status_code == 400
    unchanged = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "noop", "rules": {"expiry.use_soon_window_days": 1},
    })
    assert unchanged.status_code == 200
    assert unchanged.json["changed_count"] == 0
    connection = connect()
    assert connection.execute("SELECT COUNT(*) FROM freshness_rule_audit").fetchone()[0] == 0
    assert connection.execute("SELECT rule_value FROM freshness_rules WHERE rule_key = 'expiry.use_soon_window_days'").fetchone()[0] == "1"
    connection.close()


def test_reset_requires_reason_and_resets_only_editable_rules(admin_client):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    assert client.post("/api/v1/admin/freshness-rules/reset", json={}).status_code == 400
    changed = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "custom", "rules": {"humidity.vegetable.min_pct": 82, "temperature.hot_threshold_c": 9}
    })
    assert changed.status_code == 200
    db = connect()
    db.execute("UPDATE freshness_rules SET rule_value = '9.0' WHERE rule_key = 'temperature.hot_threshold_c'")
    db.execute("UPDATE freshness_rules SET rule_value = '3600' WHERE rule_key = 'temperature.exposure_limit_seconds'")
    db.commit(); db.close()
    response = client.post("/api/v1/admin/freshness-rules/reset", json={"reason": "restore defaults"})
    assert response.status_code == 200 and response.json["changed_count"] == 1
    db = connect()
    assert db.execute("SELECT rule_value FROM freshness_rules WHERE rule_key = 'humidity.vegetable.min_pct'").fetchone()[0] == "80"
    assert db.execute("SELECT rule_value FROM freshness_rules WHERE rule_key = 'temperature.hot_threshold_c'").fetchone()[0] == "9.0"
    assert db.execute("SELECT rule_value FROM freshness_rules WHERE rule_key = 'temperature.exposure_limit_seconds'").fetchone()[0] == "3600"
    audit_count = db.execute("SELECT COUNT(*) FROM freshness_rule_audit").fetchone()[0]
    db.close()
    assert audit_count == 3


def test_reset_noop_does_not_add_audit(admin_client):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    assert client.post("/api/v1/admin/freshness-rules/reset", json={"reason": "already default"}).json["changed_count"] == 0
    db = connect(); assert db.execute("SELECT COUNT(*) FROM freshness_rule_audit").fetchone()[0] == 0; db.close()


def test_temperature_stateful_rules_are_editable_except_continuity_gap(admin_client):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    db = connect()
    db.execute("INSERT INTO temperature_exposure_state VALUES ('D1', '', 4000, 1, 1, '2026-01-01T00:00:00Z', 1)")
    db.execute("INSERT INTO gas_anomaly_state VALUES ('D1', '', 100, 10, 1000, 2, 1)")
    db.commit(); db.close()
    metadata = client.get("/api/v1/admin/freshness-rules").json["rules"]
    assert metadata["temperature"]["exposure_limit_seconds"]["editable"] is True
    assert metadata["temperature"]["hot_threshold_c"]["editable"] is True
    assert metadata["temperature"]["continuity_gap_seconds"]["editable"] is False
    response = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "shorten exposure", "rules": {"temperature.exposure_limit_seconds": 3600}
    })
    assert response.status_code == 200
    db = connect()
    state = db.execute("SELECT * FROM temperature_exposure_state").fetchone()
    gas = db.execute("SELECT * FROM gas_anomaly_state").fetchone()
    assert (state["exposure_seconds"], state["exposure_active"], state["exposure_exceeded"], state["last_valid_temperature_timestamp"], state["continuity_broken"]) == (0, 0, 0, None, 0)
    assert (gas["baseline"], gas["baseline_sample_count"], gas["anomaly_active"]) == (100, 10, 1)
    db.close()


@pytest.mark.parametrize("value", [6, 6.5])
def test_admin_can_update_hot_threshold_and_reset_temperature_state(admin_client, value):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    db = connect()
    db.execute("INSERT INTO temperature_exposure_state VALUES ('D1', '', 4000, 1, 1, '2026-01-01T00:00:00Z', 1)")
    db.commit(); db.close()
    response = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "adjust threshold", "rules": {"temperature.hot_threshold_c": value}
    })
    assert response.status_code == 200
    db = connect()
    state = db.execute("SELECT * FROM temperature_exposure_state").fetchone()
    assert (state["exposure_seconds"], state["exposure_active"], state["exposure_exceeded"], state["last_valid_temperature_timestamp"], state["continuity_broken"]) == (0, 0, 0, None, 0)
    db.close()


@pytest.mark.parametrize("value", [12, 13])
def test_hot_threshold_cannot_reach_or_exceed_locked_critical_threshold(admin_client, value):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    response = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "invalid relationship", "rules": {"temperature.hot_threshold_c": value}
    })
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_RULE_VALUE"
    db = connect()
    assert db.execute("SELECT rule_value FROM freshness_rules WHERE rule_key = 'temperature.hot_threshold_c'").fetchone()[0] == "5.0"
    assert db.execute("SELECT COUNT(*) FROM freshness_rule_audit").fetchone()[0] == 0
    db.close()


@pytest.mark.parametrize("value", [True, "6", float("nan"), float("inf"), -1, 51])
def test_hot_threshold_strict_domain_validation(admin_client, value):
    client, _ = admin_client
    login(client, "admin", "admin-password")
    response = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "invalid", "rules": {"temperature.hot_threshold_c": value}
    })
    assert response.status_code == 400


@pytest.mark.parametrize("value", [0, -1, True, "3600", 3600.0])
def test_exposure_limit_requires_positive_strict_integer(admin_client, value):
    client, _ = admin_client
    login(client, "admin", "admin-password")
    response = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "invalid", "rules": {"temperature.exposure_limit_seconds": value}
    })
    assert response.status_code == 400


def test_mixed_exposure_and_stateless_update_resets_once_atomically(admin_client):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    db = connect(); db.execute("INSERT INTO temperature_exposure_state VALUES ('D1', '', 4000, 1, 1, '2026-01-01T00:00:00Z', 1)"); db.commit(); db.close()
    response = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "mixed update", "rules": {"temperature.exposure_limit_seconds": 3600, "storage.MEAT.max_duration_days": 4}
    })
    assert response.status_code == 200
    db = connect()
    assert db.execute("SELECT rule_value FROM freshness_rules WHERE rule_key = 'storage.MEAT.max_duration_days'").fetchone()[0] == "4"
    assert db.execute("SELECT exposure_seconds FROM temperature_exposure_state").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM freshness_rule_audit").fetchone()[0] == 2
    db.close()


def test_reset_failure_rolls_back_exposure_rule(monkeypatch, admin_client):
    client, connect = admin_client
    login(client, "admin", "admin-password")
    monkeypatch.setattr(admin_route, "reset_state_for_rule_keys", lambda *_: (_ for _ in ()).throw(RuntimeError("reset failed")))
    response = client.put("/api/v1/admin/freshness-rules", json={
        "reason": "should rollback", "rules": {"temperature.exposure_limit_seconds": 3600}
    })
    assert response.status_code == 500
    db = connect()
    assert db.execute("SELECT rule_value FROM freshness_rules WHERE rule_key = 'temperature.exposure_limit_seconds'").fetchone()[0] == "7200"
    assert db.execute("SELECT COUNT(*) FROM freshness_rule_audit").fetchone()[0] == 0
    db.close()
