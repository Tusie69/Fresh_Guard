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


class StubResponse:
    text = "{}"

    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body or {}

    def json(self):
        return self.body


@pytest.mark.parametrize("transient_status", [408, 429, 503])
def test_transient_http_statuses_retry(transient_status, canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    calls = []
    responses = iter((StubResponse(transient_status), StubResponse(201)))

    def fake_post(_url, *, json, timeout):
        calls.append(deepcopy(json))
        return next(responses)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0]["id"] == canonical_payload["device_reading_id"]
    assert simulator.load_pending_readings(queue_file) == []


@pytest.mark.parametrize("status", [400, 409])
def test_permanent_or_conflict_status_dead_letters_and_removes(status, canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    calls = []

    def fake_post(_url, *, json, timeout):
        calls.append(deepcopy(json))
        return StubResponse(status)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert len(calls) == 1
    assert simulator.load_pending_readings(queue_file) == []
    dead_letters = queue_file.parent / "dead_letter_readings.jsonl"
    record = json.loads(dead_letters.read_text(encoding="utf-8"))
    assert record["payload"] == canonical_payload
    assert record["http_status"] == status
    assert record["payload"]["device_reading_id"] == canonical_payload["device_reading_id"]


def test_duplicate_ack_removes_item_after_lost_response(canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    stored_ids = set()
    calls = []

    def fake_post(_url, *, json, timeout):
        reading_id = json["id"]
        calls.append(deepcopy(json))
        already_stored = reading_id in stored_ids
        stored_ids.add(reading_id)
        if not already_stored:
            raise simulator.requests.Timeout("response lost after commit")
        return StubResponse(200, {"duplicate": True})

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert len(stored_ids) == 1
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert simulator.load_pending_readings(queue_file) == []


def test_pending_readings_flush_in_fifo_and_pause_when_head_fails(
    canonical_payload, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_readings.jsonl"
    readings = []
    for index in range(3):
        reading = deepcopy(canonical_payload)
        reading["device_reading_id"] = str(uuid.uuid4())
        reading["temperature_c"] += index
        readings.append(reading)
        simulator.enqueue_reading(reading, queue_file)

    attempted_ids = []
    backend_online = False

    def fake_post(_url, *, json, timeout):
        attempted_ids.append(json["id"])
        if not backend_online:
            return StubResponse(503)
        return StubResponse(201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)

    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)
    assert attempted_ids == [readings[0]["device_reading_id"]] * simulator.MAX_RETRIES
    assert simulator.load_pending_readings(queue_file) == readings

    attempted_ids.clear()
    backend_online = True
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert attempted_ids == [reading["device_reading_id"] for reading in readings]
    assert simulator.load_pending_readings(queue_file) == []


def test_permanent_reading_does_not_block_following_readings(canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    bad = deepcopy(canonical_payload)
    good = deepcopy(canonical_payload)
    bad["device_reading_id"] = str(uuid.uuid4())
    good["device_reading_id"] = str(uuid.uuid4())
    simulator.enqueue_reading(bad, queue_file)
    simulator.enqueue_reading(good, queue_file)
    attempted = []

    def fake_post(_url, *, json, timeout):
        attempted.append(json["device_reading_id"] if "device_reading_id" in json else json["id"])
        return StubResponse(400) if len(attempted) == 1 else StubResponse(201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)
    assert attempted == [bad["device_reading_id"], good["device_reading_id"]]
    assert simulator.load_pending_readings(queue_file) == []


def test_dead_letter_survives_restart_window_without_duplicate_record(
    canonical_payload, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    response = StubResponse(400)
    assert simulator._persist_dead_letter(canonical_payload, response, queue_file, "reading")

    monkeypatch.setattr(simulator.requests, "post", lambda *_args, **_kwargs: StubResponse(400))
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    dead_letters = queue_file.parent / "dead_letter_readings.jsonl"
    records = [json.loads(line) for line in dead_letters.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["payload"] == canonical_payload
    assert simulator.load_pending_readings(queue_file) == []


def test_main_checks_pending_queue_each_sampling_cycle(monkeypatch):
    class StopLoop(Exception):
        pass

    flushes = []
    sleeps = []

    class StubThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    def stop_after_first_sample(delay):
        sleeps.append(delay)
        if len(sleeps) == 2:
            raise StopLoop

    monkeypatch.setattr(simulator, "process_pending_readings", lambda *args, **kwargs: flushes.append(True))
    monkeypatch.setattr(simulator, "process_pending_events", lambda: None)
    monkeypatch.setattr(simulator, "freshness_polling_loop", lambda: None)
    monkeypatch.setattr(simulator.threading, "Thread", StubThread)
    monkeypatch.setattr(simulator, "create_reading_payload", lambda **kwargs: {"device_reading_id": "test"})
    monkeypatch.setattr(simulator, "enqueue_reading", lambda _reading: True)
    monkeypatch.setattr(simulator, "DOOR_OPEN_DURATION", 0)
    monkeypatch.setattr(simulator.time, "sleep", stop_after_first_sample)

    with pytest.raises(StopLoop):
        simulator.main()

    assert len(flushes) == 2  # startup recovery and the running sampling cycle
