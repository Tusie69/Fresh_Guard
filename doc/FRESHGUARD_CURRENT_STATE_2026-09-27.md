# FreshGuard Current State — 2026-09-27

## 1. Project status

- Project: `C:\Users\TuNgu\freshguard`
- Branch: `main`
- HEAD: `6e17f614cef4a1f95f49403e514042e15bec123a`
- This handover describes the working tree as found. It does not claim that the working tree is clean.
- Existing modified tracked files include the Flask factory, DB initialization, readings route, freshness services, stateful processors, and related tests.
- Existing untracked work includes authentication, admin, rule provider/admin services, state reset, admin creation script, auth/rule/user tests, dashboard login/admin pages, and `doc/FreshGuard_Test_Cases.md`.
- SQLite files present: `backend/freshguard.db` and `backend/freshguard_test.db`.
- Full verification command:

```text
.\backend\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -o pythonpath=C:/Users/TuNgu/freshguard/backend backend/tests firmware/tests -q
```

- Result: **516 passed in 55.35s**.
- `python -m compileall -q backend`: passed.
- `git diff --check`: passed; existing CRLF warnings were reported for tracked files.

The previously quoted baseline counts (483/497) do not match this current checkout. The current source and test run are the authoritative numbers for this document.

## 2. Current architecture

```text
ESP32 / simulator
  -> Flask API (`backend/app/routes`)
  -> SQLite (`backend/app/database.py`, `backend/app/init_db.py`)
  -> freshness engine and stateful processors (`backend/app/services`)
  -> reading response and stored snapshot
  -> vanilla HTML/JavaScript dashboard
```

- `backend/app/__init__.py` is the Flask application factory. It configures sessions, CORS, static dashboard routes, and registers the API blueprints.
- `backend/app/routes/readings.py` owns reading ingestion, duplicate/conflict/new semantics, transaction boundaries, rule snapshot capture, stateful processor calls, sensor-fault transitions, freshness evaluation, and event writes.
- `backend/app/routes/foods.py` owns food CRUD/read endpoints.
- `backend/app/routes/events.py` stores device/simulator events.
- `backend/app/services/freshness.py` owns status aggregation and stateless evaluation of temperature, humidity, gas result, door, storage, and expiry.
- `backend/app/services/temperature_exposure.py` owns per `(device_id, food_id)` exposure state.
- `backend/app/services/gas_anomaly.py` owns per `(device_id, food_id)` gas baseline/anomaly state.
- `backend/app/services/sensor_fault.py` owns sensor fault/recovery transitions.
- `backend/app/services/rule_provider.py` owns the immutable FreshRules snapshot and DB-backed rule loading.
- `backend/app/services/rule_admin.py` validates/administers persisted rules.
- `backend/app/services/state_reset.py` resets stateful tables for selected rule changes.
- `backend/app/services/auth.py` owns password hashing, session lookup, and role guards.
- `dashboard/index.html`, `dashboard/login.html`, and `dashboard/admin.html` are vanilla HTML/JavaScript; there is no frontend framework or build pipeline.

The ESP32 protocol and the reading identity `(device_id, device_reading_id)` remain unchanged. Readings still return duplicate `200`, new `201`, and conflict `409` according to the existing identity semantics.

## 3. Current temperature rules

The provider defaults are the current configurable temperature values:

| Rule | Current value | Source/consumer | Persistence/editability |
|---|---:|---|---|
| `temperature.hot_threshold_c` | `5.0 °C` | `rule_provider.py`; `freshness._evaluate_temperature_rule`; `temperature_exposure.update_temperature_exposure` | persisted; admin-editable; stateful reset on change |
| `temperature.exposure_limit_seconds` | `7200 s` (2 h) | provider; `freshness`; temperature exposure processor | persisted; admin-editable; stateful reset on change |
| `temperature.continuity_gap_seconds` | `10 s` | provider; temperature exposure processor | persisted; currently locked; reset policy is not exposed |
| `temperature.critical_threshold_c` | `12.0 °C` | `rule_provider.py`; `freshness._evaluate_temperature_rule` | persisted/seeded; visible in read-only/admin metadata; locked |

Temperature evaluation uses `temperature > rules.temperature_critical_threshold_c` for `Check Food`; values above the provider hot threshold generate a warning, and exposure over the configured limit generates `Check Food`. Critical temperature and exposure are separate semantics: a first `30 °C` reading is critical immediately, while exposure state starts hot with zero accumulated seconds.

The exposure state table stores `exposure_seconds`, `exposure_active`, `exposure_exceeded`, `last_valid_temperature_timestamp`, and `continuity_broken`. Out-of-order timestamps leave state unchanged. Invalid temperatures preserve accumulated exposure and mark continuity broken when newer. A stateful rule change currently resets all temperature rows in one transaction.

## 4. Current gas rules

| Rule | Current value | Source/consumer | State |
|---|---:|---|---|
| `gas.baseline_sample_count` | `10` valid samples | provider; `gas_anomaly.update_gas_anomaly` | persisted; locked in admin UI |
| `gas.anomaly_increase_pct` | `30.0%` (provider ratio `0.30`) | provider; gas anomaly processor | persisted; locked |
| `gas.anomaly_consecutive_readings` | `3` consecutive anomalous readings | provider; gas anomaly processor | persisted; locked |

Gas state is keyed by `(device_id, food_id)` and stores baseline, sample count, baseline sum, consecutive anomaly count, and sticky anomaly status. Invalid readings reset the consecutive counter but preserve an active anomaly. A baseline of zero cannot produce a percentage anomaly. Starts/recoveries are emitted only on state transitions; no synthetic rule-change events are generated. Gas rule changes are not currently allowed because runtime migration/reset semantics have not been exposed.

## 5. Humidity, door, storage, and expiry

| Rule | Current value | Current behavior |
|---|---|---|
| `humidity.vegetable_min_pct` / `max_pct` | `80 / 95` | outside range produces a warning reason; severity remains `Fresh` |
| `humidity.fruit_min_pct` / `max_pct` | `80 / 95` | same behavior for FRUIT |
| `door.open_duration_seconds` | `30 s` | open duration `>= 30` is `Check Food`; open with shorter duration is `Fresh` with “Door is open.” |
| `storage.<category>.max_days` | MEAT `3`, DAIRY `14`, VEGETABLE `7`, FRUIT `14`, COOKED_FOOD `4` | over max is `Check Food`; near max uses the warning window |
| `storage.<category>.warning_days` | `1` for every category | `duration >= max_days - warning_days` gives `Use Soon` |
| `expiry.use_soon_window_days` | `1` | expiry within one day is `Use Soon`; past expiry is `Check Food` |

Humidity, storage, and expiry are stateless and are currently editable. Backend door evaluation is stateless, but the simulator also has in-memory door timeout state and emits door events using the same numeric threshold. There is no backend door state table, so ownership of door timeout/event semantics is split.

## 6. Freshness aggregation and fault behavior

- The only statuses are `Fresh / Normal`, `Use Soon`, and `Check Food`.
- Severity is `0/1/2`; final status is the maximum severity from temperature, humidity, gas, door, storage, and expiry.
- Reasons include every non-empty warning/fault/violation reason and are joined with `; `; an otherwise clean reading uses `All sensor readings are available`.
- Null or invalid sensor values produce `Check Food` sensor-fault/invalid-value reasons. `sensor_fault.py` records independent fault/recovery transitions in `sensor_fault_state`.
- Temperature `> 12 °C` is an immediate critical `Check Food` condition, but the threshold is still a source literal rather than a provider rule.
- A reading captures one rule snapshot from the database connection and passes that same snapshot to gas, temperature exposure, and freshness evaluation, avoiding mixed-rule evaluation within one reading.

## 7. Complete FreshRules inventory

`rule_provider.py` defines an immutable `FreshnessRules` snapshot. The persisted database keys are seeded if missing and are loaded as one complete snapshot; partial/invalid DB data raises a provider error rather than silently mixing defaults.

| Rule key | Default | Persisted | Editable class | Stateful? | Reset required |
|---|---:|---|---|---|---|
| `temperature.hot_threshold_c` | 5.0 | yes | `STATEFUL_EDITABLE` | yes | temperature state; must remain below critical |
| `temperature.critical_threshold_c` | 12.0 | yes | `LOCKED_RULE_KEYS` | yes | no runtime reset; locked |
| `temperature.exposure_limit_seconds` | 7200 | yes | `STATEFUL_EDITABLE` | yes | temperature state |
| `temperature.continuity_gap_seconds` | 10 | yes | `LOCKED_RULE_KEYS` | yes | policy not exposed |
| `gas.baseline_sample_count` | 10 | yes | locked | yes | gas state policy not exposed |
| `gas.anomaly_increase_pct` | 30.0 | yes | locked | yes | gas state policy not exposed |
| `gas.anomaly_consecutive_readings` | 3 | yes | locked | yes | gas state policy not exposed |
| `humidity.vegetable_min_pct` | 80 | yes | `STATELESS_EDITABLE` | no | no |
| `humidity.vegetable_max_pct` | 95 | yes | `STATELESS_EDITABLE` | no | no |
| `humidity.fruit_min_pct` | 80 | yes | `STATELESS_EDITABLE` | no | no |
| `humidity.fruit_max_pct` | 95 | yes | `STATELESS_EDITABLE` | no | no |
| `door.open_duration_seconds` | 30 | yes | locked | backend stateless; simulator stateful | unsupported |
| `storage.MEAT.max_days` / `warning_days` | 3 / 1 | yes | `STATELESS_EDITABLE` | no | no |
| `storage.DAIRY.max_days` / `warning_days` | 14 / 1 | yes | `STATELESS_EDITABLE` | no | no |
| `storage.VEGETABLE.max_days` / `warning_days` | 7 / 1 | yes | `STATELESS_EDITABLE` | no | no |
| `storage.FRUIT.max_days` / `warning_days` | 14 / 1 | yes | `STATELESS_EDITABLE` | no | no |
| `storage.COOKED_FOOD.max_days` / `warning_days` | 4 / 1 | yes | `STATELESS_EDITABLE` | no | no |
| `expiry.use_soon_window_days` | 1 | yes | `STATELESS_EDITABLE` | no | no |

The critical threshold is provider-backed and persisted, but intentionally locked. It is normalized for one source of truth without expanding runtime editability.

## 8. Current state reset behavior

- `reset_temperature_state` sets exposure seconds to zero, clears active/exceeded flags, clears the last valid timestamp, and clears continuity-broken state.
- `reset_gas_state` clears baseline, sample count, baseline sum, consecutive count, and anomaly-active state.
- `reset_state_for_rule_keys` maps any `temperature.*` change to temperature reset and any `gas.*` change to gas reset; a `door.*` reset raises “Door state reset is unsupported”.
- `apply_stateful_rule_transaction` performs update, audit, reset, and commit atomically; exceptions roll back the transaction.
- The current admin update route resets temperature state for changed hot-threshold or exposure-limit rules. Gas, continuity-gap, and door edits remain unavailable.
- Reset operations do not write synthetic freshness, gas, temperature, or door events. Audit rows are the only configuration-history record.
- “Reset defaults” currently resets only stateless editable rules; it excludes the two editable temperature stateful rules.

## 9. Authentication and RBAC

- Users are stored in `users` with unique username, Werkzeug password hash, role check (`USER`/`ADMIN`), active flag, and timestamps.
- Login stores only `user_id` in the session. Each request reloads the user, so role and active status changes take effect on the next request.
- `/api/v1/auth/login`, `/api/v1/auth/me`, and `/api/v1/auth/logout` are implemented.
- `/api/v1/freshness-rules` requires authentication and is read-only for USER and ADMIN.
- Admin routes require ADMIN. Reading, food, and event routes remain public for firmware/dashboard compatibility.
- Session cookies are HTTPOnly and SameSite Lax. `SECRET_KEY` comes from `FRESHGUARD_SECRET_KEY` or a random fallback; production configuration still needs hardening.
- CORS remains wildcard for `/api/*`, which is convenient for local use but unsafe as a production cross-origin/session policy.

## 10. User management

Implemented admin endpoints:

- list/get users;
- create user with username, password, and role;
- update role or active status;
- user-management history.

Passwords are hashed. Duplicate usernames return `409`. There is no delete endpoint. Self-demotion/deactivation and removal of the last active admin are protected. Changes requiring a reason are audited with actor and target snapshots in `user_management_audit`.

## 11. Admin dashboard state

`dashboard/admin.html` is a vanilla admin dashboard with auth check, overview cards, user CRUD/history, freshness rule editing/history, and stateless reset-defaults UI. Stateful temperature edits display a warning/confirmation. Rule metadata controls editable versus locked fields.

Implemented UI areas: users, user audit, freshness rules, freshness audit, overview. Foods, readings, and events are sidebar placeholders. There is no framework, bundler, or production frontend build. Static route smoke checks for `/`, `/login`, and `/admin` returned `200`; a full browser walkthrough was not performed.

## 12. Freshness rule audit and persistence

`freshness_rules` stores one row per key: `rule_key`, text `rule_value`, `value_type`, update timestamp, and optional updater user id. `freshness_rule_audit` stores actor id/username/role snapshots, key, old/new values, value type, reason, and change time.

The admin PUT validates the complete request before updating. Changed values are written and audited; unchanged values are skipped. A reason is required for changes. Mixed batches are atomic. Stateful temperature updates call the state reset in the same transaction. Reset-defaults audits changed stateless values only. There are no version columns, effective-from timestamps, or synthetic reading/event records for configuration changes.

## 13. API inventory

| Endpoint | Access | Purpose |
|---|---|---|
| `POST /api/v1/readings` | public | ingest reading; preserves 200/201/409 semantics |
| `GET /api/v1/readings`, `/readings/latest` | public | read readings |
| `POST /api/v1/foods`; `GET /api/v1/foods`; `GET /api/v1/foods/<food_id>` | public | food data |
| `POST /api/v1/events` | public | store device/simulator events |
| `POST /api/v1/auth/login` | public | create session |
| `GET /api/v1/auth/me` | authenticated | current user |
| `POST /api/v1/auth/logout` | public/session | clear session |
| `GET /api/v1/freshness-rules` | USER/ADMIN | read current rules |
| `GET /api/v1/admin/status` | ADMIN | admin status |
| `GET /api/v1/admin/overview` | ADMIN | aggregate overview |
| `GET/PUT /api/v1/admin/freshness-rules` | ADMIN | read/update rules |
| `POST /api/v1/admin/freshness-rules/reset` | ADMIN | reset stateless editable defaults |
| `GET /api/v1/admin/freshness-rules/history` | ADMIN | rule audit history |
| `GET/POST /api/v1/admin/users`; `GET/PATCH /api/v1/admin/users/<id>` | ADMIN | user management |
| `GET /api/v1/admin/users/history` | ADMIN | user-management audit |

## 14. SQLite schema

`init_db.py` creates or migrates these tables:

- `sensor_readings`, with unique `(device_id, device_reading_id)` and stored freshness snapshot fields;
- `food_items`, unique `food_id`;
- `gas_anomaly_state`, keyed by `(device_id, food_id)`;
- `temperature_exposure_state`, keyed by `(device_id, food_id)`;
- `sensor_fault_state`, uniquely keyed by device/food/sensor;
- `events`, unique `event_id`;
- `users`;
- `freshness_rules`;
- `freshness_rule_audit`;
- `user_management_audit`.

Connections are SQLite connections with `sqlite3.Row`, and route-level transactions preserve reading/state/event atomicity. Existing snapshot columns are not recalculated when rules change.

## 15. Test coverage

The current suite has **516 passing tests** across backend and firmware tests. Coverage includes:

- reading idempotency, conflict handling, freshness snapshots, foods, and events;
- temperature business boundaries, exposure continuity, out-of-order/invalid samples, and reset behavior;
- gas baseline, anomaly, invalid input, sticky state, transitions, and provider use;
- humidity, storage, expiry, door, and sensor-fault behavior;
- provider defaults/immutability and DB loading;
- auth login/session/role/inactive-user behavior;
- admin rule validation, persistence, audit, reset, and stateful transaction behavior;
- user management protections and audit;
- admin overview and simulator integration.

Remaining verification gaps are primarily production/browser validation, real ESP32 integration, and runtime policy tests for currently locked gas/continuity/door rules.

## 16. Locked or unfinished areas

- Gas rules are persisted and provider-backed but cannot be edited safely at runtime yet.
- Temperature continuity-gap rule is persisted but locked.
- Door threshold ownership is split between backend evaluation and simulator in-memory timeout state; backend has no door state table.
- Critical temperature is now provider-backed and persisted at `12.0 °C`, but remains locked for runtime editing.
- Reset-defaults semantics intentionally skip stateful temperature rules; this needs a product decision before broader runtime editing.
- Production secret management, secure CORS origins, cookie deployment settings, and CSRF strategy need hardening.
- Admin dashboard has placeholder navigation for foods/readings/events and has not had a full manual browser pass.
- Real hardware/queue/QR workflows have not been validated in this audit.

## 17. Business-rule drift found

| Area | Current source of truth | Drift/risk |
|---|---|---|
| Temperature critical | `temperature.critical_threshold_c` in provider/DB; consumed by `freshness.py` | normalized and locked; hot threshold validation enforces hot < critical |
| Temperature aliases | provider defaults re-exported by compatibility aliases in services | duplicate names remain, although processors receive provider snapshots |
| Door timeout | provider/backend `30`; simulator constants `30` | duplicated ownership and no shared state/reset semantics |
| Gas/temperature numeric literals | provider plus tests/compatibility constants | tests intentionally repeat boundary values; verify any future source literal before changing behavior |
| Stored snapshots | `sensor_readings` stores evaluated status/reason | rule changes do not recalculate history, by design |
| Rule reset | stateless defaults only | stateful defaults require explicit reset policy |

## 18. Source-of-truth summary

```text
OVERALL STATUS: Functional current baseline; working tree contains substantial uncommitted auth/RBAC, configurable-rule, dashboard, and temperature-business-rule work.

VERIFIED TEST STATUS: 516 passed in 55.35s across backend/tests and firmware/tests.

CURRENT USER/ADMIN STATUS: Session authentication, USER/ADMIN roles, admin user management, rule read access, and protected admin APIs are implemented.

CURRENT FRESHRULES STATUS: Immutable provider snapshot is shared by freshness, temperature exposure, and gas processing; critical threshold is persisted/read-only and the approved editable subset remains unchanged.

CURRENT TEMPERATURE RULE: Hot threshold 5.0 °C, critical threshold 12.0 °C, exposure limit 7200 s, continuity gap 10 s; critical Check Food remains strictly `temperature > 12.0` and critical readings still enter hot exposure processing.

CURRENT GAS RULE: Baseline 10 samples, anomaly increase 30%, consecutive count 3; provider-backed but locked for runtime editing.

CURRENT LOCKED RULES: Temperature critical threshold and continuity gap, all gas rules, and door timeout.

CURRENT HARDWARE STATUS: ESP32 protocol and reading identity are unchanged; real-device integration was not validated in this audit.

TOP 5 NEXT TASKS:
1. Define production secret, CORS, session-cookie, and CSRF configuration, then perform browser validation.
2. Unify door threshold/event ownership between backend and simulator.
3. Decide stateful Reset Defaults/versioning semantics for temperature and future gas edits.
4. Add runtime policy tests before unlocking gas or continuity-gap rules.
5. Validate real ESP32 integration, queue behavior, and QR flow.

NEXT RECOMMENDED PHASE: Freeze/tag this handover baseline, then resolve rule drift and production hardening before adding more feature scope.
```

## 19. Scope of this handover file

This file is the current audit handover requested for 2026-09-27. It is documentation only. No runtime source file, SQLite database, test file, commit, or push was performed as part of creating it.
