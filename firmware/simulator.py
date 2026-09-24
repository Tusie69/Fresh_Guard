import time
import requests

API_URL = "http://127.0.0.1:5000/api/v1/readings"

DOOR_OPEN_DURATION = 40
SAMPLE_INTERVAL = 5


def generate_reading(door_open, open_duration_seconds):
    return {
        "device_id": "FG-ESP32-01",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "temperature_c": 5.0,
        "humidity_pct": 60.0,
        "gas_raw": 300,
        "door_open": door_open,
        "open_duration_seconds": open_duration_seconds
    }


door_open = False
door_open_started_at = None

while True:

    # Sau 10 giây đóng cửa thì mở cửa
    if not door_open:
        reading = generate_reading(
            door_open=False,
            open_duration_seconds=0
        )

        print("Door: CLOSED")

        time.sleep(10)

        door_open = True
        door_open_started_at = time.monotonic()

    else:
        open_duration = int(
            time.monotonic() - door_open_started_at
        )

        reading = generate_reading(
            door_open=True,
            open_duration_seconds=open_duration
        )

        print(f"Door: OPEN | Duration: {open_duration}s")

        # Sau 40 giây thì đóng cửa
        if open_duration >= DOOR_OPEN_DURATION:
            door_open = False
            door_open_started_at = None

    try:
        response = requests.post(
            API_URL,
            json=reading,
            timeout=5
        )

        print(
            f"Sent | Status: {response.status_code} | "
            f"Freshness: {response.json().get('freshness')}"
        )

    except requests.RequestException as error:
        print(f"Connection error: {error}")

    time.sleep(SAMPLE_INTERVAL)