import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timedelta, timezone
import time
import uuid

import requests

API_URL = "http://127.0.0.1:5000/api/v1/readings"

DOOR_OPEN_DURATION = 30
SAMPLE_INTERVAL = 5
QUEUE_FILE = Path(__file__).resolve().parent / "data" / "pending_readings.jsonl"
INITIAL_BACKOFF_SECONDS = 2
BACKOFF_MULTIPLIER = 2
MAX_RETRIES = 5
SIMULATOR_TIMEZONE = timezone(timedelta(hours=7))


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
    if 500 <= response.status_code <= 599:
        return "transient"
    return "permanent"


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
        if classification == "conflict":
            print(
                f"[QUEUE] conflict device_reading_id={device_reading_id} "
                f"classification=conflict status={status} retry=false"
            )
            return response
        if classification == "permanent":
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
        results.append(send_with_retry(payload, queue_file, sleep_fn))
    return results


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
    process_pending_readings()

    door_open = False
    door_open_started_at = None

    while True:
        if not door_open:
            reading = create_reading_payload(
                door_open=False,
                open_duration_seconds=0
            )
            enqueue_reading(reading)

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

            print(f"Door: OPEN | Duration: {open_duration}s")

            # Sau 40 giây thì đóng cửa
            if open_duration >= DOOR_OPEN_DURATION:
                door_open = False
                door_open_started_at = None

        send_with_retry(reading)
        time.sleep(SAMPLE_INTERVAL)


if __name__ == "__main__":
    main()
