import sqlite3
import uuid

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings
from app.services.rule_provider import RULE_KEYS, get_freshness_rules


@pytest.mark.parametrize("legacy_state", ["missing_table", "missing_critical_key"])
def test_startup_upgrades_existing_db_and_preserves_data(tmp_path, monkeypatch, legacy_state):
    path = tmp_path / "existing.db"

    def connect():
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(init_db_module, "get_db_connection", connect)
    monkeypatch.setattr(readings, "get_db_connection", connect)
    init_db_module.init_db()
    connection = connect()
    connection.execute(
        "INSERT INTO sensor_readings (device_id, timestamp, temperature_c, "
        "humidity_pct, gas_raw, door_open) VALUES ('legacy', '2026-01-01T00:00:00Z', 4, 60, 100, 0)"
    )
    if legacy_state == "missing_table":
        connection.execute("DROP TABLE freshness_rules")
    else:
        connection.execute(
            "DELETE FROM freshness_rules WHERE rule_key='temperature.critical_threshold_c'"
        )
        connection.execute(
            "UPDATE freshness_rules SET rule_value='6.5' WHERE rule_key='temperature.hot_threshold_c'"
        )
    connection.commit()
    connection.close()

    payload = dict(device_id="startup-test", device_reading_id=str(uuid.uuid4()),
                   timestamp="2026-09-28T10:00:00+07:00", temperature_c=4,
                   humidity_pct=60, gas_raw=100, door_open=False)
    for expected_code in (201, 200):
        # Recreate the application using the SAME existing database.
        client = create_app().test_client()
        response = client.post("/api/v1/readings", json=payload)
        assert response.status_code == expected_code
        assert response.json["freshness"]["status"] == "Fresh / Normal"
        connection = connect()
        rules = get_freshness_rules(connection)
        assert rules.temperature_critical_threshold_c == 12
        assert rules.temperature_hot_threshold_c == (6.5 if legacy_state == "missing_critical_key" else 5)
        assert {r[0] for r in connection.execute("SELECT rule_key FROM freshness_rules")} == RULE_KEYS
        assert connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0] == 2
        assert connection.execute("SELECT temperature_c FROM sensor_readings WHERE device_id='legacy'").fetchone()[0] == 4
        connection.close()
