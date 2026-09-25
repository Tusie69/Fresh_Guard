# FreshGuard IoT Test Matrix

This matrix records behavior present in the current FreshGuard prototype. It separates verified test results from planned/manual checks and functionality that does not exist in the inspected project. The code and test files are the sources of truth; a scenario is not considered passed merely because its expected result follows from code.

## 1. Test Scope

The scope covers sensor reading ingestion, Freshness Engine rules, Food metadata integration, storage duration and expiry, door state, sensor faults, API validation, Dashboard presentation, Events idempotency, SQLite persistence, and current prototype limitations.

The current project includes a Python simulator that sends readings to a local Flask API. This simulator is separate from backend integration tests, which use Flask's test client and temporary SQLite databases, and from real ESP32 hardware testing. It does not provide real ESP32 sensor/LED evidence. Features without an implementation are not counted as passing test cases.

## 2. Test Environment

| Component | Current project configuration |
| --- | --- |
| Backend | Flask application; pinned Flask version in `backend/requirements.txt` is 3.1.3 |
| Persistence | SQLite, connection path configured in `backend/app/database.py`; automated API tests use temporary SQLite databases |
| API transport | REST over HTTP |
| Readings endpoint | `POST /api/v1/readings`; `GET /api/v1/readings/latest`; `GET /api/v1/readings` |
| Food endpoints | `POST /api/v1/foods`; `GET /api/v1/foods`; `GET /api/v1/foods/<food_id>` |
| Events endpoint | `POST /api/v1/events` |
| Dashboard | HTML and JavaScript in `dashboard/index.html`; API base URL is local (`http://127.0.0.1:5000/api/v1`) |
| Firmware-side project file | `firmware/simulator.py`, a Python HTTP simulator using `requests`; no actual ESP32 firmware or sensor driver was found in the inspected project files |
| Simulator sample interval | 5 seconds after each send; its closed-door branch also waits 10 seconds before sending that sample |
| Simulator door behavior | Closed samples use 0 seconds; open samples measure elapsed time and close at 30 seconds (`DOOR_OPEN_DURATION = 30`) |
| Simulator sensor values | Constant: temperature 5.0 °C, humidity 60.0, gas_raw 300 |
| Auto Test 3 States / LEDs | Not present in `firmware/simulator.py`; there is no code evidence for 5/10/15 °C scenarios or LED outputs |

The simulator's comment says to close the door after 40 seconds, while the executable constant is 30 seconds. The simulator checks elapsed duration on its loop (approximately every 5 seconds) and closes on the first check at or above 30 seconds. The backend Freshness Engine also uses a 30-second threshold. The comment is inconsistent and is not treated as behavior.

## 3. Test Result Convention

| Status | Meaning |
| --- | --- |
| PASS | The test was actually run and its assertion/result matched the expected result. Evidence is named in the row. |
| FAIL | The test was run and the observed result did not match the expected result. |
| NOT TESTED | The behavior exists or is testable, but this matrix has no run evidence for that case. Actual Result is `Not tested`; Evidence is `Pending`. |
| NOT IMPLEMENTED | The required function is absent in the inspected prototype. This is not a failed test. |
| BLOCKED | Testing requires a missing hardware/dependency/environment. No case is marked BLOCKED unless that dependency is the specific obstacle. |

PASS entries below are supported by the backend test run performed for this review: `python -m pytest -q` from `backend/` could not start because the default Python environment has no pytest module; running `\.venv\Scripts\python.exe -m pytest -q` from `backend/` reported **130 passed**. Evidence names the relevant test function(s). Dashboard and physical-hardware cases have no such test evidence.

## 4. IoT Test Matrix

| Test ID | Category | Scenario | Input / Setup | Expected Result | Actual Result | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FG-IOT-001 | Readings API | Valid reading without linked food | Complete readings payload; finite sensors; door closed | HTTP 201; reading persisted; freshness returned | Created with Fresh / Normal in tested case | PASS | `test_reading_without_food_id_keeps_response_contract`; `test_reading_without_food_id_remains_supported` |
| FG-IOT-002 | Readings API | Empty, malformed, null, or non-object JSON | Empty body, malformed JSON, JSON null, or array | HTTP 400 JSON error | All tested variants returned 400 | PASS | `test_readings_reject_empty_malformed_and_non_object_json` |
| FG-IOT-003 | Readings API | Missing required field | Omit a required sensor field, e.g. `gas_raw` | HTTP 400 with missing-field information | Returned 400; missing field reported | PASS | `test_readings_reject_missing_required_fields` |
| FG-IOT-004 | Readings API | Empty/invalid device ID | Blank or non-string `device_id` | HTTP 400 | Both tested variants returned 400 | PASS | `test_readings_reject_invalid_fields` |
| FG-IOT-005 | Readings API | Invalid timestamp | Non-ISO datetime string | HTTP 400 | Returned 400 | PASS | `test_readings_reject_invalid_fields` |
| FG-IOT-006 | Readings API | Malformed or non-finite sensor value | Text sensor value, NaN, or infinity | HTTP 400; invalid value is not stored | Tested variants returned 400 | PASS | `test_readings_reject_invalid_fields` |
| FG-IOT-007 | Readings API / Freshness | Null sensor values | `temperature_c`, `humidity_pct`, and `gas_raw` are null | Reading may be stored; engine reports Check Food, not Fresh | HTTP 201 and Check Food in tested case | PASS | `test_readings_accept_null_sensor_values_without_marking_them_fresh` |
| FG-IOT-008 | Readings API | Invalid door state | `door_open` is string or null | HTTP 400 | Tested variants returned 400 | PASS | `test_readings_reject_invalid_fields` |
| FG-IOT-009 | Readings API | Invalid door duration | Negative, string, or null duration | HTTP 400 | Tested variants returned 400 | PASS | `test_readings_reject_invalid_fields` |
| FG-IOT-010 | Food / Readings API | Unknown `food_id` | Submit reading linked to unregistered food | HTTP 404; no reading is persisted | 404; history remained empty | PASS | `test_unknown_food_does_not_create_reading`; `test_unknown_food_returns_404_without_saving_reading` |
| FG-IOT-011 | Readings API | Latest and history retrieval | Create reading, then request latest and history | Existing reading and computed freshness are returned | Tested food-linked reading appeared in both responses | PASS | `test_reading_history_recomputes_freshness_from_linked_food`; `test_latest_and_history_reload_linked_food_for_freshness` |
| FG-IOT-012 | Readings API | History limit | Missing/unparseable, 0, negative, and very large limit | Default 20; non-positive returns 400; values above 100 capped at 100 | Tested behavior matched these outcomes | PASS | `test_history_uses_default_limit_for_missing_or_unparseable_limit`; `test_history_rejects_non_positive_limit`; `test_history_caps_oversized_limit` |
| FG-IOT-013 | SQLite | Reading persistence | Create reading through API using temporary database, reload via history | Reading remains available after request connection closes | Read-back verified by API integration tests | PASS | `test_reading_history_recomputes_freshness_from_linked_food`; temporary DB test fixtures in `backend/tests/` |
| FG-IOT-014 | Events API | Valid event creation | Required `event_id`, `device_id`, ISO timestamp, and `event_type` | HTTP 201 on first create | First create returned 201 in idempotency test | PASS | `test_duplicate_event_remains_idempotent` |
| FG-IOT-015 | Events API | Missing event ID or invalid required field | Omit event ID; use blank/non-string field, null event type, or invalid timestamp | HTTP 400 | Tested variants returned 400 | PASS | `test_events_missing_required_field_reports_400`; `test_events_reject_missing_or_invalid_fields` |
| FG-IOT-016 | Events API | Invalid JSON | Empty, malformed, null, or non-object JSON | HTTP 400 | Tested variants returned 400 | PASS | `test_events_reject_empty_malformed_and_non_object_json` |
| FG-IOT-017 | Events / Reliability | Duplicate event ID | Submit same valid event twice | First request creates event; duplicate is idempotent and does not create a second record | First returned 201; duplicate returned 200 with `duplicate: true` | PASS | `test_duplicate_event_remains_idempotent` |
| FG-IOT-018 | Local persistence | Food record persistence and retrieval | Create food, retrieve by ID/list | Created food is available from SQLite-backed API | Create and retrieval verified | PASS | `test_create_food_success`; `test_get_foods_returns_created_foods`; `test_get_existing_food` |

## 5. Freshness Decision Tests

The backend engine maps severity 0/1/2 to Fresh / Normal, Use Soon, and Check Food. The active rules and thresholds are documented in [freshness-decision-rule-matrix.md](freshness-decision-rule-matrix.md). `evaluate_freshness()` uses maximum severity across all rules.

| Test ID | Category | Scenario | Input / Setup | Expected Result | Actual Result | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FG-IOT-019 | Sensor data | All valid sensors, door closed | Finite temperature/humidity/gas; door false | Fresh / Normal | Fresh in unit test | PASS | `test_freshness_all_sensors_normal` |
| FG-IOT-020 | Sensor fault | Temperature unavailable | `temperature_c = None` | Check Food with temperature sensor fault reason | Check Food asserted | PASS | `test_temperature_sensor_fault` |
| FG-IOT-021 | Sensor fault | Humidity unavailable | `humidity_pct = None` | Check Food with humidity sensor fault reason | Check Food asserted | PASS | `test_humidity_sensor_fault` |
| FG-IOT-022 | Sensor fault | Gas unavailable | `gas_raw = None` | Check Food with gas sensor fault reason | Check Food asserted | PASS | `test_gas_sensor_fault` |
| FG-IOT-023 | Sensor fault | Door state omitted/null at engine boundary | Call engine with `door_open = None` | Check Food with door sensor fault reason | Not tested | NOT TESTED | Pending; no matching assertion found in current tests |
| FG-IOT-024 | Sensor validity | Invalid temperature/humidity/gas/door/duration values | Strings, booleans for numeric values, invalid open duration | Check Food; reasons identify invalid value | Tested malformed and boolean values returned Check Food | PASS | `test_malformed_sensor_inputs_return_check_food`; `test_boolean_sensor_values_are_invalid`; `test_negative_open_duration_is_invalid` |
| FG-IOT-025 | Temperature | Exact lower boundary | 8 °C | Fresh / Normal | Fresh asserted | PASS | `test_temperature_threshold_boundaries` |
| FG-IOT-026 | Temperature | Between thresholds | 8.01 °C | Use Soon | Use Soon asserted | PASS | `test_temperature_threshold_boundaries` |
| FG-IOT-027 | Temperature | Exact upper boundary | 12 °C | Use Soon | Use Soon asserted | PASS | `test_temperature_threshold_boundaries` |
| FG-IOT-028 | Temperature | Above upper boundary | 12.01 °C | Check Food | Check Food asserted | PASS | `test_temperature_threshold_boundaries` |
| FG-IOT-029 | Door | Closed | Door false | Fresh / Normal; duration ignored by engine rule | Fresh asserted | PASS | `test_door_closed`; `test_evaluate_door_wrapper` |
| FG-IOT-030 | Door | Open below timeout | Door true, 29 seconds | Use Soon | Use Soon asserted | PASS | `test_door_timeout_boundary` |
| FG-IOT-031 | Door | Exactly at timeout | Door true, 30 seconds | Check Food | Check Food asserted | PASS | `test_door_timeout_boundary` |
| FG-IOT-032 | Door | Above timeout | Door true, 31 seconds | Check Food | Check Food asserted | PASS | `test_door_timeout_boundary` |
| FG-IOT-033 | Door | Legacy helper behavior | Call `evaluate_door(True)` without duration | Use Soon; this helper does not apply 30-second timeout | Use Soon and `Door is open.` asserted | PASS | `test_evaluate_door_wrapper` |
| FG-IOT-034 | Storage | MEAT boundary cases | 1, 2, 3, and 4 calendar days | Fresh, Use Soon, Use Soon, Check Food | All four asserted | PASS | `test_storage_duration_boundaries`; `test_storage_duration_flows_from_food_record` |
| FG-IOT-035 | Storage | DAIRY 12 days | 12 calendar days | Fresh | Not tested | NOT TESTED | Pending; 12-day boundary absent from tests |
| FG-IOT-036 | Storage | DAIRY 13, 14, 15 days | Calendar-day duration | Use Soon, Use Soon, Check Food | All three asserted | PASS | `test_storage_duration_boundaries` |
| FG-IOT-037 | Storage | VEGETABLE 5 days | 5 calendar days | Fresh | Fresh asserted in category profile comparison | PASS | `test_food_id_selects_the_registered_category` |
| FG-IOT-038 | Storage | VEGETABLE 6, 7, 8 days | Calendar-day duration | Use Soon, Use Soon, Check Food | Not tested | NOT TESTED | Pending; these boundary values absent from tests |
| FG-IOT-039 | Storage | FRUIT 12, 13, 14, 15 days | Calendar-day duration | Fresh, Use Soon, Use Soon, Check Food | Not tested | NOT TESTED | Pending; no FRUIT duration cases found |
| FG-IOT-040 | Storage | COOKED_FOOD 2, 3, 4, 5 days | Calendar-day duration | Fresh, Use Soon, Use Soon, Check Food | Not tested | NOT TESTED | Pending; no COOKED_FOOD duration cases found |
| FG-IOT-041 | Storage | Missing category | `category = None`, valid insertion date | Storage rule skipped; this rule contributes Fresh | Not tested independently | NOT TESTED | Pending; current optional-data test omits both category and insertion date |
| FG-IOT-042 | Storage | Missing `inserted_at` | Known category, `inserted_at = None` | Storage rule skipped; this rule contributes Fresh | Not tested independently | NOT TESTED | Pending |
| FG-IOT-043 | Storage | Unknown category | Unknown category string and valid date | Check Food | Check Food asserted | PASS | `test_unknown_food_category_is_invalid` |
| FG-IOT-044 | Storage | Future insertion date | Insertion date after today | Check Food with invalid insertion date reason | Check Food asserted | PASS | `test_future_inserted_at_is_invalid` |
| FG-IOT-045 | Storage | Malformed insertion date | Invalid date string | Check Food with invalid insertion date reason | Not tested | NOT TESTED | Pending; existing invalid-date engine test covers expiry, not insertion date |
| FG-IOT-046 | Expiry | Missing expiry | `expiry_date = None` | Expiry rule contributes Fresh | Covered as part of normal/optional food inputs; no dedicated assertion for missing expiry only | NOT TESTED | Pending isolated expiry-missing case |
| FG-IOT-047 | Expiry | Expiry today | Expiry offset 0 days | Use Soon | Use Soon asserted | PASS | `test_expiry_date_boundaries`; `test_expiry_flows_from_food_record` |
| FG-IOT-048 | Expiry | Expiry tomorrow | Expiry offset 1 day | Use Soon | Use Soon asserted | PASS | `test_expiry_date_boundaries`; `test_expiry_flows_from_food_record` |
| FG-IOT-049 | Expiry | Expiry after tomorrow | Expiry offset 2 days | Fresh | Fresh asserted | PASS | `test_expiry_date_boundaries` |
| FG-IOT-050 | Expiry | Expiry yesterday | Expiry offset -1 day | Check Food | Check Food asserted | PASS | `test_expiry_date_boundaries`; `test_expiry_flows_from_food_record` |
| FG-IOT-051 | Expiry | Invalid expiry date | Unsupported date string | Check Food with invalid expiry reason | Check Food asserted | PASS | `test_invalid_expiry_date_is_invalid` |
| FG-IOT-052 | Aggregation | All rules Fresh | Normal sensor values; no triggering food rule | Fresh / Normal | Fresh asserted | PASS | `test_freshness_all_sensors_normal`; `test_optional_food_data_does_not_change_normal_environment` |
| FG-IOT-053 | Aggregation | One Use Soon, all remaining rules Fresh | Temperature 10 °C; other rules normal | Use Soon | Use Soon asserted | PASS | `test_max_severity_across_rules` |
| FG-IOT-054 | Aggregation | One Check Food, remaining rules Fresh | Temperature above 12 °C | Check Food | Check Food asserted | PASS | `test_max_severity_across_rules`; `test_tc11_fresh_food_and_check_food_temperature` |
| FG-IOT-055 | Aggregation | Use Soon plus Check Food | Use Soon temperature plus past expiry | Check Food | Check Food asserted | PASS | `test_max_severity_across_rules` |
| FG-IOT-056 | Aggregation / reasons | Multiple rules warn together | Fault sensors, long-open door, old food, past expiry | Maximum severity retained and all triggered reasons concatenated | All six rule reasons asserted present | PASS | `test_all_active_rules_reasons_are_preserved` |

## 6. Food Integration Tests

| Test ID | Category | Scenario | Input / Setup | Expected Result | Actual Result | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FG-IOT-057 | Food API | Create valid food | Required fields and valid dates | HTTP 201; food record returned | 201 and food fields asserted | PASS | `test_create_food_success`; `test_tc01_registered_food_and_normal_environment` |
| FG-IOT-058 | Food API | Missing required food field | Omit each required field in turn | HTTP 400 and missing field identified | Parameterized cases returned 400 | PASS | `test_create_food_requires_fields` |
| FG-IOT-059 | Food API | Invalid food date | Invalid `inserted_at`, `manufacture_date`, or `expiry_date` | HTTP 400 | Parameterized cases returned 400 | PASS | `test_create_food_rejects_invalid_dates` |
| FG-IOT-060 | Food API | Invalid/negative quantity | Non-number, negative, infinity, or boolean | HTTP 400 | Tested variants returned 400 | PASS | `test_create_food_rejects_invalid_quantity`; `test_create_food_rejects_boolean_quantity` |
| FG-IOT-061 | Food API | Duplicate food ID | Create same `food_id` twice | Second response HTTP 409 | 409 asserted | PASS | `test_duplicate_food_id_returns_conflict` |
| FG-IOT-062 | Food API | Get existing/non-existing food | Query registered and unknown IDs | Existing returns 200; unknown returns 404 | Both outcomes asserted | PASS | `test_get_existing_food`; `test_get_nonexistent_food_returns_404` |
| FG-IOT-063 | Food integration | Reading with valid food ID | Register food, submit linked reading | HTTP 201; category/storage/expiry affect computed freshness | Linked profile and storage/expiry status asserted | PASS | `test_reading_with_registered_food_uses_food_profile`; `test_storage_duration_flows_from_food_record`; `test_expiry_flows_from_food_record` |
| FG-IOT-064 | Food integration | Reading without food ID | Submit legacy reading payload | HTTP 201; sensor-only contract retained | HTTP 201 and freshness contract asserted | PASS | `test_reading_without_food_id_remains_supported`; `test_reading_without_food_id_keeps_response_contract` |
| FG-IOT-065 | Food integration | Unknown food ID cannot create reading | Submit unregistered ID and inspect history | HTTP 404; history count remains zero | 404 and no persisted reading asserted | PASS | `test_unknown_food_returns_404_without_saving_reading` |

## 7. API Robustness Tests

The current readings API requires `device_id`, `timestamp`, all three sensor fields, and `door_open`. Sensor fields may be JSON null; the engine then returns a sensor fault status. `open_duration_seconds` defaults to 0 when omitted and must otherwise be a non-negative integer at the API boundary. The Events endpoint requires non-empty string event/device/type fields and a parseable ISO datetime. Current history limit behavior is: default 20 for omitted or non-integer query values, HTTP 400 below 1, and cap at 100.

The applicable executed cases and evidence are FG-IOT-001 through FG-IOT-017 above. The following boundary combinations do not have a distinct assertion in the current tests:

| Test ID | Category | Scenario | Input / Setup | Expected Result | Actual Result | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FG-IOT-066 | Readings API | Missing `door_open` field | Omit `door_open` from otherwise valid JSON | HTTP 400 with missing-field information | Not tested as a distinct case | NOT TESTED | Pending |
| FG-IOT-067 | Readings API | Valid reading with omitted duration | Omit optional `open_duration_seconds` | Accepted with duration default 0 | Not tested as a distinct case | NOT TESTED | Pending |
| FG-IOT-068 | Readings API | Missing temperature field | Omit `temperature_c` from otherwise valid JSON | HTTP 400 with missing-field information | Not tested as a distinct case | NOT TESTED | Pending |
| FG-IOT-069 | Readings API | Missing humidity field | Omit `humidity_pct` from otherwise valid JSON | HTTP 400 with missing-field information | Not tested as a distinct case | NOT TESTED | Pending |
| FG-IOT-070 | Events API | Missing event type field | Omit `event_type` from otherwise valid event JSON | HTTP 400 with missing-field information | Not tested as a distinct case; invalid null event type is tested | NOT TESTED | Pending; `test_events_reject_missing_or_invalid_fields` tests `event_type = null` |
| FG-IOT-071 | Events API | Missing device ID field | Omit `device_id` from otherwise valid event JSON | HTTP 400 with missing-field information | Not tested as a distinct case | NOT TESTED | Pending |

## 8. Dashboard Integration Tests

The Dashboard code calls latest reading, linked food, and history APIs. It renders missing numeric readings as `Data Unavailable`, shows `No food linked` when the reading has no `food_id`, shows `Food information unavailable` on a food fetch failure, and refreshes every 2000 ms. These are code-inspected expected results, not executed UI tests; actual results remain Not tested. No Dashboard test function or screenshot/log artifact was found in the current project during this review, so prior verbal/manual context is not used to mark these cases PASS.

| Test ID | Category | Scenario | Input / Setup | Expected Result | Actual Result | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FG-IOT-072 | Dashboard | Valid latest reading and temperature | Backend returns latest reading | Temperature value displayed | Not tested in browser | NOT TESTED | Pending screenshot/browser run |
| FG-IOT-073 | Dashboard | Humidity, gas, and door display | Backend returns valid sensor values | Values and OPEN/CLOSED state displayed | Not tested in browser | NOT TESTED | Pending screenshot/browser run |
| FG-IOT-074 | Dashboard | Freshness status and reason | Latest response includes `freshness.status` and `.reason` | Status and reason displayed | Not tested in browser | NOT TESTED | Pending screenshot/browser run |
| FG-IOT-075 | Dashboard | Missing sensor value | Latest response contains a null sensor value | Corresponding field displays `Data Unavailable` | Not tested in browser | NOT TESTED | Pending screenshot/browser run |
| FG-IOT-076 | Dashboard | No food linked | Latest reading has no `food_id` | `No food linked` displayed | Not tested in browser | NOT TESTED | Pending screenshot/browser run |
| FG-IOT-077 | Dashboard | Food linked | Latest reading has registered `food_id` | Food metadata displayed | Not tested in browser | NOT TESTED | Pending screenshot/browser run |
| FG-IOT-078 | Dashboard | Food API failure | Food lookup fails or returns error | `Food information unavailable` displayed | Not tested in browser | NOT TESTED | Pending screenshot/browser run |
| FG-IOT-079 | Dashboard | History and auto refresh | History endpoint responds; observe refresh interval | History displayed; dashboard refresh initiated every 2 seconds | Not tested in browser | NOT TESTED | Pending browser run/screenshot |
| FG-IOT-080 | Dashboard | No latest reading | Latest endpoint returns `NO_DATA`/404 | No-data message shown; no array indexing crash | Not tested in browser | NOT TESTED | Pending screenshot/browser run |

## 9. Event / Reliability Tests

SQLite reading/food/event persistence and duplicate event protection are implemented. The simulator catches `requests.RequestException` and prints a connection error, but it does not queue readings or retry them. No firmware offline buffering, retry queue, or hardware synchronization implementation was found.

| Test ID | Category | Scenario | Input / Setup | Expected Result | Actual Result | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FG-IOT-081 | Events | Event create and idempotent duplicate | Create one valid ID twice | One create; repeated ID returns duplicate response without duplicate persistence | First 201; second 200 with duplicate flag | PASS | `test_duplicate_event_remains_idempotent` |
| FG-IOT-082 | Simulator | Normal local sending | Run simulator with backend available | POST readings to `/api/v1/readings` at configured loop timing | Not tested end-to-end | NOT TESTED | Pending simulator/backend run evidence |
| FG-IOT-083 | Reliability | Network unavailable | Stop/unreach backend while simulator is sending | Current simulator prints connection error; readings are not buffered for later sync | Not tested by automated test; no queue/retry code found | NOT IMPLEMENTED | `firmware/simulator.py` catches request exception and continues; no buffer/retry |
| FG-IOT-084 | Reliability | Sync without duplicates after outage | Restore network after outage | Requires offline queue/replay behavior | Not available in current simulator/prototype | NOT IMPLEMENTED | No offline queue/replay implementation found |
| FG-IOT-085 | Database | Legacy readings schema migration | Initialize an older readings table | Add new columns without losing existing row | Migration and row retention asserted | PASS | `test_init_db_migrates_existing_readings_without_data_loss` |

## 10. Known Not-Implemented Tests

| Feature | Current State | Testability | Note |
| --- | --- | --- | --- |
| Humidity quality threshold | Not implemented yet | Not testable in current prototype | Engine validates availability/finite numeric value only; finite values return severity 0. |
| Calibrated gas threshold / ppm | Not implemented yet | Not testable in current prototype | Engine checks finite `gas_raw` only; no calibration/ppm conversion is present. |
| Real sensor integration | Not implemented in inspected project files | Not testable in current prototype | `firmware/simulator.py` generates constants; no sensor driver/ESP32 firmware was found. |
| Auto Test 3 States (5/10/15 °C) | Not implemented in simulator | Not testable in current prototype | Simulator temperature is fixed at 5 °C; no three-state mode was found. |
| Physical Green/Yellow/Red LED output | Not implemented in inspected project files | Not testable in current prototype | No LED pins or output logic found. Do not infer LED behavior from freshness status. |
| Offline buffering and retry | Not implemented in simulator | Not testable in current prototype | Failed HTTP request is printed; there is no persistent queue/retry mechanism. |
| Remote notifications | Not implemented in inspected API/dashboard/firmware | Not testable in current prototype | No notification service or endpoint found. |
| QR workflow | Not implemented in inspected API/dashboard/firmware | Not testable in current prototype | No QR workflow found. |

## 11. Test Evidence Checklist

- [x] Backend pytest result — `python -m pytest -q` could not start because pytest is absent from the default Python environment; `\.venv\Scripts\python.exe -m pytest -q` from `backend/` completed with 130 passed.
- [ ] API request/response screenshot — Pending.
- [ ] Dashboard screenshot — Pending.
- [ ] ESP32 serial monitor — Pending; no real ESP32 firmware evidence found.
- [ ] LED Green evidence — Pending; LED behavior not implemented in inspected files.
- [ ] LED Yellow evidence — Pending; LED behavior not implemented in inspected files.
- [ ] LED Red evidence — Pending; LED behavior not implemented in inspected files.
- [x] Sensor fault evidence — automated engine/API assertions: `test_temperature_sensor_fault`, `test_humidity_sensor_fault`, `test_gas_sensor_fault`, `test_readings_accept_null_sensor_values_without_marking_them_fresh`.
- [x] Door timeout evidence — automated boundary assertions at 29/30/31 seconds: `test_door_timeout_boundary`.
- [x] Food expiry evidence — automated boundary assertions: `test_expiry_date_boundaries`, `test_expiry_flows_from_food_record`.
- [x] Food storage duration evidence — automated cases for tested category/day combinations: `test_storage_duration_boundaries`, `test_storage_duration_flows_from_food_record` (does not cover every category boundary requested in this matrix).
- [x] Database evidence — temporary SQLite API tests and migration assertion: `test_init_db_migrates_existing_readings_without_data_loss`.
- [x] Event idempotency evidence — `test_duplicate_event_remains_idempotent`.

Checked items above refer to automated test output, not hardware or screenshot evidence. LED and serial-monitor evidence remain pending and are not implied by backend test results.

## 12. Test Summary

Counts below are for the explicit `FG-IOT-*` test IDs in Sections 4–9. A row is one matrix case; grouped boundary inputs within a row count as one case. The latest recorded test run is the existing backend suite, not a new hardware or Dashboard run. `NOT IMPLEMENTED` rows describe missing functionality and are not counted as executed failures.

| Area | Test Cases | Passed | Failed | Not Tested | Not Implemented | Blocked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IoT / API / persistence (FG-IOT-001–018) | 18 | 18 | 0 | 0 | 0 | 0 |
| Freshness rules (FG-IOT-019–056) | 38 | 29 | 0 | 9 | 0 | 0 |
| Food API/integration (FG-IOT-057–065) | 9 | 9 | 0 | 0 | 0 | 0 |
| API edge cases (FG-IOT-066–071) | 6 | 0 | 0 | 6 | 0 | 0 |
| Dashboard (FG-IOT-072–080) | 9 | 0 | 0 | 9 | 0 | 0 |
| Events / reliability / database (FG-IOT-081–085) | 5 | 2 | 0 | 1 | 2 | 0 |
| **Total** | **85** | **58** | **0** | **25** | **2** | **0** |

The total counts individual matrix rows, not the number of pytest parameter combinations. SRS-style requests for LED states, real sensors, offline retry, remote notification, and QR workflow are separately identified as not implemented in Section 10 and are not assigned fictional PASS results.
