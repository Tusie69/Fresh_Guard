import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid

import pytest
import requests

from app import create_app
from app import init_db as init_db_module
from app.routes import events as events_module
from app.routes import readings as readings_module
from app.services.reading_protocol import decode_compact_reading
from firmware import simulator


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "hardening-test.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(events_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    init_db_module.init_db()

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


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


def event_payload(**overrides):
    payload = {
        "event_id": "event-001",
        "device_id": "FG-ESP32-01",
        "timestamp": "2026-09-25T12:00:00+07:00",
        "event_type": "door_closed",
        "payload": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def compact_reading_payload(**overrides):
    payload = {
        "id": str(uuid.uuid4()),
        "d": "FG-ESP32-01",
        "t": 1727253000,
        "tc": 5.2,
        "h": 61.5,
        "g": 302,
        "o": 0,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "", "content_type": "application/json"},
        {"data": "{", "content_type": "application/json"},
        {"json": []},
        {"json": None},
    ],
)
def test_readings_reject_empty_malformed_and_non_object_json(client, kwargs):
    response = client.post("/api/v1/readings", **kwargs)
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_JSON"
    assert response.json["message"]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("device_id", "  ", "INVALID_DEVICE_ID"),
        ("device_id", 123, "INVALID_DEVICE_ID"),
        ("timestamp", "not-a-date", "INVALID_TIMESTAMP"),
        ("temperature_c", "cold", "INVALID_SENSOR_VALUE"),
        ("humidity_pct", float("nan"), "INVALID_SENSOR_VALUE"),
        ("gas_raw", float("inf"), "INVALID_SENSOR_VALUE"),
        ("door_open", "false", "INVALID_DOOR_STATE"),
        ("door_open", None, "INVALID_DOOR_STATE"),
        ("open_duration_seconds", -1, "INVALID_OPEN_DURATION"),
        ("open_duration_seconds", "10", "INVALID_OPEN_DURATION"),
        ("open_duration_seconds", None, "INVALID_OPEN_DURATION"),
    ],
)
def test_readings_reject_invalid_fields(client, field, value, error):
    response = client.post(
        "/api/v1/readings", json=reading_payload(**{field: value})
    )
    assert response.status_code == 400
    assert response.json["error"] == error


def test_readings_accept_null_sensor_values_without_marking_them_fresh(client):
    response = client.post(
        "/api/v1/readings",
        json=reading_payload(temperature_c=None, humidity_pct=None, gas_raw=None),
    )
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Check Food"


def test_unknown_food_does_not_create_reading(client):
    response = client.post(
        "/api/v1/readings", json=reading_payload(food_id="missing-food")
    )
    history = client.get("/api/v1/readings")
    assert response.status_code == 404
    assert response.json["error"] == "FOOD_NOT_FOUND"
    assert history.json["count"] == 0


def test_readings_reject_missing_required_fields(client):
    payload = reading_payload()
    del payload["gas_raw"]
    response = client.post("/api/v1/readings", json=payload)
    assert response.status_code == 400
    assert "gas_raw" in response.json["fields"]


def test_compact_reading_create_returns_canonical_response(client):
    payload = compact_reading_payload(od=0, f=None)

    response = client.post("/api/v1/readings", json=payload)

    assert response.status_code == 201
    assert response.json["success"] is True
    assert response.json["duplicate"] is False
    assert response.json["device_reading_id"] == payload["id"]
    assert response.json["reading_id"] == 1
    assert set(response.json["freshness"]) == {"status", "reason"}
    assert _reading_count() == 1
    row = _stored_reading(payload["d"], payload["id"])
    assert row["timestamp"] == "2024-09-25T15:30:00+07:00"
    assert row["door_open"] == 0
    assert row["temperature_c"] == payload["tc"]
    assert row["humidity_pct"] == payload["h"]
    assert row["gas_raw"] == payload["g"]


def test_compact_reading_duplicate_returns_original_without_second_row(client):
    payload = compact_reading_payload()
    first = client.post("/api/v1/readings", json=payload)
    duplicate = client.post("/api/v1/readings", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert duplicate.json["reading_id"] == first.json["reading_id"]
    assert duplicate.json["freshness"] == first.json["freshness"]
    assert _reading_count() == 1


def test_compact_reading_changed_sensor_conflicts_without_second_row(client):
    payload = compact_reading_payload()
    assert client.post("/api/v1/readings", json=payload).status_code == 201

    conflict = client.post(
        "/api/v1/readings", json={**payload, "tc": payload["tc"] + 1}
    )

    assert conflict.status_code == 409
    assert conflict.json["error"] == "DEVICE_READING_ID_CONFLICT"
    assert _reading_count() == 1


def test_compact_reading_unknown_food_keeps_existing_404(client):
    response = client.post(
        "/api/v1/readings", json=compact_reading_payload(f="missing-food")
    )

    assert response.status_code == 404
    assert response.json["error"] == "FOOD_NOT_FOUND"
    assert _reading_count() == 0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"t": "not-a-timestamp"}, "Unix timestamp in seconds"),
        ({"o": 2}, "integer 0 or 1"),
        ({"o": True}, "integer 0 or 1"),
        ({"o": False}, "integer 0 or 1"),
        ({"o": "1"}, "integer 0 or 1"),
        ({"temperature_c": 5.2}, "cannot be mixed"),
    ],
)
def test_invalid_compact_payload_returns_400(client, change, message):
    response = client.post(
        "/api/v1/readings", json={**compact_reading_payload(), **change}
    )

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_COMPACT_PAYLOAD"
    assert message in response.json["message"]


def test_canonical_reading_still_creates_duplicate_and_conflict(client):
    reading_id = str(uuid.uuid4())
    payload = reading_payload(device_reading_id=reading_id)
    first = client.post("/api/v1/readings", json=payload)
    duplicate = client.post("/api/v1/readings", json=payload)
    conflict = client.post(
        "/api/v1/readings", json={**payload, "temperature_c": 6}
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert conflict.status_code == 409
    assert _reading_count() == 1


def test_compact_then_equivalent_canonical_is_idempotent(client):
    compact = compact_reading_payload(od=0)
    canonical = decode_compact_reading(compact)

    first = client.post("/api/v1/readings", json=compact)
    equivalent = client.post("/api/v1/readings", json=canonical)

    assert first.status_code == 201
    assert equivalent.status_code == 200
    assert equivalent.json["duplicate"] is True
    assert equivalent.json["reading_id"] == first.json["reading_id"]
    assert equivalent.json["freshness"] == first.json["freshness"]
    assert _reading_count() == 1


def test_compact_and_canonical_equivalent_readings_have_same_freshness(client):
    compact = compact_reading_payload()
    canonical = decode_compact_reading(compact)
    canonical["device_reading_id"] = str(uuid.uuid4())

    compact_response = client.post("/api/v1/readings", json=compact)
    canonical_response = client.post("/api/v1/readings", json=canonical)

    assert compact_response.status_code == 201
    assert canonical_response.status_code == 201
    assert compact_response.json["freshness"] == canonical_response.json["freshness"]
    assert _reading_count() == 2


def _reading_count():
    connection = readings_module.get_db_connection()
    try:
        return connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
    finally:
        connection.close()


def _stored_reading(device_id, reading_id):
    connection = readings_module.get_db_connection()
    try:
        return connection.execute(
            "SELECT * FROM sensor_readings WHERE device_id = ? AND device_reading_id = ?",
            (device_id, reading_id),
        ).fetchone()
    finally:
        connection.close()


def test_idemp_001_new_uuid_reading_is_saved_and_echoed(client):
    reading_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/readings",
        json=reading_payload(device_reading_id=reading_id.upper()),
    )

    assert response.status_code == 201
    assert response.json["device_reading_id"] == reading_id
    assert response.json["duplicate"] is False
    assert _reading_count() == 1
    row = _stored_reading("FG-ESP32-01", reading_id)
    assert row is not None
    assert row["freshness_status"] == response.json["freshness"]["status"]
    assert row["freshness_reason"] == response.json["freshness"]["reason"]
    assert row["freshness_evaluated_at"]


def test_idemp_002_same_payload_returns_original_reading(client, monkeypatch):
    reading_id = str(uuid.uuid4())
    payload = reading_payload(device_reading_id=reading_id)
    first = client.post("/api/v1/readings", json=payload)

    def freshness_must_not_be_recalculated(**_kwargs):
        raise AssertionError("duplicate request recalculated freshness")

    monkeypatch.setattr(readings_module, "evaluate_freshness", freshness_must_not_be_recalculated)
    duplicate = client.post("/api/v1/readings", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert duplicate.json["reading_id"] == first.json["reading_id"]
    assert duplicate.json["freshness"] == first.json["freshness"]
    assert _reading_count() == 1


def test_idemp_002_defaults_and_trimmed_food_id_are_canonicalized(client):
    reading_id = str(uuid.uuid4())
    first = client.post(
        "/api/v1/readings",
        json=reading_payload(device_reading_id=reading_id),
    )
    duplicate_payload = reading_payload(
        device_reading_id=reading_id.upper(), open_duration_seconds=0
    )
    duplicate = client.post("/api/v1/readings", json=duplicate_payload)

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert duplicate.json["reading_id"] == first.json["reading_id"]
    assert _reading_count() == 1


@pytest.mark.parametrize(
    "change",
    [
        {"temperature_c": 6},
        {"humidity_pct": 61},
        {"gas_raw": 301},
        {"door_open": True},
        {"open_duration_seconds": 1},
        {"timestamp": "2026-09-25T12:00:01+07:00"},
        {"food_id": "FG-FOOD-OTHER"},
    ],
)
def test_idemp_003_to_010_payload_change_conflicts_without_mutation(client, change):
    reading_id = str(uuid.uuid4())
    original = reading_payload(device_reading_id=reading_id)
    first = client.post("/api/v1/readings", json=original)
    before = dict(_stored_reading("FG-ESP32-01", reading_id))

    conflict = client.post(
        "/api/v1/readings", json={**original, **change}
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert _reading_count() == 1
    assert dict(_stored_reading("FG-ESP32-01", reading_id)) == before


def test_idemp_004_food_id_conflict_even_if_new_food_does_not_exist(client):
    reading_id = str(uuid.uuid4())
    original = reading_payload(device_reading_id=reading_id, food_id="food-one")
    assert client.post("/api/v1/foods", json={
        "food_id": "food-one", "food_name": "Food", "category": "MEAT",
        "inserted_at": "2026-09-25"
    }).status_code == 201
    assert client.post("/api/v1/readings", json=original).status_code == 201

    conflict = client.post(
        "/api/v1/readings", json={**original, "food_id": "food-two"}
    )

    assert conflict.status_code == 409
    assert _reading_count() == 1


def test_idemp_006_same_uuid_on_different_devices_is_allowed(client):
    reading_id = str(uuid.uuid4())
    first = client.post("/api/v1/readings", json=reading_payload(device_reading_id=reading_id))
    second = client.post(
        "/api/v1/readings",
        json=reading_payload(device_id="FG-ESP32-02", device_reading_id=reading_id),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert _reading_count() == 2


def test_idemp_007_concurrent_duplicate_requests_create_one_row(client):
    reading_id = str(uuid.uuid4())
    payload = reading_payload(device_reading_id=reading_id)
    barrier = Barrier(2)
    app = client.application

    def send_request():
        with app.test_client() as thread_client:
            barrier.wait(timeout=5)
            response = thread_client.post("/api/v1/readings", json=payload)
            return response.status_code, response.json

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: send_request(), range(2)))

    assert sorted(status for status, _body in results) == [200, 201]
    assert sum(body["duplicate"] is False for _status, body in results) == 1
    assert _reading_count() == 1


def test_idemp_008_reading_id_is_required(client):
    payload = reading_payload()
    payload.pop("device_reading_id")
    response = client.post("/api/v1/readings", json=payload)
    assert response.status_code == 400
    assert response.json["error"] == "MISSING_FIELDS"
    assert response.json["fields"] == ["device_reading_id"]
    assert _reading_count() == 0


@pytest.mark.parametrize(
    "invalid_id",
    [
        "random-id",
        "550e8400-e29b-11d4-a716-446655440000",
        "550e8400-e29b-41d4-a716-44665544000",
        None,
        123,
    ],
)
def test_idemp_009_rejects_non_v4_or_malformed_ids(client, invalid_id):
    response = client.post(
        "/api/v1/readings", json=reading_payload(device_reading_id=invalid_id)
    )
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_DEVICE_READING_ID"


def test_snapshot_003_persists_after_database_reopen(client):
    reading_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/readings", json=reading_payload(device_reading_id=reading_id)
    )
    row = _stored_reading("FG-ESP32-01", reading_id)
    assert response.status_code == 201
    assert row["freshness_status"] == response.json["freshness"]["status"]
    assert row["freshness_reason"] == response.json["freshness"]["reason"]
    assert row["freshness_evaluated_at"]


def test_snapshot_004_missing_reading_id_is_rejected_without_row(client):
    payload = reading_payload()
    payload.pop("device_reading_id")
    assert client.post("/api/v1/readings", json=payload).status_code == 400
    assert _reading_count() == 0


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_history_rejects_non_positive_limit(client, limit):
    response = client.get(f"/api/v1/readings?limit={limit}")
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_LIMIT"


@pytest.mark.parametrize("limit", [None, "abc", "null"])
def test_history_uses_default_limit_for_missing_or_unparseable_limit(client, limit):
    url = "/api/v1/readings" if limit is None else f"/api/v1/readings?limit={limit}"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json["limit"] == 20


def test_history_caps_oversized_limit(client):
    response = client.get("/api/v1/readings?limit=999999999")
    assert response.status_code == 200
    assert response.json["limit"] == 100


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "", "content_type": "application/json"},
        {"data": "{", "content_type": "application/json"},
        {"json": []},
        {"json": None},
    ],
)
def test_events_reject_empty_malformed_and_non_object_json(client, kwargs):
    response = client.post("/api/v1/events", **kwargs)
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_JSON"


@pytest.mark.parametrize(
    "payload",
    [
        {"device_id": "dev", "timestamp": "2026-09-25T12:00:00", "event_type": "door"},
        {"event_id": "e", "timestamp": "2026-09-25T12:00:00", "event_type": "door"},
        event_payload(event_id=""),
        event_payload(event_id=12),
        event_payload(device_id=" "),
        event_payload(event_type=None),
        event_payload(timestamp="yesterday"),
    ],
)
def test_events_reject_missing_or_invalid_fields(client, payload):
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 400
    assert response.json["error"]


def test_duplicate_event_remains_idempotent(client):
    first = client.post("/api/v1/events", json=event_payload())
    duplicate = client.post("/api/v1/events", json=event_payload())
    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True


def test_event_sync_lost_response_retries_same_id_and_creates_one_row(
    client, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_events.jsonl"
    payload = event_payload(event_id=str(uuid.uuid4()))
    calls = []

    class ClientResponse:
        def __init__(self, response):
            self.status_code = response.status_code
            self.body = response.get_json()

        def json(self):
            return self.body

    def post_via_test_client(_url, *, json, timeout):
        calls.append(dict(json))
        response = client.post("/api/v1/events", json=json)
        if len(calls) == 1:
            assert response.status_code == 201
            raise requests.Timeout("backend committed; response lost")
        return ClientResponse(response)

    monkeypatch.setattr(simulator.requests, "post", post_via_test_client)
    result = simulator.submit_event(
        payload, queue_file, sleep_fn=lambda _delay: None
    )

    assert [call["event_id"] for call in calls] == [payload["event_id"]] * 2
    assert calls == [payload, payload]
    assert result.status_code == 200
    assert result.body["duplicate"] is True
    assert _event_count(payload["event_id"]) == 1
    assert simulator.load_pending_events(queue_file) == []


def _event_count(event_id):
    connection = events_module.get_db_connection()
    try:
        return connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()[0]
    finally:
        connection.close()


def test_events_missing_required_field_reports_400(client):
    payload = event_payload()
    del payload["event_id"]
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 400
    assert "event_id" in response.json["fields"]
