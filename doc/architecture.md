# FreshGuard Architecture

This document separates the **current implementation** from a **proposed reliability/compact-protocol design**. Current behavior is based on the source files and test suite in this repository. It does not describe real ESP32 hardware: the only firmware-side file found is a Python HTTP simulator.

## 1. System Overview

### Current implementation

```text
Python simulator
  -- HTTP POST /api/v1/readings --> Flask route
    -> validate request and optional Food lookup
    -> Freshness Engine
    -> INSERT and COMMIT in SQLite
  <-- HTTP 201 (reading_id + freshness) -- Flask route
      simulator prints the response

Dashboard -- GET latest / Food / history --> Flask routes --> SQLite
```

The simulator sends canonical JSON readings to `POST /api/v1/readings`. The backend validates the input, optionally looks up the linked food, evaluates freshness, commits the reading to SQLite, and returns the assigned database ID and freshness result. The Dashboard retrieves the latest reading and history through separate GET requests. The backend is the source of truth for freshness decisions.

The repository contains no ESP32 sensor driver, device firmware, or LED control implementation. The simulator is not evidence of physical sensor or LED behavior.

### Proposed design

An eventual device can use a compact transport payload and persistent local queue. The backend should normalize that transport payload into the existing canonical fields before applying current validation and freshness logic. These changes are proposals only; the current API does not accept the compact payload.

## 2. Core Design Principles

- **Current:** The backend owns freshness rules; the simulator sends measurements and displays the returned response.
- **Current:** Canonical sensor field names are used in the API and backend.
- **Current:** Accepted readings and events are persisted in SQLite.
- **Current:** Event IDs have duplicate protection. Reading POSTs do not have client-generated idempotency IDs.
- **Proposed:** Keep compact transport aliases at the network boundary and map them to canonical backend fields. Do not make the Dashboard depend on compact keys.
- **Proposed:** Treat a reading as synchronized only after a successful backend response confirms persistence.

## 3. System Components

| Component | Technology | Responsibility | State |
| --- | --- | --- | --- |
| ESP32 device | No ESP32 source file found | Target: acquire sensors, timestamp, create/send readings, manage local queue, and optionally control LEDs | Not implemented / not verifiable in this repository |
| Sensors | No real sensor integration found | Target: measure temperature, humidity, gas, and door state | Simulator supplies fixed values; real sensors not implemented |
| Python simulator | `firmware/simulator.py`, Python `requests` | Sends readings to local Flask API and prints HTTP status/freshness | Implemented; not real hardware |
| Flask Backend | Flask application and route blueprints | Validate requests, invoke rules, persist records, serve API responses | Implemented |
| Freshness Engine | `backend/app/services/freshness.py` | Evaluate temperature, humidity/gas validity, door duration, storage duration, expiry, and MAX severity | Implemented; see [Freshness Decision Rule Matrix](freshness-decision-rule-matrix.md) |
| SQLite | Python `sqlite3` | Persist readings, events, and food items | Implemented |
| Dashboard | `dashboard/index.html`, HTML/JavaScript | Fetch latest reading, linked food, and history; display sensor and freshness data | Implemented |

## 4. End-to-End Data Flow

### Current reading flow

1. The Python simulator builds a reading with fixed sensor values, `device_id`, timestamp, door state, and open duration.
2. It sends JSON to `POST /api/v1/readings` over HTTP.
3. Flask checks the body and required fields, validates timestamp/sensors/door/duration, and validates `food_id` if present.
4. If a food ID is supplied, the route loads that food's category, insertion date, and expiry date. An unknown ID returns 404 without inserting a reading.
5. The route calls `evaluate_freshness()` using canonical fields.
6. The route inserts and commits the reading to SQLite.
7. The API returns HTTP 201 with `reading_id` and freshness status/reason. The simulator prints the response status and freshness object; it does not control an LED or maintain sync state.

### Current Dashboard flow

The Dashboard calls `GET /api/v1/readings/latest`, then loads linked food through `GET /api/v1/foods/<food_id>` when applicable, and loads `GET /api/v1/readings?limit=20`. It refreshes every two seconds. The API returns 404 with `NO_DATA` if there is no reading.

## 5. Backend Architecture

| Layer/file | Current responsibility |
| --- | --- |
| `backend/app/__init__.py` | Creates the Flask app, configures CORS for `/api/*`, and registers route blueprints. |
| `backend/app/routes/readings.py` | Implements food and reading endpoints; validates payloads; performs food lookup; calls the Freshness Engine; reads/writes SQLite. |
| `backend/app/routes/events.py` | Validates and stores events; checks `event_id` for duplicates and returns an idempotent response for an existing ID. |
| `backend/app/services/freshness.py` | Contains freshness statuses, severity mapping, category profiles, and rule evaluation. |
| `backend/app/database.py` | Creates SQLite connections and sets `sqlite3.Row` as the row factory. |
| `backend/app/init_db.py` | Creates current tables and adds `open_duration_seconds` / `food_id` to older `sensor_readings` schemas when missing. |

No ORM or active model layer was found in the reading/event request paths. SQLite access is performed directly from route handlers through the connection factory.

## 6. Database Architecture

`backend/app/database.py` places `freshguard.db` in the `backend/` directory. `init_db.py` creates these tables:

| Table | Current role and important columns |
| --- | --- |
| `sensor_readings` | Sensor samples: auto-increment integer `id`, `device_id`, `timestamp`, `temperature_c`, `humidity_pct`, `gas_raw`, `door_open`, `open_duration_seconds`, optional `food_id`, and `created_at`. |
| `food_items` | Food metadata: auto-increment integer `id`, unique `food_id`, name/category, quantity, required `inserted_at`, optional manufacture/expiry dates and storage location, and `created_at`. |
| `events` | Events: auto-increment integer `id`, unique required `event_id`, device/timestamp/type, payload, door state/duration, and `created_at`. |

`sensor_readings.food_id` is used by route queries to look up/join `food_items.food_id`; the shown schema does not declare a foreign-key constraint. `events` is a separate table; no reading-to-event relationship is implemented. `event_id UNIQUE` plus the route's existence check provide event duplicate protection. The integer reading primary key is not a client-supplied idempotency key.

## 7. Freshness Decision Flow

```text
Canonical sensor / optional food inputs
  -> route validation
  -> temperature
  -> humidity validity
  -> gas validity
  -> door / open duration
  -> optional food storage duration
  -> optional expiry
  -> MAX severity
  -> status and combined reasons
```

Severity 0 maps to Fresh / Normal, 1 to Use Soon, and 2 to Check Food. Missing/null or invalid sensor values do not silently become Fresh: sensor faults/invalid values contribute Check Food. Humidity and gas currently have availability/validity checks but no quality thresholds. See [Freshness Decision Rule Matrix](freshness-decision-rule-matrix.md) and [Food Threshold Matrix](food-threshold-matrix.md) for exact rules.

## 8. IoT Communication Protocol

### 8.1 Current API

`POST /api/v1/readings` accepts a JSON object with these required fields:

| Field | Current meaning / validation |
| --- | --- |
| `device_id` | Required non-empty string |
| `timestamp` | Required parseable ISO datetime string |
| `temperature_c` | Required; finite number or null |
| `humidity_pct` | Required; finite number or null |
| `gas_raw` | Required; finite number or null |
| `door_open` | Required boolean |
| `open_duration_seconds` | Optional non-negative integer; defaults to 0 |
| `food_id` | Optional non-empty string; if supplied it must identify an existing food item |

The current simulator sends these canonical keys. A compact payload is not accepted by this endpoint. Successful creation returns HTTP 201. Example response shape:

```json
{
  "success": true,
  "message": "Reading saved",
  "reading_id": 4466,
  "freshness": {
    "status": "Fresh / Normal",
    "reason": "All sensor readings are available"
  }
}
```

The numeric `reading_id` is SQLite's generated row ID. Errors include HTTP 400 for invalid/missing request fields and HTTP 404 for an unknown `food_id`.

### 8.2 Proposed Compact JSON

This is a **proposed** transport format only. No current route accepts it, and no API changes are made by this document.

```json
{
  "id": "R8F21A",
  "d": "esp32_01",
  "t": 1727253000,
  "tc": 5.2,
  "h": 61.5,
  "g": 302,
  "o": 0,
  "od": 0,
  "f": "FOOD001"
}
```

### 8.3 Field Mapping

| Proposed key | Canonical backend field |
| --- | --- |
| `id` | Proposed device-generated reading identity; not the current SQLite `reading_id` |
| `d` | `device_id` |
| `t` | `timestamp` (proposed Unix timestamp) |
| `tc` | `temperature_c` |
| `h` | `humidity_pct` |
| `g` | `gas_raw` |
| `o` | `door_open` (`0`/`1` would need normalization to boolean) |
| `od` | `open_duration_seconds` |
| `f` | `food_id` |

Proposed normalization should happen at the API boundary. Internal validation, Freshness Engine calls, database fields, and Dashboard responses should continue to use canonical names.

### 8.4 Response Protocol

**Current:** the reading route commits before returning HTTP 201 with the integer `reading_id` and `freshness.status` / `freshness.reason`. The simulator prints the HTTP status and freshness result. It does not persist an acknowledgement or mark a record synchronized.

**Proposed:** a device should treat a reading as synchronized only after receiving a successful response that confirms backend acceptance/persistence. A future compact-protocol response shape and explicit echo of the device reading ID have not been defined or implemented.

## 9. Reading Identity and Idempotency

### 9.1 Current Reading ID

The database assigns `sensor_readings.id` as an auto-increment integer. On creation, the POST response exposes that value as `reading_id`. It is assigned after the insert and cannot identify a retry that arrives before the device learns the database ID.

There is no client-generated reading ID, uniqueness constraint for a reading request, or reading-level duplicate check. Retrying a POST after a lost response can create another row. **Reading-level idempotency is not implemented.**

### 9.2 Proposed Reading ID

The proposed compact `id` is a stable device-generated reading ID. A device would create it once, store it with the queued reading, and reuse the same ID on every retry. Backend storage would need a unique constraint and lookup for this device ID before duplicate-safe retry is possible. This is a design proposal; no schema or route currently implements it.

```text
CREATE stable device reading ID
  -> persist in local queue
  -> POST same ID
  -> on timeout, retry the same ID
  -> backend deduplicates and acknowledges
```

### 9.3 Event ID

`event_id` is separate from `reading_id`. The current Events endpoint requires it, and `events.event_id` is `UNIQUE`. A first accepted event returns HTTP 201; a repeated ID returns HTTP 200 with `duplicate: true` without inserting a second event. This event-level behavior does not provide reading-level idempotency.

## 10. Reliability Design

### 10.1 Current State

- **Simulator:** `requests.post()` uses a 5-second timeout. `requests.RequestException` is caught and printed; the loop continues.
- **Simulator response:** prints HTTP status and `freshness`; it does not call `raise_for_status()`, keep a pending queue, or record sync state.
- **Backend:** a reading is committed before the 201 response. If the response is lost, a repeated POST has no reading-level duplicate protection.
- **Events:** duplicate event IDs are protected as described above.
- **Real device:** no ESP32 implementation, local storage, or device retry logic is present in the repository.

### 10.2 Network Failure

**Current:** the Python simulator prints a connection error and then continues its loop. The failed sample is not retained for later delivery. No real ESP32 network-failure behavior is verifiable.

**Proposed:** retain readings locally during timeout, connection refusal, or unavailable network; retry transient backend failures; do not retry permanently rejected payloads forever.

### 10.3 Local Buffer

**Current:** no local reading buffer exists in the simulator or backend protocol.

**Proposed logical record:** device reading ID, device ID, timestamp, sensor payload, optional food ID, retry count, sync status, last attempt time, and next retry time. These are design fields only; no queue/table/migration is created here.

Proposed statuses: `PENDING`, `SENDING`, `SYNCED`, `FAILED_PERMANENT`.

### 10.4 Retry

**Current:** there is no retry loop/backoff. The simulator performs one request attempt for each generated sample.

**Proposed:** retry transient timeout, connection, network, and HTTP 5xx failures using exponential backoff (2, 4, 8, 16 seconds). Treat HTTP 400, HTTP 404, invalid payload, and unknown food ID as permanent rejection unless the product defines a correction flow. Reuse the same proposed reading ID for every attempt.

### 10.5 Synchronization

**Current:** HTTP 201 is returned after the database commit, but the simulator only prints the response; there is no synchronized/pending state. Event duplicate handling is implemented independently.

**Proposed:** device sends a queued record, backend validates and persists it, backend acknowledges it, and the device marks that queue entry synced only after verifying the acknowledgement.

### 10.6 Restart Recovery

**Current:** no device-side queue exists to recover after restart. SQLite persists backend rows, but this does not recover readings that were never delivered.

**Proposed:** persist the device queue across restart and resume pending retries using the original reading IDs.

## 11. Device Responsibilities

| Responsibility | Current state | Target / proposed state |
| --- | --- | --- |
| Sensor acquisition | Simulator supplies fixed values; real acquisition absent | ESP32 reads physical sensors |
| Timestamp | Simulator calls `time.strftime()` and appends a literal `+07:00`; there is no RTC/NTP setup in the file | Device provides a trustworthy synchronized time, or follows an explicitly defined server-time policy |
| Reading identity | No device reading ID | Generate and retain a stable ID for retries |
| Payload | Sends canonical JSON fields | May send compact aliases, normalized by backend |
| Local queue/retry | Absent | Persistent queue and retry policy |
| Response handling | Prints status/freshness only | Validate acknowledgement and mark the matching queued item synced |
| LED control | No LED code | Optional device output driven by backend result, if later implemented |

The simulator timestamp is generated from the host's current clock, but the timezone suffix is a fixed string. This is not evidence of an ESP32 RTC/NTP implementation or timezone-aware conversion.

## 12. Backend Responsibilities

### Current

- Validate canonical request fields, timestamps, sensor values, door state/duration, and optional food ID.
- Calculate freshness through the backend service.
- Persist readings, foods, and events in SQLite.
- Protect duplicate Events using `event_id`.
- Serve latest reading/history and Food lookup APIs used by the Dashboard.
- Return the reading ID and freshness result to the HTTP caller.

### Proposed

- Optionally decode compact transport keys into canonical fields before applying the existing validation and engine logic.
- Add device reading ID persistence and unique duplicate handling before claiming reading retry safety.
- Keep canonical response objects for Dashboard clients.

The canonical internal fields remain `temperature_c`, `humidity_pct`, `gas_raw`, `door_open`, `open_duration_seconds`, and `food_id`.

## 13. Dashboard Responsibilities

The Dashboard consumes canonical backend responses, not the proposed compact payload. It fetches the latest reading, linked Food details when a `food_id` exists, and reading history. It displays sensor values, door state, freshness status/reason, unavailable/no-data messages, Food fields, and history. No compact-protocol parsing or device acknowledgement logic belongs in the current Dashboard.

## 14. Security and Validation

### Current validation

- Reading and Event bodies must be JSON objects.
- Readings require device ID, ISO datetime, all three sensor keys, and boolean door state; sensor values may be null or finite numbers.
- Reading duration, when provided, must be a non-negative integer. Unknown `food_id` returns 404.
- Events require non-empty string `event_id`, `device_id`, and `event_type`, plus a parseable ISO datetime.
- Food creation validates required identity/category/date fields and supported optional values.

### Current security limits

- No authentication/authorization layer was found in the app routes.
- Flask CORS is configured for all origins on `/api/*`.
- The simulator uses local plain HTTP; TLS setup is not present in the inspected project files.

No authentication, TLS configuration, or new validation contract is proposed as implemented behavior here.

## 15. Current Limitations

- No real ESP32 firmware, sensor integration, or LED control is present in the inspected repository; only the Python simulator is present.
- Simulator sensor values are constants (5.0 °C, 60.0 humidity, `gas_raw` 300); it does not implement Auto Test 3 States.
- The simulator has no persistent offline buffer, retry/backoff, acknowledgement state, or restart recovery.
- Reading-level idempotency is not implemented. The current SQLite integer `reading_id` is not a device retry key.
- The simulator timestamp uses host `time.strftime()` with a literal `+07:00` suffix; there is no device RTC/NTP synchronization logic in the file.
- Humidity quality and calibrated gas/ppm thresholds are not implemented in the Freshness Engine.
- Remote notification and QR workflows were not found in the inspected API, firmware-side file, or Dashboard.
- Event idempotency exists, but the simulator does not submit Events and event IDs do not deduplicate readings.

## 16. Implementation Roadmap

The following is a **proposed** sequence, not completed work:

1. Freeze and document the current canonical reading API.
2. Define a stable device-side reading ID and its persistence/uniqueness behavior.
3. Add backend support for compact request decoding while preserving canonical internal fields and existing clients.
4. Update the device to send the agreed compact format.
5. Add a persistent local reading queue.
6. Add retry classification and exponential backoff.
7. Implement reading-level idempotency using the stable device ID.
8. Add restart recovery for pending queue entries.
9. Add reliability tests for network failures, retries, duplicate delivery, and recovery.

No roadmap phase is implemented by this document.
