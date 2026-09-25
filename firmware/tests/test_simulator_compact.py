from copy import deepcopy
import json
import uuid

import pytest

from firmware import simulator


@pytest.fixture
def canonical_payload():
    return {
        "device_reading_id": str(uuid.uuid4()),
        "device_id": "esp32_01",
        "timestamp": "2026-09-25T15:00:00+07:00",
        "temperature_c": 5.2,
        "humidity_pct": 61.5,
        "gas_raw": 302,
        "door_open": False,
        "open_duration_seconds": 0,
        "food_id": "FOOD001",
    }


def test_encoder_maps_fields_and_preserves_timestamp_and_id(canonical_payload):
    original = deepcopy(canonical_payload)

    compact = simulator.encode_compact_reading(canonical_payload)

    assert compact == {
        "id": original["device_reading_id"],
        "d": "esp32_01",
        "t": 1790323200,
        "tc": 5.2,
        "h": 61.5,
        "g": 302,
        "o": 0,
        "od": 0,
        "f": "FOOD001",
    }
    assert canonical_payload == original


@pytest.mark.parametrize(("door_open", "expected"), [(False, 0), (True, 1)])
def test_encoder_maps_boolean_door_values(canonical_payload, door_open, expected):
    canonical_payload["door_open"] = door_open
    assert simulator.encode_compact_reading(canonical_payload)["o"] == expected


@pytest.mark.parametrize("door_open", [0, 1, "true", None])
def test_encoder_rejects_non_boolean_door_values(canonical_payload, door_open):
    canonical_payload["door_open"] = door_open
    with pytest.raises(ValueError, match="door_open must be a boolean"):
        simulator.encode_compact_reading(canonical_payload)


def test_encoder_rejects_invalid_timestamp(canonical_payload):
    canonical_payload["timestamp"] = "2026-09-25"
    with pytest.raises(ValueError, match="valid ISO datetime"):
        simulator.encode_compact_reading(canonical_payload)


def test_encoder_defaults_duration_and_omits_absent_food_id(canonical_payload):
    canonical_payload.pop("open_duration_seconds")
    canonical_payload.pop("food_id")

    compact = simulator.encode_compact_reading(canonical_payload)

    assert compact["od"] == 0
    assert "f" not in compact


def test_send_reading_posts_compact_body_and_leaves_input_unchanged(
    canonical_payload, monkeypatch
):
    captured = {}

    class Response:
        status_code = 201
        text = "{}"

        @staticmethod
        def json():
            return {"device_reading_id": canonical_payload["device_reading_id"]}

    def fake_post(url, *, json, timeout):
        captured.update(url=url, body=deepcopy(json), timeout=timeout)
        return Response()

    original = deepcopy(canonical_payload)
    monkeypatch.setattr(simulator.requests, "post", fake_post)

    response = simulator.send_reading(canonical_payload)

    assert response.status_code == 201
    assert captured["url"] == simulator.API_URL
    assert captured["timeout"] == 5
    assert set(captured["body"]) == {"id", "d", "t", "tc", "h", "g", "o", "od", "f"}
    assert not ({"device_id", "timestamp", "temperature_c", "humidity_pct", "gas_raw", "door_open", "device_reading_id"} & captured["body"].keys())
    assert captured["body"]["id"] == original["device_reading_id"]
    assert canonical_payload == original


def test_queue_stays_canonical_and_retries_send_identical_compact_body(
    canonical_payload, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_readings.jsonl"
    assert simulator.enqueue_reading(canonical_payload, queue_file)
    queued_json = json.loads(queue_file.read_text(encoding="utf-8").strip())
    assert queued_json == canonical_payload
    assert "device_reading_id" in queued_json and "id" not in queued_json

    bodies = []
    statuses = iter((503, 201))

    class Response:
        text = "{}"

        def __init__(self, status_code):
            self.status_code = status_code

        def json(self):
            return {"device_reading_id": canonical_payload["device_reading_id"]}

    def fake_post(_url, *, json, timeout):
        bodies.append(deepcopy(json))
        return Response(next(statuses))

    monkeypatch.setattr(simulator.requests, "post", fake_post)

    simulator.send_with_retry(
        simulator.load_pending_readings(queue_file)[0],
        queue_file,
        sleep_fn=lambda _delay: None,
    )

    assert bodies[0] == bodies[1]
    assert bodies[0]["id"] == canonical_payload["device_reading_id"]
    assert simulator.load_pending_readings(queue_file) == []


def test_restart_recovery_encodes_original_queued_identity(canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    recovered = simulator.load_pending_readings(queue_file)[0]
    captured = []

    class Response:
        status_code = 201
        text = "{}"

        @staticmethod
        def json():
            return {"device_reading_id": canonical_payload["device_reading_id"]}

    def fake_post(_url, *, json, timeout):
        captured.append(deepcopy(json))
        return Response()

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert captured[0]["id"] == canonical_payload["device_reading_id"]
    assert simulator.load_pending_readings(queue_file) == []
