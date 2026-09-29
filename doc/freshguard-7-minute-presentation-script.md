# FreshGuard — 7-Minute Presentation Script

## 0:00–0:40 — Opening

Good morning everyone.

Today I would like to introduce FreshGuard, an IoT-based food freshness monitoring system. FreshGuard combines an ESP32 device, environmental sensors, a backend freshness engine, a dashboard, and Telegram notifications.

The main problem we address is simple: food can become unsafe or lose quality while nobody is watching. A temperature spike, high humidity, abnormal gas levels, or a door left open may happen between two manual checks. FreshGuard continuously collects these signals and converts them into an understandable freshness status.

Our three user-facing statuses are **Fresh / Normal**, **Use Soon**, and **Check Food**.

## 0:40–1:35 — System overview

The system has two main parts.

The first part is the ESP32 device. It reads a DHT11 temperature and humidity sensor, an MQ135 gas sensor, and a DS3231 real-time clock. It also controls a 16-by-2 LCD, three status LEDs, and a buzzer.

The second part is the backend. It receives readings through the `/api/v1/readings` API, stores them in SQLite, evaluates the freshness rules, stores the result, and sends remote notifications when a meaningful status transition occurs.

The ESP32 is responsible for sensing, local display, durable offline storage, and communication. The backend is the source of truth for freshness decisions. This separation keeps business rules in one place and prevents the device from making inconsistent decisions.

## 1:35–2:25 — How a reading is processed

Every reading contains the device ID, a UUID called `device_reading_id`, the capture timestamp, temperature, humidity, gas level, door state, and optionally a food ID.

The timestamp represents when the ESP32 captured the reading. The backend also records when it received the request. This lets us measure delivery delay without overwriting the original device time.

The backend then evaluates several factors: temperature, humidity, gas behavior, door-open duration, storage duration, expiry date, sensor faults, and temperature exposure over time.

The result is the most severe applicable status. For example, a normal temperature does not automatically mean the food is safe if the gas sensor is reporting a persistent anomaly or the food has passed its expiry date.

Connectivity status is kept separate. A reading that arrives late may be classified as `OFFLINE_RECOVERED`, but that does not automatically change its freshness status to `Check Food`. A delayed reading can still be `Fresh / Normal`.

## 2:25–3:35 — Offline reliability

Offline operation is one of the most important parts of FreshGuard.

The ESP32 does not send a new reading directly from volatile memory. It first appends the JSON record to LittleFS, using a JSON Lines FIFO file named `pending_readings.jsonl`. A reading is considered durable only after the write, flush, synchronization, and close operations succeed.

When the network or backend is unavailable, the records remain in that file. When connectivity returns, the ESP32 requests a synchronization cycle and sends records in FIFO order, with a maximum of five records per cycle.

A record is removed only after the backend returns a validated acknowledgement. The response must have HTTP status 200 or 201, `success: true`, the same `device_reading_id`, and one of the three recognized freshness statuses.

If the response is a timeout, a network error, a 5xx response, or an invalid acknowledgement, the original record remains in the queue. Permanent 4xx responses are written to a separate rejected log before the record is retired.

This design protects older readings and prevents a temporary outage from silently losing data.

## 3:35–4:25 — Backend idempotency and time metadata

Offline delivery uses an at-least-once model. The same record may be sent again if the ESP32 does not receive the acknowledgement.

To handle this safely, the backend enforces uniqueness on the pair `(device_id, device_reading_id)`. If the same UUID and the same payload arrive again, the backend returns the existing result instead of inserting a second logical reading. It also avoids recalculating freshness and avoids repeating notification side effects.

If the UUID is reused with a different payload, the backend returns a conflict error. This helps reveal corrupted or incorrectly reused identities.

The API also stores `received_at`, `delivery_delay_seconds`, and `ingest_status`. The current policy classifies readings as `LIVE`, `DELAYED`, or `OFFLINE_RECOVERED`. This allows the dashboard and operators to distinguish capture time from delivery time.

## 4:25–5:20 — Telegram notification policy

Telegram is an asynchronous side effect. It never decides freshness and it never controls whether the ESP32 receives an acknowledgement.

Notifications are generated for active food items when their freshness status changes. A transition from Fresh / Normal to Use Soon creates a warning. A transition to Check Food creates an alert. A transition from Check Food back to a safer status creates a recovery notification.

Repeated readings with the same status do not create repeated alerts. Therefore, twenty consecutive Check Food readings do not produce twenty Telegram messages. A duplicate replay of the same device reading also does not create another notification.

Notifications are first stored in a database outbox. A background worker sends them to the Telegram Bot API, verifies the HTTP and JSON response, and records either `DELIVERED`, `PENDING`, or `FAILED`. The worker retries temporary failures up to three times. If Telegram is unavailable, the sensor reading remains safely stored and the API still succeeds.

## 5:20–6:15 — User experience and example

The local device provides immediate feedback. The LCD shows measurements and connection or storage state. The green, yellow, and red LEDs represent Fresh / Normal, Use Soon, and Check Food. The buzzer gives a short warning for Use Soon and a repeating alarm pattern for Check Food.

The dashboard provides current readings, history, food records, freshness explanations, and administrative rule management.

Consider this example. The ESP32 captures a temperature of 13 degrees Celsius at 1:00 AM, but the Wi-Fi connection is unavailable. The reading is safely stored locally. At 1:20 AM, the connection returns and the ESP32 replays the same UUID and timestamp. The backend preserves the 1:00 AM capture time, stores the 1:20 AM receipt time, calculates a delay of about 1,200 seconds, and may classify the ingest as `OFFLINE_RECOVERED`. Freshness is still evaluated independently. If the food status transitions to Check Food, one Telegram alert is queued.

## 6:15–7:00 — Closing

To conclude, FreshGuard provides four important guarantees.

First, readings are durable before they are sent.

Second, offline readings survive temporary network outages and are replayed in FIFO order.

Third, a record is retired only after a validated backend acknowledgement, or after a permanent rejection has been safely quarantined.

Fourth, freshness, connectivity, and notification delivery remain separate concerns. This makes the system easier to test and safer to operate.

FreshGuard is still a prototype. Real deployments would require hardware endurance testing, calibrated gas sensing, secure transport such as HTTPS, protected production secrets, monitoring, and further testing during power loss. Telegram also cannot provide an absolute exactly-once guarantee if it accepts a message while the backend loses its delivery update.

Even with those limits, the project demonstrates a complete path from physical sensing to durable storage, backend reasoning, user feedback, and controlled remote alerting.

Thank you for listening. I am happy to answer your questions.
