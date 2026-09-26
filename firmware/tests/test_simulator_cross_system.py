"""Combined durable queue checks that model a simulator process restart."""

import json
import uuid

from firmware import simulator


class Response:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body or {}

    def json(self):
        return self.body


def test_reading_and_event_queues_recover_independently_after_restart(
    tmp_path, monkeypatch
):
    reading_file = tmp_path / "pending_readings.jsonl"
    event_file = tmp_path / "pending_events.jsonl"
    reading = {
        "device_id": "RESTART-DEVICE",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": "2026-09-26T12:00:00+00:00",
        "temperature_c": 6,
        "humidity_pct": 60,
        "gas_raw": 130,
        "door_open": False,
    }
    event = {
        "event_id": str(uuid.uuid4()),
        "device_id": "RESTART-DEVICE",
        "timestamp": reading["timestamp"],
        "event_type": "DOOR_OPENED",
        "payload": {"door_open": True},
    }
    simulator.enqueue_reading(reading, reading_file)
    simulator.enqueue_event(event, event_file)

    # A new simulator instance reconstructs both identities from disk.
    restored_reading = simulator.load_pending_readings(reading_file)[0]
    restored_event = simulator.load_pending_events(event_file)[0]
    assert restored_reading == reading
    assert restored_event == event

    monkeypatch.setattr(simulator, "send_reading", lambda _payload: Response(400, {"error": "invalid"}))
    simulator.process_pending_readings(reading_file, sleep_fn=lambda _delay: None)
    assert simulator.load_pending_readings(reading_file) == []
    assert simulator.load_pending_events(event_file) == [event]
    dead_letter = json.loads(
        (tmp_path / "dead_letter_readings.jsonl").read_text(encoding="utf-8")
    )
    assert dead_letter["payload"] == reading
    assert dead_letter["payload"]["device_reading_id"] == reading["device_reading_id"]

    monkeypatch.setattr(simulator, "send_event", lambda _event: Response(201))
    simulator.process_pending_events(event_file, sleep_fn=lambda _delay: None)
    assert simulator.load_pending_readings(reading_file) == []
    assert simulator.load_pending_events(event_file) == []
