# FreshGuard

FreshGuard is an IoT food-freshness monitoring system. An ESP32 reads temperature, humidity, MQ-135 gas level, DS3231 time, and an MC-38 reed switch, then sends readings to a Flask backend. The backend is authoritative for freshness decisions, dashboard data, and Telegram notifications.

## Project layout

- `firmware/ESP32-WROOM-32/ESP32-WROOM-32.ino` — ESP32 firmware with LittleFS offline FIFO, Wi-Fi retry, sensor reads, and MC-38 door monitoring.
- `backend/` — Flask API, SQLite schema initialization, freshness rules, ingest metadata, and Telegram notification outbox.
- `dashboard/` — browser dashboard for readings, freshness status, food records, and events.
- `doc/` — architecture, threshold matrices, offline-ingest, Telegram, and presentation documentation.

## Run the backend

From the repository root on Windows PowerShell:

```powershell
.\backend\.venv\Scripts\python.exe -B .\backend\run.py
```

The API listens on `0.0.0.0:5000`. The ESP32 and the computer running Flask must be on the same reachable LAN. Set the computer's LAN address in `SERVER_URL` in the firmware; do not use `localhost`.

Create local configuration from the example and keep secrets out of Git:

```powershell
Copy-Item backend/.env.example backend/.env
```

Set the Telegram bot token and chat ID in `backend/.env` if Telegram notifications are required. The real `.env` is ignored by Git.

## Test Telegram

With the backend environment installed and `backend/.env` configured:

```powershell
.\backend\.venv\Scripts\python.exe backend/check_telegram.py --send-test
```

See [`doc/telegram-notifications.md`](doc/telegram-notifications.md) for transition rules and retry behavior.

## ESP32 wiring

The current firmware uses:

| Device | ESP32 pin |
|---|---:|
| DHT11 | GPIO 4 |
| DS3231 SDA/SCL | GPIO 21 / 22 |
| MQ-135 analog output | GPIO 34 |
| MC-38 reed switch | GPIO 16 / RX2 to GND |
| LEDs | GPIO 23 / 25 / 26 |
| Active buzzer | GPIO 17 |
| LCD1602 parallel | RS 13, EN 14, D4 27, D5 33, D6 32, D7 18 |

The reed input uses `INPUT_PULLUP`: LOW means the magnet is near and the door is closed; HIGH means the door is open. The firmware debounces the switch and creates a priority reading after 30 seconds continuously open.

Install the Arduino libraries listed in the firmware comments, select an ESP32-WROOM-32/ESP32 Dev Module with a LittleFS-capable partition, and open Serial Monitor at 115200 baud. The first normal reading is captured after 60 seconds. The backend must have a valid RTC or NTP timestamp before a new reading can be queued.

## Offline demonstration

1. Start Flask and confirm the ESP32 reports Wi-Fi and backend connectivity.
2. Let at least one reading be acknowledged.
3. Stop Flask or disconnect the ESP32 from Wi-Fi.
4. The ESP32 keeps readings in LittleFS at `pending_readings.jsonl`; it does not discard them when delivery is unconfirmed.
5. Reboot while offline and verify `LittleFS recovered: ... records` in Serial output.
6. Restore Flask/Wi-Fi. The durable FIFO is sent in order in bounded batches of five; the next batch starts immediately after compaction, and records are removed only after a validated backend acknowledgement.

Detailed acceptance checks are in [`doc/offline-reading-ingest.md`](doc/offline-reading-ingest.md).

## Tests

Run the backend test suite with:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Do not commit `backend/.env`, SQLite databases, virtual environments, or generated caches. Use [`backend/.env.example`](backend/.env.example) as the configuration template.
