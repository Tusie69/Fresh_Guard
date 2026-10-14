import sqlite3
from datetime import datetime, timedelta, timezone

from app.services.gas_anomaly import update_gas_anomaly_state
from app.services.state_reset import reset_gas_state_for_device


def db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE gas_anomaly_state (
        device_id TEXT NOT NULL, food_id TEXT NOT NULL DEFAULT '',
        baseline REAL NULL, baseline_sample_count INTEGER NOT NULL DEFAULT 0,
        baseline_sum REAL NOT NULL DEFAULT 0,
        consecutive_anomaly_count INTEGER NOT NULL DEFAULT 0,
        anomaly_active INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (device_id, food_id)
    )""")
    connection.execute("""CREATE TABLE gas_baseline_lifecycle (
        device_id TEXT NOT NULL, food_id TEXT NOT NULL DEFAULT '',
        baseline_status TEXT NOT NULL DEFAULT 'WARMING_UP',
        warmup_started_at TEXT NULL,
        stability_values TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (device_id, food_id)
    )""")
    return connection


def reading(connection, value, seconds):
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    return update_gas_anomaly_state(
        connection, "D1", None, value, reading_timestamp=timestamp.isoformat()
    )


def state(connection):
    return connection.execute(
        "SELECT s.*, l.baseline_status FROM gas_anomaly_state s "
        "JOIN gas_baseline_lifecycle l ON l.device_id = s.device_id "
        "AND l.food_id = s.food_id"
    ).fetchone()


def test_unstable_startup_never_finalizes_baseline():
    connection = db()
    for index, value in enumerate((200, 230, 300, 450, 600)):
        reading(connection, value, index * 60)
    row = state(connection)
    assert row["baseline_status"] == "WARMING_UP"
    assert row["baseline"] is None
    assert row["baseline_sample_count"] == 0


def test_stable_window_learns_only_after_warmup():
    connection = db()
    values = (790, 805, 798, 810, 802, 795, 806, 801, 799, 804, 802, 801, 800, 803, 799)
    for index, value in enumerate(values):
        reading(connection, value, index * 60)
    row = state(connection)
    assert row["baseline_status"] == "READY"
    assert 795 <= row["baseline"] <= 805
    assert row["baseline_sample_count"] == 10


def test_reset_device_preserves_state_row_but_restarts_learning():
    connection = db()
    for index in range(15):
        reading(connection, 800, index * 60)
    assert state(connection)["baseline_status"] == "READY"
    assert reset_gas_state_for_device(connection, "D1") == 1
    row = state(connection)
    assert row["baseline"] is None
    assert row["baseline_status"] == "WARMING_UP"
    assert row["anomaly_active"] == 0
