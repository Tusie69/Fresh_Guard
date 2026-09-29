import json
import sqlite3
from datetime import date, timedelta
import uuid

import pytest

from app import create_app
from app import init_db as init_db_module
from app.routes import readings as readings_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "freshguard-outbox.db"

    def connect():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect)
    init_db_module.init_db()
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def add_food(client, food_id, expiry, name=None):
    today = date.today()
    assert client.post("/api/v1/foods", json={
        "food_id": food_id,
        "food_name": name or food_id,
        "category": "MEAT",
        "inserted_at": today.isoformat(),
        "expiry_date": expiry,
    }).status_code == 201
    assert client.post(f"/api/v1/foods/{food_id}/activate").status_code == 200


def payload(timestamp="2026-09-28T12:00:00+07:00", **overrides):
    value = {
        "device_id": "FG-ESP32-01",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": timestamp,
        "temperature_c": 4,
        "humidity_pct": 50,
        "gas_raw": 100,
        "door_open": False,
    }
    value.update(overrides)
    return value


def outbox(client):
    connection = readings_module.get_db_connection()
    try:
        return connection.execute(
            "SELECT * FROM notification_outbox ORDER BY id"
        ).fetchall()
    finally:
        connection.close()


def update_expiry(expiry, food_id=None):
    connection = readings_module.get_db_connection()
    try:
        if food_id is None:
            connection.execute("UPDATE food_items SET expiry_date = ?", (expiry,))
        else:
            connection.execute(
                "UPDATE food_items SET expiry_date = ? WHERE food_id = ?",
                (expiry, food_id),
            )
        connection.commit()
    finally:
        connection.close()


def post(client, timestamp):
    response = client.post("/api/v1/readings", json=payload(timestamp))
    assert response.status_code in (201, 200)
    return response


def test_first_snapshot_policy_and_payload(client):
    today = date.today()
    add_food(client, "SOON", (today + timedelta(days=1)).isoformat())
    add_food(client, "FRESH", (today + timedelta(days=10)).isoformat())
    response = post(client, "2026-09-28T12:00:00+07:00")
    assert response.status_code == 201
    rows = outbox(client)
    assert [(row["food_id"], row["notification_type"]) for row in rows] == [
        ("SOON", "FOOD_USE_SOON"),
    ]
    data = json.loads(rows[0]["payload_json"])
    assert data["previous_status"] is None
    assert data["current_status"] == "Use Soon"
    assert data["food_name"] == "SOON"
    assert rows[0]["delivery_status"] == "PENDING"


@pytest.mark.parametrize(("previous_expiry", "current_expiry", "expected"), [
    ((date.today() + timedelta(days=10)), date.today(), "FOOD_USE_SOON"),
    ((date.today() + timedelta(days=10)), date.today() - timedelta(days=1), "FOOD_CHECK_FOOD"),
    (date.today(), date.today() - timedelta(days=1), "FOOD_CHECK_FOOD"),
    (date.today() - timedelta(days=1), date.today() + timedelta(days=10), "FOOD_RECOVERED"),
    (date.today() - timedelta(days=1), date.today(), "FOOD_RECOVERED"),
])
def test_status_transition_policy(client, previous_expiry, current_expiry, expected):
    add_food(client, "F1", previous_expiry.isoformat())
    post(client, "2026-09-28T12:00:00+07:00")
    update_expiry(current_expiry.isoformat())
    post(client, "2026-09-28T12:01:00+07:00")
    rows = outbox(client)
    assert rows[-1]["notification_type"] == expected
    first_status_type = (
        "FOOD_CHECK_FOOD" if previous_expiry < date.today()
        else "FOOD_USE_SOON" if previous_expiry == date.today()
        else None
    )
    if first_status_type is None:
        assert len(rows) == 1
    else:
        assert rows[0]["notification_type"] == first_status_type


@pytest.mark.parametrize(("first_expiry", "second_expiry"), [
    (date.today() + timedelta(days=10), date.today() + timedelta(days=9)),
    (date.today(), date.today() + timedelta(days=10)),
])
def test_unchanged_or_silent_transition_has_no_extra_notification(
    client, first_expiry, second_expiry
):
    add_food(client, "F1", first_expiry.isoformat())
    post(client, "2026-09-28T12:00:00+07:00")
    update_expiry(second_expiry.isoformat())
    post(client, "2026-09-28T12:01:00+07:00")
    post(client, "2026-09-28T12:02:00+07:00")
    rows = outbox(client)
    assert len(rows) == (1 if first_expiry == date.today() else 0)


def test_multiple_foods_are_independent(client):
    today = date.today()
    add_food(client, "A", (today + timedelta(days=10)).isoformat())
    add_food(client, "B", (today + timedelta(days=1)).isoformat())
    add_food(client, "C", (today + timedelta(days=10)).isoformat())
    post(client, "2026-09-28T12:00:00+07:00")
    update_expiry((today - timedelta(days=1)).isoformat(), "B")
    post(client, "2026-09-28T12:01:00+07:00")
    rows = outbox(client)
    assert [(row["food_id"], row["notification_type"]) for row in rows] == [
        ("B", "FOOD_USE_SOON"),
        ("B", "FOOD_CHECK_FOOD"),
    ]


def test_exact_duplicate_does_not_reprocess_outbox(client):
    today = date.today()
    add_food(client, "F1", (today + timedelta(days=1)).isoformat())
    reading = payload()
    assert client.post("/api/v1/readings", json=reading).status_code == 201
    assert client.post("/api/v1/readings", json=reading).status_code == 200
    assert len(outbox(client)) == 1


def test_unchanged_status_after_restart_does_not_notify_again(client):
    today = date.today()
    add_food(client, "F1", (today + timedelta(days=1)).isoformat())
    post(client, "2026-09-28T12:00:00+07:00")
    count_before = len(outbox(client))
    # Re-run idempotent startup against the same SQLite database.
    init_db_module.init_db()
    post(client, "2026-09-28T12:01:00+07:00")
    assert len(outbox(client)) == count_before


def test_event_key_is_deterministic_and_unique(client):
    today = date.today()
    add_food(client, "F1", (today + timedelta(days=1)).isoformat())
    post(client, "2026-09-28T12:00:00+07:00")
    row = outbox(client)[0]
    assert row["event_key"] == f"food:F1:reading:{row['reading_id']}:FOOD_USE_SOON"
    connection = readings_module.get_db_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO notification_outbox "
                "(event_key, notification_type, payload_json, created_at) "
                "VALUES (?, 'FOOD_USE_SOON', '{}', 'now')",
                (row["event_key"],),
            )
    finally:
        connection.close()


def test_outbox_failure_rolls_back_entire_reading(client, monkeypatch):
    today = date.today()
    add_food(client, "F1", (today + timedelta(days=1)).isoformat())
    monkeypatch.setattr(
        readings_module,
        "_persist_food_notification",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("outbox down")),
    )
    with pytest.raises(RuntimeError):
        client.post("/api/v1/readings", json=payload())
    connection = readings_module.get_db_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM food_freshness_snapshots").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM gas_anomaly_state").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM temperature_exposure_state").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM sensor_fault_state").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    finally:
        connection.close()


def test_deactivation_preserves_outbox_and_snapshots(client):
    today = date.today()
    add_food(client, "F1", (today + timedelta(days=1)).isoformat())
    post(client, "2026-09-28T12:00:00+07:00")
    assert client.post("/api/v1/foods/F1/deactivate").status_code == 200
    assert len(outbox(client)) == 1
    connection = readings_module.get_db_connection()
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM food_freshness_snapshots"
        ).fetchone()[0] == 1
    finally:
        connection.close()
