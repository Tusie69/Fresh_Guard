import sqlite3

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import freshness_rules as rules_route
from app.routes import admin as admin_route
from app.services import auth as auth_service
from app.services.auth import create_user
from app.services.rule_provider import (
    DEFAULT_RULES,
    FreshnessRuleProvider,
    FreshnessRuleProviderError,
    FoodCategory,
    RULE_KEYS,
    get_freshness_rules,
)


@pytest.fixture
def rules_db(tmp_path, monkeypatch):
    path = tmp_path / "rules.db"

    def connect():
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(init_db_module, "get_db_connection", connect)
    monkeypatch.setattr(auth_service, "get_db_connection", connect)
    monkeypatch.setattr(rules_route, "get_db_connection", connect)
    monkeypatch.setattr(admin_route, "get_db_connection", connect)
    init_db_module.init_db()
    return connect, path


def test_init_seeds_all_rule_keys_and_reinit_preserves_edit(rules_db):
    connect, _ = rules_db
    connection = connect()
    rows = connection.execute(
        "SELECT rule_key, rule_value FROM freshness_rules ORDER BY rule_key"
    ).fetchall()
    assert len(rows) == 23
    assert {row["rule_key"] for row in rows} == RULE_KEYS
    connection.execute(
        "UPDATE freshness_rules SET rule_value = '6.5' "
        "WHERE rule_key = 'temperature.hot_threshold_c'"
    )
    connection.commit()
    connection.close()
    init_db_module.init_db()
    connection = connect()
    assert connection.execute(
        "SELECT rule_value FROM freshness_rules WHERE rule_key = 'temperature.hot_threshold_c'"
    ).fetchone()[0] == "6.5"
    connection.close()


def test_init_seeds_missing_critical_threshold_without_touching_state(rules_db):
    connect, _ = rules_db
    connection = connect()
    connection.execute(
        "DELETE FROM freshness_rules WHERE rule_key = 'temperature.critical_threshold_c'"
    )
    connection.execute(
        "INSERT INTO temperature_exposure_state (device_id, food_id, exposure_seconds, exposure_active, exposure_exceeded, last_valid_temperature_timestamp, continuity_broken) "
        "VALUES ('D', '', 123, 1, 0, '2026-01-01T00:00:00Z', 0)"
    )
    connection.commit(); connection.close()
    init_db_module.init_db()
    connection = connect()
    assert connection.execute(
        "SELECT rule_value FROM freshness_rules WHERE rule_key = 'temperature.critical_threshold_c'"
    ).fetchone()[0] == "12.0"
    assert connection.execute(
        "SELECT exposure_seconds FROM temperature_exposure_state WHERE device_id = 'D'"
    ).fetchone()[0] == 123
    connection.close()

def test_provider_loads_complete_snapshot_and_preserves_types(rules_db):
    connect, _ = rules_db
    connection = connect()
    rules = get_freshness_rules(connection)
    connection.close()
    assert rules.temperature_hot_threshold_c == 5.0
    assert rules.temperature_critical_threshold_c == 12.0
    assert isinstance(rules.temperature_exposure_limit_seconds, int)
    assert rules.gas_anomaly_deviation_ratio == 0.30
    assert rules.storage_profiles[FoodCategory.MEAT].max_duration_days == 3


def test_provider_loads_persisted_critical_threshold_without_rewriting_it(rules_db):
    connect, _ = rules_db
    connection = connect()
    connection.execute(
        "UPDATE freshness_rules SET rule_value = '14.0' WHERE rule_key = 'temperature.critical_threshold_c'"
    )
    connection.commit()
    assert get_freshness_rules(connection).temperature_critical_threshold_c == 14.0
    connection.close()
    init_db_module.init_db()
    connection = connect()
    assert connection.execute(
        "SELECT rule_value FROM freshness_rules WHERE rule_key = 'temperature.critical_threshold_c'"
    ).fetchone()[0] == "14.0"
    connection.close()


def test_provider_snapshot_loaded_from_db_is_immutable(rules_db):
    connect, _ = rules_db
    connection = connect()
    provider = FreshnessRuleProvider.from_connection(connection)
    connection.close()
    with pytest.raises((AttributeError, TypeError)):
        provider.snapshot().temperature_hot_threshold_c = 8
    with pytest.raises(TypeError):
        provider.snapshot().storage_profiles[FoodCategory.MEAT] = None


def test_provider_missing_row_fails_without_partial_defaults(rules_db):
    connect, _ = rules_db
    connection = connect()
    connection.execute(
        "DELETE FROM freshness_rules WHERE rule_key = 'door.open_duration_seconds'"
    )
    connection.commit()
    with pytest.raises(FreshnessRuleProviderError):
        get_freshness_rules(connection)
    connection.close()


@pytest.fixture
def rules_client(rules_db):
    connect, _ = rules_db
    connection = connect()
    create_user(connection, "user", "user-password", "USER")
    create_user(connection, "admin", "admin-password", "ADMIN")
    connection.commit()
    connection.close()
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="rules-test-secret")
    return app.test_client()


def _login(client, username, password):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_freshness_rules_api_requires_authentication(rules_client):
    assert rules_client.get("/api/v1/freshness-rules").status_code == 401


@pytest.mark.parametrize("username,password", [("user", "user-password"), ("admin", "admin-password")])
def test_freshness_rules_api_is_readable_by_both_roles(rules_client, username, password):
    assert _login(rules_client, username, password).status_code == 200
    response = rules_client.get("/api/v1/freshness-rules")
    assert response.status_code == 200
    rules = response.json["rules"]
    assert rules["temperature"]["hot_threshold_c"] == 5.0
    assert rules["temperature"]["critical_threshold_c"] == 12.0
    assert rules["gas"]["anomaly_increase_pct"] == 30.0
    assert rules["storage"]["MEAT"]["max_duration_days"] == 3


def test_freshness_rules_api_has_no_mutation_methods(rules_client):
    assert rules_client.put("/api/v1/freshness-rules", json={}).status_code == 405
    assert rules_client.patch("/api/v1/freshness-rules", json={}).status_code == 405
