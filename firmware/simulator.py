import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timedelta, timezone
import threading
import time
import uuid

import requests

API_URL = "http://127.0.0.1:5000/api/v1/readings"
LATEST_READING_URL = f"{API_URL}/latest"
FOODS_API_URL = "http://127.0.0.1:5000/api/v1/foods"
EVENTS_API_URL = "http://127.0.0.1:5000/api/v1/events"

AUTO_TEST = False
DOOR_OPEN_DURATION = 30
DOOR_TIMEOUT_SECONDS = 30
SAMPLE_INTERVAL = 5
FRESHNESS_POLL_INTERVAL = 5
FRESHNESS_POLL_TIMEOUT = 3
LED_GREEN = "GREEN"
LED_YELLOW = "YELLOW"
LED_RED = "RED"
LED_UNKNOWN = "OFF/UNKNOWN"
FRESHNESS_STATUS_TO_LED = {
    "Fresh / Normal": LED_GREEN,
    "Use Soon": LED_YELLOW,
    "Check Food": LED_RED,
}
QUEUE_FILE = Path(__file__).resolve().parent / "data" / "pending_readings.jsonl"
EVENT_QUEUE_FILE = Path(__file__).resolve().parent / "data" / "pending_events.jsonl"
INITIAL_BACKOFF_SECONDS = 2
BACKOFF_MULTIPLIER = 2
MAX_RETRIES = 5
SIMULATOR_TIMEZONE = timezone(timedelta(hours=7))


def status_to_led(status):
    """Map only recognized business statuses to the three LED states."""
    if not isinstance(status, str):
        return None
    return FRESHNESS_STATUS_TO_LED.get(status)


class LedStateMachine:
    def __init__(self):
        self.last_led_state = LED_UNKNOWN
        self.last_poll_status = None

    def update_from_status(self, status):
        led_state = status_to_led(status)
        if led_state is not None:
            self.last_led_state = led_state
        return led_state


led_state_machine = LedStateMachine()


def poll_latest_freshness(state_machine=None):
    """Poll backend freshness; on any invalid response, retain the last LED."""
    state_machine = state_machine or led_state_machine
    state_machine.last_poll_status = None
    try:
        response = requests.get(
            LATEST_READING_URL,
            timeout=FRESHNESS_POLL_TIMEOUT,
        )
    except requests.Timeout:
        print(
            "[FRESHNESS POLL] timeout -> keep "
            f"LED={state_machine.last_led_state}"
        )
        return state_machine.last_led_state
    except requests.RequestException as error:
        error_name = type(error).__name__
        print(
            f"[FRESHNESS POLL] {error_name} -> "
            f"keep LED={state_machine.last_led_state}"
        )
        return state_machine.last_led_state

    if response.status_code != 200:
        print(
            f"[FRESHNESS POLL] HTTP {response.status_code} -> "
            f"keep LED={state_machine.last_led_state}"
        )
        return state_machine.last_led_state

    try:
        body = response.json()
    except (ValueError, requests.RequestException):
        print(
            "[FRESHNESS POLL] malformed JSON -> "
            f"keep LED={state_machine.last_led_state}"
        )
        return state_machine.last_led_state

    data = body.get("data") if isinstance(body, dict) and body.get("success") is True else None
    freshness = data.get("freshness") if isinstance(data, dict) else None
    status = freshness.get("status") if isinstance(freshness, dict) else None
    led_state = status_to_led(status)
    if led_state is None:
        print(
            "[FRESHNESS POLL] missing or unknown freshness status -> "
            f"keep LED={state_machine.last_led_state}"
        )
        return state_machine.last_led_state

    state_machine.update_from_status(status)
    state_machine.last_poll_status = status
    print(f"[FRESHNESS POLL] status={status} -> LED={led_state}")
    return state_machine.last_led_state


def freshness_polling_loop():
    while True:
        poll_started = time.monotonic()
        poll_latest_freshness()
        remaining = FRESHNESS_POLL_INTERVAL - (time.monotonic() - poll_started)
        time.sleep(max(0, remaining))


def _create_auto_test_food(food_id):
    today = datetime.now(SIMULATOR_TIMEZONE).date()
    payload = {
        "food_id": food_id,
        "food_name": "FreshGuard Auto Test Meat",
        "category": "MEAT",
        "quantity": 1,
        # Day 2 or 3 remains Use Soon even if client and server date differ by one day.
        "inserted_at": (today - timedelta(days=3)).isoformat(),
        "expiry_date": (today + timedelta(days=30)).isoformat(),
        "storage_location": "AUTO_TEST",
    }
    try:
        response = requests.post(FOODS_API_URL, json=payload, timeout=5)
    except requests.RequestException as error:
        print(f"[AUTO TEST] food setup failed: {type(error).__name__}")
        return False
    if response.status_code != 201:
        print(f"[AUTO TEST] food setup failed: HTTP {response.status_code}")
        return False
    return True


def run_auto_test():
    """Exercise backend status calculation and client LED mapping end to end."""
    print("========================================")
    print("FRESHGUARD AUTO TEST")
    print("========================================")

    run_id = uuid.uuid4().hex
    device_id = f"FG-AUTO-TEST-{run_id[:12]}"
    food_id = f"FG-AUTO-TEST-FOOD-{run_id}"
    scenarios = (
        {
            "name": "FRESH",
            "expected_status": "Fresh / Normal",
            "expected_led": LED_GREEN,
            "door_open": False,
            "open_duration_seconds": 0,
        },
        {
            "name": "USE SOON",
            "expected_status": "Use Soon",
            "expected_led": LED_YELLOW,
            "door_open": False,
            "open_duration_seconds": 0,
            "food_id": food_id,
        },
        {
            "name": "CHECK FOOD",
            "expected_status": "Check Food",
            "expected_led": LED_RED,
            "door_open": True,
            "open_duration_seconds": 30,
        },
    )
    state_machine = LedStateMachine()
    passed = 0

    for index, scenario in enumerate(scenarios, start=1):
        print(f"\n[{index}/3] {scenario['name']}")
        setup_ok = True
        if "food_id" in scenario:
            setup_ok = _create_auto_test_food(scenario["food_id"])

        actual_status = None
        post_ok = False
        if setup_ok:
            reading = create_reading_payload(
                scenario["door_open"], scenario["open_duration_seconds"]
            )
            reading["device_id"] = device_id
            if "food_id" in scenario:
                reading["food_id"] = scenario["food_id"]
            response = send_reading(reading)
            post_ok = is_acknowledged(response)

            if post_ok:
                # The POST acknowledgement is sent after the backend commits.
                poll_latest_freshness(state_machine)
                actual_status = state_machine.last_poll_status

        print(f"POST: {'PASS' if post_ok else 'FAIL'}")
        print(f"BACKEND STATUS: {actual_status or 'unavailable'}")
        print(
            f"EXPECTED STATUS: {scenario['expected_status']} | "
            f"EXPECTED LED: {scenario['expected_led']} | "
            f"ACTUAL LED: {state_machine.last_led_state}"
        )
        scenario_passed = (
            post_ok
            and actual_status == scenario["expected_status"]
            and state_machine.last_led_state == scenario["expected_led"]
        )
        print(f"RESULT: {'PASS' if scenario_passed else 'FAIL'}")
        passed += int(scenario_passed)

    print("\n========================================")
    if passed == len(scenarios):
        print("AUTO TEST RESULT: 3/3 PASS")
        return True
    print(f"AUTO TEST RESULT: FAIL ({passed}/3 PASS)")
    return False


def create_reading_payload(door_open, open_duration_seconds):
    return {
        "device_reading_id": str(uuid.uuid4()),
        "device_id": "FG-ESP32-01",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "temperature_c": 5.0,
        "humidity_pct": 60.0,
        "gas_raw": 300,
        "door_open": door_open,
        "open_duration_seconds": open_duration_seconds
    }


def encode_compact_reading(payload):
    """Encode one canonical reading as the compact HTTP wire payload."""
    required_fields = (
        "device_reading_id",
        "device_id",
        "timestamp",
        "temperature_c",
        "humidity_pct",
        "gas_raw",
        "door_open",
    )
    missing_fields = [field for field in required_fields if field not in payload]
    if missing_fields:
        raise ValueError(
            "Canonical reading is missing required fields: "
            + ", ".join(missing_fields)
        )

    timestamp_text = payload["timestamp"]
    if not isinstance(timestamp_text, str):
        raise ValueError("Canonical timestamp must be an ISO datetime string")
    if not any(separator in timestamp_text for separator in ("T", "t", " ")):
        raise ValueError("Canonical timestamp must be a valid ISO datetime")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp_text)
    except ValueError as error:
        raise ValueError("Canonical timestamp must be a valid ISO datetime") from error

    if parsed_timestamp.tzinfo is None:
        parsed_timestamp = parsed_timestamp.replace(tzinfo=SIMULATOR_TIMEZONE)
    try:
        epoch_seconds = parsed_timestamp.timestamp()
    except (OverflowError, OSError, ValueError) as error:
        raise ValueError("Canonical timestamp is outside the supported range") from error
    if not epoch_seconds.is_integer():
        compact_timestamp = epoch_seconds
    else:
        compact_timestamp = int(epoch_seconds)

    door_open = payload["door_open"]
    if not isinstance(door_open, bool):
        raise ValueError("Canonical door_open must be a boolean")

    compact_payload = {
        "id": payload["device_reading_id"],
        "d": payload["device_id"],
        "t": compact_timestamp,
        "tc": payload["temperature_c"],
        "h": payload["humidity_pct"],
        "g": payload["gas_raw"],
        "o": 1 if door_open else 0,
        "od": payload.get("open_duration_seconds", 0),
    }
    if "food_id" in payload:
        compact_payload["f"] = payload["food_id"]
    return compact_payload


def _resolve_queue_file(queue_file=None):
    return Path(queue_file) if queue_file is not None else QUEUE_FILE


def _decode_queue_line(line, line_number):
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        print(f"Warning: skipping invalid JSON in queue line {line_number}")
        return None

    if not isinstance(payload, dict):
        print(f"Warning: skipping non-object queue entry on line {line_number}")
        return None
    if not isinstance(payload.get("device_reading_id"), str) or not payload["device_reading_id"]:
        print(f"Warning: skipping queue entry without device_reading_id on line {line_number}")
        return None
    return payload


def load_pending_readings(queue_file=None):
    path = _resolve_queue_file(queue_file)
    if not path.exists():
        return []

    pending = []
    with path.open("r", encoding="utf-8", newline="") as queue:
        for line_number, line in enumerate(queue, start=1):
            if not line.strip():
                print(f"Warning: skipping empty queue line {line_number}")
                continue
            payload = _decode_queue_line(line, line_number)
            if payload is not None:
                pending.append(payload)
    return pending


def enqueue_reading(payload, queue_file=None):
    if not isinstance(payload, dict):
        raise ValueError("Reading queue payload must be an object")
    device_reading_id = payload.get("device_reading_id")
    device_id = payload.get("device_id")
    if not isinstance(device_reading_id, str) or not device_reading_id:
        raise ValueError("Reading queue payload requires device_reading_id")
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("Reading queue payload requires device_id")

    path = _resolve_queue_file(queue_file)
    for queued in load_pending_readings(path):
        if (
            queued.get("device_id") == device_id
            and queued.get("device_reading_id") == device_reading_id
        ):
            if queued != payload:
                print(
                    "Warning: refusing conflicting queue payload for "
                    f"device_reading_id={device_reading_id}"
                )
            return False

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    with path.open("a+b") as queue:
        queue.seek(0, os.SEEK_END)
        if queue.tell() > 0:
            queue.seek(-1, os.SEEK_END)
            if queue.read(1) not in (b"\n", b"\r"):
                queue.seek(0, os.SEEK_END)
                queue.write(b"\n")
        queue.seek(0, os.SEEK_END)
        queue.write((encoded + "\n").encode("utf-8"))
        queue.flush()
        os.fsync(queue.fileno())
    return True


def remove_reading(payload, queue_file=None):
    path = _resolve_queue_file(queue_file)
    if not path.exists():
        return False

    device_reading_id = payload.get("device_reading_id")
    device_id = payload.get("device_id")
    retained_lines = []
    removed = False
    with path.open("r", encoding="utf-8", newline="") as queue:
        for line_number, line in enumerate(queue, start=1):
            if not line.strip():
                retained_lines.append(line)
                continue
            queued = _decode_queue_line(line, line_number)
            if (
                queued is not None
                and queued.get("device_id") == device_id
                and queued.get("device_reading_id") == device_reading_id
            ):
                removed = True
            else:
                retained_lines.append(line)

    if not removed:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.writelines(retained_lines)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return True


def is_acknowledged(response):
    if response is None:
        return False
    if response.status_code == 201:
        return True
    if response.status_code != 200:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("duplicate") is True


def classify_response(response):
    if response is None:
        return "transient"
    if is_acknowledged(response):
        return "ack"
    if response.status_code == 409:
        return "conflict"
    if response.status_code in (408, 429) or 500 <= response.status_code <= 599:
        return "transient"
    return "permanent"


def _dead_letter_path(queue_file, kind):
    pending_path = Path(queue_file) if queue_file is not None else (
        QUEUE_FILE if kind == "reading" else EVENT_QUEUE_FILE
    )
    name = "dead_letter_readings.jsonl" if kind == "reading" else "dead_letter_events.jsonl"
    return pending_path.parent / name


def _dead_letter_identity(kind, payload):
    if kind == "reading":
        return (payload.get("device_id"), payload.get("device_reading_id"))
    return (payload.get("event_id"),)


def _dead_letter_record_exists(path, kind, payload):
    if not path.exists():
        return False
    identity = _dead_letter_identity(kind, payload)
    try:
        with path.open("r", encoding="utf-8") as records:
            for line in records:
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                original = record.get("payload") if isinstance(record, dict) else None
                if isinstance(original, dict) and _dead_letter_identity(kind, original) == identity:
                    return True
    except OSError as error:
        print(f"Warning: cannot inspect dead-letter file {path}: {error}")
    return False


def _persist_dead_letter(payload, response, queue_file, kind):
    path = _dead_letter_path(queue_file, kind)
    if _dead_letter_record_exists(path, kind, payload):
        return True
    try:
        reason = None
        if response is not None:
            try:
                body = response.json()
                reason = body.get("message") or body.get("error") if isinstance(body, dict) else None
            except (ValueError, AttributeError):
                reason = getattr(response, "reason", None)
        record = {
            "payload": payload,
            "http_status": response.status_code if response is not None else None,
            "reason": reason or ("non-retryable HTTP response" if response is not None else "unknown failure"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="") as records:
            records.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")
            records.flush()
            os.fsync(records.fileno())
        return True
    except OSError as error:
        print(f"Warning: failed to persist dead-letter item: {error}")
        return False


def calculate_backoff(retry_number):
    return INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** (retry_number - 1))


def send_with_retry(payload, queue_file=None, sleep_fn=None):
    sleep_fn = sleep_fn or time.sleep
    device_reading_id = payload["device_reading_id"]

    for attempt in range(1, MAX_RETRIES + 1):
        response = send_reading(payload)
        classification = classify_response(response)

        if classification == "ack":
            status = response.status_code
            remove_reading(payload, queue_file)
            print(
                f"[QUEUE] acknowledged device_reading_id={device_reading_id} "
                f"status={status}"
            )
            return response

        status = response.status_code if response is not None else "network"
        if classification in ("conflict", "permanent"):
            print(
                f"[QUEUE] permanent failure device_reading_id={device_reading_id} "
                f"classification=permanent status={status} retry=false"
            )
            return response

        if attempt == MAX_RETRIES:
            print(
                f"[RETRY] exhausted device_reading_id={device_reading_id} "
                f"attempts={MAX_RETRIES}"
            )
            return response

        delay = calculate_backoff(attempt)
        print(
            f"[RETRY] device_reading_id={device_reading_id} "
            f"attempt={attempt} status={status}"
        )
        print(f"[RETRY] waiting={delay}s")
        sleep_fn(delay)

    return None


def process_pending_readings(queue_file=None, sleep_fn=None):
    pending = load_pending_readings(queue_file)
    print(f"[QUEUE] pending_readings={len(pending)}")
    results = []
    for payload in pending:
        result = send_with_retry(payload, queue_file, sleep_fn)
        results.append(result)
        if classify_response(result) in ("permanent", "conflict"):
            if _persist_dead_letter(payload, result, queue_file, "reading"):
                if remove_reading(payload, queue_file):
                    continue
            break
        if not is_acknowledged(result):
            print(
                "[QUEUE] paused at first unacknowledged reading; "
                "later readings remain queued"
            )
            break
    return results


def _resolve_event_queue_file(queue_file=None):
    return Path(queue_file) if queue_file is not None else EVENT_QUEUE_FILE


def _decode_event_queue_line(line, line_number):
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        print(f"Warning: skipping invalid JSON in event queue line {line_number}")
        return None

    if not isinstance(event, dict):
        print(f"Warning: skipping non-object event queue entry on line {line_number}")
        return None
    if not isinstance(event.get("event_id"), str) or not event["event_id"].strip():
        print(f"Warning: skipping event queue entry without event_id on line {line_number}")
        return None
    required_fields = ("device_id", "timestamp", "event_type")
    if any(not isinstance(event.get(field), str) or not event[field].strip() for field in required_fields):
        print(f"Warning: skipping incomplete event queue entry on line {line_number}")
        return None
    return event


def load_pending_events(queue_file=None):
    path = _resolve_event_queue_file(queue_file)
    if not path.exists():
        return []

    pending = []
    with path.open("r", encoding="utf-8", newline="") as queue:
        for line_number, line in enumerate(queue, start=1):
            if not line.strip():
                print(f"Warning: skipping empty event queue line {line_number}")
                continue
            event = _decode_event_queue_line(line, line_number)
            if event is not None:
                pending.append(event)
    return pending


def enqueue_event(event, queue_file=None):
    if not isinstance(event, dict):
        raise ValueError("Event queue payload must be an object")
    required_fields = ("event_id", "device_id", "timestamp", "event_type")
    if any(not isinstance(event.get(field), str) or not event[field].strip() for field in required_fields):
        raise ValueError("Event queue payload requires event_id, device_id, timestamp, and event_type")

    path = _resolve_event_queue_file(queue_file)
    for queued in load_pending_events(path):
        if queued["event_id"] == event["event_id"]:
            if queued != event:
                print(
                    "Warning: refusing conflicting queued event for "
                    f"event_id={event['event_id']}"
                )
            return False

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    with path.open("a+b") as queue:
        queue.seek(0, os.SEEK_END)
        if queue.tell() > 0:
            queue.seek(-1, os.SEEK_END)
            if queue.read(1) not in (b"\n", b"\r"):
                queue.seek(0, os.SEEK_END)
                queue.write(b"\n")
        queue.seek(0, os.SEEK_END)
        queue.write((encoded + "\n").encode("utf-8"))
        queue.flush()
        os.fsync(queue.fileno())
    return True


def remove_event(event, queue_file=None):
    path = _resolve_event_queue_file(queue_file)
    if not path.exists():
        return False

    event_id = event.get("event_id")
    retained_lines = []
    removed = False
    with path.open("r", encoding="utf-8", newline="") as queue:
        for line_number, line in enumerate(queue, start=1):
            if not line.strip():
                retained_lines.append(line)
                continue
            queued = _decode_event_queue_line(line, line_number)
            if queued is not None and queued.get("event_id") == event_id:
                removed = True
            else:
                retained_lines.append(line)

    if not removed:
        return False

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.writelines(retained_lines)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return True


def send_event(event):
    try:
        response = requests.post(EVENTS_API_URL, json=event, timeout=5)
    except requests.RequestException as error:
        print(f"Event send error: {error}")
        return None
    print(f"Event response: status={response.status_code}, event_id={event['event_id']}")
    return response


def send_event_with_retry(event, queue_file=None, sleep_fn=None):
    sleep_fn = sleep_fn or time.sleep
    event_id = event["event_id"]

    for attempt in range(1, MAX_RETRIES + 1):
        response = send_event(event)
        classification = classify_response(response)

        if classification == "ack":
            remove_event(event, queue_file)
            print(f"[EVENT QUEUE] acknowledged event_id={event_id}")
            return response
        if classification in ("conflict", "permanent"):
            status = response.status_code if response is not None else "unknown"
            print(
                f"[EVENT QUEUE] permanent failure event_id={event_id} "
                f"status={status}; queue item retained"
            )
            return response
        if attempt == MAX_RETRIES:
            print(
                f"[EVENT RETRY] exhausted event_id={event_id} "
                f"attempts={MAX_RETRIES}; queue item retained"
            )
            return response

        status = response.status_code if response is not None else "network"
        delay = calculate_backoff(attempt)
        print(f"[EVENT RETRY] event_id={event_id} attempt={attempt} status={status} waiting={delay}s")
        sleep_fn(delay)

    return None


def process_pending_events(queue_file=None, sleep_fn=None):
    pending = load_pending_events(queue_file)
    print(f"[EVENT QUEUE] pending_events={len(pending)}")
    results = []
    for event in pending:
        result = send_event_with_retry(event, queue_file, sleep_fn)
        results.append(result)
        if classify_response(result) in ("permanent", "conflict"):
            if _persist_dead_letter(event, result, queue_file, "event"):
                if remove_event(event, queue_file):
                    continue
            break
        if not is_acknowledged(result):
            print(
                "[EVENT QUEUE] paused at first unacknowledged event; "
                "later events remain queued"
            )
            break
    return results


def submit_event(event, queue_file=None, sleep_fn=None, flush=True):
    """Durably queue a canonical event and optionally attempt FIFO delivery."""
    enqueue_event(event, queue_file)
    if not flush:
        return None
    results = process_pending_events(queue_file, sleep_fn)
    return results[-1] if results else None


class DoorEventProducer:
    """Create one event per observed door transition, scoped by device.

    The first reading after process startup seeds state. If it is already open,
    the producer assumes that episode began before observation and suppresses
    an opened/expired event that may already have been emitted before restart.
    """

    def __init__(self):
        self._states = {}

    @staticmethod
    def _event(reading, event_type, payload):
        return {
            "event_id": str(uuid.uuid4()),
            "device_id": reading["device_id"],
            "timestamp": reading["timestamp"],
            "event_type": event_type,
            "payload": payload,
        }

    def observe(self, reading):
        device_id = reading.get("device_id")
        timestamp = reading.get("timestamp")
        door_open = reading.get("door_open")
        if (
            not isinstance(device_id, str)
            or not device_id.strip()
            or not isinstance(timestamp, str)
            or not timestamp.strip()
            or type(door_open) is not bool
        ):
            return []

        duration = reading.get("open_duration_seconds", 0)
        if type(duration) is not int or duration < 0:
            duration = 0

        state = self._states.setdefault(
            device_id,
            {"previous_door_state": None, "timeout_emitted": False},
        )
        previous = state["previous_door_state"]
        if previous is None:
            state["previous_door_state"] = door_open
            state["timeout_emitted"] = door_open and duration >= DOOR_TIMEOUT_SECONDS
            return []

        events = []
        if previous is False and door_open is True:
            events.append(self._event(reading, "DOOR_OPENED", {"door_open": True}))
            state["timeout_emitted"] = False
        elif previous is True and door_open is False:
            events.append(
                self._event(
                    reading,
                    "DOOR_CLOSED",
                    {"door_open": False, "open_duration_seconds": 0},
                )
            )
            state["timeout_emitted"] = False

        if (
            door_open is True
            and duration >= DOOR_TIMEOUT_SECONDS
            and not state["timeout_emitted"]
        ):
            events.append(
                self._event(
                    reading,
                    "DOOR_TIMEOUT",
                    {
                        "door_open": True,
                        "open_duration_seconds": duration,
                    },
                )
            )
            state["timeout_emitted"] = True

        state["previous_door_state"] = door_open
        return events


def submit_door_events(reading, producer, queue_file=None):
    """Queue transition events; the main loop flushes them with the shared worker."""
    events = producer.observe(reading)
    for event in events:
        # Queue all transitions detected on this reading before the periodic
        # worker sends them, avoiding a separate retry burst per event.
        submit_event(event, queue_file=queue_file, flush=False)
    return events


def send_reading(payload):
    device_reading_id = payload["device_reading_id"]
    print(f"Sending reading: device_reading_id={device_reading_id}")

    try:
        compact_payload = encode_compact_reading(payload)
        response = requests.post(
            API_URL,
            json=compact_payload,
            timeout=5
        )
    except requests.RequestException as error:
        print(f"Connection error: {error}")
        return None

    try:
        body = response.json()
    except ValueError:
        body = None

    if response.status_code == 201 and isinstance(body, dict):
        print(
            f"Response: status=201, "
            f"device_reading_id={body.get('device_reading_id', device_reading_id)}, "
            f"reading_id={body.get('reading_id')}"
        )
    elif response.status_code == 200 and isinstance(body, dict) and body.get("duplicate"):
        print(
            f"Response: status=200, duplicate=true, "
            f"device_reading_id={body.get('device_reading_id', device_reading_id)}, "
            f"reading_id={body.get('reading_id')}"
        )
    elif response.status_code == 409:
        response_reading_id = device_reading_id
        if isinstance(body, dict):
            response_reading_id = body.get("device_reading_id", device_reading_id)
        print(
            f"Response: status=409, conflict, "
            f"device_reading_id={response_reading_id}, "
            f"body={body if body is not None else response.text}"
        )
    elif response.status_code >= 400:
        print(
            f"Response: status={response.status_code}, "
            f"body={body if body is not None else response.text}"
        )
    else:
        freshness = body.get("freshness") if isinstance(body, dict) else None
        print(f"Sent | Status: {response.status_code} | Freshness: {freshness}")

    return response


def main():
    if AUTO_TEST:
        return run_auto_test()

    process_pending_readings()
    process_pending_events()
    threading.Thread(target=freshness_polling_loop, daemon=True).start()

    door_event_producer = DoorEventProducer()
    door_open = False
    door_open_started_at = None

    while True:
        if not door_open:
            reading = create_reading_payload(
                door_open=False,
                open_duration_seconds=0
            )
            enqueue_reading(reading)
            submit_door_events(reading, door_event_producer)

            print("Door: CLOSED")

            time.sleep(10)

            door_open = True
            door_open_started_at = time.monotonic()

        else:
            open_duration = int(
                time.monotonic() - door_open_started_at
            )

            reading = create_reading_payload(
                door_open=True,
                open_duration_seconds=open_duration
            )
            enqueue_reading(reading)
            submit_door_events(reading, door_event_producer)

            print(f"Door: OPEN | Duration: {open_duration}s")

            # Sau 40 giây thì đóng cửa
            if open_duration >= DOOR_OPEN_DURATION:
                door_open = False
                door_open_started_at = None

        # Re-check the durable queue every sampling cycle. This also sends the
        # new reading, while preserving FIFO with any older pending readings.
        process_pending_readings()
        process_pending_events()
        time.sleep(SAMPLE_INTERVAL)


if __name__ == "__main__":
    result = main()
    if isinstance(result, bool):
        raise SystemExit(0 if result else 1)
