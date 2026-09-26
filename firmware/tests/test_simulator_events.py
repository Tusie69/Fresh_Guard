from copy import deepcopy
import json
import uuid

import pytest
import requests

from firmware import simulator


@pytest.fixture
def canonical_event():
    return {
        "event_id": str(uuid.uuid4()),
        "device_id": "FG-ESP32-01",
        "timestamp": "2026-09-25T12:00:00+07:00",
        "event_type": "door_closed",
        "payload": {"source": "simulator", "door_open": False},
    }


class StubResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body or {}

    def json(self):
        return self.body


def test_successful_event_is_acknowledged_without_queue(canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    sent = []

    def fake_post(url, *, json, timeout):
        sent.append((url, deepcopy(json), timeout))
        return StubResponse(201, {"event_id": canonical_event["event_id"]})

    monkeypatch.setattr(simulator.requests, "post", fake_post)

    response = simulator.submit_event(canonical_event, queue_file, sleep_fn=lambda _delay: None)

    assert response.status_code == 201
    assert sent == [(simulator.EVENTS_API_URL, canonical_event, 5)]
    assert simulator.load_pending_events(queue_file) == []


def test_offline_event_is_durably_queued_and_survives_reload(canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    attempts = []
    backend_online = False

    def offline_post(url, *, json, timeout):
        attempts.append(deepcopy(json))
        if not backend_online:
            raise requests.ConnectionError("backend offline")
        return StubResponse(201)

    monkeypatch.setattr(simulator.requests, "post", offline_post)
    simulator.submit_event(canonical_event, queue_file, sleep_fn=lambda _delay: None)

    lines = queue_file.read_text(encoding="utf-8").splitlines()
    assert len(attempts) == simulator.MAX_RETRIES
    assert len(lines) == 1
    assert json.loads(lines[0]) == canonical_event
    assert simulator.load_pending_events(queue_file) == [canonical_event]

    # Simulate a new process after recovery: state is reconstructed from JSONL.
    backend_online = True
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert attempts[-1] == canonical_event
    assert simulator.load_pending_events(queue_file) == []


@pytest.mark.parametrize("transient_status", [408, 429, 503])
def test_transient_http_status_retries_same_canonical_event(
    transient_status, canonical_event, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_events.jsonl"
    simulator.enqueue_event(canonical_event, queue_file)
    sent = []
    responses = iter((StubResponse(transient_status), StubResponse(201)))

    def fake_post(_url, *, json, timeout):
        sent.append(deepcopy(json))
        return next(responses)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)

    assert sent == [canonical_event, canonical_event]
    assert simulator.load_pending_events(queue_file) == []


@pytest.mark.parametrize("status", [400, 409])
def test_nonretryable_or_conflict_event_is_dead_lettered(status, canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    simulator.enqueue_event(canonical_event, queue_file)
    attempts = []

    def fake_post(_url, *, json, timeout):
        attempts.append(deepcopy(json))
        return StubResponse(status)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)

    assert attempts == [canonical_event]
    assert simulator.load_pending_events(queue_file) == []
    record = json.loads((queue_file.parent / "dead_letter_events.jsonl").read_text(encoding="utf-8"))
    assert record["payload"] == canonical_event
    assert record["http_status"] == status


def test_permanent_event_does_not_block_later_event(canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    bad = deepcopy(canonical_event)
    good = deepcopy(canonical_event)
    good["event_id"] = "event-later"
    simulator.enqueue_event(bad, queue_file)
    simulator.enqueue_event(good, queue_file)
    sent_ids = []

    def fake_post(_url, *, json, timeout):
        sent_ids.append(json["event_id"])
        return StubResponse(400) if len(sent_ids) == 1 else StubResponse(201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert sent_ids == [bad["event_id"], good["event_id"]]
    assert simulator.load_pending_events(queue_file) == []


def test_fifo_recovery_stops_at_failed_head_then_syncs_all_in_order(
    canonical_event, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_events.jsonl"
    events = []
    for index in range(3):
        event = deepcopy(canonical_event)
        event["event_id"] = f"event-{index}"
        event["payload"]["sequence"] = index
        events.append(event)
        simulator.enqueue_event(event, queue_file)

    sent_ids = []
    backend_online = False

    def fake_post(_url, *, json, timeout):
        sent_ids.append(json["event_id"])
        return StubResponse(503 if not backend_online else 201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert sent_ids == [events[0]["event_id"]] * simulator.MAX_RETRIES
    assert simulator.load_pending_events(queue_file) == events

    sent_ids.clear()
    backend_online = True
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert sent_ids == [event["event_id"] for event in events]
    assert simulator.load_pending_events(queue_file) == []


def test_duplicate_ack_removes_event(canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    simulator.enqueue_event(canonical_event, queue_file)
    sent = []
    monkeypatch.setattr(
        simulator,
        "send_event",
        lambda event: (sent.append(deepcopy(event)) or StubResponse(200, {"duplicate": True})),
    )

    response = simulator.send_event_with_retry(
        canonical_event, queue_file, sleep_fn=lambda _delay: None
    )

    assert response.status_code == 200
    assert sent == [canonical_event]
    assert simulator.load_pending_events(queue_file) == []


def test_corrupt_event_queue_line_is_skipped_without_crashing(canonical_event, tmp_path, capsys):
    queue_file = tmp_path / "pending_events.jsonl"
    queue_file.write_text("{not-json}\n" + json.dumps(canonical_event) + "\n", encoding="utf-8")

    assert simulator.load_pending_events(queue_file) == [canonical_event]
    assert "invalid JSON in event queue line 1" in capsys.readouterr().out


def test_main_flushes_event_queue_at_startup_and_during_sampling(monkeypatch):
    class StopLoop(Exception):
        pass

    flushes = []
    sleeps = []

    class StubThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    def stop_after_one_sample(delay):
        sleeps.append(delay)
        if len(sleeps) == 2:
            raise StopLoop

    monkeypatch.setattr(simulator, "process_pending_readings", lambda: None)
    monkeypatch.setattr(simulator, "process_pending_events", lambda: flushes.append(True))
    monkeypatch.setattr(simulator, "freshness_polling_loop", lambda: None)
    monkeypatch.setattr(simulator.threading, "Thread", StubThread)
    monkeypatch.setattr(simulator, "create_reading_payload", lambda **_kwargs: {"event_id": "sample"})
    monkeypatch.setattr(simulator, "enqueue_reading", lambda _reading: True)
    monkeypatch.setattr(simulator, "DOOR_OPEN_DURATION", 0)
    monkeypatch.setattr(simulator.time, "sleep", stop_after_one_sample)

    with pytest.raises(StopLoop):
        simulator.main()

    assert len(flushes) == 2


def door_reading(door_open, duration, second, device_id="FG-ESP32-01"):
    return {
        "device_id": device_id,
        "timestamp": f"2026-09-25T12:00:{second:02d}+07:00",
        "door_open": door_open,
        "open_duration_seconds": duration,
    }


def test_door_open_timeout_and_close_are_emitted_once_per_transition():
    producer = simulator.DoorEventProducer()
    stream = [
        door_reading(False, 0, 0),
        door_reading(True, 0, 5),
        door_reading(True, 10, 10),
        door_reading(True, 20, 15),
        door_reading(True, 29, 20),
        door_reading(True, 30, 25),
        door_reading(True, 35, 30),
        door_reading(True, 40, 35),
        door_reading(True, 45, 40),
        door_reading(False, 0, 45),
    ]

    events = [event for reading in stream for event in producer.observe(reading)]

    assert [event["event_type"] for event in events] == [
        "DOOR_OPENED", "DOOR_TIMEOUT", "DOOR_CLOSED"
    ]
    assert events[0]["payload"] == {"door_open": True}
    assert events[1]["payload"] == {"door_open": True, "open_duration_seconds": 30}
    assert events[2]["payload"] == {"door_open": False, "open_duration_seconds": 0}
    assert [event["timestamp"] for event in events] == [
        stream[1]["timestamp"], stream[5]["timestamp"], stream[9]["timestamp"]
    ]
    assert all(event["device_id"] == "FG-ESP32-01" for event in events)
    assert all(event["event_id"] for event in events)


def test_door_close_before_timeout_and_repeated_open_cycles():
    producer = simulator.DoorEventProducer()
    events = []
    stream = [
        door_reading(False, 0, 0),
        door_reading(True, 0, 5),
        door_reading(True, 10, 10),
        door_reading(False, 0, 15),
        door_reading(True, 0, 20),
        door_reading(True, 30, 25),
        door_reading(False, 0, 30),
        door_reading(True, 0, 35),
        door_reading(True, 30, 40),
        door_reading(False, 0, 45),
    ]
    for reading in stream:
        events.extend(producer.observe(reading))

    event_types = [event["event_type"] for event in events]
    assert event_types == [
        "DOOR_OPENED", "DOOR_CLOSED",
        "DOOR_OPENED", "DOOR_TIMEOUT", "DOOR_CLOSED",
        "DOOR_OPENED", "DOOR_TIMEOUT", "DOOR_CLOSED",
    ]


def test_door_producer_state_is_scoped_per_device():
    producer = simulator.DoorEventProducer()
    producer.observe(door_reading(False, 0, 0, "device-a"))
    producer.observe(door_reading(False, 0, 0, "device-b"))

    events = producer.observe(door_reading(True, 0, 5, "device-a"))

    assert [event["event_type"] for event in events] == ["DOOR_OPENED"]
    assert events[0]["device_id"] == "device-a"
    device_b_events = producer.observe(door_reading(True, 0, 5, "device-b"))
    assert [event["event_type"] for event in device_b_events] == ["DOOR_OPENED"]
    assert device_b_events[0]["device_id"] == "device-b"
    assert producer.observe(door_reading(True, 5, 10, "device-b")) == []


def test_first_open_reading_after_restart_seeds_without_reemitting_episode():
    producer = simulator.DoorEventProducer()

    assert producer.observe(door_reading(True, 35, 0)) == []
    assert producer.observe(door_reading(True, 40, 5)) == []
    closed_events = producer.observe(door_reading(False, 0, 10))
    assert [event["event_type"] for event in closed_events] == ["DOOR_CLOSED"]


def test_produced_event_uses_shared_queue_and_keeps_id_across_retry(
    tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_events.jsonl"
    producer = simulator.DoorEventProducer()
    monkeypatch.setattr(simulator, "submit_event", simulator.submit_event)
    closed = door_reading(False, 0, 0)
    opened = door_reading(True, 0, 5)
    simulator.submit_door_events(closed, producer, queue_file)
    generated = simulator.submit_door_events(opened, producer, queue_file)
    assert len(generated) == 1
    queued = simulator.load_pending_events(queue_file)
    assert queued == generated

    attempts = []
    backend_online = False

    def fake_post(_url, *, json, timeout):
        attempts.append(deepcopy(json))
        return StubResponse(503 if not backend_online else 201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert len(attempts) == simulator.MAX_RETRIES
    assert all(attempt == generated[0] for attempt in attempts)
    assert simulator.load_pending_events(queue_file) == generated

    backend_online = True
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert attempts[-1] == generated[0]
    assert simulator.load_pending_events(queue_file) == []
