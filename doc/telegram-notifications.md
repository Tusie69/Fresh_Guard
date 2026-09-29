# Telegram audit and verification

## Audit before this change

1. Service: `backend/app/services/telegram_notifier.py`.
2. `send_telegram_message()` called Telegram `sendMessage` through `urllib.request.urlopen`.
3. `TelegramNotificationWorker.run_once()` called that sender. `create_app()` started
   the daemon worker; `backend/send_pending_notifications.py` provided one batch delivery.
4. Triggers were food freshness transitions for **active foods only**, not all raw
   readings or arbitrary events. Use Soon, Check Food and recovery were supported.
   A door timeout/sensor fault could cause a food freshness transition, but neither
   had a separate Telegram event subscription.
5. Credentials came only from process environment `TELEGRAM_BOT_TOKEN` and
   `TELEGRAM_CHAT_ID`. There was no `.env` loader or `.env.example` in this checkout.
6. Startup only checked that both values were nonempty; it did not verify them with Telegram.
7. HTTP timeout was five seconds.
8. HTTP/network/JSON errors were handled; worker also caught general sender exceptions.
   However, arbitrary exception text was stored as `last_error` and worker traceback
   logging could expose sensitive URLs.
9. Telegram transport was already outside the reading transaction and could not
   directly roll back a successful reading. Outbox insertion itself remained in
   the reading transaction, preserving atomicity.
10. Pending entries were retried on a five-second polling cycle, at most three attempts.
11. Success/failure logs existed, but omitted device/reading/status/error context.
12. `notification_outbox` stored unique event keys, payload, delivery status,
    attempt count, last error and delivery time.
13. Food snapshots suppressed unchanged status; unique event keys protected logical
    notifications. Worker delivery had no atomic claim, so concurrent workers could
    select and send the same PENDING entry.
14. Duplicate `(device_id, device_reading_id)` returned the existing reading before
    policy/state/outbox work; it did not create a second alert.
15. Twenty consecutive Check Food readings for one active food created one logical
    alert when entering that state (or zero if it was already in that state).
16. Existing tests: `test_telegram_notifier.py` and `test_notification_outbox.py`.

Observed in this session on 2026-09-29: both credential variables were missing/blank;
no `.env` file was found. A read-only DB check found two active foods, five outbox
rows (one DELIVERED, four PENDING). Missing configuration disables this process's
worker. These observations do not prove why another shell/deployment failed or
whether the previously DELIVERED row reached a real chat.

Also found: `run.py` enabled the debug reloader while startup treated an absent
`WERKZEUG_RUN_MAIN` as true, allowing both parent and child to start workers.
The prototype entry point now disables the reloader. DB claims also protect
overlap with the manual batch command or other processes.

## Policy preserved

| Previous food status | Current status | Notification |
|---|---|---|
| No previous snapshot | Fresh / Normal | None |
| No previous snapshot | Use Soon / Check Food | Corresponding warning/alert |
| Fresh / Normal | Use Soon | FOOD_USE_SOON |
| Fresh / Normal | Check Food | FOOD_CHECK_FOOD |
| Use Soon | Check Food | FOOD_CHECK_FOOD |
| Check Food | Fresh / Normal or Use Soon | FOOD_RECOVERED |
| Use Soon | Fresh / Normal | None |
| Unchanged | Same status | None |

This remains per active food, not per raw sensor reading. Without an active food,
there is no food notification even if the device response says Check Food.
LIVE/DELAYED/OFFLINE_RECOVERED do not trigger notifications by themselves.

## Delivery flow after the fix

```text
POST reading -> validate -> freshness -> reading + snapshots + outbox commit -> ACK

Worker -> atomic DB claim -> commit/release DB writer lock -> Telegram HTTP
       -> verified success: DELIVERED
       -> failure: safe error, PENDING until attempt limit, then FAILED
```

Worker scheduling is independent; Telegram may run before or after the response
reaches ESP32, but the HTTP call is never awaited by the reading route.

Two nullable outbox columns (`claim_token`, `lease_until`) are added through the
existing idempotent startup migration. Each claim increments attempt count
atomically before HTTP. Only that claim owner may mark its result. Leases last
120 seconds; a crashed worker's expired claim can retry. An exhausted expired
claim becomes FAILED with an unknown-outcome error. No SQLite writer lock is
held during the network call.

`send_telegram_message()` builds the message; `send_telegram_text()` is the shared
transport also used by the explicit manual test. Transport checks HTTP 2xx,
JSON `ok == true` and an integer `result.message_id`. The body is bounded at
64 KiB. Messages are plain text (no parse_mode) and bounded to 4000 UTF-16 units.
See the official [Telegram sendMessage contract](https://core.telegram.org/bots/api#sendmessage).

Message payload now includes the UUID, temperature, humidity, gas and door state.
Old pending payloads still work and display missing sensor values as N/A.
Logs include SENT/FAILED/SKIPPED/DISABLED with useful identifiers. Exception text
is allowlisted before persistence; neither token nor raw Telegram error URL/body
is printed. Chat is masked in delivery logs.

## Configuration

Install the updated requirements into the backend environment:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
```

Copy only if `backend/.env` does not already exist. Edit it locally:

```dotenv
TELEGRAM_BOT_TOKEN=<your bot token>
TELEGRAM_CHAT_ID=<your target chat ID>
```

Do not commit `.env`. `.env.example` contains no secrets and is explicitly allowed
by `.gitignore`. The app and manual commands load **backend/.env**, independent
of current working directory. Existing process environment takes precedence.
Missing/blank or embedded-whitespace config disables notifications without
stopping the backend. Presence validation does not prove token validity or bot
permissions; the manual network test is separate.

Start the backend normally with `backend/run.py`. Once configured, the existing
worker will process pending notifications. FAILED rows are not automatically
reset after changing credentials; inspect them before choosing a retry.

## Manual integration test (not executed against Telegram in this task)

Check config without sending:

```powershell
.\backend\.venv\Scripts\python.exe backend/check_telegram.py
```

Explicitly send one test message:

```powershell
.\backend\.venv\Scripts\python.exe backend/check_telegram.py --send-test
```

This uses the same transport, sends a clearly labelled connectivity test,
does not invent a sensor reading, and does not drain/change the outbox.
The bot must have access to the configured chat. Verify both API acceptance
(`message_id` output) **and the test appearing in the actual chat**. No credentials
are printed. In this session, the config-only command reported disabled and sent nothing.

## Example message (illustrative)

```text
🚨 FreshGuard — Check Food

Food: Beef
Category: MEAT
Status: Check Food
Temperature: 13 C
Humidity: 60 %
Gas: 100
Door: Closed
Device: FG-ESP32-01
Captured at: 2026-09-29T01:00:00+07:00
Reason: Critical Temperature: temperature is too high.
```

Actual logs from mock integration tests in this session:

```text
[TELEGRAM SENT] outbox_id=1 device='FG-ESP32-01' reading_id='aa6ceb44-69c7-4267-bc30-2cfda17476d8' status='Use Soon' chat=***
[TELEGRAM FAILED] outbox_id=1 device='FG-ESP32-01' reading_id='84a9df98-5d57-4266-a51b-9d81915e6245' status='Check Food' error=timeout attempt=1 delivery_status=PENDING
[TELEGRAM SKIPPED] reason=duplicate_replay device='FG-ESP32-01' reading_id=84a9df98-5d57-4266-a51b-9d81915e6245
```

## Tests and limitations

New/expanded tests cover normal/no-send, warning/alert send, success logging,
timeouts and HTTP 400/401/403/429/500 without broken reading ACKs, duplicate UUID
after successful delivery, twenty unchanged Check Food readings, recovery then
another alert, ingest-status independence, missing config, dotenv precedence,
claim concurrency/expiry, migration, message limits/nulls, invalid response
bodies, HTTP failures with misleading ok bodies, and exception redaction.

An autouse test fixture clears real Telegram environment, skips the real `.env`
and blocks real transport. Individual tests use mocks or temporary dotenv files.

Final executed verification on 2026-09-29:

```text
backend/.venv/Scripts/python.exe -m pytest -q -c backend/pytest.ini backend/tests
555 passed in 70.08s
```

The focused Telegram/outbox run before the last additional HTTP-status test had
44 passing cases. The final full run includes that additional test and the
network-isolation fixture. `git diff --check` reported no whitespace errors.
The config-only manual command ran and reported missing config; no real message
was sent. Successful delivery logs above are from mocks, not the live Bot API.

Files changed for this task:

- `backend/app/services/telegram_notifier.py`
- `backend/app/routes/readings.py`
- `backend/app/init_db.py`
- `backend/app/__init__.py`
- `backend/run.py`
- `backend/send_pending_notifications.py`
- `backend/check_telegram.py` (new)
- `backend/requirements.txt`
- `backend/.env.example` (new)
- `.gitignore`
- `backend/tests/test_telegram_notifier.py`
- `backend/tests/test_telegram_integration.py` (new)
- `backend/tests/conftest.py` (new)
- `doc/telegram-notifications.md` (new)

Remaining limits:

- No true exactly-once guarantee across Telegram and SQLite: Telegram can accept
  a message before the response or DB delivery update is lost; a retry can duplicate it.
- The 120-second lease assumes the request finishes before expiration. A hung or
  suspended process beyond the lease can overlap recovery. The five-second socket
  timeout is not a strict end-to-end deadline against a continuously trickling peer.
- Retries stay bounded at three, with the existing polling interval. Permanent
  4xx is also retried up to this limit. No special Retry-After/backoff policy was added.
- Multiple active foods can legitimately create multiple notifications. Food
  snapshot state is shared per food as before; this task does not redesign device ownership.
- Historical replay is evaluated under existing freshness/active-food policy;
  a historical transition can still create a legitimate notification. No new
  suppression based solely on ingest status was introduced.
- Outbox persistence failure is a DB transaction failure; Telegram HTTP failure
  is isolated. These are different failure conditions.
- Real bot credentials, permissions, message arrival, live network failures and
  ESP32 hardware were not tested here.
