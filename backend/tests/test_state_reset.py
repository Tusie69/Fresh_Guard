import sqlite3

import pytest

from app.services.state_reset import (
    apply_stateful_rule_transaction,
    reset_gas_state,
    reset_state_for_rule_keys,
    reset_temperature_state,
)


@pytest.fixture
def state_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE temperature_exposure_state (
            device_id TEXT, food_id TEXT, exposure_seconds REAL,
            exposure_active INTEGER, exposure_exceeded INTEGER,
            last_valid_temperature_timestamp TEXT, continuity_broken INTEGER,
            PRIMARY KEY (device_id, food_id)
        );
        CREATE TABLE gas_anomaly_state (
            device_id TEXT, food_id TEXT, baseline REAL,
            baseline_sample_count INTEGER, baseline_sum REAL,
            consecutive_anomaly_count INTEGER, anomaly_active INTEGER,
            PRIMARY KEY (device_id, food_id)
        );
        CREATE TABLE sensor_fault_state (id INTEGER PRIMARY KEY, fault_active INTEGER);
        CREATE TABLE sensor_readings (id INTEGER PRIMARY KEY, freshness_status TEXT);
        CREATE TABLE events (id INTEGER PRIMARY KEY, event_type TEXT);
        CREATE TABLE food_items (id INTEGER PRIMARY KEY, food_id TEXT);
        INSERT INTO temperature_exposure_state VALUES
            ('D1', 'F1', 4000, 1, 1, '2026-01-01T00:00:00+00:00', 1),
            ('D2', '', 20, 1, 0, '2026-01-02T00:00:00+00:00', 0);
        INSERT INTO gas_anomaly_state VALUES
            ('D1', 'F1', 100, 10, 1000, 3, 1),
            ('D2', '', 200, 5, 1000, 1, 0);
        INSERT INTO sensor_fault_state VALUES (1, 1);
        INSERT INTO sensor_readings VALUES (1, 'Fresh / Normal');
        INSERT INTO events VALUES (1, 'GAS_ANOMALY_STARTED');
        INSERT INTO food_items VALUES (1, 'F1');
    """)
    yield db
    db.close()


def test_temperature_reset_clears_fields_and_keeps_rows(state_db):
    assert reset_temperature_state(state_db) == 2
    rows = state_db.execute("SELECT * FROM temperature_exposure_state ORDER BY device_id").fetchall()
    assert [(row["device_id"], row["exposure_seconds"], row["exposure_active"], row["exposure_exceeded"], row["last_valid_temperature_timestamp"], row["continuity_broken"]) for row in rows] == [
        ("D1", 0, 0, 0, None, 0), ("D2", 0, 0, 0, None, 0)
    ]


def test_gas_reset_clears_fields_and_keeps_rows(state_db):
    assert reset_gas_state(state_db) == 2
    rows = state_db.execute("SELECT * FROM gas_anomaly_state ORDER BY device_id").fetchall()
    assert [(row["device_id"], row["baseline"], row["baseline_sample_count"], row["baseline_sum"], row["consecutive_anomaly_count"], row["anomaly_active"]) for row in rows] == [
        ("D1", None, 0, 0, 0, 0), ("D2", None, 0, 0, 0, 0)
    ]


def test_mapping_resets_only_affected_state_and_preserves_history(state_db):
    reset_state_for_rule_keys(state_db, {"temperature.hot_threshold_c"})
    assert state_db.execute("SELECT baseline FROM gas_anomaly_state WHERE device_id = 'D1'").fetchone()[0] == 100
    assert state_db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert state_db.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0] == 1
    assert state_db.execute("SELECT COUNT(*) FROM food_items").fetchone()[0] == 1
    assert state_db.execute("SELECT fault_active FROM sensor_fault_state").fetchone()[0] == 1


def test_reset_emits_no_events(state_db):
    before = state_db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    reset_state_for_rule_keys(state_db, {"temperature.exposure_limit_seconds", "gas.anomaly_increase_pct"})
    assert state_db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before


def test_transaction_rolls_back_update_audit_and_state_on_failure(state_db):
    state_db.execute("CREATE TABLE rule_audit (value TEXT)")
    def update(connection):
        connection.execute("UPDATE temperature_exposure_state SET exposure_seconds = 0")
    def audit(connection):
        connection.execute("INSERT INTO rule_audit VALUES ('change')")
        raise RuntimeError("simulated reset failure")
    with pytest.raises(RuntimeError):
        apply_stateful_rule_transaction(state_db, update, audit, {"temperature.hot_threshold_c"})
    assert state_db.execute("SELECT exposure_seconds FROM temperature_exposure_state WHERE device_id = 'D1'").fetchone()[0] == 4000
    assert state_db.execute("SELECT COUNT(*) FROM rule_audit").fetchone()[0] == 0


def test_door_mapping_is_explicitly_unsupported(state_db):
    with pytest.raises(ValueError, match="Door"):
        reset_state_for_rule_keys(state_db, {"door.open_duration_seconds"})
