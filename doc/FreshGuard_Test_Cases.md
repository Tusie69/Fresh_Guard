# FRESHGUARD TEST CASE DOCUMENT

## 1. Document Information

| Field | Value |
|---|---|
| Project | FreshGuard prototype — ESP32 → Flask Backend → Freshness Engine → SQLite → API response → LED / Dashboard |
| Version / commit | main / 6e17f61 — feat: add cross-system freshness and firmware support |
| Audit date | 2026-09-27, Asia/Saigon (UTC+07:00); pytest hoàn tất trước lần ghi nhận môi trường 18:21:58+07:00 |
| Test environment | Windows / PowerShell; Python 3.12.10; pytest 9.1.1; Flask 3.1.3; requests 2.34.2; SQLite 3.49.1 |
| Interpreter | backend/.venv/Scripts/python.exe |
| Result summary | 424 collected/executed; 424 passed; 0 failed; 0 skipped; 0 errors; 16.30s |
| Catalog counting | 212 automated test-function records; 424 expanded pytest invocations. Không đếm từng assertion thành một testcase. |
| Authoring scope | Chỉ tạo doc/FreshGuard_Test_Cases.md; không sửa source, test, DB hoặc tài liệu khác; không commit/push. |

Test command chạy **đúng từ project root**:

~~~powershell
.\backend\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -o pythonpath=C:/Users/TuNgu/freshguard/backend backend/tests firmware/tests -q
~~~

Observed terminal result:

~~~text
424 passed in 16.30s
~~~

Collection-only dùng đối chiếu node IDs/parametrization, không tính như một lần PASS bổ sung. Không tạo JUnit/raw-log artifact; kết quả terminal được ghi lại ở đây. Tests dùng SQLite/JSONL tạm theo fixtures, không DB vận hành. -B và no:cacheprovider tránh ghi bytecode/cache.

DB active: backend/freshguard.db, kiểm tra read-only. SHA-256 trước/sau test:
d4abade0440e256f16ad5aad4f8fabac3cbefa004c5711d3ca255f2b488ba66d.

## 2. Test Scope

Phạm vi: backend automated tests, API canonical/compact, freshness, stateful processing, database transaction/migration, simulator, firmware static validation, hardware manual validation và dashboard manual validation. Đã inventory toàn bộ 14 file test; tests/ ở root không chứa test source.

Nguồn sự thật là implementation và assertions hiện tại. Tài liệu cũ chỉ dùng phát hiện mismatch. Các rule là **derived implementation requirements**, không phải requirement mới hoặc chứng nhận an toàn thực phẩm.

Backend là source of truth cho freshness, gas anomaly, temperature exposure, sensor-fault transitions và food/storage/expiry. ESP32 chỉ READ → SEND → RECEIVE STATUS → ACT. isfinite/ADC validity dùng gửi null và diagnostic, không phải quyết định business freshness. Door transition producer hiện thuộc simulator; .ino chưa có door sensor thật.

### Evidence levels

| Level | Meaning | Cách ghi |
|---|---|---|
| A — Automated Verified | Existing pytest thực thi và PASS | Automated / PASS, chỉ với input và assertions hiện có |
| B — Static Code Verified | Code được đọc và xác nhận tồn tại | Không nâng thành hardware/browser PASS; firmware cases Manual / NOT VALIDATED execution |
| C — Manual Verified | Có ảnh/log/đo đạc thực tế truy vết được | **Không có ca Level C trong audit này** |
| D — Not Yet Validated | Scenario chưa thực thi hoặc thiếu evidence | Manual / NOT VALIDATED |

Manual count bao gồm planned software/hardware/browser scenarios và firmware static checklist. Bằng chứng source trong Actual không phải manual execution result. Các bước manual chỉ là kế hoạch cho môi trường test riêng; chưa chạy hoặc chỉnh configuration trong audit.

### Implementation baseline and rule IDs

| Rule ID | Area | Current behavior | Implementation |
|---|---|---|---|
| R-API | API Input Validation | Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. | [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| R-IDEMP | Reading Idempotency | Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. | [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| R-FRESH | Freshness Severity Aggregation | Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. | [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| R-TEMP | Temperature Exposure | Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. | [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| R-GAS | Gas Baseline & Anomaly | 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. | [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| R-SENSOR | Sensor Fault | Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. | [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| R-HUM | Humidity | VEGETABLE/FRUIT <80% hoặc >95% chỉ thêm warning, không tăng severity; 80 và 95 không warning. Category khác không warning theo ngưỡng. Null/nonfinite là rule validity riêng. | [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| R-DOOR | Door Freshness & Producer | Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. | [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| R-STORAGE | Storage Duration | MEAT=3, DAIRY=14, VEGETABLE=7, FRUIT=14, COOKED_FOOD=4 ngày. Tuổi <max-1 Fresh; max-1..max Use Soon; >max Check Food. Dùng server date.today(), không reading timestamp. | [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| R-EXPIRY | Expiry Date | Expiry hôm nay/ngày mai Use Soon, đã qua Check Food, xa hơn không tăng severity; dùng server date. Không expiry thì không penalty. | [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| R-FOOD | Food Registration / QR | FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. | [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| R-EVENT | Events | Event ID unique toàn bảng; mới 201, lặp ID 200 duplicate (không so payload). Backend phát gas/exposure/sensor transitions, simulator phát door. Payload lưu str(dict), không mặc định JSON chuẩn. | [backend/app/routes/events.py](../backend/app/routes/events.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| R-DB | Database Transaction / Migration | Reading, state update và backend event nằm cùng transaction; event insert failure rollback. Migration thêm columns/index, giữ legacy; init không tự chạy từ run.py. Schema events thực tế khác schema khởi tạo mới. | [backend/app/init_db.py](../backend/app/init_db.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| R-GET | GET API / Snapshot | Latest global ORDER BY id DESC, không theo device; history mặc định 20/max100. Snapshot được lưu và trả lại; chỉ legacy freshness_status NULL mới fallback; không tự aging snapshot. | [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| R-SIM | Simulator Reliability / Polling / AUTO_TEST | Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. | [firmware/simulator.py](../firmware/simulator.py) |
| R-FW | Firmware ESP32 Static Validation | READ -> SEND -> RECEIVE STATUS -> ACT. DHT4, DS3231 SDA21/SCL22, MQ34, LEDs23/25/26. Canonical payload + UUID v4 + ISO +07:00; sensor null. ENABLE_BACKEND=false, door placeholder, FOOD_ID rỗng. | [firmware/ESP32-WROOM-32.ino](../firmware/ESP32-WROOM-32.ino) |
| R-DASH | Dashboard Manual Validation | GET latest/history/food mỗi 2s, freshness từ backend, null -> Data Unavailable; không có fourth business status. Base URL loopback; chưa browser validation. | [dashboard/index.html](../dashboard/index.html) |
| R-HW | Physical Hardware End-to-End | Đo và gửi thật -> backend/SQLite/freshness -> response -> LED thật. Chưa compile/upload hoặc có physical evidence; không suy diễn hardware PASS từ pytest. | [firmware/ESP32-WROOM-32.ino](../firmware/ESP32-WROOM-32.ino); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |

### Database baseline

- sensor_readings: id INTEGER PK AUTOINCREMENT; device_id/timestamp TEXT NOT NULL; temperature_c/humidity_pct REAL nullable; gas_raw INTEGER nullable; door_open INTEGER NOT NULL; created_at TEXT DEFAULT CURRENT_TIMESTAMP; open_duration_seconds INTEGER NOT NULL DEFAULT 0; food_id/device_reading_id/freshness_status/freshness_reason/freshness_evaluated_at TEXT nullable; gas_anomaly_active INTEGER NOT NULL DEFAULT 0.
- Unique index (device_id, device_reading_id); DB legacy cho phép UUID NULL nhưng API bắt buộc. food_id không có FK; route kiểm tra tồn tại.
- gas_anomaly_state/temperature_exposure_state theo (device_id,food_id), no-food dùng empty string. sensor_fault_state unique (device_id,COALESCE(food_id,''),sensor_name).
- events **DB thực tế**: id, event_id UNIQUE NOT NULL, device_id, timestamp, event_type, payload, sync_status NOT NULL DEFAULT 'synced', created_at. Không door_open/open_duration_seconds.
- events **init_db mới**: có door_open/open_duration_seconds, không sync_status. Route dùng PRAGMA để tương thích. Không suy diễn có sync worker từ tên cột.
- Active DB: 4541 readings, 3 events, 0 foods, ba state tables đều rỗng khi kiểm tra. Ba reading mới nhất đã kiểm tra là legacy thiếu UUID/snapshot; không coi đây là bằng chứng luồng hardware/stateful đã hoạt động.
- GET snapshot không tự aging; legacy fallback không tái dựng historical temperature exposure.
- Firmware ENABLE_BACKEND=false, FOOD_ID=""; chưa thể tuyên bố end-to-end chạy với cấu hình nguyên trạng.

### Reproducibility conventions

Mỗi automated record là một function, có số expanded invocations, parameter sets thực tế, assertions và scenario source nguyên bản. Symbols response/result/expected_status được giải nghĩa trong scenario; không phải literal output độc lập. Assertion trong loop/branch/mock chỉ áp dụng khi control flow đó chạy.

Fixtures client/api_client/temperature_client/sensor_client/system dùng tmp_path SQLite; gas_db dùng :memory:. Simulator dùng tmp_path JSONL và mocked HTTP; không phải WiFi/live server evidence. UUID và date.today/timedelta là giá trị động. Phụ lục fixture/helper cuối tài liệu cung cấp đầy đủ defaults/setup hiện có.

## 3. Test Case Summary

Bảng đếm **document records**, không cộng trùng parameter variants/assertions. Passed = automated function records có toàn bộ variants PASS; 424 là tổng pytest invocations.

| Test Area | Automated | Manual | Passed | Not Validated | Total |
|---|---:|---:|---:|---:|---:|
| API — API Input Validation | 30 | 3 | 30 | 3 | 33 |
| IDEMP — Reading Idempotency | 15 | 0 | 15 | 0 | 15 |
| FRESH — Freshness Severity Aggregation | 21 | 0 | 21 | 0 | 21 |
| TEMP — Temperature Exposure | 17 | 2 | 17 | 2 | 19 |
| GAS — Gas Baseline & Anomaly | 19 | 2 | 19 | 2 | 21 |
| SENSOR — Sensor Fault | 12 | 1 | 12 | 1 | 13 |
| HUM — Humidity | 3 | 2 | 3 | 2 | 5 |
| DOOR — Door Freshness & Producer | 10 | 1 | 10 | 1 | 11 |
| STORAGE — Storage Duration | 4 | 1 | 4 | 1 | 5 |
| EXPIRY — Expiry Date | 3 | 1 | 3 | 1 | 4 |
| FOOD — Food Registration / QR | 24 | 1 | 24 | 1 | 25 |
| EVENT — Events | 6 | 1 | 6 | 1 | 7 |
| DB — Database Transaction / Migration | 6 | 1 | 6 | 1 | 7 |
| GET — GET API / Snapshot | 7 | 4 | 7 | 4 | 11 |
| SIM — Simulator Reliability / Polling / AUTO_TEST | 35 | 3 | 35 | 3 | 38 |
| FW — Firmware ESP32 Static Validation | 0 | 9 | 0 | 9 | 9 |
| DASH — Dashboard Manual Validation | 0 | 7 | 0 | 7 | 7 |
| HW — Physical Hardware End-to-End | 0 | 10 | 0 | 10 | 10 |
| **TOTAL** | **212** | **49** | **212** | **49** | **261** |

| Test file | Function records | Expanded pytest cases | Result |
|---|---:|---:|---|
| [backend/tests/test_api_hardening.py](../backend/tests/test_api_hardening.py) | 32 | 72 | PASS — Level A |
| [backend/tests/test_cross_system_integration.py](../backend/tests/test_cross_system_integration.py) | 9 | 13 | PASS — Level A |
| [backend/tests/test_food_api.py](../backend/tests/test_food_api.py) | 24 | 35 | PASS — Level A |
| [backend/tests/test_food_freshness_integration.py](../backend/tests/test_food_freshness_integration.py) | 11 | 17 | PASS — Level A |
| [backend/tests/test_freshness.py](../backend/tests/test_freshness.py) | 35 | 100 | PASS — Level A |
| [backend/tests/test_gas_anomaly.py](../backend/tests/test_gas_anomaly.py) | 22 | 41 | PASS — Level A |
| [backend/tests/test_reading_protocol.py](../backend/tests/test_reading_protocol.py) | 17 | 42 | PASS — Level A |
| [backend/tests/test_sensor_fault.py](../backend/tests/test_sensor_fault.py) | 10 | 30 | PASS — Level A |
| [backend/tests/test_temperature_exposure.py](../backend/tests/test_temperature_exposure.py) | 13 | 17 | PASS — Level A |
| [firmware/tests/test_simulator_auto_test.py](../firmware/tests/test_simulator_auto_test.py) | 2 | 2 | PASS — Level A |
| [firmware/tests/test_simulator_compact.py](../firmware/tests/test_simulator_compact.py) | 15 | 22 | PASS — Level A |
| [firmware/tests/test_simulator_cross_system.py](../firmware/tests/test_simulator_cross_system.py) | 1 | 1 | PASS — Level A |
| [firmware/tests/test_simulator_events.py](../firmware/tests/test_simulator_events.py) | 14 | 17 | PASS — Level A |
| [firmware/tests/test_simulator_freshness_poll.py](../firmware/tests/test_simulator_freshness_poll.py) | 7 | 15 | PASS — Level A |

Manual breakdown: 9 firmware static-review records (Level B, execution chưa validated); 40 remaining manual scenarios (Level D); Level C = 0.

## 4. Detailed Test Cases

Một automated testcase tương ứng một function; Input liệt kê các tham số đã collect. Scenario có thể mở rộng để xem đầy đủ calls/loops/conditional assertions. Không tạo hoặc sửa automation.

### API — API Input Validation

Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format.

<a id="tc-api-001"></a>

#### TC-API-001 — Readings reject empty malformed and non object json

| Field | Value |
|---|---|
| Test Case ID | TC-API-001 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Readings reject empty malformed and non object json. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | 1. <code>kwargs={&#x27;data&#x27;: &#x27;&#x27;, &#x27;content_type&#x27;: &#x27;application/json&#x27;}</code><br>2. <code>kwargs={&#x27;data&#x27;: &#x27;{&#x27;, &#x27;content_type&#x27;: &#x27;application/json&#x27;}</code><br>3. <code>kwargs={&#x27;json&#x27;: []}</code><br>4. <code>kwargs={&#x27;json&#x27;: None}</code><br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/readings&#x27;, **kwargs)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_JSON&#x27;</code><br><code>response.json[&#x27;message&#x27;]</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_readings_reject_empty_malformed_and_non_object_json</code> — [source L85](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "", "content_type": "application/json"},
        {"data": "{", "content_type": "application/json"},
        {"json": []},
        {"json": None},
    ],
)
def test_readings_reject_empty_malformed_and_non_object_json(client, kwargs):
    response = client.post("/api/v1/readings", **kwargs)
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_JSON"
    assert response.json["message"]
~~~

</details>

<a id="tc-api-002"></a>

#### TC-API-002 — Readings reject invalid fields

| Field | Value |
|---|---|
| Test Case ID | TC-API-002 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Readings reject invalid fields. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | 1. <code>field=&#x27;device_id&#x27;; value=&#x27;  &#x27;; error=&#x27;INVALID_DEVICE_ID&#x27;</code><br>2. <code>field=&#x27;device_id&#x27;; value=123; error=&#x27;INVALID_DEVICE_ID&#x27;</code><br>3. <code>field=&#x27;timestamp&#x27;; value=&#x27;not-a-date&#x27;; error=&#x27;INVALID_TIMESTAMP&#x27;</code><br>4. <code>field=&#x27;temperature_c&#x27;; value=&#x27;cold&#x27;; error=&#x27;INVALID_SENSOR_VALUE&#x27;</code><br>5. <code>field=&#x27;humidity_pct&#x27;; value=nan; error=&#x27;INVALID_SENSOR_VALUE&#x27;</code><br>6. <code>field=&#x27;gas_raw&#x27;; value=inf; error=&#x27;INVALID_SENSOR_VALUE&#x27;</code><br>7. <code>field=&#x27;door_open&#x27;; value=&#x27;false&#x27;; error=&#x27;INVALID_DOOR_STATE&#x27;</code><br>8. <code>field=&#x27;door_open&#x27;; value=None; error=&#x27;INVALID_DOOR_STATE&#x27;</code><br>9. <code>field=&#x27;open_duration_seconds&#x27;; value=-1; error=&#x27;INVALID_OPEN_DURATION&#x27;</code><br>10. <code>field=&#x27;open_duration_seconds&#x27;; value=&#x27;10&#x27;; error=&#x27;INVALID_OPEN_DURATION&#x27;</code><br>11. <code>field=&#x27;open_duration_seconds&#x27;; value=None; error=&#x27;INVALID_OPEN_DURATION&#x27;</code><br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(**{field: value}))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == error</code> |
| Actual Result | Level A — 11/11 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_readings_reject_invalid_fields</code> — [source L108](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("device_id", "  ", "INVALID_DEVICE_ID"),
        ("device_id", 123, "INVALID_DEVICE_ID"),
        ("timestamp", "not-a-date", "INVALID_TIMESTAMP"),
        ("temperature_c", "cold", "INVALID_SENSOR_VALUE"),
        ("humidity_pct", float("nan"), "INVALID_SENSOR_VALUE"),
        ("gas_raw", float("inf"), "INVALID_SENSOR_VALUE"),
        ("door_open", "false", "INVALID_DOOR_STATE"),
        ("door_open", None, "INVALID_DOOR_STATE"),
        ("open_duration_seconds", -1, "INVALID_OPEN_DURATION"),
        ("open_duration_seconds", "10", "INVALID_OPEN_DURATION"),
        ("open_duration_seconds", None, "INVALID_OPEN_DURATION"),
    ],
)
def test_readings_reject_invalid_fields(client, field, value, error):
    response = client.post(
        "/api/v1/readings", json=reading_payload(**{field: value})
    )
    assert response.status_code == 400
    assert response.json["error"] == error
~~~

</details>

<a id="tc-api-003"></a>

#### TC-API-003 — Readings accept null sensor values without marking them fresh

| Field | Value |
|---|---|
| Test Case ID | TC-API-003 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Readings accept null sensor values without marking them fresh. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(temperature_c=None, humidity_pct=None, gas_raw=None))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_readings_accept_null_sensor_values_without_marking_them_fresh</code> — [source L116](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_readings_accept_null_sensor_values_without_marking_them_fresh(client):
    response = client.post(
        "/api/v1/readings",
        json=reading_payload(temperature_c=None, humidity_pct=None, gas_raw=None),
    )
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Check Food"
~~~

</details>

<a id="tc-api-004"></a>

#### TC-API-004 — Unknown food does not create reading

| Field | Value |
|---|---|
| Test Case ID | TC-API-004 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Unknown food does not create reading. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(food_id=&#x27;missing-food&#x27;))</code><br><code>history = client.get(&#x27;/api/v1/readings&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 404</code><br><code>response.json[&#x27;error&#x27;] == &#x27;FOOD_NOT_FOUND&#x27;</code><br><code>history.json[&#x27;count&#x27;] == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_unknown_food_does_not_create_reading</code> — [source L125](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_unknown_food_does_not_create_reading(client):
    response = client.post(
        "/api/v1/readings", json=reading_payload(food_id="missing-food")
    )
    history = client.get("/api/v1/readings")
    assert response.status_code == 404
    assert response.json["error"] == "FOOD_NOT_FOUND"
    assert history.json["count"] == 0
~~~

</details>

<a id="tc-api-005"></a>

#### TC-API-005 — Readings reject missing required fields

| Field | Value |
|---|---|
| Test Case ID | TC-API-005 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Readings reject missing required fields. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = reading_payload()</code><br><code>response = client.post(&#x27;/api/v1/readings&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>&#x27;gas_raw&#x27; in response.json[&#x27;fields&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_readings_reject_missing_required_fields</code> — [source L135](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_readings_reject_missing_required_fields(client):
    payload = reading_payload()
    del payload["gas_raw"]
    response = client.post("/api/v1/readings", json=payload)
    assert response.status_code == 400
    assert "gas_raw" in response.json["fields"]
~~~

</details>

<a id="tc-api-006"></a>

#### TC-API-006 — Compact reading create returns canonical response

| Field | Value |
|---|---|
| Test Case ID | TC-API-006 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Compact reading create returns canonical response. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = compact_reading_payload(od=0, f=None)</code><br><code>response = client.post(&#x27;/api/v1/readings&#x27;, json=payload)</code><br><code>row = _stored_reading(payload[&#x27;d&#x27;], payload[&#x27;id&#x27;])</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;success&#x27;] is True</code><br><code>response.json[&#x27;duplicate&#x27;] is False</code><br><code>response.json[&#x27;device_reading_id&#x27;] == payload[&#x27;id&#x27;]</code><br><code>response.json[&#x27;reading_id&#x27;] == 1</code><br><code>set(response.json[&#x27;freshness&#x27;]) == {&#x27;status&#x27;, &#x27;reason&#x27;}</code><br><code>_reading_count() == 1</code><br><code>row[&#x27;timestamp&#x27;] == &#x27;2024-09-25T15:30:00+07:00&#x27;</code><br><code>row[&#x27;door_open&#x27;] == 0</code><br><code>row[&#x27;temperature_c&#x27;] == payload[&#x27;tc&#x27;]</code><br><code>row[&#x27;humidity_pct&#x27;] == payload[&#x27;h&#x27;]</code><br><code>row[&#x27;gas_raw&#x27;] == payload[&#x27;g&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_compact_reading_create_returns_canonical_response</code> — [source L143](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_compact_reading_create_returns_canonical_response(client):
    payload = compact_reading_payload(od=0, f=None)

    response = client.post("/api/v1/readings", json=payload)

    assert response.status_code == 201
    assert response.json["success"] is True
    assert response.json["duplicate"] is False
    assert response.json["device_reading_id"] == payload["id"]
    assert response.json["reading_id"] == 1
    assert set(response.json["freshness"]) == {"status", "reason"}
    assert _reading_count() == 1
    row = _stored_reading(payload["d"], payload["id"])
    assert row["timestamp"] == "2024-09-25T15:30:00+07:00"
    assert row["door_open"] == 0
    assert row["temperature_c"] == payload["tc"]
    assert row["humidity_pct"] == payload["h"]
    assert row["gas_raw"] == payload["g"]
~~~

</details>

<a id="tc-api-007"></a>

#### TC-API-007 — Compact reading changed sensor conflicts without second row

| Field | Value |
|---|---|
| Test Case ID | TC-API-007 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Compact reading changed sensor conflicts without second row. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = compact_reading_payload()</code><br><code>conflict = client.post(&#x27;/api/v1/readings&#x27;, json={**payload, &#x27;tc&#x27;: payload[&#x27;tc&#x27;] + 1})</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>client.post(&#x27;/api/v1/readings&#x27;, json=payload).status_code == 201</code><br><code>conflict.status_code == 409</code><br><code>conflict.json[&#x27;error&#x27;] == &#x27;DEVICE_READING_ID_CONFLICT&#x27;</code><br><code>_reading_count() == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_compact_reading_changed_sensor_conflicts_without_second_row</code> — [source L176](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_compact_reading_changed_sensor_conflicts_without_second_row(client):
    payload = compact_reading_payload()
    assert client.post("/api/v1/readings", json=payload).status_code == 201

    conflict = client.post(
        "/api/v1/readings", json={**payload, "tc": payload["tc"] + 1}
    )

    assert conflict.status_code == 409
    assert conflict.json["error"] == "DEVICE_READING_ID_CONFLICT"
    assert _reading_count() == 1
~~~

</details>

<a id="tc-api-008"></a>

#### TC-API-008 — Compact reading unknown food keeps existing 404

| Field | Value |
|---|---|
| Test Case ID | TC-API-008 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Compact reading unknown food keeps existing 404. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/readings&#x27;, json=compact_reading_payload(f=&#x27;missing-food&#x27;))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 404</code><br><code>response.json[&#x27;error&#x27;] == &#x27;FOOD_NOT_FOUND&#x27;</code><br><code>_reading_count() == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_compact_reading_unknown_food_keeps_existing_404</code> — [source L189](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_compact_reading_unknown_food_keeps_existing_404(client):
    response = client.post(
        "/api/v1/readings", json=compact_reading_payload(f="missing-food")
    )

    assert response.status_code == 404
    assert response.json["error"] == "FOOD_NOT_FOUND"
    assert _reading_count() == 0
~~~

</details>

<a id="tc-api-009"></a>

#### TC-API-009 — Invalid compact payload returns 400

| Field | Value |
|---|---|
| Test Case ID | TC-API-009 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Invalid compact payload returns 400. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | 1. <code>change={&#x27;t&#x27;: &#x27;not-a-timestamp&#x27;}; message=&#x27;Unix timestamp in seconds&#x27;</code><br>2. <code>change={&#x27;o&#x27;: 2}; message=&#x27;integer 0 or 1&#x27;</code><br>3. <code>change={&#x27;o&#x27;: True}; message=&#x27;integer 0 or 1&#x27;</code><br>4. <code>change={&#x27;o&#x27;: False}; message=&#x27;integer 0 or 1&#x27;</code><br>5. <code>change={&#x27;o&#x27;: &#x27;1&#x27;}; message=&#x27;integer 0 or 1&#x27;</code><br>6. <code>change={&#x27;temperature_c&#x27;: 5.2}; message=&#x27;cannot be mixed&#x27;</code><br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/readings&#x27;, json={**compact_reading_payload(), **change})</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_COMPACT_PAYLOAD&#x27;</code><br><code>message in response.json[&#x27;message&#x27;]</code> |
| Actual Result | Level A — 6/6 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_invalid_compact_payload_returns_400</code> — [source L210](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"t": "not-a-timestamp"}, "Unix timestamp in seconds"),
        ({"o": 2}, "integer 0 or 1"),
        ({"o": True}, "integer 0 or 1"),
        ({"o": False}, "integer 0 or 1"),
        ({"o": "1"}, "integer 0 or 1"),
        ({"temperature_c": 5.2}, "cannot be mixed"),
    ],
)
def test_invalid_compact_payload_returns_400(client, change, message):
    response = client.post(
        "/api/v1/readings", json={**compact_reading_payload(), **change}
    )

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_COMPACT_PAYLOAD"
    assert message in response.json["message"]
~~~

</details>

<a id="tc-api-010"></a>

#### TC-API-010 — Compact and canonical equivalent readings have same freshness

| Field | Value |
|---|---|
| Test Case ID | TC-API-010 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Compact and canonical equivalent readings have same freshness. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>compact = compact_reading_payload()</code><br><code>canonical = decode_compact_reading(compact)</code><br><code>canonical[&#x27;device_reading_id&#x27;] = str(uuid.uuid4())</code><br><code>compact_response = client.post(&#x27;/api/v1/readings&#x27;, json=compact)</code><br><code>canonical_response = client.post(&#x27;/api/v1/readings&#x27;, json=canonical)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>compact_response.status_code == 201</code><br><code>canonical_response.status_code == 201</code><br><code>compact_response.json[&#x27;freshness&#x27;] == canonical_response.json[&#x27;freshness&#x27;]</code><br><code>_reading_count() == 2</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_compact_and_canonical_equivalent_readings_have_same_freshness</code> — [source L251](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_compact_and_canonical_equivalent_readings_have_same_freshness(client):
    compact = compact_reading_payload()
    canonical = decode_compact_reading(compact)
    canonical["device_reading_id"] = str(uuid.uuid4())

    compact_response = client.post("/api/v1/readings", json=compact)
    canonical_response = client.post("/api/v1/readings", json=canonical)

    assert compact_response.status_code == 201
    assert canonical_response.status_code == 201
    assert compact_response.json["freshness"] == canonical_response.json["freshness"]
    assert _reading_count() == 2
~~~

</details>

<a id="tc-api-011"></a>

#### TC-API-011 — Idemp 008 reading id is required

| Field | Value |
|---|---|
| Test Case ID | TC-API-011 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Idemp 008 reading id is required. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = reading_payload()</code><br><code>payload.pop(&#x27;device_reading_id&#x27;)</code><br><code>response = client.post(&#x27;/api/v1/readings&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;MISSING_FIELDS&#x27;</code><br><code>response.json[&#x27;fields&#x27;] == [&#x27;device_reading_id&#x27;]</code><br><code>_reading_count() == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_idemp_008_reading_id_is_required</code> — [source L417](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_idemp_008_reading_id_is_required(client):
    payload = reading_payload()
    payload.pop("device_reading_id")
    response = client.post("/api/v1/readings", json=payload)
    assert response.status_code == 400
    assert response.json["error"] == "MISSING_FIELDS"
    assert response.json["fields"] == ["device_reading_id"]
    assert _reading_count() == 0
~~~

</details>

<a id="tc-api-012"></a>

#### TC-API-012 — Idemp 009 rejects non v4 or malformed ids

| Field | Value |
|---|---|
| Test Case ID | TC-API-012 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Idemp 009 rejects non v4 or malformed ids. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | 1. <code>invalid_id=&#x27;random-id&#x27;</code><br>2. <code>invalid_id=&#x27;550e8400-e29b-11d4-a716-446655440000&#x27;</code><br>3. <code>invalid_id=&#x27;550e8400-e29b-41d4-a716-44665544000&#x27;</code><br>4. <code>invalid_id=None</code><br>5. <code>invalid_id=123</code><br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(device_reading_id=invalid_id))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_DEVICE_READING_ID&#x27;</code> |
| Actual Result | Level A — 5/5 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_idemp_009_rejects_non_v4_or_malformed_ids</code> — [source L437](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    "invalid_id",
    [
        "random-id",
        "550e8400-e29b-11d4-a716-446655440000",
        "550e8400-e29b-41d4-a716-44665544000",
        None,
        123,
    ],
)
def test_idemp_009_rejects_non_v4_or_malformed_ids(client, invalid_id):
    response = client.post(
        "/api/v1/readings", json=reading_payload(device_reading_id=invalid_id)
    )
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_DEVICE_READING_ID"
~~~

</details>

<a id="tc-api-013"></a>

#### TC-API-013 — Snapshot 004 missing reading id is rejected without row

| Field | Value |
|---|---|
| Test Case ID | TC-API-013 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Snapshot 004 missing reading id is rejected without row. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = reading_payload()</code><br><code>payload.pop(&#x27;device_reading_id&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>client.post(&#x27;/api/v1/readings&#x27;, json=payload).status_code == 400</code><br><code>_reading_count() == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_snapshot_004_missing_reading_id_is_rejected_without_row</code> — [source L457](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_snapshot_004_missing_reading_id_is_rejected_without_row(client):
    payload = reading_payload()
    payload.pop("device_reading_id")
    assert client.post("/api/v1/readings", json=payload).status_code == 400
    assert _reading_count() == 0
~~~

</details>

<a id="tc-api-014"></a>

#### TC-API-014 — Valid compact payload maps all fields

| Field | Value |
|---|---|
| Test Case ID | TC-API-014 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Valid compact payload maps all fields. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>decoded = decode_compact_reading(compact_payload)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>decoded == {&#x27;device_reading_id&#x27;: compact_payload[&#x27;id&#x27;], &#x27;device_id&#x27;: &#x27;esp32_01&#x27;, &#x27;timestamp&#x27;: &#x27;2024-09-25T15:30:00+07:00&#x27;, &#x27;temperature_c&#x27;: 5.2, &#x27;humidity_pct&#x27;: 61.5, &#x27;gas_raw&#x27;: 302, &#x27;door_open&#x27;: False, &#x27;open_duration_seconds&#x27;: 0, &#x27;food_id&#x27;: &#x27;FOOD001&#x27;}</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_valid_compact_payload_maps_all_fields</code> — [source L28](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_valid_compact_payload_maps_all_fields(compact_payload):
    decoded = decode_compact_reading(compact_payload)

    assert decoded == {
        "device_reading_id": compact_payload["id"],
        "device_id": "esp32_01",
        "timestamp": "2024-09-25T15:30:00+07:00",
        "temperature_c": 5.2,
        "humidity_pct": 61.5,
        "gas_raw": 302,
        "door_open": False,
        "open_duration_seconds": 0,
        "food_id": "FOOD001",
    }
~~~

</details>

<a id="tc-api-015"></a>

#### TC-API-015 — Reading id is preserved without regeneration

| Field | Value |
|---|---|
| Test Case ID | TC-API-015 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Reading id is preserved without regeneration. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>decode_compact_reading(compact_payload)[&#x27;device_reading_id&#x27;] == compact_payload[&#x27;id&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_reading_id_is_preserved_without_regeneration</code> — [source L44](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_reading_id_is_preserved_without_regeneration(compact_payload):
    assert decode_compact_reading(compact_payload)["device_reading_id"] == compact_payload["id"]
~~~

</details>

<a id="tc-api-016"></a>

#### TC-API-016 — Sensor and device fields are mapped without coercion

| Field | Value |
|---|---|
| Test Case ID | TC-API-016 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Sensor and device fields are mapped without coercion. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | 1. <code>compact_key=&#x27;d&#x27;; canonical_key=&#x27;device_id&#x27;; value=&#x27;device-42&#x27;</code><br>2. <code>compact_key=&#x27;tc&#x27;; canonical_key=&#x27;temperature_c&#x27;; value=8.25</code><br>3. <code>compact_key=&#x27;h&#x27;; canonical_key=&#x27;humidity_pct&#x27;; value=44.5</code><br>4. <code>compact_key=&#x27;g&#x27;; canonical_key=&#x27;gas_raw&#x27;; value=303</code><br>Setup/input cố định: <code>compact_payload[compact_key] = value</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>decode_compact_reading(compact_payload)[canonical_key] == value</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_sensor_and_device_fields_are_mapped_without_coercion</code> — [source L57](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("compact_key", "canonical_key", "value"),
    [
        ("d", "device_id", "device-42"),
        ("tc", "temperature_c", 8.25),
        ("h", "humidity_pct", 44.5),
        ("g", "gas_raw", 303),
    ],
)
def test_sensor_and_device_fields_are_mapped_without_coercion(
    compact_payload, compact_key, canonical_key, value
):
    compact_payload[compact_key] = value
    assert decode_compact_reading(compact_payload)[canonical_key] == value
~~~

</details>

<a id="tc-api-017"></a>

#### TC-API-017 — Door values map exactly

| Field | Value |
|---|---|
| Test Case ID | TC-API-017 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Door values map exactly. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | 1. <code>door_value=0; expected=False</code><br>2. <code>door_value=1; expected=True</code><br>Setup/input cố định: <code>compact_payload[&#x27;o&#x27;] = door_value</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>decode_compact_reading(compact_payload)[&#x27;door_open&#x27;] is expected</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_door_values_map_exactly</code> — [source L65](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(("door_value", "expected"), [(0, False), (1, True)])
def test_door_values_map_exactly(compact_payload, door_value, expected):
    compact_payload["o"] = door_value
    assert decode_compact_reading(compact_payload)["door_open"] is expected
~~~

</details>

<a id="tc-api-018"></a>

#### TC-API-018 — Invalid door values are rejected

| Field | Value |
|---|---|
| Test Case ID | TC-API-018 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Invalid door values are rejected. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | 1. <code>door_value=True</code><br>2. <code>door_value=False</code><br>3. <code>door_value=2</code><br>4. <code>door_value=-1</code><br>5. <code>door_value=&#x27;1&#x27;</code><br>6. <code>door_value=&#x27;0&#x27;</code><br>7. <code>door_value=None</code><br>8. <code>door_value=1.0</code><br>Setup/input cố định: <code>compact_payload[&#x27;o&#x27;] = door_value</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ReadingProtocolError, match=&#x27;integer 0 or 1&#x27;)</code> |
| Actual Result | Level A — 8/8 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_invalid_door_values_are_rejected</code> — [source L71](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("door_value", [True, False, 2, -1, "1", "0", None, 1.0])
def test_invalid_door_values_are_rejected(compact_payload, door_value):
    compact_payload["o"] = door_value
    with pytest.raises(ReadingProtocolError, match="integer 0 or 1"):
        decode_compact_reading(compact_payload)
~~~

</details>

<a id="tc-api-019"></a>

#### TC-API-019 — Unix timestamp seconds use sagion offset

| Field | Value |
|---|---|
| Test Case ID | TC-API-019 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Unix timestamp seconds use sagion offset. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>decode_compact_reading(compact_payload)[&#x27;timestamp&#x27;] == &#x27;2024-09-25T15:30:00+07:00&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_unix_timestamp_seconds_use_sagion_offset</code> — [source L77](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_unix_timestamp_seconds_use_sagion_offset(compact_payload):
    assert decode_compact_reading(compact_payload)["timestamp"] == (
        "2024-09-25T15:30:00+07:00"
    )
~~~

</details>

<a id="tc-api-020"></a>

#### TC-API-020 — Timestamp conversion is deterministic

| Field | Value |
|---|---|
| Test Case ID | TC-API-020 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Timestamp conversion is deterministic. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>first = decode_compact_reading(compact_payload)</code><br><code>second = decode_compact_reading(deepcopy(compact_payload))</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first[&#x27;timestamp&#x27;] == second[&#x27;timestamp&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_timestamp_conversion_is_deterministic</code> — [source L83](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_timestamp_conversion_is_deterministic(compact_payload):
    first = decode_compact_reading(compact_payload)
    second = decode_compact_reading(deepcopy(compact_payload))
    assert first["timestamp"] == second["timestamp"]
~~~

</details>

<a id="tc-api-021"></a>

#### TC-API-021 — Millisecond timestamp is rejected as out of range

| Field | Value |
|---|---|
| Test Case ID | TC-API-021 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Millisecond timestamp is rejected as out of range. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>compact_payload[&#x27;t&#x27;] = 1727253000000</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ReadingProtocolError, match=&#x27;supported timestamp range&#x27;)</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_millisecond_timestamp_is_rejected_as_out_of_range</code> — [source L89](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_millisecond_timestamp_is_rejected_as_out_of_range(compact_payload):
    compact_payload["t"] = 1727253000000
    with pytest.raises(ReadingProtocolError, match="supported timestamp range"):
        decode_compact_reading(compact_payload)
~~~

</details>

<a id="tc-api-022"></a>

#### TC-API-022 — Missing required compact field is rejected

| Field | Value |
|---|---|
| Test Case ID | TC-API-022 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Missing required compact field is rejected. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | 1. <code>missing=&#x27;id&#x27;</code><br>2. <code>missing=&#x27;d&#x27;</code><br>3. <code>missing=&#x27;t&#x27;</code><br>4. <code>missing=&#x27;tc&#x27;</code><br>5. <code>missing=&#x27;h&#x27;</code><br>6. <code>missing=&#x27;g&#x27;</code><br>7. <code>missing=&#x27;o&#x27;</code><br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ReadingProtocolError, match=missing)</code> |
| Actual Result | Level A — 7/7 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_missing_required_compact_field_is_rejected</code> — [source L96](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("missing", ["id", "d", "t", "tc", "h", "g", "o"])
def test_missing_required_compact_field_is_rejected(compact_payload, missing):
    del compact_payload[missing]
    with pytest.raises(ReadingProtocolError, match=missing):
        decode_compact_reading(compact_payload)
~~~

</details>

<a id="tc-api-023"></a>

#### TC-API-023 — Omitted duration defaults to zero

| Field | Value |
|---|---|
| Test Case ID | TC-API-023 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Omitted duration defaults to zero. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>decode_compact_reading(compact_payload)[&#x27;open_duration_seconds&#x27;] == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_omitted_duration_defaults_to_zero</code> — [source L102](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_omitted_duration_defaults_to_zero(compact_payload):
    del compact_payload["od"]
    assert decode_compact_reading(compact_payload)["open_duration_seconds"] == 0
~~~

</details>

<a id="tc-api-024"></a>

#### TC-API-024 — Omitted food maps to none

| Field | Value |
|---|---|
| Test Case ID | TC-API-024 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Omitted food maps to none. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>decode_compact_reading(compact_payload)[&#x27;food_id&#x27;] is None</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_omitted_food_maps_to_none</code> — [source L107](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_omitted_food_maps_to_none(compact_payload):
    del compact_payload["f"]
    assert decode_compact_reading(compact_payload)["food_id"] is None
~~~

</details>

<a id="tc-api-025"></a>

#### TC-API-025 — Invalid timestamp types and values are rejected

| Field | Value |
|---|---|
| Test Case ID | TC-API-025 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Invalid timestamp types and values are rejected. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | 1. <code>timestamp=&#x27;1727253000&#x27;</code><br>2. <code>timestamp=None</code><br>3. <code>timestamp=True</code><br>4. <code>timestamp=nan</code><br>5. <code>timestamp=inf</code><br>6. <code>timestamp=-inf</code><br>Setup/input cố định: <code>compact_payload[&#x27;t&#x27;] = timestamp</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ReadingProtocolError, match=&#x27;Unix timestamp in seconds&#x27;)</code> |
| Actual Result | Level A — 6/6 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_invalid_timestamp_types_and_values_are_rejected</code> — [source L116](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    "timestamp",
    ["1727253000", None, True, math.nan, math.inf, -math.inf],
)
def test_invalid_timestamp_types_and_values_are_rejected(compact_payload, timestamp):
    compact_payload["t"] = timestamp
    with pytest.raises(ReadingProtocolError, match="Unix timestamp in seconds"):
        decode_compact_reading(compact_payload)
~~~

</details>

<a id="tc-api-026"></a>

#### TC-API-026 — Out of range integer timestamp is rejected

| Field | Value |
|---|---|
| Test Case ID | TC-API-026 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Out of range integer timestamp is rejected. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>compact_payload[&#x27;t&#x27;] = 10 ** 1000</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ReadingProtocolError, match=&#x27;supported timestamp range&#x27;)</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_out_of_range_integer_timestamp_is_rejected</code> — [source L122](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_out_of_range_integer_timestamp_is_rejected(compact_payload):
    compact_payload["t"] = 10**1000
    with pytest.raises(ReadingProtocolError, match="supported timestamp range"):
        decode_compact_reading(compact_payload)
~~~

</details>

<a id="tc-api-027"></a>

#### TC-API-027 — Invalid required string fields are rejected

| Field | Value |
|---|---|
| Test Case ID | TC-API-027 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Invalid required string fields are rejected. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | 1. <code>field=&#x27;id&#x27;; value=&#x27;&#x27;</code><br>2. <code>field=&#x27;id&#x27;; value=123</code><br>3. <code>field=&#x27;d&#x27;; value=&#x27; &#x27;</code><br>4. <code>field=&#x27;d&#x27;; value=123</code><br>Setup/input cố định: <code>compact_payload[field] = value</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ReadingProtocolError)</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_invalid_required_string_fields_are_rejected</code> — [source L131](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("field", "value"), [("id", ""), ("id", 123), ("d", " "), ("d", 123)]
)
def test_invalid_required_string_fields_are_rejected(compact_payload, field, value):
    compact_payload[field] = value
    with pytest.raises(ReadingProtocolError):
        decode_compact_reading(compact_payload)
~~~

</details>

<a id="tc-api-028"></a>

#### TC-API-028 — Mixed compact and canonical fields are rejected

| Field | Value |
|---|---|
| Test Case ID | TC-API-028 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Mixed compact and canonical fields are rejected. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>compact_payload[&#x27;temperature_c&#x27;] = 5</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ReadingProtocolError, match=&#x27;cannot be mixed&#x27;)</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_mixed_compact_and_canonical_fields_are_rejected</code> — [source L137](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_mixed_compact_and_canonical_fields_are_rejected(compact_payload):
    compact_payload["temperature_c"] = 5
    with pytest.raises(ReadingProtocolError, match="cannot be mixed"):
        decode_compact_reading(compact_payload)
~~~

</details>

<a id="tc-api-029"></a>

#### TC-API-029 — Gọi trực tiếp compact decoder bằng canonical-only bị báo thiếu compact fields

| Field | Value |
|---|---|
| Test Case ID | TC-API-029 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Gọi trực tiếp compact decoder bằng canonical-only bị báo thiếu compact fields. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>canonical = {&#x27;device_id&#x27;: compact_payload[&#x27;d&#x27;], &#x27;timestamp&#x27;: &#x27;2026-09-25T15:00:00+07:00&#x27;, &#x27;temperature_c&#x27;: 5.2, &#x27;humidity_pct&#x27;: 61.5, &#x27;gas_raw&#x27;: 302, &#x27;door_open&#x27;: False}</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ReadingProtocolError, match=&#x27;Missing required compact fields&#x27;)</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_canonical_only_payload_is_not_treated_as_compact</code> — [source L143](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | Test này không gọi route. Route hỗ trợ canonical, được kiểm chứng bằng các API test riêng. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_canonical_only_payload_is_not_treated_as_compact(compact_payload):
    canonical = {
        "device_id": compact_payload["d"],
        "timestamp": "2026-09-25T15:00:00+07:00",
        "temperature_c": 5.2,
        "humidity_pct": 61.5,
        "gas_raw": 302,
        "door_open": False,
    }
    with pytest.raises(ReadingProtocolError, match="Missing required compact fields"):
        decode_compact_reading(canonical)
~~~

</details>

<a id="tc-api-030"></a>

#### TC-API-030 — Decoder does not access database or freshness

| Field | Value |
|---|---|
| Test Case ID | TC-API-030 |
| Module | API Input Validation — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/reading_protocol.py](../backend/app/services/reading_protocol.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Decoder does not access database or freshness. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>compact_payload, monkeypatch</code>; [fixture/helper defaults](#fixture-test-reading-protocol); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>decode_compact_reading(compact_payload)[&#x27;device_reading_id&#x27;] == compact_payload[&#x27;id&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_reading_protocol.py::test_decoder_does_not_access_database_or_freshness</code> — [source L156](../backend/tests/test_reading_protocol.py) |
| Requirement / Rule | R-API: Canonical bắt buộc device_id, UUID v4 device_reading_id, ISO timestamp, temperature_c/humidity_pct/gas_raw finite hoặc null, boolean door_open. Duration integer >=0 mặc định 0; food_id optional/null, nếu có phải tồn tại. Compact id,d,t,tc,h,g,o + optional od,f; Unix seconds -> +07:00; o chỉ integer 0/1; không trộn format. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_decoder_does_not_access_database_or_freshness(compact_payload, monkeypatch):
    from app import database
    from app.services import freshness

    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("decoder must remain independent of application services")

    monkeypatch.setattr(database, "get_db_connection", unexpected_call)
    monkeypatch.setattr(freshness, "evaluate_freshness", unexpected_call)
    assert decode_compact_reading(compact_payload)["device_reading_id"] == compact_payload["id"]
~~~

</details>

<a id="tc-api-031"></a>

#### TC-API-031 — Canonical: bỏ lần lượt từng required key

| Field | Value |
|---|---|
| Test Case ID | TC-API-031 |
| Module | API Input Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Canonical: bỏ lần lượt từng required key |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Payload hợp lệ; bỏ device_id, timestamp, temperature_c, humidity_pct, door_open từng lần; UUID mới cho mỗi request. |
| Steps | POST từng payload vào DB thử nghiệm sạch; đọc response và row count. |
| Expected Result | 400 MISSING_FIELDS chứa key thiếu; không tạo reading/state/event. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-API; backend/app/routes/readings.py::create_reading |
| Notes | Automation đã bỏ gas_raw và device_reading_id; compact có coverage đủ 7 keys. Ca này chỉ bổ sung 5 canonical keys còn lại. |

<a id="tc-api-032"></a>

#### TC-API-032 — Biên type cho duration, door và food_id

| Field | Value |
|---|---|
| Test Case ID | TC-API-032 |
| Module | API Input Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Biên type cho duration, door và food_id |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Duration=True, 1.5; canonical door=0/1; food_id='', ' ', 123; các field khác hợp lệ. |
| Steps | POST độc lập từng biến thể; kiểm tra HTTP/error và DB. |
| Expected Result | 400 INVALID_OPEN_DURATION / INVALID_DOOR_STATE / INVALID_FOOD_ID tương ứng. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-API; backend/app/routes/readings.py::create_reading |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-api-033"></a>

#### TC-API-033 — Canonical timestamp timezone và date-only

| Field | Value |
|---|---|
| Test Case ID | TC-API-033 |
| Module | API Input Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Canonical timestamp timezone và date-only |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | timestamp='2026-09-26', ISO có +07:00, ISO không timezone; UUID riêng. |
| Steps | POST từng payload và đối chiếu timestamp lưu. |
| Expected Result | Date-only 400; ISO có giờ hợp lệ được nhận kể cả không timezone; không tự áp yêu cầu timezone mới. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-API; backend/app/routes/readings.py::_is_valid_timestamp |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

### IDEMP — Reading Idempotency

Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate.

<a id="tc-idemp-001"></a>

#### TC-IDEMP-001 — Compact reading duplicate returns original without second row

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-001 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Compact reading duplicate returns original without second row. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = compact_reading_payload()</code><br><code>first = client.post(&#x27;/api/v1/readings&#x27;, json=payload)</code><br><code>duplicate = client.post(&#x27;/api/v1/readings&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>duplicate.status_code == 200</code><br><code>duplicate.json[&#x27;duplicate&#x27;] is True</code><br><code>duplicate.json[&#x27;reading_id&#x27;] == first.json[&#x27;reading_id&#x27;]</code><br><code>duplicate.json[&#x27;freshness&#x27;] == first.json[&#x27;freshness&#x27;]</code><br><code>_reading_count() == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_compact_reading_duplicate_returns_original_without_second_row</code> — [source L163](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_compact_reading_duplicate_returns_original_without_second_row(client):
    payload = compact_reading_payload()
    first = client.post("/api/v1/readings", json=payload)
    duplicate = client.post("/api/v1/readings", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert duplicate.json["reading_id"] == first.json["reading_id"]
    assert duplicate.json["freshness"] == first.json["freshness"]
    assert _reading_count() == 1
~~~

</details>

<a id="tc-idemp-002"></a>

#### TC-IDEMP-002 — Canonical reading still creates duplicate and conflict

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-002 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Canonical reading still creates duplicate and conflict. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>payload = reading_payload(device_reading_id=reading_id)</code><br><code>first = client.post(&#x27;/api/v1/readings&#x27;, json=payload)</code><br><code>duplicate = client.post(&#x27;/api/v1/readings&#x27;, json=payload)</code><br><code>conflict = client.post(&#x27;/api/v1/readings&#x27;, json={**payload, &#x27;temperature_c&#x27;: 6})</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>duplicate.status_code == 200</code><br><code>duplicate.json[&#x27;duplicate&#x27;] is True</code><br><code>conflict.status_code == 409</code><br><code>_reading_count() == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_canonical_reading_still_creates_duplicate_and_conflict</code> — [source L220](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_canonical_reading_still_creates_duplicate_and_conflict(client):
    reading_id = str(uuid.uuid4())
    payload = reading_payload(device_reading_id=reading_id)
    first = client.post("/api/v1/readings", json=payload)
    duplicate = client.post("/api/v1/readings", json=payload)
    conflict = client.post(
        "/api/v1/readings", json={**payload, "temperature_c": 6}
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert conflict.status_code == 409
    assert _reading_count() == 1
~~~

</details>

<a id="tc-idemp-003"></a>

#### TC-IDEMP-003 — Compact then equivalent canonical is idempotent

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-003 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Compact then equivalent canonical is idempotent. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>compact = compact_reading_payload(od=0)</code><br><code>canonical = decode_compact_reading(compact)</code><br><code>first = client.post(&#x27;/api/v1/readings&#x27;, json=compact)</code><br><code>equivalent = client.post(&#x27;/api/v1/readings&#x27;, json=canonical)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>equivalent.status_code == 200</code><br><code>equivalent.json[&#x27;duplicate&#x27;] is True</code><br><code>equivalent.json[&#x27;reading_id&#x27;] == first.json[&#x27;reading_id&#x27;]</code><br><code>equivalent.json[&#x27;freshness&#x27;] == first.json[&#x27;freshness&#x27;]</code><br><code>_reading_count() == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_compact_then_equivalent_canonical_is_idempotent</code> — [source L236](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_compact_then_equivalent_canonical_is_idempotent(client):
    compact = compact_reading_payload(od=0)
    canonical = decode_compact_reading(compact)

    first = client.post("/api/v1/readings", json=compact)
    equivalent = client.post("/api/v1/readings", json=canonical)

    assert first.status_code == 201
    assert equivalent.status_code == 200
    assert equivalent.json["duplicate"] is True
    assert equivalent.json["reading_id"] == first.json["reading_id"]
    assert equivalent.json["freshness"] == first.json["freshness"]
    assert _reading_count() == 1
~~~

</details>

<a id="tc-idemp-004"></a>

#### TC-IDEMP-004 — Idemp 001 new uuid reading is saved and echoed

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-004 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Idemp 001 new uuid reading is saved and echoed. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>response = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(device_reading_id=reading_id.upper()))</code><br><code>row = _stored_reading(&#x27;FG-ESP32-01&#x27;, reading_id)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;device_reading_id&#x27;] == reading_id</code><br><code>response.json[&#x27;duplicate&#x27;] is False</code><br><code>_reading_count() == 1</code><br><code>row is not None</code><br><code>row[&#x27;freshness_status&#x27;] == response.json[&#x27;freshness&#x27;][&#x27;status&#x27;]</code><br><code>row[&#x27;freshness_reason&#x27;] == response.json[&#x27;freshness&#x27;][&#x27;reason&#x27;]</code><br><code>row[&#x27;freshness_evaluated_at&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_idemp_001_new_uuid_reading_is_saved_and_echoed</code> — [source L284](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_idemp_001_new_uuid_reading_is_saved_and_echoed(client):
    reading_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/readings",
        json=reading_payload(device_reading_id=reading_id.upper()),
    )

    assert response.status_code == 201
    assert response.json["device_reading_id"] == reading_id
    assert response.json["duplicate"] is False
    assert _reading_count() == 1
    row = _stored_reading("FG-ESP32-01", reading_id)
    assert row is not None
    assert row["freshness_status"] == response.json["freshness"]["status"]
    assert row["freshness_reason"] == response.json["freshness"]["reason"]
    assert row["freshness_evaluated_at"]
~~~

</details>

<a id="tc-idemp-005"></a>

#### TC-IDEMP-005 — Idemp 002 same payload returns original reading

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-005 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Idemp 002 same payload returns original reading. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client, monkeypatch</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>payload = reading_payload(device_reading_id=reading_id)</code><br><code>first = client.post(&#x27;/api/v1/readings&#x27;, json=payload)</code><br><code>duplicate = client.post(&#x27;/api/v1/readings&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>duplicate.status_code == 200</code><br><code>duplicate.json[&#x27;duplicate&#x27;] is True</code><br><code>duplicate.json[&#x27;reading_id&#x27;] == first.json[&#x27;reading_id&#x27;]</code><br><code>duplicate.json[&#x27;freshness&#x27;] == first.json[&#x27;freshness&#x27;]</code><br><code>_reading_count() == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_idemp_002_same_payload_returns_original_reading</code> — [source L302](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_idemp_002_same_payload_returns_original_reading(client, monkeypatch):
    reading_id = str(uuid.uuid4())
    payload = reading_payload(device_reading_id=reading_id)
    first = client.post("/api/v1/readings", json=payload)

    def freshness_must_not_be_recalculated(**_kwargs):
        raise AssertionError("duplicate request recalculated freshness")

    monkeypatch.setattr(readings_module, "evaluate_freshness", freshness_must_not_be_recalculated)
    duplicate = client.post("/api/v1/readings", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert duplicate.json["reading_id"] == first.json["reading_id"]
    assert duplicate.json["freshness"] == first.json["freshness"]
    assert _reading_count() == 1
~~~

</details>

<a id="tc-idemp-006"></a>

#### TC-IDEMP-006 — UUID chữ hoa và duration mặc định được chuẩn hóa khi retry

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-006 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | UUID chữ hoa và duration mặc định được chuẩn hóa khi retry. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>first = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(device_reading_id=reading_id))</code><br><code>duplicate_payload = reading_payload(device_reading_id=reading_id.upper(), open_duration_seconds=0)</code><br><code>duplicate = client.post(&#x27;/api/v1/readings&#x27;, json=duplicate_payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>duplicate.status_code == 200</code><br><code>duplicate.json[&#x27;duplicate&#x27;] is True</code><br><code>duplicate.json[&#x27;reading_id&#x27;] == first.json[&#x27;reading_id&#x27;]</code><br><code>_reading_count() == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_idemp_002_defaults_and_trimmed_food_id_are_canonicalized</code> — [source L321](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | Test không truyền food_id và không chứng minh trim food_id dù tên có trimmed_food_id. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_idemp_002_defaults_and_trimmed_food_id_are_canonicalized(client):
    reading_id = str(uuid.uuid4())
    first = client.post(
        "/api/v1/readings",
        json=reading_payload(device_reading_id=reading_id),
    )
    duplicate_payload = reading_payload(
        device_reading_id=reading_id.upper(), open_duration_seconds=0
    )
    duplicate = client.post("/api/v1/readings", json=duplicate_payload)

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
    assert duplicate.json["reading_id"] == first.json["reading_id"]
    assert _reading_count() == 1
~~~

</details>

<a id="tc-idemp-007"></a>

#### TC-IDEMP-007 — Idemp 003 to 010 payload change conflicts without mutation

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-007 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Idemp 003 to 010 payload change conflicts without mutation. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | 1. <code>change={&#x27;temperature_c&#x27;: 6}</code><br>2. <code>change={&#x27;humidity_pct&#x27;: 61}</code><br>3. <code>change={&#x27;gas_raw&#x27;: 301}</code><br>4. <code>change={&#x27;door_open&#x27;: True}</code><br>5. <code>change={&#x27;open_duration_seconds&#x27;: 1}</code><br>6. <code>change={&#x27;timestamp&#x27;: &#x27;2026-09-25T12:00:01+07:00&#x27;}</code><br>7. <code>change={&#x27;food_id&#x27;: &#x27;FG-FOOD-OTHER&#x27;}</code><br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>original = reading_payload(device_reading_id=reading_id)</code><br><code>first = client.post(&#x27;/api/v1/readings&#x27;, json=original)</code><br><code>before = dict(_stored_reading(&#x27;FG-ESP32-01&#x27;, reading_id))</code><br><code>conflict = client.post(&#x27;/api/v1/readings&#x27;, json={**original, **change})</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>conflict.status_code == 409</code><br><code>_reading_count() == 1</code><br><code>dict(_stored_reading(&#x27;FG-ESP32-01&#x27;, reading_id)) == before</code> |
| Actual Result | Level A — 7/7 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_idemp_003_to_010_payload_change_conflicts_without_mutation</code> — [source L351](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    "change",
    [
        {"temperature_c": 6},
        {"humidity_pct": 61},
        {"gas_raw": 301},
        {"door_open": True},
        {"open_duration_seconds": 1},
        {"timestamp": "2026-09-25T12:00:01+07:00"},
        {"food_id": "FG-FOOD-OTHER"},
    ],
)
def test_idemp_003_to_010_payload_change_conflicts_without_mutation(client, change):
    reading_id = str(uuid.uuid4())
    original = reading_payload(device_reading_id=reading_id)
    first = client.post("/api/v1/readings", json=original)
    before = dict(_stored_reading("FG-ESP32-01", reading_id))

    conflict = client.post(
        "/api/v1/readings", json={**original, **change}
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert _reading_count() == 1
    assert dict(_stored_reading("FG-ESP32-01", reading_id)) == before
~~~

</details>

<a id="tc-idemp-008"></a>

#### TC-IDEMP-008 — Idemp 004 food id conflict even if new food does not exist

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-008 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Idemp 004 food id conflict even if new food does not exist. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>original = reading_payload(device_reading_id=reading_id, food_id=&#x27;food-one&#x27;)</code><br><code>conflict = client.post(&#x27;/api/v1/readings&#x27;, json={**original, &#x27;food_id&#x27;: &#x27;food-two&#x27;})</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>client.post(&#x27;/api/v1/foods&#x27;, json={&#x27;food_id&#x27;: &#x27;food-one&#x27;, &#x27;food_name&#x27;: &#x27;Food&#x27;, &#x27;category&#x27;: &#x27;MEAT&#x27;, &#x27;inserted_at&#x27;: &#x27;2026-09-25&#x27;}).status_code == 201</code><br><code>client.post(&#x27;/api/v1/readings&#x27;, json=original).status_code == 201</code><br><code>conflict.status_code == 409</code><br><code>_reading_count() == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_idemp_004_food_id_conflict_even_if_new_food_does_not_exist</code> — [source L367](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_idemp_004_food_id_conflict_even_if_new_food_does_not_exist(client):
    reading_id = str(uuid.uuid4())
    original = reading_payload(device_reading_id=reading_id, food_id="food-one")
    assert client.post("/api/v1/foods", json={
        "food_id": "food-one", "food_name": "Food", "category": "MEAT",
        "inserted_at": "2026-09-25"
    }).status_code == 201
    assert client.post("/api/v1/readings", json=original).status_code == 201

    conflict = client.post(
        "/api/v1/readings", json={**original, "food_id": "food-two"}
    )

    assert conflict.status_code == 409
    assert _reading_count() == 1
~~~

</details>

<a id="tc-idemp-009"></a>

#### TC-IDEMP-009 — Idemp 006 same uuid on different devices is allowed

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-009 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Idemp 006 same uuid on different devices is allowed. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>first = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(device_reading_id=reading_id))</code><br><code>second = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(device_id=&#x27;FG-ESP32-02&#x27;, device_reading_id=reading_id))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>second.status_code == 201</code><br><code>_reading_count() == 2</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_idemp_006_same_uuid_on_different_devices_is_allowed</code> — [source L384](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_idemp_006_same_uuid_on_different_devices_is_allowed(client):
    reading_id = str(uuid.uuid4())
    first = client.post("/api/v1/readings", json=reading_payload(device_reading_id=reading_id))
    second = client.post(
        "/api/v1/readings",
        json=reading_payload(device_id="FG-ESP32-02", device_reading_id=reading_id),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert _reading_count() == 2
~~~

</details>

<a id="tc-idemp-010"></a>

#### TC-IDEMP-010 — Idemp 007 concurrent duplicate requests create one row

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-010 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Idemp 007 concurrent duplicate requests create one row. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>payload = reading_payload(device_reading_id=reading_id)</code><br><code>barrier = Barrier(2)</code><br><code>app = client.application</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>sorted((status for status, _body in results)) == [200, 201]</code><br><code>sum((body[&#x27;duplicate&#x27;] is False for _status, body in results)) == 1</code><br><code>_reading_count() == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_idemp_007_concurrent_duplicate_requests_create_one_row</code> — [source L397](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_idemp_007_concurrent_duplicate_requests_create_one_row(client):
    reading_id = str(uuid.uuid4())
    payload = reading_payload(device_reading_id=reading_id)
    barrier = Barrier(2)
    app = client.application

    def send_request():
        with app.test_client() as thread_client:
            barrier.wait(timeout=5)
            response = thread_client.post("/api/v1/readings", json=payload)
            return response.status_code, response.json

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: send_request(), range(2)))

    assert sorted(status for status, _body in results) == [200, 201]
    assert sum(body["duplicate"] is False for _status, body in results) == 1
    assert _reading_count() == 1
~~~

</details>

<a id="tc-idemp-011"></a>

#### TC-IDEMP-011 — Lost reading response does not replay transition

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-011 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Lost reading response does not replay transition. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>system</code>; [fixture/helper defaults](#fixture-test-cross-system-integration); không dùng DB vận hành. |
| Input | 1. <code>event_type=&#x27;GAS_ANOMALY_STARTED&#x27;</code><br>2. <code>event_type=&#x27;TEMPERATURE_EXPOSURE_EXCEEDED&#x27;</code><br>3. <code>event_type=&#x27;SENSOR_FAULT&#x27;</code><br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>second = 5</code><br><code>kwargs = {&#x27;gas&#x27;: 130} if event_type == &#x27;GAS_ANOMALY_STARTED&#x27; else {}</code><br><code>first = post_reading(system, second, reading_id=reading_id, **kwargs)</code><br><code>retry = post_reading(system, second, reading_id=reading_id, **kwargs)</code><br><code>changed = post_reading(system, second, reading_id=reading_id, **{**kwargs, &#x27;humidity&#x27;: 61})</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>retry.status_code == 200 and retry.json[&#x27;duplicate&#x27;] is True</code><br><code>changed.status_code == 409</code><br><code>rows(system, &#x27;SELECT COUNT(*) AS n FROM sensor_readings&#x27;)[0][&#x27;n&#x27;] == 1</code><br><code>event_types(system) == [event_type]</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_cross_system_integration.py::test_lost_reading_response_does_not_replay_transition</code> — [source L181](../backend/tests/test_cross_system_integration.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("event_type", [
    "GAS_ANOMALY_STARTED", "TEMPERATURE_EXPOSURE_EXCEEDED", "SENSOR_FAULT"
])
def test_lost_reading_response_does_not_replay_transition(system, event_type):
    reading_id = str(uuid.uuid4())
    second = 5
    if event_type == "GAS_ANOMALY_STARTED":
        connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
        connection.execute(
            """INSERT INTO gas_anomaly_state (
                   device_id, food_id, baseline, baseline_sample_count,
                   baseline_sum, consecutive_anomaly_count, anomaly_active
               ) VALUES ('CROSS-DEVICE', '', 100, 10, 1000, 2, 0)"""
        )
        connection.commit()
        connection.close()
    elif event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
        connection.execute(
            """INSERT INTO temperature_exposure_state (
                   device_id, food_id, exposure_seconds, exposure_active,
                   exposure_exceeded, last_valid_temperature_timestamp,
                   continuity_broken
               ) VALUES ('CROSS-DEVICE', '', 7200, 1, 0, ?, 0)""",
            (timestamp(0),),
        )
        connection.commit()
        connection.close()

    kwargs = {"gas": 130} if event_type == "GAS_ANOMALY_STARTED" else {}
    if event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        kwargs["temperature"] = 6
    if event_type == "SENSOR_FAULT":
        kwargs["temperature"] = None
    first = post_reading(system, second, reading_id=reading_id, **kwargs)
    retry = post_reading(system, second, reading_id=reading_id, **kwargs)
    changed = post_reading(system, second, reading_id=reading_id,
                           **{**kwargs, "humidity": 61})
    assert first.status_code == 201
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    assert changed.status_code == 409
    assert rows(system, "SELECT COUNT(*) AS n FROM sensor_readings")[0]["n"] == 1
    assert event_types(system) == [event_type]
~~~

</details>

<a id="tc-idemp-012"></a>

#### TC-IDEMP-012 — Duplicate food id returns conflict

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-012 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Duplicate food id returns conflict. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(food_name=&#x27;Another Milk&#x27;))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>client.post(&#x27;/api/v1/foods&#x27;, json=food_payload()).status_code == 201</code><br><code>response.status_code == 409</code><br><code>response.json[&#x27;error&#x27;] == &#x27;DUPLICATE_FOOD_ID&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_duplicate_food_id_returns_conflict</code> — [source L249](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_duplicate_food_id_returns_conflict(client):
    assert client.post("/api/v1/foods", json=food_payload()).status_code == 201

    response = client.post("/api/v1/foods", json=food_payload(food_name="Another Milk"))

    assert response.status_code == 409
    assert response.json["error"] == "DUPLICATE_FOOD_ID"
~~~

</details>

<a id="tc-idemp-013"></a>

#### TC-IDEMP-013 — Api retry and lost response keep one reading and gas event

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-013 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Api retry and lost response keep one reading and gas event. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>post_gas(api_client, 130)</code><br><code>post_gas(api_client, 130)</code><br><code>reading_id = str(uuid.uuid4())</code><br><code>timestamp = &#x27;2026-09-26T13:00:00+07:00&#x27;</code><br><code>first = post_gas(api_client, 130, reading_id=reading_id, timestamp=timestamp)</code><br><code>retry = post_gas(api_client, 130, reading_id=reading_id, timestamp=timestamp)</code><br><code>connection = sqlite3.connect(api_client.application.config[&#x27;TEST_DB_PATH&#x27;])</code><br><code>events = gas_events(api_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>retry.status_code == 200 and retry.json[&#x27;duplicate&#x27;] is True</code><br><code>connection.execute(&#x27;SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?&#x27;, (reading_id,)).fetchone()[0] == 1</code><br><code>[event[&#x27;event_type&#x27;] for event in events] == [&#x27;GAS_ANOMALY_STARTED&#x27;]</code><br><code>events[0][&#x27;timestamp&#x27;] == timestamp</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_api_retry_and_lost_response_keep_one_reading_and_gas_event</code> — [source L351](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_api_retry_and_lost_response_keep_one_reading_and_gas_event(api_client):
    for _ in range(10):
        post_gas(api_client, 100)
    post_gas(api_client, 130)
    post_gas(api_client, 130)
    reading_id = str(uuid.uuid4())
    timestamp = "2026-09-26T13:00:00+07:00"
    first = post_gas(api_client, 130, reading_id=reading_id, timestamp=timestamp)
    # Treat the committed response as lost, then retry the identical reading.
    retry = post_gas(api_client, 130, reading_id=reading_id, timestamp=timestamp)
    assert first.status_code == 201
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    connection = sqlite3.connect(api_client.application.config["TEST_DB_PATH"])
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?",
            (reading_id,),
        ).fetchone()[0] == 1
    finally:
        connection.close()
    events = gas_events(api_client)
    assert [event["event_type"] for event in events] == ["GAS_ANOMALY_STARTED"]
    assert events[0]["timestamp"] == timestamp
~~~

</details>

<a id="tc-idemp-014"></a>

#### TC-IDEMP-014 — Duplicate reading does not repeat fault transition and id is deterministic

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-014 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Duplicate reading does not repeat fault transition and id is deterministic. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>first = post_reading(sensor_client, seconds=1, temperature_c=None, device_reading_id=reading_id)</code><br><code>retry = post_reading(sensor_client, seconds=1, temperature_c=None, device_reading_id=reading_id)</code><br><code>created = fault_events(sensor_client)</code><br><code>expected = uuid.uuid5(uuid.NAMESPACE_URL, f&#x27;freshguard:sensor-fault:[&quot;SENSOR-DEVICE&quot;,null,&quot;temperature&quot;,&quot;{reading_id}&quot;,&quot;SENSOR_FAULT&quot;]&#x27;)</code><br><code>connection = connect(sensor_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>retry.status_code == 200 and retry.json[&#x27;duplicate&#x27;] is True</code><br><code>len(created) == 1</code><br><code>created[0][&#x27;event_id&#x27;] == str(expected)</code><br><code>connection.execute(&#x27;SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?&#x27;, (reading_id,)).fetchone()[0] == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_duplicate_reading_does_not_repeat_fault_transition_and_id_is_deterministic</code> — [source L213](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_duplicate_reading_does_not_repeat_fault_transition_and_id_is_deterministic(sensor_client):
    reading_id = str(uuid.uuid4())
    first = post_reading(sensor_client, seconds=1, temperature_c=None,
                         device_reading_id=reading_id)
    retry = post_reading(sensor_client, seconds=1, temperature_c=None,
                         device_reading_id=reading_id)
    assert first.status_code == 201
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    created = fault_events(sensor_client)
    assert len(created) == 1
    expected = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "freshguard:sensor-fault:[\"SENSOR-DEVICE\",null,\"temperature\","
        f"\"{reading_id}\",\"SENSOR_FAULT\"]",
    )
    assert created[0]["event_id"] == str(expected)
    connection = connect(sensor_client)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?",
            (reading_id,),
        ).fetchone()[0] == 1
    finally:
        connection.close()
~~~

</details>

<a id="tc-idemp-015"></a>

#### TC-IDEMP-015 — Duplicate and lost response retry update exposure once

| Field | Value |
|---|---|
| Test Case ID | TC-IDEMP-015 |
| Module | Reading Idempotency — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/init_db.py](../backend/app/init_db.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Duplicate and lost response retry update exposure once. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_exposure_state(temperature_client, exposure_seconds=7200)</code><br><code>reading_id = str(uuid.uuid4())</code><br><code>first = post_temperature(temperature_client, 6, seconds=5, reading_id=reading_id)</code><br><code>retry = post_temperature(temperature_client, 6, seconds=5, reading_id=reading_id)</code><br><code>connection = db_connect(temperature_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>retry.status_code == 200 and retry.json[&#x27;duplicate&#x27;] is True</code><br><code>state_for(temperature_client)[&#x27;exposure_seconds&#x27;] == 7205</code><br><code>len(temperature_events(temperature_client)) == 1</code><br><code>connection.execute(&#x27;SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?&#x27;, (reading_id,)).fetchone()[0] == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_duplicate_and_lost_response_retry_update_exposure_once</code> — [source L242](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-IDEMP: Identity (device_id, device_reading_id): mới 201, duplicate giống canonical payload 200 với snapshot gốc, thay payload 409; không chạy lại state/event trên duplicate. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_duplicate_and_lost_response_retry_update_exposure_once(temperature_client):
    prime_exposure_state(temperature_client, exposure_seconds=7200)
    reading_id = str(uuid.uuid4())
    first = post_temperature(temperature_client, 6, seconds=5, reading_id=reading_id)
    retry = post_temperature(temperature_client, 6, seconds=5, reading_id=reading_id)
    assert first.status_code == 201
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    assert state_for(temperature_client)["exposure_seconds"] == 7205
    assert len(temperature_events(temperature_client)) == 1
    connection = db_connect(temperature_client)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?",
            (reading_id,),
        ).fetchone()[0] == 1
    finally:
        connection.close()
~~~

</details>

### FRESH — Freshness Severity Aggregation

Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0.

<a id="tc-fresh-001"></a>

#### TC-FRESH-001 — Gas anomaly and gas sensor fault are independent

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-001 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Gas anomaly and gas sensor fault are independent. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>system</code>; [fixture/helper defaults](#fixture-test-cross-system-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>invalid_id = str(uuid.uuid4())</code><br><code>invalid = post_reading(system, 65, reading_id=invalid_id, gas=None)</code><br><code>retry = post_reading(system, 65, reading_id=invalid_id, gas=None)</code><br><code>post_reading(system, 70, gas=130)</code><br><code>post_reading(system, 75, gas=100)</code><br><code>gas_events = rows(system, &quot;SELECT event_id FROM events WHERE event_type LIKE &#x27;GAS_%&#x27;&quot;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>post_reading(system, index * 5, gas=100).status_code == 201</code><br><code>response.status_code == 201</code><br><code>event_types(system) == [&#x27;GAS_ANOMALY_STARTED&#x27;]</code><br><code>invalid.status_code == 201</code><br><code>rows(system, &#x27;SELECT anomaly_active FROM gas_anomaly_state&#x27;)[0][&#x27;anomaly_active&#x27;] == 1</code><br><code>event_types(system) == [&#x27;GAS_ANOMALY_STARTED&#x27;, &#x27;SENSOR_FAULT&#x27;]</code><br><code>retry.status_code == 200 and retry.json[&#x27;duplicate&#x27;] is True</code><br><code>event_types(system) == [&#x27;GAS_ANOMALY_STARTED&#x27;, &#x27;SENSOR_FAULT&#x27;]</code><br><code>&#x27;GAS_ANOMALY_RECOVERED&#x27; not in event_types(system)</code><br><code>&#x27;SENSOR_RECOVERED&#x27; in event_types(system)</code><br><code>event_types(system)[-1] == &#x27;GAS_ANOMALY_RECOVERED&#x27;</code><br><code>len({event[&#x27;event_id&#x27;] for event in gas_events}) == len(gas_events)</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_cross_system_integration.py::test_gas_anomaly_and_gas_sensor_fault_are_independent</code> — [source L73](../backend/tests/test_cross_system_integration.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_gas_anomaly_and_gas_sensor_fault_are_independent(system):
    for index in range(10):
        assert post_reading(system, index * 5, gas=100).status_code == 201
    for index in range(3):
        response = post_reading(system, 50 + index * 5, gas=130)
    assert response.status_code == 201
    assert event_types(system) == ["GAS_ANOMALY_STARTED"]

    invalid_id = str(uuid.uuid4())
    invalid = post_reading(system, 65, reading_id=invalid_id, gas=None)
    assert invalid.status_code == 201
    assert rows(system, "SELECT anomaly_active FROM gas_anomaly_state")[0]["anomaly_active"] == 1
    assert event_types(system) == ["GAS_ANOMALY_STARTED", "SENSOR_FAULT"]

    retry = post_reading(system, 65, reading_id=invalid_id, gas=None)
    assert retry.status_code == 200 and retry.json["duplicate"] is True
    assert event_types(system) == ["GAS_ANOMALY_STARTED", "SENSOR_FAULT"]

    post_reading(system, 70, gas=130)
    assert "GAS_ANOMALY_RECOVERED" not in event_types(system)
    assert "SENSOR_RECOVERED" in event_types(system)
    post_reading(system, 75, gas=100)
    assert event_types(system)[-1] == "GAS_ANOMALY_RECOVERED"
    gas_events = rows(system, "SELECT event_id FROM events WHERE event_type LIKE 'GAS_%'")
    assert len({event["event_id"] for event in gas_events}) == len(gas_events)
~~~

</details>

<a id="tc-fresh-002"></a>

#### TC-FRESH-002 — Gas and temperature transition events coexist and freshness is consistent

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-002 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Gas and temperature transition events coexist and freshness is consistent. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>system</code>; [fixture/helper defaults](#fixture-test-cross-system-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>connection = sqlite3.connect(system.application.config[&#x27;TEST_DB_PATH&#x27;])</code><br><code>connection.execute(&quot;UPDATE temperature_exposure_state\n           SET exposure_seconds = 7190, exposure_active = 1,\n               exposure_exceeded = 0, last_valid_temperature_timestamp = ?,\n               continuity_broken = 0\n           WHERE device_id = ? AND food_id = &#x27;&#x27;&quot;, (timestamp(45), &#x27;CROSS-DEVICE&#x27;))</code><br><code>connection.commit()</code><br><code>connection.close()</code><br><code>post_reading(system, 50, temperature=6, gas=130)</code><br><code>post_reading(system, 55, temperature=6, gas=130)</code><br><code>trigger = post_reading(system, 60, temperature=6, gas=130)</code><br><code>latest = system.get(&#x27;/api/v1/readings/latest&#x27;).json[&#x27;data&#x27;]</code><br><code>history = system.get(&#x27;/api/v1/readings?limit=1&#x27;).json[&#x27;data&#x27;][0]</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>trigger.status_code == 201</code><br><code>set(event_types(system)) == {&#x27;GAS_ANOMALY_STARTED&#x27;, &#x27;TEMPERATURE_EXPOSURE_EXCEEDED&#x27;}</code><br><code>rows(system, &#x27;SELECT COUNT(*) AS n FROM sensor_readings&#x27;)[0][&#x27;n&#x27;] == 13</code><br><code>&#x27;FRESHNESS_CHANGED&#x27; not in event_types(system)</code><br><code>trigger.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code><br><code>latest[&#x27;freshness&#x27;] == history[&#x27;freshness&#x27;] == trigger.json[&#x27;freshness&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_cross_system_integration.py::test_gas_and_temperature_transition_events_coexist_and_freshness_is_consistent</code> — [source L124](../backend/tests/test_cross_system_integration.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_gas_and_temperature_transition_events_coexist_and_freshness_is_consistent(system):
    for index in range(10):
        post_reading(system, index * 5, temperature=4, gas=100)
    connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
    connection.execute(
        """UPDATE temperature_exposure_state
           SET exposure_seconds = 7190, exposure_active = 1,
               exposure_exceeded = 0, last_valid_temperature_timestamp = ?,
               continuity_broken = 0
           WHERE device_id = ? AND food_id = ''""",
        (timestamp(45), "CROSS-DEVICE"),
    )
    connection.commit()
    connection.close()

    post_reading(system, 50, temperature=6, gas=130)
    post_reading(system, 55, temperature=6, gas=130)
    trigger = post_reading(system, 60, temperature=6, gas=130)
    assert trigger.status_code == 201
    assert set(event_types(system)) == {
        "GAS_ANOMALY_STARTED", "TEMPERATURE_EXPOSURE_EXCEEDED"
    }
    assert rows(system, "SELECT COUNT(*) AS n FROM sensor_readings")[0]["n"] == 13
    assert "FRESHNESS_CHANGED" not in event_types(system)
    assert trigger.json["freshness"]["status"] == "Check Food"
    latest = system.get("/api/v1/readings/latest").json["data"]
    history = system.get("/api/v1/readings?limit=1").json["data"][0]
    assert latest["freshness"] == history["freshness"] == trigger.json["freshness"]
~~~

</details>

<a id="tc-fresh-003"></a>

#### TC-FRESH-003 — Tc01 registered food and normal environment

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-003 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Tc01 registered food and normal environment. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>register_food(api_client, &#x27;FG-TEST-001&#x27;, &#x27;MEAT&#x27;, 0, 10)</code><br><code>response = post_reading(api_client, food_id=&#x27;FG-TEST-001&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_tc01_registered_food_and_normal_environment</code> — [source L64](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_tc01_registered_food_and_normal_environment(api_client):
    register_food(api_client, "FG-TEST-001", "MEAT", 0, 10)

    response = post_reading(api_client, food_id="FG-TEST-001")

    # POST /readings has historically returned 201 for a created reading.
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Fresh / Normal"
~~~

</details>

<a id="tc-fresh-004"></a>

#### TC-FRESH-004 — Tc10 food use soon and fresh temperature

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-004 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Tc10 food use soon and fresh temperature. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>register_food(api_client, &#x27;FG-AGG-10&#x27;, stored_days=2, expiry_days=10)</code><br><code>response = post_reading(api_client, food_id=&#x27;FG-AGG-10&#x27;, temperature_c=5)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Use Soon&#x27;</code><br><code>&#x27;storage duration&#x27; in response.json[&#x27;freshness&#x27;][&#x27;reason&#x27;].lower()</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_tc10_food_use_soon_and_fresh_temperature</code> — [source L112](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_tc10_food_use_soon_and_fresh_temperature(api_client):
    register_food(api_client, "FG-AGG-10", stored_days=2, expiry_days=10)

    response = post_reading(api_client, food_id="FG-AGG-10", temperature_c=5)

    assert response.json["freshness"]["status"] == "Use Soon"
    assert "storage duration" in response.json["freshness"]["reason"].lower()
~~~

</details>

<a id="tc-fresh-005"></a>

#### TC-FRESH-005 — Tc11 temperature without exposure does not change fresh status

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-005 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Tc11 temperature without exposure does not change fresh status. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>register_food(api_client, &#x27;FG-AGG-11&#x27;, stored_days=0, expiry_days=10)</code><br><code>response = post_reading(api_client, food_id=&#x27;FG-AGG-11&#x27;, temperature_c=15)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_tc11_temperature_without_exposure_does_not_change_fresh_status</code> — [source L121](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_tc11_temperature_without_exposure_does_not_change_fresh_status(api_client):
    register_food(api_client, "FG-AGG-11", stored_days=0, expiry_days=10)

    response = post_reading(api_client, food_id="FG-AGG-11", temperature_c=15)

    assert response.json["freshness"]["status"] == "Fresh / Normal"
~~~

</details>

<a id="tc-fresh-006"></a>

#### TC-FRESH-006 — Tc12 storage use soon wins when temperature exposure is not provided

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-006 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Tc12 storage use soon wins when temperature exposure is not provided. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>register_food(api_client, &#x27;FG-AGG-12&#x27;, stored_days=2, expiry_days=10)</code><br><code>response = post_reading(api_client, food_id=&#x27;FG-AGG-12&#x27;, temperature_c=15)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Use Soon&#x27;</code><br><code>&#x27;storage duration&#x27; in response.json[&#x27;freshness&#x27;][&#x27;reason&#x27;].lower()</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_tc12_storage_use_soon_wins_when_temperature_exposure_is_not_provided</code> — [source L129](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_tc12_storage_use_soon_wins_when_temperature_exposure_is_not_provided(api_client):
    register_food(api_client, "FG-AGG-12", stored_days=2, expiry_days=10)

    response = post_reading(api_client, food_id="FG-AGG-12", temperature_c=15)

    assert response.json["freshness"]["status"] == "Use Soon"
    assert "storage duration" in response.json["freshness"]["reason"].lower()
~~~

</details>

<a id="tc-fresh-007"></a>

#### TC-FRESH-007 — Short door open warning does not change storage or expiry result

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-007 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Short door open warning does not change storage or expiry result. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>register_food(api_client, &#x27;FG-MULTI&#x27;, stored_days=2, expiry_days=1)</code><br><code>response = post_reading(api_client, food_id=&#x27;FG-MULTI&#x27;, door_open=True, open_duration_seconds=10)</code><br><code>reason = response.json[&#x27;freshness&#x27;][&#x27;reason&#x27;].lower()</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Use Soon&#x27;</code><br><code>&#x27;storage duration&#x27; in reason</code><br><code>&#x27;expiry date&#x27; in reason</code><br><code>&#x27;door&#x27; in reason</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_short_door_open_warning_does_not_change_storage_or_expiry_result</code> — [source L138](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_short_door_open_warning_does_not_change_storage_or_expiry_result(api_client):
    register_food(api_client, "FG-MULTI", stored_days=2, expiry_days=1)

    response = post_reading(
        api_client,
        food_id="FG-MULTI",
        door_open=True,
        open_duration_seconds=10,
    )

    assert response.json["freshness"]["status"] == "Use Soon"
    reason = response.json["freshness"]["reason"].lower()
    assert "storage duration" in reason
    assert "expiry date" in reason
    assert "door" in reason
~~~

</details>

<a id="tc-fresh-008"></a>

#### TC-FRESH-008 — Freshness all sensors normal

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-008 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Freshness all sensors normal. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_freshness(temperature_c=4, humidity_pct=60, gas_raw=330, door_open=False, open_duration_seconds=0)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.FRESH</code><br><code>result.status == FreshnessStatus.FRESH</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_freshness_all_sensors_normal</code> — [source L52](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_freshness_all_sensors_normal():
    result = evaluate_freshness(
        temperature_c=4,
        humidity_pct=60,
        gas_raw=330,
        door_open=False,
        open_duration_seconds=0
    )
    assert result.status == FreshnessStatus.FRESH

    assert result.status == FreshnessStatus.FRESH
~~~

</details>

<a id="tc-fresh-009"></a>

#### TC-FRESH-009 — Storage and expiry aggregate by max

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-009 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Storage and expiry aggregate by max. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>days_stored=4; expiry_offset=2; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>2. <code>days_stored=1; expiry_offset=-1; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>3. <code>days_stored=2; expiry_offset=-1; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>Setup/input cố định: <code>result = evaluate_with_optional_food(&#x27;MEAT&#x27;, days_stored, expiry_offset)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == expected_status</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_storage_and_expiry_aggregate_by_max</code> — [source L152](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("days_stored", "expiry_offset", "expected_status"),
    [
        (4, 2, FreshnessStatus.CHECK_FOOD),
        (1, -1, FreshnessStatus.CHECK_FOOD),
        (2, -1, FreshnessStatus.CHECK_FOOD),
    ],
)
def test_storage_and_expiry_aggregate_by_max(days_stored, expiry_offset, expected_status):
    result = evaluate_with_optional_food(
        "MEAT",
        days_stored,
        expiry_offset,
    )

    assert result.status == expected_status
~~~

</details>

<a id="tc-fresh-010"></a>

#### TC-FRESH-010 — Max severity across rules

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-010 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Max severity across rules. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>temperature_c=10; expiry_offset=None; category=None; days_stored=None; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>2. <code>temperature_c=5; expiry_offset=None; category=&#x27;MEAT&#x27;; days_stored=4; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>3. <code>temperature_c=10; expiry_offset=-1; category=None; days_stored=None; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>Setup/input cố định: <code>result = evaluate_with_optional_food(category, days_stored, expiry_offset, temperature_c=temperature_c)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == expected_status</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_max_severity_across_rules</code> — [source L170](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("temperature_c", "expiry_offset", "category", "days_stored", "expected_status"),
    [
        (10, None, None, None, FreshnessStatus.FRESH),
        (5, None, "MEAT", 4, FreshnessStatus.CHECK_FOOD),
        (10, -1, None, None, FreshnessStatus.CHECK_FOOD),
    ],
)
def test_max_severity_across_rules(
    temperature_c, expiry_offset, category, days_stored, expected_status
):
    result = evaluate_with_optional_food(
        category,
        days_stored,
        expiry_offset,
        temperature_c=temperature_c,
    )

    assert result.status == expected_status
~~~

</details>

<a id="tc-fresh-011"></a>

#### TC-FRESH-011 — All active rules reasons are preserved

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-011 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | All active rules reasons are preserved. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>today = date.today()</code><br><code>result = evaluate_freshness(temperature_c=15, temperature_exposure_hours=3, humidity_pct=None, gas_raw=None, door_open=True, open_duration_seconds=40, category=&#x27;MEAT&#x27;, inserted_at=today - timedelta(days=5), expiry_date=today - timedelta(days=1))</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code><br><code>reason_fragment.lower() in result.reason.lower()</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_all_active_rules_reasons_are_preserved</code> — [source L183](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_all_active_rules_reasons_are_preserved():
    today = date.today()
    result = evaluate_freshness(
        temperature_c=15,
        temperature_exposure_hours=3,
        humidity_pct=None,
        gas_raw=None,
        door_open=True,
        open_duration_seconds=40,
        category="MEAT",
        inserted_at=today - timedelta(days=5),
        expiry_date=today - timedelta(days=1),
    )

    assert result.status == FreshnessStatus.CHECK_FOOD
    for reason_fragment in ("Temperature", "Humidity", "Gas", "Door", "storage duration", "expiry date"):
        assert reason_fragment.lower() in result.reason.lower()
~~~

</details>

<a id="tc-fresh-012"></a>

#### TC-FRESH-012 — Malformed sensor inputs return check food

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-012 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Malformed sensor inputs return check food. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>overrides={&#x27;temperature_c&#x27;: &#x27;abc&#x27;}; expected_reason=&#x27;temperature&#x27;</code><br>2. <code>overrides={&#x27;humidity_pct&#x27;: &#x27;abc&#x27;}; expected_reason=&#x27;humidity&#x27;</code><br>3. <code>overrides={&#x27;gas_raw&#x27;: &#x27;abc&#x27;}; expected_reason=&#x27;gas&#x27;</code><br>4. <code>overrides={&#x27;door_open&#x27;: &#x27;true&#x27;}; expected_reason=&#x27;door&#x27;</code><br>5. <code>overrides={&#x27;door_open&#x27;: True, &#x27;open_duration_seconds&#x27;: &#x27;30&#x27;}; expected_reason=&#x27;duration&#x27;</code><br>6. <code>overrides={&#x27;door_open&#x27;: True, &#x27;open_duration_seconds&#x27;: None}; expected_reason=&#x27;duration&#x27;</code><br>Setup/input cố định: <code>result = evaluate_with_optional_food(**overrides)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code><br><code>expected_reason in result.reason.lower()</code> |
| Actual Result | Level A — 6/6 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_malformed_sensor_inputs_return_check_food</code> — [source L213](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"temperature_c": "abc"}, "temperature"),
        ({"humidity_pct": "abc"}, "humidity"),
        ({"gas_raw": "abc"}, "gas"),
        ({"door_open": "true"}, "door"),
        ({"door_open": True, "open_duration_seconds": "30"}, "duration"),
        ({"door_open": True, "open_duration_seconds": None}, "duration"),
    ],
)
def test_malformed_sensor_inputs_return_check_food(overrides, expected_reason):
    result = evaluate_with_optional_food(**overrides)

    assert result.status == FreshnessStatus.CHECK_FOOD
    assert expected_reason in result.reason.lower()
~~~

</details>

<a id="tc-fresh-013"></a>

#### TC-FRESH-013 — Boolean sensor values are invalid

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-013 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Boolean sensor values are invalid. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>field=&#x27;temperature_c&#x27;; invalid_value=True</code><br>2. <code>field=&#x27;temperature_c&#x27;; invalid_value=False</code><br>3. <code>field=&#x27;humidity_pct&#x27;; invalid_value=True</code><br>4. <code>field=&#x27;humidity_pct&#x27;; invalid_value=False</code><br>5. <code>field=&#x27;gas_raw&#x27;; invalid_value=True</code><br>6. <code>field=&#x27;gas_raw&#x27;; invalid_value=False</code><br>Setup/input cố định: <code>result = evaluate_with_optional_food(**{field: invalid_value})</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code> |
| Actual Result | Level A — 6/6 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_boolean_sensor_values_are_invalid</code> — [source L222](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("invalid_value", [True, False])
@pytest.mark.parametrize("field", ["temperature_c", "humidity_pct", "gas_raw"])
def test_boolean_sensor_values_are_invalid(field, invalid_value):
    result = evaluate_with_optional_food(**{field: invalid_value})

    assert result.status == FreshnessStatus.CHECK_FOOD
~~~

</details>

<a id="tc-fresh-014"></a>

#### TC-FRESH-014 — Non finite or negative sensor data is never fresh

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-014 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Non finite or negative sensor data is never fresh. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>field=&#x27;temperature_c&#x27;; value=nan</code><br>2. <code>field=&#x27;temperature_c&#x27;; value=inf</code><br>3. <code>field=&#x27;humidity_pct&#x27;; value=nan</code><br>4. <code>field=&#x27;humidity_pct&#x27;; value=inf</code><br>5. <code>field=&#x27;gas_raw&#x27;; value=nan</code><br>6. <code>field=&#x27;gas_raw&#x27;; value=inf</code><br>7. <code>field=&#x27;gas_raw&#x27;; value=-1</code><br>Setup/input cố định: <code>result = evaluate_with_optional_food(**{field: value})</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code> |
| Actual Result | Level A — 7/7 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_non_finite_or_negative_sensor_data_is_never_fresh</code> — [source L296](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature_c", float("nan")),
        ("temperature_c", float("inf")),
        ("humidity_pct", float("nan")),
        ("humidity_pct", float("inf")),
        ("gas_raw", float("nan")),
        ("gas_raw", float("inf")),
        ("gas_raw", -1),
    ],
)
def test_non_finite_or_negative_sensor_data_is_never_fresh(field, value):
    result = evaluate_with_optional_food(**{field: value})
    assert result.status == FreshnessStatus.CHECK_FOOD
~~~

</details>

<a id="tc-fresh-015"></a>

#### TC-FRESH-015 — Invalid sensor dominates another rule use soon

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-015 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Invalid sensor dominates another rule use soon. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_with_optional_food(category=&#x27;MEAT&#x27;, days_stored=2, humidity_pct=float(&#x27;nan&#x27;))</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code><br><code>&#x27;humidity&#x27; in result.reason.lower()</code><br><code>&#x27;storage duration&#x27; in result.reason.lower()</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_invalid_sensor_dominates_another_rule_use_soon</code> — [source L301](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_invalid_sensor_dominates_another_rule_use_soon():
    result = evaluate_with_optional_food(
        category="MEAT", days_stored=2, humidity_pct=float("nan")
    )
    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "humidity" in result.reason.lower()
    assert "storage duration" in result.reason.lower()
~~~

</details>

<a id="tc-fresh-016"></a>

#### TC-FRESH-016 — Temperature does not override storage use soon

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-016 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Temperature does not override storage use soon. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_with_optional_food(&#x27;MEAT&#x27;, 2, temperature_c=15)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.USE_SOON</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_temperature_does_not_override_storage_use_soon</code> — [source L340](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_temperature_does_not_override_storage_use_soon():
    result = evaluate_with_optional_food("MEAT", 2, temperature_c=15)
    assert result.status == FreshnessStatus.USE_SOON
~~~

</details>

<a id="tc-fresh-017"></a>

#### TC-FRESH-017 — Cross rule integration

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-017 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Cross rule integration. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>case=&#x27;all_fresh&#x27;; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;; expected_reasons=()</code><br>2. <code>case=&#x27;storage_soon&#x27;; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;; expected_reasons=(&#x27;storage duration&#x27;,)</code><br>3. <code>case=&#x27;expiry_soon&#x27;; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;; expected_reasons=(&#x27;expiry&#x27;,)</code><br>4. <code>case=&#x27;gas_anomaly&#x27;; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;; expected_reasons=(&#x27;gas&#x27;,)</code><br>5. <code>case=&#x27;temperature_exposure&#x27;; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;; expected_reasons=(&#x27;temperature&#x27;,)</code><br>6. <code>case=&#x27;door_timeout&#x27;; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;; expected_reasons=(&#x27;door&#x27;,)</code><br>7. <code>case=&#x27;gas_and_expiry&#x27;; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;; expected_reasons=(&#x27;gas&#x27;, &#x27;expiry&#x27;)</code><br>8. <code>case=&#x27;temperature_and_expiry&#x27;; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;; expected_reasons=(&#x27;temperature&#x27;, &#x27;expiry&#x27;)</code><br>9. <code>case=&#x27;gas_and_storage&#x27;; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;; expected_reasons=(&#x27;gas&#x27;, &#x27;storage duration&#x27;)</code><br>10. <code>case=&#x27;recovered_gas_and_temperature&#x27;; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;; expected_reasons=(&#x27;temperature&#x27;,)</code><br>11. <code>case=&#x27;recovered_gas_and_expiry&#x27;; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;; expected_reasons=(&#x27;expiry&#x27;,)</code><br>12. <code>case=&#x27;humidity_warning_and_storage&#x27;; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;; expected_reasons=(&#x27;low humidity&#x27;, &#x27;storage duration&#x27;)</code><br>13. <code>case=&#x27;humidity_warning_and_gas&#x27;; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;; expected_reasons=(&#x27;low humidity&#x27;, &#x27;gas&#x27;)</code><br>14. <code>case=&#x27;short_door_open_fresh&#x27;; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;; expected_reasons=(&#x27;door&#x27;,)</code><br>15. <code>case=&#x27;short_door_open_storage&#x27;; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;; expected_reasons=(&#x27;door&#x27;, &#x27;storage duration&#x27;)</code><br>Setup/input cố định: <code>today = date.today()</code><br><code>args = {&#x27;temperature_c&#x27;: 5, &#x27;temperature_exposure_hours&#x27;: 0, &#x27;humidity_pct&#x27;: 90, &#x27;gas_raw&#x27;: 100, &#x27;gas_anomaly_active&#x27;: False, &#x27;door_open&#x27;: False, &#x27;open_duration_seconds&#x27;: 0, &#x27;category&#x27;: &#x27;MEAT&#x27;, &#x27;inserted_at&#x27;: today, &#x27;expiry_date&#x27;: today + timedelta(days=2)}</code><br><code>result = evaluate_freshness(**args)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == expected_status</code><br><code>fragment in result.reason.lower()</code> |
| Actual Result | Level A — 15/15 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_cross_rule_integration</code> — [source L365](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("case", "expected_status", "expected_reasons"),
    [
        ("all_fresh", FreshnessStatus.FRESH, ()),
        ("storage_soon", FreshnessStatus.USE_SOON, ("storage duration",)),
        ("expiry_soon", FreshnessStatus.USE_SOON, ("expiry",)),
        ("gas_anomaly", FreshnessStatus.CHECK_FOOD, ("gas",)),
        ("temperature_exposure", FreshnessStatus.CHECK_FOOD, ("temperature",)),
        ("door_timeout", FreshnessStatus.CHECK_FOOD, ("door",)),
        ("gas_and_expiry", FreshnessStatus.CHECK_FOOD, ("gas", "expiry")),
        ("temperature_and_expiry", FreshnessStatus.CHECK_FOOD, ("temperature", "expiry")),
        ("gas_and_storage", FreshnessStatus.CHECK_FOOD, ("gas", "storage duration")),
        ("recovered_gas_and_temperature", FreshnessStatus.CHECK_FOOD, ("temperature",)),
        ("recovered_gas_and_expiry", FreshnessStatus.USE_SOON, ("expiry",)),
        ("humidity_warning_and_storage", FreshnessStatus.USE_SOON, ("low humidity", "storage duration")),
        ("humidity_warning_and_gas", FreshnessStatus.CHECK_FOOD, ("low humidity", "gas")),
        ("short_door_open_fresh", FreshnessStatus.FRESH, ("door",)),
        ("short_door_open_storage", FreshnessStatus.USE_SOON, ("door", "storage duration")),
    ],
)
def test_cross_rule_integration(case, expected_status, expected_reasons):
    today = date.today()
    args = {
        "temperature_c": 5,
        "temperature_exposure_hours": 0,
        "humidity_pct": 90,
        "gas_raw": 100,
        "gas_anomaly_active": False,
        "door_open": False,
        "open_duration_seconds": 0,
        "category": "MEAT",
        "inserted_at": today,
        "expiry_date": today + timedelta(days=2),
    }
    if case in ("storage_soon", "gas_and_storage", "humidity_warning_and_storage", "short_door_open_storage"):
        args["inserted_at"] = today - timedelta(days=2 if args["category"] == "MEAT" else 6)
    if case in ("expiry_soon", "gas_and_expiry", "temperature_and_expiry", "recovered_gas_and_expiry"):
        args["expiry_date"] = today + timedelta(days=1)
    if case in ("gas_anomaly", "gas_and_expiry", "gas_and_storage", "humidity_warning_and_gas"):
        args["gas_anomaly_active"] = True
    if case in ("temperature_exposure", "temperature_and_expiry", "recovered_gas_and_temperature"):
        args["temperature_c"] = 10
        args["temperature_exposure_hours"] = 2.1
    if case == "door_timeout":
        args["door_open"] = True
        args["open_duration_seconds"] = 30
    if case in ("humidity_warning_and_storage", "humidity_warning_and_gas"):
        args["category"] = "VEGETABLE"
        args["humidity_pct"] = 79
        if case == "humidity_warning_and_storage":
            args["inserted_at"] = today - timedelta(days=6)
    if case in ("short_door_open_fresh", "short_door_open_storage"):
        args["door_open"] = True
        args["open_duration_seconds"] = 29

    result = evaluate_freshness(**args)
    assert result.status == expected_status
    for fragment in expected_reasons:
        assert fragment in result.reason.lower()
~~~

</details>

<a id="tc-fresh-018"></a>

#### TC-FRESH-018 — Unknown food category is invalid

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-018 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Unknown food category is invalid. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_with_optional_food(&#x27;UNKNOWN&#x27;, 0)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code><br><code>&#x27;Unknown food category.&#x27; in result.reason</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_unknown_food_category_is_invalid</code> — [source L416](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_unknown_food_category_is_invalid():
    result = evaluate_with_optional_food("UNKNOWN", 0)

    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "Unknown food category." in result.reason
~~~

</details>

<a id="tc-fresh-019"></a>

#### TC-FRESH-019 — Optional food data does not change normal environment

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-019 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Optional food data does not change normal environment. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_with_optional_food()</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.FRESH</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_optional_food_data_does_not_change_normal_environment</code> — [source L430](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_optional_food_data_does_not_change_normal_environment():
    result = evaluate_with_optional_food()

    assert result.status == FreshnessStatus.FRESH
~~~

</details>

<a id="tc-fresh-020"></a>

#### TC-FRESH-020 — Freshness aggregation keeps gas and other rules independent

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-020 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Freshness aggregation keeps gas and other rules independent. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>anomaly = result(gas_anomaly_active=True)</code><br><code>today = date.today()</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>anomaly.status == FreshnessStatus.CHECK_FOOD</code><br><code>&#x27;gas&#x27; in anomaly.reason.lower() and &#x27;baseline&#x27; in anomaly.reason.lower()</code><br><code>result(gas_raw=-1).status == FreshnessStatus.CHECK_FOOD</code><br><code>result(temperature_c=None, gas_anomaly_active=False).status == FreshnessStatus.CHECK_FOOD</code><br><code>result(expiry_date=&#x27;2000-01-01&#x27;, gas_anomaly_active=False).status == FreshnessStatus.CHECK_FOOD</code><br><code>result(category=&#x27;MEAT&#x27;, inserted_at=&#x27;2000-01-01&#x27;, gas_anomaly_active=False).status == FreshnessStatus.CHECK_FOOD</code><br><code>result(category=&#x27;MEAT&#x27;, inserted_at=today, gas_anomaly_active=False).status == FreshnessStatus.FRESH</code><br><code>result(expiry_date=today + timedelta(days=1)).status == FreshnessStatus.USE_SOON</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_freshness_aggregation_keeps_gas_and_other_rules_independent</code> — [source L163](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_freshness_aggregation_keeps_gas_and_other_rules_independent():
    def result(**overrides):
        values = dict(
            temperature_c=5, humidity_pct=60, gas_raw=100,
            door_open=False, open_duration_seconds=0,
        )
        values.update(overrides)
        return evaluate_freshness(**values)

    anomaly = result(gas_anomaly_active=True)
    assert anomaly.status == FreshnessStatus.CHECK_FOOD
    assert "gas" in anomaly.reason.lower() and "baseline" in anomaly.reason.lower()
    assert result(gas_raw=-1).status == FreshnessStatus.CHECK_FOOD
    assert result(temperature_c=None, gas_anomaly_active=False).status == FreshnessStatus.CHECK_FOOD
    assert result(expiry_date="2000-01-01", gas_anomaly_active=False).status == FreshnessStatus.CHECK_FOOD
    assert result(category="MEAT", inserted_at="2000-01-01", gas_anomaly_active=False).status == FreshnessStatus.CHECK_FOOD
    today = date.today()
    assert result(category="MEAT", inserted_at=today, gas_anomaly_active=False).status == FreshnessStatus.FRESH
    assert result(expiry_date=today + timedelta(days=1)).status == FreshnessStatus.USE_SOON
~~~

</details>

<a id="tc-fresh-021"></a>

#### TC-FRESH-021 — Gas recovery leaves other rules to determine final severity

| Field | Value |
|---|---|
| Test Case ID | TC-FRESH-021 |
| Module | Freshness Severity Aggregation — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Gas recovery leaves other rules to determine final severity. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>establish_baseline(gas_db)</code><br><code>result = evaluate_freshness(temperature_c=10, temperature_exposure_hours=2.1, humidity_pct=60, gas_raw=100, gas_anomaly_active=False, door_open=False, category=&#x27;MEAT&#x27;, inserted_at=&#x27;2000-01-01&#x27;, expiry_date=&#x27;2000-01-01&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 1</code><br><code>update(gas_db, 100) is False</code><br><code>result.status == FreshnessStatus.CHECK_FOOD</code><br><code>&#x27;temperature&#x27; in result.reason.lower()</code><br><code>&#x27;storage duration&#x27; in result.reason.lower()</code><br><code>&#x27;expiry date&#x27; in result.reason.lower()</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_gas_recovery_leaves_other_rules_to_determine_final_severity</code> — [source L184](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-FRESH: Chỉ Fresh / Normal (0), Use Soon (1), Check Food (2). Lấy MAX severity; nối reasons; backend là source of truth. Warning reason có thể tồn tại ở severity 0. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_gas_recovery_leaves_other_rules_to_determine_final_severity(gas_db):
    establish_baseline(gas_db)
    for _ in range(3):
        update(gas_db, 130)
    assert state(gas_db)["anomaly_active"] == 1
    assert update(gas_db, 100) is False

    result = evaluate_freshness(
        temperature_c=10, temperature_exposure_hours=2.1,
        humidity_pct=60, gas_raw=100, gas_anomaly_active=False,
        door_open=False, category="MEAT", inserted_at="2000-01-01",
        expiry_date="2000-01-01",
    )
    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "temperature" in result.reason.lower()
    assert "storage duration" in result.reason.lower()
    assert "expiry date" in result.reason.lower()
~~~

</details>

### TEMP — Temperature Exposure

Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode.

<a id="tc-temp-001"></a>

#### TC-TEMP-001 — Temperature fault breaks continuity without resetting exposure

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-001 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Temperature fault breaks continuity without resetting exposure. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>system</code>; [fixture/helper defaults](#fixture-test-cross-system-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>post_reading(system, 0, temperature=6)</code><br><code>post_reading(system, 5, temperature=6)</code><br><code>fault = post_reading(system, 10, temperature=None)</code><br><code>state = rows(system, &#x27;SELECT * FROM temperature_exposure_state&#x27;)[0]</code><br><code>recovery = post_reading(system, 15, temperature=6)</code><br><code>state = rows(system, &#x27;SELECT * FROM temperature_exposure_state&#x27;)[0]</code><br><code>post_reading(system, 20, temperature=6)</code><br><code>sensor_events = rows(system, &quot;SELECT event_type, timestamp FROM events WHERE event_type LIKE &#x27;SENSOR_%&#x27; ORDER BY id&quot;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>fault.status_code == 201</code><br><code>state[&#x27;exposure_seconds&#x27;] == 5</code><br><code>state[&#x27;continuity_broken&#x27;] == 1</code><br><code>&#x27;TEMPERATURE_EXPOSURE_EXCEEDED&#x27; not in event_types(system)</code><br><code>recovery.status_code == 201</code><br><code>state[&#x27;exposure_seconds&#x27;] == 5</code><br><code>state[&#x27;continuity_broken&#x27;] == 0</code><br><code>rows(system, &#x27;SELECT * FROM temperature_exposure_state&#x27;)[0][&#x27;exposure_seconds&#x27;] == 10</code><br><code>[(event[&#x27;event_type&#x27;], event[&#x27;timestamp&#x27;]) for event in sensor_events] == [(&#x27;SENSOR_FAULT&#x27;, timestamp(10)), (&#x27;SENSOR_RECOVERED&#x27;, timestamp(15))]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_cross_system_integration.py::test_temperature_fault_breaks_continuity_without_resetting_exposure</code> — [source L100](../backend/tests/test_cross_system_integration.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_temperature_fault_breaks_continuity_without_resetting_exposure(system):
    post_reading(system, 0, temperature=6)
    post_reading(system, 5, temperature=6)
    fault = post_reading(system, 10, temperature=None)
    assert fault.status_code == 201
    state = rows(system, "SELECT * FROM temperature_exposure_state")[0]
    assert state["exposure_seconds"] == 5
    assert state["continuity_broken"] == 1
    assert "TEMPERATURE_EXPOSURE_EXCEEDED" not in event_types(system)

    recovery = post_reading(system, 15, temperature=6)
    assert recovery.status_code == 201
    state = rows(system, "SELECT * FROM temperature_exposure_state")[0]
    assert state["exposure_seconds"] == 5
    assert state["continuity_broken"] == 0
    post_reading(system, 20, temperature=6)
    assert rows(system, "SELECT * FROM temperature_exposure_state")[0]["exposure_seconds"] == 10
    sensor_events = rows(system,
        "SELECT event_type, timestamp FROM events WHERE event_type LIKE 'SENSOR_%' ORDER BY id")
    assert [(event["event_type"], event["timestamp"]) for event in sensor_events] == [
        ("SENSOR_FAULT", timestamp(10)), ("SENSOR_RECOVERED", timestamp(15))
    ]
~~~

</details>

<a id="tc-temp-002"></a>

#### TC-TEMP-002 — Temperature fresh

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-002 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Temperature fresh. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_temperature(4)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.FRESH</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_temperature_fresh</code> — [source L16](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_temperature_fresh():
    result = evaluate_temperature(4)

    assert result.status == FreshnessStatus.FRESH
~~~

</details>

<a id="tc-temp-003"></a>

#### TC-TEMP-003 — Nhiệt độ 10 C chưa có exposure vẫn Fresh

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-003 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Nhiệt độ 10 C chưa có exposure vẫn Fresh. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_temperature(10)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.FRESH</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_temperature_use_soon</code> — [source L22](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | Tên test lịch sử có chữ use_soon nhưng assertion thực tế là FRESH, không phải Use Soon. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_temperature_use_soon():
    result = evaluate_temperature(10)

    assert result.status == FreshnessStatus.FRESH
~~~

</details>

<a id="tc-temp-004"></a>

#### TC-TEMP-004 — Temperature check food

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-004 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Temperature check food. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_temperature(15, 2.1)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_temperature_check_food</code> — [source L28](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_temperature_check_food():
    result = evaluate_temperature(15, 2.1)

    assert result.status == FreshnessStatus.CHECK_FOOD
~~~

</details>

<a id="tc-temp-005"></a>

#### TC-TEMP-005 — Temperature threshold boundaries

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-005 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Temperature threshold boundaries. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>temperature_c=5; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>2. <code>temperature_c=5.01; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>3. <code>temperature_c=8; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>4. <code>temperature_c=8.01; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>5. <code>temperature_c=12; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>6. <code>temperature_c=12.01; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>Setup/input cố định: <code>result = evaluate_with_optional_food(temperature_c=temperature_c)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == expected_status</code> |
| Actual Result | Level A — 6/6 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_temperature_threshold_boundaries</code> — [source L265](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("temperature_c", "expected_status"),
    [
        (5, FreshnessStatus.FRESH),
        (5.01, FreshnessStatus.FRESH),
        (8, FreshnessStatus.FRESH),
        (8.01, FreshnessStatus.FRESH),
        (12, FreshnessStatus.FRESH),
        (12.01, FreshnessStatus.FRESH),
    ],
)
def test_temperature_threshold_boundaries(temperature_c, expected_status):
    result = evaluate_with_optional_food(temperature_c=temperature_c)

    assert result.status == expected_status
~~~

</details>

<a id="tc-temp-006"></a>

#### TC-TEMP-006 — Temperature exposure rule

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-006 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Temperature exposure rule. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>temperature=5.01</code><br>2. <code>temperature=8</code><br>3. <code>temperature=12</code><br>4. <code>temperature=15</code><br>Setup/input cố định: <code>result = evaluate_temperature(temperature, 2.01)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>evaluate_temperature(temperature, 2).status == FreshnessStatus.FRESH</code><br><code>result.status == FreshnessStatus.CHECK_FOOD</code><br><code>&#x27;exceeded 2 hours&#x27; in result.reason</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_temperature_exposure_rule</code> — [source L272](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("temperature", [5.01, 8, 12, 15])
def test_temperature_exposure_rule(temperature):
    assert evaluate_temperature(temperature, 2).status == FreshnessStatus.FRESH
    result = evaluate_temperature(temperature, 2.01)
    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "exceeded 2 hours" in result.reason
~~~

</details>

<a id="tc-temp-007"></a>

#### TC-TEMP-007 — Pure temperature rule trả Fresh với 4/5 C dù truyền exposure 10h

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-007 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Pure temperature rule trả Fresh với 4/5 C dù truyền exposure 10h. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>evaluate_temperature(5, 10).status == FreshnessStatus.FRESH</code><br><code>evaluate_temperature(4, 10).status == FreshnessStatus.FRESH</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_temperature_recovery_at_or_below_five_resets_exposure</code> — [source L279](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | Không sửa DB state; persistent reset được kiểm tra riêng trong test_temperature_exposure.py. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_temperature_recovery_at_or_below_five_resets_exposure():
    assert evaluate_temperature(5, 10).status == FreshnessStatus.FRESH
    assert evaluate_temperature(4, 10).status == FreshnessStatus.FRESH
~~~

</details>

<a id="tc-temp-008"></a>

#### TC-TEMP-008 — At or below five resets and never emits temperature event

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-008 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | At or below five resets and never emits temperature event. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code><br><code>state_for(temperature_client)[&#x27;exposure_seconds&#x27;] == 0</code><br><code>temperature_events(temperature_client) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_at_or_below_five_resets_and_never_emits_temperature_event</code> — [source L100](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_at_or_below_five_resets_and_never_emits_temperature_event(temperature_client):
    for temperature in (4, 5):
        response = post_temperature(temperature_client, temperature)
        assert response.status_code == 201
        assert response.json["freshness"]["status"] == "Fresh / Normal"
        assert state_for(temperature_client)["exposure_seconds"] == 0
    assert temperature_events(temperature_client) == []
~~~

</details>

<a id="tc-temp-009"></a>

#### TC-TEMP-009 — First hot reading starts exposure without event

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-009 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | First hot reading starts exposure without event. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = post_temperature(temperature_client, 6)</code><br><code>state = state_for(temperature_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code><br><code>state[&#x27;exposure_active&#x27;] == 1</code><br><code>state[&#x27;exposure_seconds&#x27;] == 0</code><br><code>temperature_events(temperature_client) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_first_hot_reading_starts_exposure_without_event</code> — [source L109](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_first_hot_reading_starts_exposure_without_event(temperature_client):
    response = post_temperature(temperature_client, 6)
    assert response.json["freshness"]["status"] == "Fresh / Normal"
    state = state_for(temperature_client)
    assert state["exposure_active"] == 1
    assert state["exposure_seconds"] == 0
    assert temperature_events(temperature_client) == []
~~~

</details>

<a id="tc-temp-010"></a>

#### TC-TEMP-010 — Exposure threshold is strictly greater than two hours

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-010 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Exposure threshold is strictly greater than two hours. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>connection = sqlite3.connect(&#x27;:memory:&#x27;)</code><br><code>connection.row_factory = sqlite3.Row</code><br><code>connection.execute(&quot;CREATE TABLE temperature_exposure_state (\n        device_id TEXT NOT NULL, food_id TEXT NOT NULL DEFAULT &#x27;&#x27;,\n        exposure_seconds REAL NOT NULL DEFAULT 0,\n        exposure_active INTEGER NOT NULL DEFAULT 0,\n        exposure_exceeded INTEGER NOT NULL DEFAULT 0,\n        last_valid_temperature_timestamp TEXT NULL,\n        continuity_broken INTEGER NOT NULL DEFAULT 0,\n        PRIMARY KEY(device_id, food_id)\n    )&quot;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.exposure_seconds == TEMPERATURE_EXPOSURE_LIMIT_SECONDS</code><br><code>result.exceeded_transition is False</code><br><code>result.exposure_seconds == TEMPERATURE_EXPOSURE_LIMIT_SECONDS + 10</code><br><code>result.exceeded_transition is True</code><br><code>result.exceeded_transition is False</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_exposure_threshold_is_strictly_greater_than_two_hours</code> — [source L118](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_exposure_threshold_is_strictly_greater_than_two_hours():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE temperature_exposure_state (
        device_id TEXT NOT NULL, food_id TEXT NOT NULL DEFAULT '',
        exposure_seconds REAL NOT NULL DEFAULT 0,
        exposure_active INTEGER NOT NULL DEFAULT 0,
        exposure_exceeded INTEGER NOT NULL DEFAULT 0,
        last_valid_temperature_timestamp TEXT NULL,
        continuity_broken INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(device_id, food_id)
    )""")
    try:
        update_temperature_exposure(connection, "D", None, 6, iso_time(0))
        result = None
        # Use ten-second intervals up to exactly two hours.
        for second in range(10, TEMPERATURE_EXPOSURE_LIMIT_SECONDS + 1, 10):
            result = update_temperature_exposure(connection, "D", None, 6, iso_time(second))
        assert result.exposure_seconds == TEMPERATURE_EXPOSURE_LIMIT_SECONDS
        assert result.exceeded_transition is False
        result = update_temperature_exposure(
            connection, "D", None, 6, iso_time(TEMPERATURE_EXPOSURE_LIMIT_SECONDS + 10)
        )
        assert result.exposure_seconds == TEMPERATURE_EXPOSURE_LIMIT_SECONDS + 10
        assert result.exceeded_transition is True
        result = update_temperature_exposure(
            connection, "D", None, 6, iso_time(TEMPERATURE_EXPOSURE_LIMIT_SECONDS + 20)
        )
        assert result.exceeded_transition is False
    finally:
        connection.close()
~~~

</details>

<a id="tc-temp-011"></a>

#### TC-TEMP-011 — Backend emits one event on threshold transition and no spam

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-011 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Backend emits one event on threshold transition and no spam. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_exposure_state(temperature_client)</code><br><code>trigger_id = str(uuid.uuid4())</code><br><code>response = post_temperature(temperature_client, 6, seconds=5, reading_id=trigger_id)</code><br><code>events = temperature_events(temperature_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code><br><code>len(events) == 1</code><br><code>events[0][&#x27;event_type&#x27;] == &#x27;TEMPERATURE_EXPOSURE_EXCEEDED&#x27;</code><br><code>events[0][&#x27;timestamp&#x27;] == iso_time(5)</code><br><code>str(uuid.uuid5(uuid.NAMESPACE_URL, f&#x27;freshguard:temperature:TEMP-DEVICE:{trigger_id}:TEMPERATURE_EXPOSURE_EXCEEDED&#x27;)) == events[0][&#x27;event_id&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_backend_emits_one_event_on_threshold_transition_and_no_spam</code> — [source L151](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_backend_emits_one_event_on_threshold_transition_and_no_spam(temperature_client):
    prime_exposure_state(temperature_client)
    trigger_id = str(uuid.uuid4())
    response = post_temperature(
        temperature_client, 6, seconds=5, reading_id=trigger_id
    )
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Check Food"
    for seconds in (10, 15, 20, 25):
        post_temperature(temperature_client, 7, seconds=seconds)
    events = temperature_events(temperature_client)
    assert len(events) == 1
    assert events[0]["event_type"] == "TEMPERATURE_EXPOSURE_EXCEEDED"
    assert events[0]["timestamp"] == iso_time(5)
    assert str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"freshguard:temperature:TEMP-DEVICE:{trigger_id}:TEMPERATURE_EXPOSURE_EXCEEDED",
    )) == events[0]["event_id"]
~~~

</details>

<a id="tc-temp-012"></a>

#### TC-TEMP-012 — Valid normal resets period and allows a later event

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-012 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Valid normal resets period and allows a later event. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_exposure_state(temperature_client, last_seconds=0)</code><br><code>post_temperature(temperature_client, 6, seconds=5)</code><br><code>state = state_for(temperature_client)</code><br><code>post_temperature(temperature_client, 5, seconds=10)</code><br><code>state = state_for(temperature_client)</code><br><code>post_temperature(temperature_client, 6, seconds=15)</code><br><code>connection = db_connect(temperature_client)</code><br><code>post_temperature(temperature_client, 6, seconds=7220)</code><br><code>events = temperature_events(temperature_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>len(temperature_events(temperature_client)) == 1</code><br><code>state[&#x27;exposure_seconds&#x27;] == 7205</code><br><code>state[&#x27;exposure_seconds&#x27;] == 0</code><br><code>state[&#x27;exposure_active&#x27;] == 0</code><br><code>state_for(temperature_client)[&#x27;exposure_seconds&#x27;] == 0</code><br><code>len(events) == 2</code><br><code>events[0][&#x27;event_type&#x27;] == events[1][&#x27;event_type&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_valid_normal_resets_period_and_allows_a_later_event</code> — [source L171](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_valid_normal_resets_period_and_allows_a_later_event(temperature_client):
    prime_exposure_state(temperature_client, last_seconds=0)
    post_temperature(temperature_client, 6, seconds=5)
    assert len(temperature_events(temperature_client)) == 1
    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 7205
    post_temperature(temperature_client, 5, seconds=10)
    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 0
    assert state["exposure_active"] == 0
    post_temperature(temperature_client, 6, seconds=15)
    assert state_for(temperature_client)["exposure_seconds"] == 0

    connection = db_connect(temperature_client)
    try:
        for second in range(25, 7216, 10):
            update_temperature_exposure(
                connection, "TEMP-DEVICE", None, 6, iso_time(second)
            )
        connection.commit()
    finally:
        connection.close()
    post_temperature(temperature_client, 6, seconds=7220)
    events = temperature_events(temperature_client)
    assert len(events) == 2
    assert events[0]["event_type"] == events[1]["event_type"]
~~~

</details>

<a id="tc-temp-013"></a>

#### TC-TEMP-013 — Invalid temperature preserves exposure and breaks continuity

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-013 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Invalid temperature preserves exposure and breaks continuity. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_exposure_state(temperature_client, exposure_seconds=400)</code><br><code>invalid = post_temperature(temperature_client, None, seconds=5)</code><br><code>after_invalid = state_for(temperature_client)</code><br><code>post_temperature(temperature_client, 6, seconds=10)</code><br><code>post_temperature(temperature_client, 6, seconds=15)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>invalid.status_code == 201</code><br><code>after_invalid[&#x27;exposure_seconds&#x27;] == 400</code><br><code>after_invalid[&#x27;continuity_broken&#x27;] == 1</code><br><code>state_for(temperature_client)[&#x27;exposure_seconds&#x27;] == 400</code><br><code>state_for(temperature_client)[&#x27;exposure_seconds&#x27;] == 405</code><br><code>temperature_events(temperature_client) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_invalid_temperature_preserves_exposure_and_breaks_continuity</code> — [source L199](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_invalid_temperature_preserves_exposure_and_breaks_continuity(temperature_client):
    prime_exposure_state(temperature_client, exposure_seconds=400)
    invalid = post_temperature(temperature_client, None, seconds=5)
    assert invalid.status_code == 201
    after_invalid = state_for(temperature_client)
    assert after_invalid["exposure_seconds"] == 400
    assert after_invalid["continuity_broken"] == 1
    post_temperature(temperature_client, 6, seconds=10)
    assert state_for(temperature_client)["exposure_seconds"] == 400
    post_temperature(temperature_client, 6, seconds=15)
    assert state_for(temperature_client)["exposure_seconds"] == 405
    assert temperature_events(temperature_client) == []
~~~

</details>

<a id="tc-temp-014"></a>

#### TC-TEMP-014 — Rejected invalid temperature values do not reset exposure

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-014 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Rejected invalid temperature values do not reset exposure. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | 1. <code>invalid=True</code><br>2. <code>invalid=False</code><br>3. <code>invalid=nan</code><br>4. <code>invalid=inf</code><br>5. <code>invalid=-inf</code><br>Setup/input cố định: <code>prime_exposure_state(temperature_client, exposure_seconds=400)</code><br><code>response = post_temperature(temperature_client, invalid, seconds=5)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>state_for(temperature_client)[&#x27;exposure_seconds&#x27;] == 400</code><br><code>temperature_events(temperature_client) == []</code> |
| Actual Result | Level A — 5/5 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_rejected_invalid_temperature_values_do_not_reset_exposure</code> — [source L214](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("invalid", [True, False, float("nan"), float("inf"), -float("inf")])
def test_rejected_invalid_temperature_values_do_not_reset_exposure(temperature_client, invalid):
    prime_exposure_state(temperature_client, exposure_seconds=400)
    response = post_temperature(temperature_client, invalid, seconds=5)
    assert response.status_code == 400
    assert state_for(temperature_client)["exposure_seconds"] == 400
    assert temperature_events(temperature_client) == []
~~~

</details>

<a id="tc-temp-015"></a>

#### TC-TEMP-015 — Long reading gap is not counted as observed exposure

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-015 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Long reading gap is not counted as observed exposure. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>post_temperature(temperature_client, 6, seconds=0)</code><br><code>post_temperature(temperature_client, 6, seconds=3 * 60 * 60)</code><br><code>state = state_for(temperature_client)</code><br><code>post_temperature(temperature_client, 6, seconds=3 * 60 * 60 + 5)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>state[&#x27;exposure_seconds&#x27;] == 0</code><br><code>state_for(temperature_client)[&#x27;exposure_seconds&#x27;] == 5</code><br><code>temperature_events(temperature_client) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_long_reading_gap_is_not_counted_as_observed_exposure</code> — [source L222](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_long_reading_gap_is_not_counted_as_observed_exposure(temperature_client):
    post_temperature(temperature_client, 6, seconds=0)
    post_temperature(temperature_client, 6, seconds=3 * 60 * 60)
    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 0
    post_temperature(temperature_client, 6, seconds=3 * 60 * 60 + 5)
    assert state_for(temperature_client)["exposure_seconds"] == 5
    assert temperature_events(temperature_client) == []
~~~

</details>

<a id="tc-temp-016"></a>

#### TC-TEMP-016 — Out of order reading does not corrupt exposure state

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-016 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Out of order reading does not corrupt exposure state. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_exposure_state(temperature_client, exposure_seconds=100, last_seconds=20)</code><br><code>post_temperature(temperature_client, 6, seconds=10)</code><br><code>state = state_for(temperature_client)</code><br><code>post_temperature(temperature_client, 6, seconds=25)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>state[&#x27;exposure_seconds&#x27;] == 100</code><br><code>state[&#x27;last_valid_temperature_timestamp&#x27;] == iso_time(20)</code><br><code>state_for(temperature_client)[&#x27;exposure_seconds&#x27;] == 105</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_out_of_order_reading_does_not_corrupt_exposure_state</code> — [source L232](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_out_of_order_reading_does_not_corrupt_exposure_state(temperature_client):
    prime_exposure_state(temperature_client, exposure_seconds=100, last_seconds=20)
    post_temperature(temperature_client, 6, seconds=10)
    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 100
    assert state["last_valid_temperature_timestamp"] == iso_time(20)
    post_temperature(temperature_client, 6, seconds=25)
    assert state_for(temperature_client)["exposure_seconds"] == 105
~~~

</details>

<a id="tc-temp-017"></a>

#### TC-TEMP-017 — Exposure state survives new client and is scoped by device food

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-017 |
| Module | Temperature Exposure — [backend/app/services/temperature_exposure.py](../backend/app/services/temperature_exposure.py); [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Exposure state survives new client and is scoped by device food. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_exposure_state(temperature_client, device=&#x27;A&#x27;, food_id=&#x27;food-A&#x27;, exposure_seconds=90)</code><br><code>restarted_client = temperature_client.application.test_client()</code><br><code>post_temperature(restarted_client, 6, seconds=5, device=&#x27;A&#x27;, food_id=&#x27;food-A&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>state_for(restarted_client, &#x27;A&#x27;, &#x27;food-A&#x27;)[&#x27;exposure_seconds&#x27;] == 95</code><br><code>state_for(restarted_client, &#x27;A&#x27;, &#x27;food-B&#x27;) is None</code><br><code>state_for(restarted_client, &#x27;B&#x27;, &#x27;food-A&#x27;) is None</code><br><code>state_for(restarted_client, &#x27;A&#x27;, None) is None</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_exposure_state_survives_new_client_and_is_scoped_by_device_food</code> — [source L276](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-TEMP: Hot >5 C; cộng gap giữa hot readings hợp lệ khi 0<gap<=10s; >7200s mới exceeded. <=5 C ở timestamp mới reset; gap/null không cộng và giữ exposure, null ngắt continuity; timestamp bằng/cũ hơn valid gần nhất không đổi state. Một TEMPERATURE_EXPOSURE_EXCEEDED mỗi episode. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_exposure_state_survives_new_client_and_is_scoped_by_device_food(temperature_client):
    for food_id in ("food-A", "food-B"):
        response = temperature_client.post("/api/v1/foods", json={
            "food_id": food_id, "food_name": food_id, "category": "MEAT",
            "inserted_at": "2026-09-26", "expiry_date": "2027-09-26",
        })
        assert response.status_code == 201
    prime_exposure_state(
        temperature_client, device="A", food_id="food-A", exposure_seconds=90
    )
    restarted_client = temperature_client.application.test_client()
    post_temperature(restarted_client, 6, seconds=5, device="A", food_id="food-A")
    assert state_for(restarted_client, "A", "food-A")["exposure_seconds"] == 95
    assert state_for(restarted_client, "A", "food-B") is None
    assert state_for(restarted_client, "B", "food-A") is None
    assert state_for(restarted_client, "A", None) is None
~~~

</details>

<a id="tc-temp-018"></a>

#### TC-TEMP-018 — Timestamp bằng nhau không reset/cộng exposure

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-018 |
| Module | Temperature Exposure |
| Test Type | Manual |
| Priority | High |
| Objective | Timestamp bằng nhau không reset/cộng exposure |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Prime exposure 100s, last valid=t20; gửi 6 C rồi 5 C tại t20 với UUID khác. |
| Steps | Dùng DB tạm; so state trước/sau từng reading. |
| Expected Result | Reading có thể lưu, temperature state không đổi; exposure vẫn 100, timestamp t20. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-TEMP; backend/app/services/temperature_exposure.py::update_temperature_exposure |
| Notes | Automation stale hiện dùng t10 < t20; equal timestamp chưa có assertion riêng. |

<a id="tc-temp-019"></a>

#### TC-TEMP-019 — Gap dài bảo toàn exposure đã tích lũy

| Field | Value |
|---|---|
| Test Case ID | TC-TEMP-019 |
| Module | Temperature Exposure |
| Test Type | Manual |
| Priority | High |
| Objective | Gap dài bảo toàn exposure đã tích lũy |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Prime 400s, hot tại t0; hot tại t11 rồi t16. |
| Steps | POST hai readings và đọc state. |
| Expected Result | Gap 11s không cộng, vẫn 400; gap kế 5s cộng thành 405; không reset. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-TEMP; backend/app/services/temperature_exposure.py::update_temperature_exposure |
| Notes | Automated long-gap bắt đầu từ 0; ca này kiểm tra preservation với số dương. |

### GAS — Gas Baseline & Anomaly

10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận.

<a id="tc-gas-001"></a>

#### TC-GAS-001 — Baseline is average of first ten valid readings and stays fixed

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-001 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Baseline is average of first ten valid readings and stays fixed. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>row = state(gas_db)</code><br><code>update(gas_db, 1000)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>row[&#x27;baseline_sample_count&#x27;] == 10</code><br><code>row[&#x27;baseline&#x27;] == pytest.approx(55)</code><br><code>state(gas_db)[&#x27;baseline&#x27;] == pytest.approx(55)</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_baseline_is_average_of_first_ten_valid_readings_and_stays_fixed</code> — [source L51](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_baseline_is_average_of_first_ten_valid_readings_and_stays_fixed(gas_db):
    for value in range(10, 110, 10):
        update(gas_db, value)
    row = state(gas_db)
    assert row["baseline_sample_count"] == 10
    assert row["baseline"] == pytest.approx(55)
    update(gas_db, 1000)
    assert state(gas_db)["baseline"] == pytest.approx(55)
~~~

</details>

<a id="tc-gas-002"></a>

#### TC-GAS-002 — Incomplete baseline does not flag anomaly

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-002 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Incomplete baseline does not flag anomaly. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>update(gas_db, 100) is False</code><br><code>state(gas_db)[&#x27;baseline&#x27;] is None</code><br><code>state(gas_db)[&#x27;baseline_sample_count&#x27;] == 9</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_incomplete_baseline_does_not_flag_anomaly</code> — [source L61](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_incomplete_baseline_does_not_flag_anomaly(gas_db):
    for _ in range(GAS_BASELINE_SAMPLE_COUNT - 1):
        assert update(gas_db, 100) is False
    assert state(gas_db)["baseline"] is None
    assert state(gas_db)["baseline_sample_count"] == 9
~~~

</details>

<a id="tc-gas-003"></a>

#### TC-GAS-003 — Zero baseline is not used for relative deviation

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-003 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Zero baseline is not used for relative deviation. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>establish_baseline(gas_db, value=0)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>update(gas_db, 10000) is False</code><br><code>state(gas_db)[&#x27;baseline&#x27;] == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_zero_baseline_is_not_used_for_relative_deviation</code> — [source L68](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_zero_baseline_is_not_used_for_relative_deviation(gas_db):
    establish_baseline(gas_db, value=0)
    for _ in range(5):
        assert update(gas_db, 10000) is False
    assert state(gas_db)["baseline"] == 0
~~~

</details>

<a id="tc-gas-004"></a>

#### TC-GAS-004 — Relative deviation candidate threshold

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-004 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Relative deviation candidate threshold. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | 1. <code>value=129.99; candidate=False</code><br>2. <code>value=130; candidate=True</code><br>3. <code>value=150; candidate=True</code><br>4. <code>value=50; candidate=False</code><br>Setup/input cố định: <code>establish_baseline(gas_db)</code><br><code>active = update(gas_db, value)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>active is False</code><br><code>GAS_ANOMALY_DEVIATION == 0.3</code><br><code>state(gas_db)[&#x27;consecutive_anomaly_count&#x27;] == int(candidate)</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_relative_deviation_candidate_threshold</code> — [source L79](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("value", "candidate"),
    [(129.99, False), (130, True), (150, True), (50, False)],
)
def test_relative_deviation_candidate_threshold(gas_db, value, candidate):
    establish_baseline(gas_db)
    active = update(gas_db, value)
    assert active is False
    assert GAS_ANOMALY_DEVIATION == 0.30
    assert state(gas_db)["consecutive_anomaly_count"] == int(candidate)
~~~

</details>

<a id="tc-gas-005"></a>

#### TC-GAS-005 — Three consecutive candidates activate and normal clears

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-005 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Three consecutive candidates activate and normal clears. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>establish_baseline(gas_db)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>[update(gas_db, 130) for _ in range(3)] == [False, False, True]</code><br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 1</code><br><code>update(gas_db, 100) is False</code><br><code>state(gas_db)[&#x27;consecutive_anomaly_count&#x27;] == 0</code><br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 0</code><br><code>GAS_REQUIRED_CONSECUTIVE_READINGS == 3</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_three_consecutive_candidates_activate_and_normal_clears</code> — [source L87](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_three_consecutive_candidates_activate_and_normal_clears(gas_db):
    establish_baseline(gas_db)
    assert [update(gas_db, 130) for _ in range(3)] == [False, False, True]
    assert state(gas_db)["anomaly_active"] == 1
    assert update(gas_db, 100) is False
    assert state(gas_db)["consecutive_anomaly_count"] == 0
    assert state(gas_db)["anomaly_active"] == 0
    assert GAS_REQUIRED_CONSECUTIVE_READINGS == 3
~~~

</details>

<a id="tc-gas-006"></a>

#### TC-GAS-006 — Active anomaly remains active while readings keep exceeding threshold

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-006 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Active anomaly remains active while readings keep exceeding threshold. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>establish_baseline(gas_db)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>active is True</code><br><code>state(gas_db)[&#x27;consecutive_anomaly_count&#x27;] == 4</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_active_anomaly_remains_active_while_readings_keep_exceeding_threshold</code> — [source L97](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_active_anomaly_remains_active_while_readings_keep_exceeding_threshold(gas_db):
    establish_baseline(gas_db)
    for _ in range(4):
        active = update(gas_db, 130)
    assert active is True
    assert state(gas_db)["consecutive_anomaly_count"] == 4
~~~

</details>

<a id="tc-gas-007"></a>

#### TC-GAS-007 — Active anomaly survives invalid and anomalous interleaving

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-007 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Active anomaly survives invalid and anomalous interleaving. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>establish_baseline(gas_db)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 1</code><br><code>update(gas_db, invalid) is True</code><br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 1</code><br><code>update(gas_db, 130) is True</code><br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 1</code><br><code>update(gas_db, 90) is False</code><br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_active_anomaly_survives_invalid_and_anomalous_interleaving</code> — [source L105](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_active_anomaly_survives_invalid_and_anomalous_interleaving(gas_db):
    establish_baseline(gas_db)
    for _ in range(3):
        update(gas_db, 130)
    assert state(gas_db)["anomaly_active"] == 1

    for invalid in (None, -1, None):
        assert update(gas_db, invalid) is True
        assert state(gas_db)["anomaly_active"] == 1
        assert update(gas_db, 130) is True
        assert state(gas_db)["anomaly_active"] == 1

    assert update(gas_db, 90) is False
    assert state(gas_db)["anomaly_active"] == 0
~~~

</details>

<a id="tc-gas-008"></a>

#### TC-GAS-008 — Anomaly gap resets count and requires three again

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-008 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Anomaly gap resets count and requires three again. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>establish_baseline(gas_db)</code><br><code>update(gas_db, 130)</code><br><code>update(gas_db, 130)</code><br><code>update(gas_db, 129)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>state(gas_db)[&#x27;consecutive_anomaly_count&#x27;] == 0</code><br><code>[update(gas_db, 130) for _ in range(3)] == [False, False, True]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_anomaly_gap_resets_count_and_requires_three_again</code> — [source L121](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_anomaly_gap_resets_count_and_requires_three_again(gas_db):
    establish_baseline(gas_db)
    update(gas_db, 130)
    update(gas_db, 130)
    update(gas_db, 129)
    assert state(gas_db)["consecutive_anomaly_count"] == 0
    assert [update(gas_db, 130) for _ in range(3)] == [False, False, True]
~~~

</details>

<a id="tc-gas-009"></a>

#### TC-GAS-009 — Contexts are isolated by device and food

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-009 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Contexts are isolated by device and food. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>establish_baseline(gas_db)</code><br><code>establish_baseline(gas_db, value=200, device=&#x27;device-a&#x27;, food=&#x27;food-b&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>update(gas_db, 130) is False</code><br><code>state(gas_db, device=&#x27;device-b&#x27;, food=&#x27;food-a&#x27;) is None</code><br><code>update(gas_db, 130, device=&#x27;device-b&#x27;, food=&#x27;food-a&#x27;) is False</code><br><code>state(gas_db, device=&#x27;device-a&#x27;, food=&#x27;food-b&#x27;)[&#x27;baseline&#x27;] == 200</code><br><code>state(gas_db, device=&#x27;device-a&#x27;, food=&#x27;food-a&#x27;)[&#x27;baseline&#x27;] == 100</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_contexts_are_isolated_by_device_and_food</code> — [source L130](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_contexts_are_isolated_by_device_and_food(gas_db):
    establish_baseline(gas_db)
    assert update(gas_db, 130) is False
    assert state(gas_db, device="device-b", food="food-a") is None
    assert update(gas_db, 130, device="device-b", food="food-a") is False

    establish_baseline(gas_db, value=200, device="device-a", food="food-b")
    assert state(gas_db, device="device-a", food="food-b")["baseline"] == 200
    assert state(gas_db, device="device-a", food="food-a")["baseline"] == 100
~~~

</details>

<a id="tc-gas-010"></a>

#### TC-GAS-010 — Invalid gas sau baseline hoàn chỉnh xóa candidate streak, không kích hoạt anomaly

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-010 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Invalid gas sau baseline hoàn chỉnh xóa candidate streak, không kích hoạt anomaly. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | 1. <code>invalid=None</code><br>2. <code>invalid=True</code><br>3. <code>invalid=False</code><br>4. <code>invalid=nan</code><br>5. <code>invalid=inf</code><br>6. <code>invalid=-inf</code><br>7. <code>invalid=-1</code><br>Setup/input cố định: <code>establish_baseline(gas_db)</code><br><code>update(gas_db, 130)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>update(gas_db, invalid) is False</code><br><code>state(gas_db)[&#x27;baseline_sample_count&#x27;] == 10</code><br><code>state(gas_db)[&#x27;consecutive_anomaly_count&#x27;] == 0</code> |
| Actual Result | Level A — 7/7 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_invalid_gas_does_not_seed_baseline_or_activate_anomaly</code> — [source L142](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | Test thiết lập đủ baseline trước invalid; chưa chứng minh invalid bị bỏ qua khi baseline đang thu mẫu. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("invalid", [None, True, False, float("nan"), float("inf"), -float("inf"), -1])
def test_invalid_gas_does_not_seed_baseline_or_activate_anomaly(gas_db, invalid):
    establish_baseline(gas_db)
    update(gas_db, 130)
    assert update(gas_db, invalid) is False
    assert state(gas_db)["baseline_sample_count"] == 10
    assert state(gas_db)["consecutive_anomaly_count"] == 0
~~~

</details>

<a id="tc-gas-011"></a>

#### TC-GAS-011 — Invalid gas preserves an active anomaly

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-011 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Invalid gas preserves an active anomaly. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>gas_db</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | 1. <code>invalid=None</code><br>2. <code>invalid=True</code><br>3. <code>invalid=False</code><br>4. <code>invalid=nan</code><br>5. <code>invalid=inf</code><br>6. <code>invalid=-inf</code><br>7. <code>invalid=-1</code><br>Setup/input cố định: <code>establish_baseline(gas_db)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 1</code><br><code>update(gas_db, invalid) is True</code><br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 1</code><br><code>state(gas_db)[&#x27;consecutive_anomaly_count&#x27;] == 0</code><br><code>update(gas_db, 100) is False</code><br><code>state(gas_db)[&#x27;anomaly_active&#x27;] == 0</code> |
| Actual Result | Level A — 7/7 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_invalid_gas_preserves_an_active_anomaly</code> — [source L151](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("invalid", [None, True, False, float("nan"), float("inf"), -float("inf"), -1])
def test_invalid_gas_preserves_an_active_anomaly(gas_db, invalid):
    establish_baseline(gas_db)
    for _ in range(3):
        update(gas_db, 130)
    assert state(gas_db)["anomaly_active"] == 1
    assert update(gas_db, invalid) is True
    assert state(gas_db)["anomaly_active"] == 1
    assert state(gas_db)["consecutive_anomaly_count"] == 0
    assert update(gas_db, 100) is False
    assert state(gas_db)["anomaly_active"] == 0
~~~

</details>

<a id="tc-gas-012"></a>

#### TC-GAS-012 — Api activates after ten baseline and three anomaly readings

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-012 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Api activates after ten baseline and three anomaly readings. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>active = post_gas(api_client, 130)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>post_gas(api_client, 100).json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code><br><code>post_gas(api_client, 130).json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code><br><code>post_gas(api_client, 130).json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code><br><code>active.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code><br><code>&#x27;gas&#x27; in active.json[&#x27;freshness&#x27;][&#x27;reason&#x27;].lower()</code><br><code>api_client.get(&#x27;/api/v1/readings/latest&#x27;).json[&#x27;data&#x27;][&#x27;freshness&#x27;] == active.json[&#x27;freshness&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_api_activates_after_ten_baseline_and_three_anomaly_readings</code> — [source L267](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_api_activates_after_ten_baseline_and_three_anomaly_readings(api_client):
    for _ in range(10):
        assert post_gas(api_client, 100).json["freshness"]["status"] == "Fresh / Normal"
    assert post_gas(api_client, 130).json["freshness"]["status"] == "Fresh / Normal"
    assert post_gas(api_client, 130).json["freshness"]["status"] == "Fresh / Normal"
    active = post_gas(api_client, 130)
    assert active.json["freshness"]["status"] == "Check Food"
    assert "gas" in active.json["freshness"]["reason"].lower()
    assert api_client.get("/api/v1/readings/latest").json["data"]["freshness"] == active.json["freshness"]
~~~

</details>

<a id="tc-gas-013"></a>

#### TC-GAS-013 — Gas recovery trở về Fresh trong môi trường không có rule khác active

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-013 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Gas recovery trở về Fresh trong môi trường không có rule khác active. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>recovered = post_gas(api_client, 100)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>recovered.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_api_gas_recovery_does_not_clear_other_freshness_conditions</code> — [source L278](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | Tên rộng hơn assertion: test này không bật rule freshness khác; xem unit test gas_recovery_leaves_other_rules_to_determine_final_severity. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_api_gas_recovery_does_not_clear_other_freshness_conditions(api_client):
    for _ in range(10):
        post_gas(api_client, 100)
    for _ in range(3):
        post_gas(api_client, 130)
    recovered = post_gas(api_client, 100)
    assert recovered.json["freshness"]["status"] == "Fresh / Normal"
~~~

</details>

<a id="tc-gas-014"></a>

#### TC-GAS-014 — Api gas context separates devices and foods

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-014 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Api gas context separates devices and foods. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = api_client.post(&#x27;/api/v1/foods&#x27;, json={&#x27;food_id&#x27;: &#x27;food-B&#x27;, &#x27;food_name&#x27;: &#x27;Food B&#x27;, &#x27;category&#x27;: &#x27;MEAT&#x27;, &#x27;inserted_at&#x27;: &#x27;2026-09-26&#x27;, &#x27;expiry_date&#x27;: &#x27;2027-09-26&#x27;})</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>post_gas(api_client, 130, device=&#x27;B&#x27;).json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code><br><code>post_gas(api_client, 130, food_id=&#x27;food-B&#x27;, device=&#x27;A&#x27;).json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_api_gas_context_separates_devices_and_foods</code> — [source L287](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_api_gas_context_separates_devices_and_foods(api_client):
    response = api_client.post("/api/v1/foods", json={
        "food_id": "food-B", "food_name": "Food B", "category": "MEAT",
        "inserted_at": "2026-09-26", "expiry_date": "2027-09-26",
    })
    assert response.status_code == 201
    for _ in range(10):
        post_gas(api_client, 100, device="A")
    for _ in range(3):
        post_gas(api_client, 130, device="A")
    assert post_gas(api_client, 130, device="B").json["freshness"]["status"] == "Fresh / Normal"
    assert post_gas(api_client, 130, food_id="food-B", device="A").json["freshness"]["status"] == "Fresh / Normal"
~~~

</details>

<a id="tc-gas-015"></a>

#### TC-GAS-015 — Api emits only start and recovery state transitions

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-015 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Api emits only start and recovery state transitions. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_and_activate(api_client)</code><br><code>events = gas_events(api_client)</code><br><code>recovered = post_gas(api_client, 100, timestamp=&#x27;2026-09-26T12:30:00+07:00&#x27;)</code><br><code>post_gas(api_client, 100)</code><br><code>post_gas(api_client, 100)</code><br><code>events = gas_events(api_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>[event[&#x27;event_type&#x27;] for event in events] == [&#x27;GAS_ANOMALY_STARTED&#x27;]</code><br><code>[event[&#x27;event_type&#x27;] for event in events] == [&#x27;GAS_ANOMALY_STARTED&#x27;, &#x27;GAS_ANOMALY_RECOVERED&#x27;]</code><br><code>events[1][&#x27;timestamp&#x27;] == &#x27;2026-09-26T12:30:00+07:00&#x27;</code><br><code>recovered.status_code == 201</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_api_emits_only_start_and_recovery_state_transitions</code> — [source L301](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_api_emits_only_start_and_recovery_state_transitions(api_client):
    prime_and_activate(api_client)
    for _ in range(120):
        post_gas(api_client, 130)
    events = gas_events(api_client)
    assert [event["event_type"] for event in events] == ["GAS_ANOMALY_STARTED"]

    recovered = post_gas(api_client, 100, timestamp="2026-09-26T12:30:00+07:00")
    post_gas(api_client, 100)
    post_gas(api_client, 100)
    events = gas_events(api_client)
    assert [event["event_type"] for event in events] == [
        "GAS_ANOMALY_STARTED", "GAS_ANOMALY_RECOVERED"
    ]
    assert events[1]["timestamp"] == "2026-09-26T12:30:00+07:00"
    assert recovered.status_code == 201
~~~

</details>

<a id="tc-gas-016"></a>

#### TC-GAS-016 — Api invalid gas does not recover but valid normal does

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-016 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Api invalid gas does not recover but valid normal does. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_and_activate(api_client)</code><br><code>post_gas(api_client, 100)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>gas_state(api_client)[&#x27;anomaly_active&#x27;] == 1</code><br><code>[event[&#x27;event_type&#x27;] for event in gas_events(api_client)] == [&#x27;GAS_ANOMALY_STARTED&#x27;]</code><br><code>response.status_code == 201</code><br><code>gas_state(api_client)[&#x27;anomaly_active&#x27;] == 1</code><br><code>[event[&#x27;event_type&#x27;] for event in gas_events(api_client)] == [&#x27;GAS_ANOMALY_STARTED&#x27;]</code><br><code>[event[&#x27;event_type&#x27;] for event in gas_events(api_client)] == [&#x27;GAS_ANOMALY_STARTED&#x27;, &#x27;GAS_ANOMALY_RECOVERED&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_api_invalid_gas_does_not_recover_but_valid_normal_does</code> — [source L319](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_api_invalid_gas_does_not_recover_but_valid_normal_does(api_client):
    prime_and_activate(api_client)
    for invalid in (None, -1):
        response = post_gas(api_client, invalid)
        assert response.status_code == 201
        assert gas_state(api_client)["anomaly_active"] == 1
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]
    for value in (130, None, 130):
        response = post_gas(api_client, value)
        assert response.status_code == 201
        assert gas_state(api_client)["anomaly_active"] == 1
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]
    post_gas(api_client, 100)
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED", "GAS_ANOMALY_RECOVERED"
    ]
~~~

</details>

<a id="tc-gas-017"></a>

#### TC-GAS-017 — Api rejects invalid gas values before state transition

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-017 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Api rejects invalid gas values before state transition. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | 1. <code>invalid=True</code><br>2. <code>invalid=False</code><br>3. <code>invalid=nan</code><br>4. <code>invalid=inf</code><br>5. <code>invalid=-inf</code><br>Setup/input cố định: <code>prime_and_activate(api_client)</code><br><code>response = post_gas(api_client, invalid)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>[event[&#x27;event_type&#x27;] for event in gas_events(api_client)] == [&#x27;GAS_ANOMALY_STARTED&#x27;]</code> |
| Actual Result | Level A — 5/5 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_api_rejects_invalid_gas_values_before_state_transition</code> — [source L342](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("invalid", [True, False, float("nan"), float("inf"), -float("inf")])
def test_api_rejects_invalid_gas_values_before_state_transition(api_client, invalid):
    prime_and_activate(api_client)
    response = post_gas(api_client, invalid)
    assert response.status_code == 400
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]
~~~

</details>

<a id="tc-gas-018"></a>

#### TC-GAS-018 — Api gas events are isolated by food and none context

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-018 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Api gas events are isolated by food and none context. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_and_activate(api_client, food_id=&#x27;food-A&#x27;, device=&#x27;same-device&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>[event[&#x27;event_type&#x27;] for event in gas_events(api_client)] == [&#x27;GAS_ANOMALY_STARTED&#x27;]</code><br><code>[event[&#x27;event_type&#x27;] for event in gas_events(api_client)] == [&#x27;GAS_ANOMALY_STARTED&#x27;, &#x27;GAS_ANOMALY_STARTED&#x27;, &#x27;GAS_ANOMALY_STARTED&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_api_gas_events_are_isolated_by_food_and_none_context</code> — [source L376](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_api_gas_events_are_isolated_by_food_and_none_context(api_client):
    for food_id in ("food-A", "food-B"):
        response = api_client.post("/api/v1/foods", json={
            "food_id": food_id, "food_name": food_id, "category": "MEAT",
            "inserted_at": "2026-09-26", "expiry_date": "2027-09-26",
        })
        assert response.status_code == 201
    prime_and_activate(api_client, food_id="food-A", device="same-device")
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]
    for food_id in ("food-B", None):
        for _ in range(10):
            post_gas(api_client, 100, food_id=food_id, device="same-device")
        for _ in range(3):
            post_gas(api_client, 130, food_id=food_id, device="same-device")
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED", "GAS_ANOMALY_STARTED", "GAS_ANOMALY_STARTED"
    ]
~~~

</details>

<a id="tc-gas-019"></a>

#### TC-GAS-019 — Api waits for third consecutive anomaly before start event

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-019 |
| Module | Gas Baseline & Anomaly — [backend/app/services/gas_anomaly.py](../backend/app/services/gas_anomaly.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Api waits for third consecutive anomaly before start event. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-gas-anomaly); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>post_gas(api_client, 130)</code><br><code>post_gas(api_client, 130)</code><br><code>post_gas(api_client, 130)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>gas_events(api_client) == []</code><br><code>[event[&#x27;event_type&#x27;] for event in gas_events(api_client)] == [&#x27;GAS_ANOMALY_STARTED&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_gas_anomaly.py::test_api_waits_for_third_consecutive_anomaly_before_start_event</code> — [source L397](../backend/tests/test_gas_anomaly.py) |
| Requirement / Rule | R-GAS: 10 mẫu hợp lệ đầu lập baseline trung bình cố định theo device/food. Deviation >=30%, 3 consecutive -> active/start event; một valid dưới ngưỡng -> recovery. Invalid/null reset streak nhưng không clear active. Baseline 0 không rebaseline. State theo thứ tự nhận. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_api_waits_for_third_consecutive_anomaly_before_start_event(api_client):
    for _ in range(10):
        post_gas(api_client, 100)
    post_gas(api_client, 130)
    post_gas(api_client, 130)
    assert gas_events(api_client) == []
    post_gas(api_client, 130)
    assert [event["event_type"] for event in gas_events(api_client)] == [
        "GAS_ANOMALY_STARTED"
    ]
~~~

</details>

<a id="tc-gas-020"></a>

#### TC-GAS-020 — Invalid xen kẽ trong 10 mẫu baseline đầu

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-020 |
| Module | Gas Baseline & Anomaly |
| Test Type | Manual |
| Priority | High |
| Objective | Invalid xen kẽ trong 10 mẫu baseline đầu |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Các mẫu 100 xen None/-1 khi sample_count<10; đủ tổng cộng 10 mẫu valid. |
| Steps | Gửi từng mẫu với UUID mới; kiểm tra sample_count/sum/baseline. |
| Expected Result | Invalid không tăng sample_count/sum; đủ 10 valid mới baseline=100. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-GAS; backend/app/services/gas_anomaly.py::update_gas_anomaly_state |
| Notes | Pure-service NaN/bool invalid không tương đương API: API reject các giá trị đó trước service. |

<a id="tc-gas-021"></a>

#### TC-GAS-021 — Gas xử lý theo arrival order khi timestamp cũ

| Field | Value |
|---|---|
| Test Case ID | TC-GAS-021 |
| Module | Gas Baseline & Anomaly |
| Test Type | Manual |
| Priority | High |
| Objective | Gas xử lý theo arrival order khi timestamp cũ |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Baseline=100, streak=2; nhận gas130 có timestamp cũ hơn reading trước, UUID mới. |
| Steps | POST và đọc state/event. |
| Expected Result | Gas vẫn active và có STARTED vì service không kiểm tra timestamp; không áp rule stale của temperature sang gas. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-GAS; backend/app/services/gas_anomaly.py::update_gas_anomaly_state |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

### SENSOR — Sensor Fault

Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food.

<a id="tc-sensor-001"></a>

#### TC-SENSOR-001 — Three sensor faults and recoveries remain separate

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-001 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Three sensor faults and recoveries remain separate. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>system</code>; [fixture/helper defaults](#fixture-test-cross-system-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>first = post_reading(system, 0, temperature=None, humidity=None, gas=None)</code><br><code>faults = rows(system, &quot;SELECT event_type, payload FROM events WHERE event_type = &#x27;SENSOR_FAULT&#x27; ORDER BY id&quot;)</code><br><code>post_reading(system, 5, temperature=None, humidity=None, gas=None)</code><br><code>post_reading(system, 10, temperature=4, humidity=None, gas=None)</code><br><code>post_reading(system, 15, temperature=4, humidity=60, gas=None)</code><br><code>post_reading(system, 20, temperature=4, humidity=60, gas=100)</code><br><code>recovered = rows(system, &quot;SELECT payload FROM events WHERE event_type = &#x27;SENSOR_RECOVERED&#x27; ORDER BY id&quot;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>[ast.literal_eval(event[&#x27;payload&#x27;])[&#x27;sensor_name&#x27;] for event in faults] == [&#x27;temperature&#x27;, &#x27;humidity&#x27;, &#x27;gas&#x27;]</code><br><code>len(rows(system, &quot;SELECT id FROM events WHERE event_type = &#x27;SENSOR_FAULT&#x27;&quot;)) == 3</code><br><code>[ast.literal_eval(event[&#x27;payload&#x27;])[&#x27;sensor_name&#x27;] for event in rows(system, &quot;SELECT payload FROM events WHERE event_type = &#x27;SENSOR_RECOVERED&#x27; ORDER BY id&quot;)] == [&#x27;temperature&#x27;]</code><br><code>[ast.literal_eval(event[&#x27;payload&#x27;])[&#x27;sensor_name&#x27;] for event in recovered] == [&#x27;temperature&#x27;, &#x27;humidity&#x27;, &#x27;gas&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_cross_system_integration.py::test_three_sensor_faults_and_recoveries_remain_separate</code> — [source L154](../backend/tests/test_cross_system_integration.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_three_sensor_faults_and_recoveries_remain_separate(system):
    first = post_reading(system, 0, temperature=None, humidity=None, gas=None)
    assert first.status_code == 201
    faults = rows(system,
        "SELECT event_type, payload FROM events WHERE event_type = 'SENSOR_FAULT' ORDER BY id")
    assert [ast.literal_eval(event["payload"])["sensor_name"] for event in faults] == [
        "temperature", "humidity", "gas"
    ]
    post_reading(system, 5, temperature=None, humidity=None, gas=None)
    assert len(rows(system, "SELECT id FROM events WHERE event_type = 'SENSOR_FAULT'")) == 3

    post_reading(system, 10, temperature=4, humidity=None, gas=None)
    assert [ast.literal_eval(event["payload"])["sensor_name"] for event in rows(
        system, "SELECT payload FROM events WHERE event_type = 'SENSOR_RECOVERED' ORDER BY id"
    )] == ["temperature"]
    post_reading(system, 15, temperature=4, humidity=60, gas=None)
    post_reading(system, 20, temperature=4, humidity=60, gas=100)
    recovered = rows(system,
        "SELECT payload FROM events WHERE event_type = 'SENSOR_RECOVERED' ORDER BY id")
    assert [ast.literal_eval(event["payload"])["sensor_name"] for event in recovered] == [
        "temperature", "humidity", "gas"
    ]
~~~

</details>

<a id="tc-sensor-002"></a>

#### TC-SENSOR-002 — Temperature sensor fault

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-002 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Temperature sensor fault. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_temperature(None)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_temperature_sensor_fault</code> — [source L34](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_temperature_sensor_fault():
    result = evaluate_temperature(None)

    assert result.status == FreshnessStatus.CHECK_FOOD
~~~

</details>

<a id="tc-sensor-003"></a>

#### TC-SENSOR-003 — Humidity sensor fault

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-003 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Humidity sensor fault. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_humidity(None)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_humidity_sensor_fault</code> — [source L40](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_humidity_sensor_fault():
    result = evaluate_humidity(None)

    assert result.status == FreshnessStatus.CHECK_FOOD
~~~

</details>

<a id="tc-sensor-004"></a>

#### TC-SENSOR-004 — Gas sensor fault

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-004 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Gas sensor fault. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_gas(None)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_gas_sensor_fault</code> — [source L46](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_gas_sensor_fault():
    result = evaluate_gas(None)

    assert result.status == FreshnessStatus.CHECK_FOOD
~~~

</details>

<a id="tc-sensor-005"></a>

#### TC-SENSOR-005 — Normal reading creates no events

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-005 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Normal reading creates no events. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = post_reading(sensor_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code><br><code>events(sensor_client) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_normal_reading_creates_no_events</code> — [source L92](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_normal_reading_creates_no_events(sensor_client):
    response = post_reading(sensor_client)
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Fresh / Normal"
    assert events(sensor_client) == []
~~~

</details>

<a id="tc-sensor-006"></a>

#### TC-SENSOR-006 — Each numeric sensor null emits fault

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-006 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Each numeric sensor null emits fault. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | 1. <code>sensor_name=&#x27;temperature&#x27;; field=&#x27;temperature_c&#x27;</code><br>2. <code>sensor_name=&#x27;humidity&#x27;; field=&#x27;humidity_pct&#x27;</code><br>3. <code>sensor_name=&#x27;gas&#x27;; field=&#x27;gas_raw&#x27;</code><br>Setup/input cố định: <code>response = post_reading(sensor_client, seconds=1, **{field: None})</code><br><code>created = fault_events(sensor_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code><br><code>len(created) == 1</code><br><code>created[0][&#x27;event_type&#x27;] == &#x27;SENSOR_FAULT&#x27;</code><br><code>ast.literal_eval(created[0][&#x27;payload&#x27;])[&#x27;sensor_name&#x27;] == sensor_name</code><br><code>created[0][&#x27;timestamp&#x27;] == reading_payload(1)[&#x27;timestamp&#x27;]</code><br><code>fault_state(sensor_client, sensor_name)[&#x27;fault_active&#x27;] == 1</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_each_numeric_sensor_null_emits_fault</code> — [source L100](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("sensor_name,field", SENSORS.items())
def test_each_numeric_sensor_null_emits_fault(sensor_client, sensor_name, field):
    response = post_reading(sensor_client, seconds=1, **{field: None})
    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Check Food"
    created = fault_events(sensor_client)
    assert len(created) == 1
    assert created[0]["event_type"] == "SENSOR_FAULT"
    assert ast.literal_eval(created[0]["payload"])["sensor_name"] == sensor_name
    assert created[0]["timestamp"] == reading_payload(1)["timestamp"]
    assert fault_state(sensor_client, sensor_name)["fault_active"] == 1
~~~

</details>

<a id="tc-sensor-007"></a>

#### TC-SENSOR-007 — Repeated null fault does not spam and valid recovers once

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-007 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Repeated null fault does not spam and valid recovers once. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>post_reading(sensor_client, seconds=6, temperature_c=4.2)</code><br><code>post_reading(sensor_client, seconds=7, temperature_c=4.1)</code><br><code>recovered = recovered_events(sensor_client)[0]</code><br><code>payload = ast.literal_eval(recovered[&#x27;payload&#x27;])</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>len(fault_events(sensor_client)) == 1</code><br><code>recovered_events(sensor_client) == []</code><br><code>len(fault_events(sensor_client)) == 1</code><br><code>len(recovered_events(sensor_client)) == 1</code><br><code>payload[&#x27;sensor_name&#x27;] == &#x27;temperature&#x27;</code><br><code>payload[&#x27;sensor_value&#x27;] == 4.2</code><br><code>recovered[&#x27;timestamp&#x27;] == reading_payload(6)[&#x27;timestamp&#x27;]</code><br><code>fault_state(sensor_client, &#x27;temperature&#x27;)[&#x27;fault_active&#x27;] == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_repeated_null_fault_does_not_spam_and_valid_recovers_once</code> — [source L112](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_repeated_null_fault_does_not_spam_and_valid_recovers_once(sensor_client):
    for seconds in range(1, 6):
        post_reading(sensor_client, seconds=seconds, temperature_c=None)
    assert len(fault_events(sensor_client)) == 1
    assert recovered_events(sensor_client) == []

    post_reading(sensor_client, seconds=6, temperature_c=4.2)
    post_reading(sensor_client, seconds=7, temperature_c=4.1)
    assert len(fault_events(sensor_client)) == 1
    assert len(recovered_events(sensor_client)) == 1
    recovered = recovered_events(sensor_client)[0]
    payload = ast.literal_eval(recovered["payload"])
    assert payload["sensor_name"] == "temperature"
    assert payload["sensor_value"] == 4.2
    assert recovered["timestamp"] == reading_payload(6)["timestamp"]
    assert fault_state(sensor_client, "temperature")["fault_active"] == 0
~~~

</details>

<a id="tc-sensor-008"></a>

#### TC-SENSOR-008 — Multiple sensors transition and recover independently

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-008 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Multiple sensors transition and recover independently. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>post_reading(sensor_client, seconds=1, temperature_c=None)</code><br><code>post_reading(sensor_client, seconds=2, temperature_c=None, humidity_pct=None)</code><br><code>post_reading(sensor_client, seconds=3, temperature_c=4.0, humidity_pct=60.0)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>[(event[&#x27;event_type&#x27;], ast.literal_eval(event[&#x27;payload&#x27;])[&#x27;sensor_name&#x27;]) for event in events(sensor_client)] == [(&#x27;SENSOR_FAULT&#x27;, &#x27;temperature&#x27;), (&#x27;SENSOR_FAULT&#x27;, &#x27;humidity&#x27;)]</code><br><code>[(event[&#x27;event_type&#x27;], ast.literal_eval(event[&#x27;payload&#x27;])[&#x27;sensor_name&#x27;]) for event in events(sensor_client)] == [(&#x27;SENSOR_FAULT&#x27;, &#x27;temperature&#x27;), (&#x27;SENSOR_FAULT&#x27;, &#x27;humidity&#x27;), (&#x27;SENSOR_RECOVERED&#x27;, &#x27;temperature&#x27;), (&#x27;SENSOR_RECOVERED&#x27;, &#x27;humidity&#x27;)]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_multiple_sensors_transition_and_recover_independently</code> — [source L130](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_multiple_sensors_transition_and_recover_independently(sensor_client):
    post_reading(sensor_client, seconds=1, temperature_c=None)
    post_reading(sensor_client, seconds=2, temperature_c=None, humidity_pct=None)
    assert [(event["event_type"], ast.literal_eval(event["payload"])["sensor_name"])
            for event in events(sensor_client)] == [
        ("SENSOR_FAULT", "temperature"),
        ("SENSOR_FAULT", "humidity"),
    ]

    post_reading(sensor_client, seconds=3, temperature_c=4.0, humidity_pct=60.0)
    assert [(event["event_type"], ast.literal_eval(event["payload"])["sensor_name"])
            for event in events(sensor_client)] == [
        ("SENSOR_FAULT", "temperature"),
        ("SENSOR_FAULT", "humidity"),
        ("SENSOR_RECOVERED", "temperature"),
        ("SENSOR_RECOVERED", "humidity"),
    ]
~~~

</details>

<a id="tc-sensor-009"></a>

#### TC-SENSOR-009 — Three null sensors create separate fault transitions

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-009 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Three null sensors create separate fault transitions. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = post_reading(sensor_client, seconds=1, temperature_c=None, humidity_pct=None, gas_raw=None)</code><br><code>post_reading(sensor_client, seconds=2, temperature_c=None, humidity_pct=None, gas_raw=None)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>[ast.literal_eval(event[&#x27;payload&#x27;])[&#x27;sensor_name&#x27;] for event in fault_events(sensor_client)] == [&#x27;temperature&#x27;, &#x27;humidity&#x27;, &#x27;gas&#x27;]</code><br><code>len(fault_events(sensor_client)) == 3</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_three_null_sensors_create_separate_fault_transitions</code> — [source L149](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_three_null_sensors_create_separate_fault_transitions(sensor_client):
    response = post_reading(
        sensor_client, seconds=1,
        temperature_c=None, humidity_pct=None, gas_raw=None,
    )
    assert response.status_code == 201
    assert [ast.literal_eval(event["payload"])["sensor_name"]
            for event in fault_events(sensor_client)] == [
        "temperature", "humidity", "gas"
    ]
    post_reading(sensor_client, seconds=2,
                 temperature_c=None, humidity_pct=None, gas_raw=None)
    assert len(fault_events(sensor_client)) == 3
~~~

</details>

<a id="tc-sensor-010"></a>

#### TC-SENSOR-010 — Fault state is isolated by food device and null food

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-010 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Fault state is isolated by food device and null food. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>post_reading(sensor_client, seconds=1, food_id=&#x27;FOOD-A&#x27;, temperature_c=None)</code><br><code>post_reading(sensor_client, seconds=2, food_id=&#x27;FOOD-B&#x27;, temperature_c=4.0)</code><br><code>post_reading(sensor_client, seconds=3, device_id=&#x27;OTHER-DEVICE&#x27;, food_id=&#x27;FOOD-A&#x27;, temperature_c=4.0)</code><br><code>post_reading(sensor_client, seconds=4, food_id=None, temperature_c=4.0)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>fault_state(sensor_client, &#x27;temperature&#x27;, food_id=&#x27;FOOD-A&#x27;)[&#x27;fault_active&#x27;] == 1</code><br><code>fault_state(sensor_client, &#x27;temperature&#x27;, food_id=&#x27;FOOD-B&#x27;)[&#x27;fault_active&#x27;] == 0</code><br><code>fault_state(sensor_client, &#x27;temperature&#x27;, &#x27;OTHER-DEVICE&#x27;, &#x27;FOOD-A&#x27;)[&#x27;fault_active&#x27;] == 0</code><br><code>fault_state(sensor_client, &#x27;temperature&#x27;, food_id=None)[&#x27;fault_active&#x27;] == 0</code><br><code>len(fault_events(sensor_client)) == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_fault_state_is_isolated_by_food_device_and_null_food</code> — [source L164](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_fault_state_is_isolated_by_food_device_and_null_food(sensor_client):
    for food_id in ("FOOD-A", "FOOD-B"):
        response = sensor_client.post("/api/v1/foods", json={
            "food_id": food_id,
            "food_name": food_id,
            "category": "MEAT",
            "inserted_at": "2026-09-26",
        })
        assert response.status_code == 201

    post_reading(sensor_client, seconds=1, food_id="FOOD-A", temperature_c=None)
    post_reading(sensor_client, seconds=2, food_id="FOOD-B", temperature_c=4.0)
    post_reading(sensor_client, seconds=3, device_id="OTHER-DEVICE",
                 food_id="FOOD-A", temperature_c=4.0)
    post_reading(sensor_client, seconds=4, food_id=None, temperature_c=4.0)

    assert fault_state(sensor_client, "temperature", food_id="FOOD-A")["fault_active"] == 1
    assert fault_state(sensor_client, "temperature", food_id="FOOD-B")["fault_active"] == 0
    assert fault_state(sensor_client, "temperature", "OTHER-DEVICE", "FOOD-A")["fault_active"] == 0
    assert fault_state(sensor_client, "temperature", food_id=None)["fault_active"] == 0
    assert len(fault_events(sensor_client)) == 1
~~~

</details>

<a id="tc-sensor-011"></a>

#### TC-SENSOR-011 — Malformed sensor value is validation error not fault

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-011 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Malformed sensor value is validation error not fault. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | 1. <code>field=&#x27;temperature_c&#x27;; invalid=&#x27;abc&#x27;</code><br>2. <code>field=&#x27;temperature_c&#x27;; invalid=True</code><br>3. <code>field=&#x27;temperature_c&#x27;; invalid={}</code><br>4. <code>field=&#x27;temperature_c&#x27;; invalid=nan</code><br>5. <code>field=&#x27;temperature_c&#x27;; invalid=inf</code><br>6. <code>field=&#x27;temperature_c&#x27;; invalid=-inf</code><br>7. <code>field=&#x27;humidity_pct&#x27;; invalid=&#x27;abc&#x27;</code><br>8. <code>field=&#x27;humidity_pct&#x27;; invalid=True</code><br>9. <code>field=&#x27;humidity_pct&#x27;; invalid={}</code><br>10. <code>field=&#x27;humidity_pct&#x27;; invalid=nan</code><br>11. <code>field=&#x27;humidity_pct&#x27;; invalid=inf</code><br>12. <code>field=&#x27;humidity_pct&#x27;; invalid=-inf</code><br>13. <code>field=&#x27;gas_raw&#x27;; invalid=&#x27;abc&#x27;</code><br>14. <code>field=&#x27;gas_raw&#x27;; invalid=True</code><br>15. <code>field=&#x27;gas_raw&#x27;; invalid={}</code><br>16. <code>field=&#x27;gas_raw&#x27;; invalid=nan</code><br>17. <code>field=&#x27;gas_raw&#x27;; invalid=inf</code><br>18. <code>field=&#x27;gas_raw&#x27;; invalid=-inf</code><br>Setup/input cố định: <code>response = post_reading(sensor_client, seconds=1, **{field: invalid})</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>events(sensor_client) == []</code><br><code>fault_state(sensor_client, next((name for name, sensor_field in SENSORS.items() if sensor_field == field))) is None</code> |
| Actual Result | Level A — 18/18 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_malformed_sensor_value_is_validation_error_not_fault</code> — [source L189](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("invalid", ["abc", True, {}, float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("field", list(SENSORS.values()))
def test_malformed_sensor_value_is_validation_error_not_fault(sensor_client, field, invalid):
    response = post_reading(sensor_client, seconds=1, **{field: invalid})
    assert response.status_code == 400
    assert events(sensor_client) == []
    assert fault_state(sensor_client, next(
        name for name, sensor_field in SENSORS.items() if sensor_field == field
    )) is None
~~~

</details>

<a id="tc-sensor-012"></a>

#### TC-SENSOR-012 — Fault state and events survive restart and recover

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-012 |
| Module | Sensor Fault — [backend/app/services/sensor_fault.py](../backend/app/services/sensor_fault.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Fault state and events survive restart and recover. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>first = post_reading(sensor_client, seconds=1, temperature_c=None, device_reading_id=reading_id)</code><br><code>init_db_module.init_db()</code><br><code>restarted_client = sensor_client.application.test_client()</code><br><code>post_reading(restarted_client, seconds=2, temperature_c=None)</code><br><code>post_reading(restarted_client, seconds=3, temperature_c=4.0)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>len(fault_events(restarted_client)) == 1</code><br><code>len(recovered_events(restarted_client)) == 1</code><br><code>fault_state(restarted_client, &#x27;temperature&#x27;)[&#x27;fault_active&#x27;] == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_fault_state_and_events_survive_restart_and_recover</code> — [source L198](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-SENSOR: Theo dõi temperature, humidity, gas theo device/food/sensor. Null chuyển fault, non-null được API nhận chuyển recovery; transition-only. Malformed reject 400 trước state. Gas âm không phải null fault; freshness vẫn Check Food. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_fault_state_and_events_survive_restart_and_recover(sensor_client):
    reading_id = str(uuid.uuid4())
    first = post_reading(sensor_client, seconds=1, temperature_c=None,
                         device_reading_id=reading_id)
    assert first.status_code == 201
    init_db_module.init_db()  # Simulate backend startup against the persisted DB.
    restarted_client = sensor_client.application.test_client()

    post_reading(restarted_client, seconds=2, temperature_c=None)
    assert len(fault_events(restarted_client)) == 1
    post_reading(restarted_client, seconds=3, temperature_c=4.0)
    assert len(recovered_events(restarted_client)) == 1
    assert fault_state(restarted_client, "temperature")["fault_active"] == 0
~~~

</details>

<a id="tc-sensor-013"></a>

#### TC-SENSOR-013 — Gas âm không phải null sensor fault

| Field | Value |
|---|---|
| Test Case ID | TC-SENSOR-013 |
| Module | Sensor Fault |
| Test Type | Manual |
| Priority | High |
| Objective | Gas âm không phải null sensor fault |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Gas=-1 từ trạng thái normal; sau đó gas=None rồi gas=-1; UUID riêng. |
| Steps | POST tuần tự; kiểm tra SENSOR_* và freshness. |
| Expected Result | -1 được API nhận, freshness Check Food; không tạo null fault ban đầu. Sau null, -1 tạo SENSOR_RECOVERED dù freshness vẫn Check Food. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-SENSOR; backend/app/services/sensor_fault.py::update_sensor_fault_states |
| Notes | Đây là behavior hiện tại, không phải xác nhận dữ liệu gas âm hợp lệ về vật lý. |

### HUM — Humidity

VEGETABLE/FRUIT <80% hoặc >95% chỉ thêm warning, không tăng severity; 80 và 95 không warning. Category khác không warning theo ngưỡng. Null/nonfinite là rule validity riêng.

<a id="tc-hum-001"></a>

#### TC-HUM-001 — Valid humidity does not change severity

| Field | Value |
|---|---|
| Test Case ID | TC-HUM-001 |
| Module | Humidity — [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | Valid humidity does not change severity. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>humidity=79.9</code><br>2. <code>humidity=80</code><br>3. <code>humidity=95</code><br>4. <code>humidity=95.1</code><br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>evaluate_humidity(humidity, &#x27;VEGETABLE&#x27;).status == FreshnessStatus.FRESH</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_valid_humidity_does_not_change_severity</code> — [source L311](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-HUM: VEGETABLE/FRUIT <80% hoặc >95% chỉ thêm warning, không tăng severity; 80 và 95 không warning. Category khác không warning theo ngưỡng. Null/nonfinite là rule validity riêng. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("humidity", [79.9, 80, 95, 95.1])
def test_valid_humidity_does_not_change_severity(humidity):
    assert evaluate_humidity(humidity, "VEGETABLE").status == FreshnessStatus.FRESH
~~~

</details>

<a id="tc-hum-002"></a>

#### TC-HUM-002 — Produce humidity warnings are reported without increasing severity

| Field | Value |
|---|---|
| Test Case ID | TC-HUM-002 |
| Module | Humidity — [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | Produce humidity warnings are reported without increasing severity. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>humidity=79.9; expected_warning=&#x27;low humidity&#x27;</code><br>2. <code>humidity=95.1; expected_warning=&#x27;high humidity&#x27;</code><br>Setup/input cố định: <code>result = evaluate_freshness(temperature_c=5, humidity_pct=humidity, gas_raw=100, door_open=False, category=&#x27;VEGETABLE&#x27;)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.FRESH</code><br><code>expected_warning in result.reason.lower()</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_produce_humidity_warnings_are_reported_without_increasing_severity</code> — [source L319](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-HUM: VEGETABLE/FRUIT <80% hoặc >95% chỉ thêm warning, không tăng severity; 80 và 95 không warning. Category khác không warning theo ngưỡng. Null/nonfinite là rule validity riêng. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("humidity", "expected_warning"),
    [(79.9, "low humidity"), (95.1, "high humidity")],
)
def test_produce_humidity_warnings_are_reported_without_increasing_severity(
    humidity, expected_warning
):
    result = evaluate_freshness(
        temperature_c=5, humidity_pct=humidity, gas_raw=100,
        door_open=False, category="VEGETABLE",
    )
    assert result.status == FreshnessStatus.FRESH
    assert expected_warning in result.reason.lower()
~~~

</details>

<a id="tc-hum-003"></a>

#### TC-HUM-003 — Non produce humidity does not create warning

| Field | Value |
|---|---|
| Test Case ID | TC-HUM-003 |
| Module | Humidity — [backend/app/services/freshness.py](../backend/app/services/freshness.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | Non produce humidity does not create warning. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>category=&#x27;MEAT&#x27;</code><br>2. <code>category=&#x27;DAIRY&#x27;</code><br>3. <code>category=&#x27;COOKED_FOOD&#x27;</code><br>Setup/input cố định: <code>result = evaluate_freshness(temperature_c=5, humidity_pct=50, gas_raw=100, door_open=False, category=category)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.FRESH</code><br><code>&#x27;humidity&#x27; not in result.reason.lower()</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_non_produce_humidity_does_not_create_warning</code> — [source L331](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-HUM: VEGETABLE/FRUIT <80% hoặc >95% chỉ thêm warning, không tăng severity; 80 và 95 không warning. Category khác không warning theo ngưỡng. Null/nonfinite là rule validity riêng. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("category", ["MEAT", "DAIRY", "COOKED_FOOD"])
def test_non_produce_humidity_does_not_create_warning(category):
    result = evaluate_freshness(
        temperature_c=5, humidity_pct=50, gas_raw=100,
        door_open=False, category=category,
    )
    assert result.status == FreshnessStatus.FRESH
    assert "humidity" not in result.reason.lower()
~~~

</details>

<a id="tc-hum-004"></a>

#### TC-HUM-004 — FRUIT đủ năm humidity boundaries

| Field | Value |
|---|---|
| Test Case ID | TC-HUM-004 |
| Module | Humidity |
| Test Type | Manual |
| Priority | High |
| Objective | FRUIT đủ năm humidity boundaries |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | category=FRUIT; humidity=79.9,80,90,95,95.1; sensors khác normal; không storage/expiry penalty. |
| Steps | Gọi engine từng input; kiểm tra status và reason. |
| Expected Result | Tất cả Fresh; 79.9 có Low humidity warning, 95.1 High humidity warning; 80/90/95 không humidity warning. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HUM; backend/app/services/freshness.py::_evaluate_humidity_rule |
| Notes | Existing automated produce humidity tests dùng VEGETABLE, chưa FRUIT trực tiếp. |

<a id="tc-hum-005"></a>

#### TC-HUM-005 — VEGETABLE warning absence tại 80/90/95

| Field | Value |
|---|---|
| Test Case ID | TC-HUM-005 |
| Module | Humidity |
| Test Type | Manual |
| Priority | High |
| Objective | VEGETABLE warning absence tại 80/90/95 |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | category=VEGETABLE; humidity=80,90,95; sensors normal. |
| Steps | Gọi engine và kiểm tra reason lẫn severity. |
| Expected Result | Fresh và không humidity warning ở cả ba giá trị. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HUM; backend/app/services/freshness.py::_evaluate_humidity_rule |
| Notes | Tests hiện assert severity tại 80/95, chưa assert warning absence; 90 chưa là boundary testcase riêng. |

### DOOR — Door Freshness & Producer

Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder.

<a id="tc-door-001"></a>

#### TC-DOOR-001 — Door closed

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-001 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Door closed. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_door_timeout(False, 0)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.FRESH</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_door_closed</code> — [source L65](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_door_closed():
    result = evaluate_door_timeout(False, 0)

    assert result.status == FreshnessStatus.FRESH
~~~

</details>

<a id="tc-door-002"></a>

#### TC-DOOR-002 — Door open

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-002 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Door open. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_door_timeout(True, 10)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.FRESH</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_door_open</code> — [source L71](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_door_open():
    result = evaluate_door_timeout(True, 10)

    assert result.status == FreshnessStatus.FRESH
~~~

</details>

<a id="tc-door-003"></a>

#### TC-DOOR-003 — Door open too long

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-003 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Door open too long. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_door_timeout(True, 35)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_door_open_too_long</code> — [source L77](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_door_open_too_long():
    result = evaluate_door_timeout(True, 35)

    assert result.status == FreshnessStatus.CHECK_FOOD
~~~

</details>

<a id="tc-door-004"></a>

#### TC-DOOR-004 — Negative open duration is invalid

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-004 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Negative open duration is invalid. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_with_optional_food(door_open=True, open_duration_seconds=-1)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_negative_open_duration_is_invalid</code> — [source L228](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_negative_open_duration_is_invalid():
    result = evaluate_with_optional_food(
        door_open=True,
        open_duration_seconds=-1,
    )

    assert result.status == FreshnessStatus.CHECK_FOOD
~~~

</details>

<a id="tc-door-005"></a>

#### TC-DOOR-005 — Door timeout boundary

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-005 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Door timeout boundary. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>duration=29; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>2. <code>duration=30; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>3. <code>duration=31; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>Setup/input cố định: <code>result = evaluate_with_optional_food(door_open=True, open_duration_seconds=duration)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == expected_status</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_door_timeout_boundary</code> — [source L245](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("duration", "expected_status"),
    [
        (29, FreshnessStatus.FRESH),
        (30, FreshnessStatus.CHECK_FOOD),
        (31, FreshnessStatus.CHECK_FOOD),
    ],
)
def test_door_timeout_boundary(duration, expected_status):
    result = evaluate_with_optional_food(
        door_open=True,
        open_duration_seconds=duration,
    )

    assert result.status == expected_status
~~~

</details>

<a id="tc-door-006"></a>

#### TC-DOOR-006 — Evaluate door wrapper

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-006 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Evaluate door wrapper. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>door_open=False; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;; expected_reason=&#x27;&#x27;</code><br>2. <code>door_open=True; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;; expected_reason=&#x27;Door is open.&#x27;</code><br>Setup/input cố định: <code>result = evaluate_door(door_open)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == expected_status</code><br><code>result.reason == expected_reason</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_evaluate_door_wrapper</code> — [source L443](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("door_open", "expected_status", "expected_reason"),
    [
        (False, FreshnessStatus.FRESH, ""),
        (True, FreshnessStatus.FRESH, "Door is open."),
    ],
)
def test_evaluate_door_wrapper(door_open, expected_status, expected_reason):
    result = evaluate_door(door_open)

    assert result.status == expected_status
    assert result.reason == expected_reason
~~~

</details>

<a id="tc-door-007"></a>

#### TC-DOOR-007 — Door open timeout and close are emitted once per transition

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-007 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Door open timeout and close are emitted once per transition. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>producer = simulator.DoorEventProducer()</code><br><code>stream = [door_reading(False, 0, 0), door_reading(True, 0, 5), door_reading(True, 10, 10), door_reading(True, 20, 15), door_reading(True, 29, 20), door_reading(True, 30, 25), door_reading(True, 35, 30), door_reading(True, 40, 35), door_reading(True, 45, 40), door_reading(False, 0, 45)]</code><br><code>events = [event for reading in stream for event in producer.observe(reading)]</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>[event[&#x27;event_type&#x27;] for event in events] == [&#x27;DOOR_OPENED&#x27;, &#x27;DOOR_TIMEOUT&#x27;, &#x27;DOOR_CLOSED&#x27;]</code><br><code>events[0][&#x27;payload&#x27;] == {&#x27;door_open&#x27;: True}</code><br><code>events[1][&#x27;payload&#x27;] == {&#x27;door_open&#x27;: True, &#x27;open_duration_seconds&#x27;: 30}</code><br><code>events[2][&#x27;payload&#x27;] == {&#x27;door_open&#x27;: False, &#x27;open_duration_seconds&#x27;: 0}</code><br><code>[event[&#x27;timestamp&#x27;] for event in events] == [stream[1][&#x27;timestamp&#x27;], stream[5][&#x27;timestamp&#x27;], stream[9][&#x27;timestamp&#x27;]]</code><br><code>all((event[&#x27;device_id&#x27;] == &#x27;FG-ESP32-01&#x27; for event in events))</code><br><code>all((event[&#x27;event_id&#x27;] for event in events))</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_door_open_timeout_and_close_are_emitted_once_per_transition</code> — [source L235](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_door_open_timeout_and_close_are_emitted_once_per_transition():
    producer = simulator.DoorEventProducer()
    stream = [
        door_reading(False, 0, 0),
        door_reading(True, 0, 5),
        door_reading(True, 10, 10),
        door_reading(True, 20, 15),
        door_reading(True, 29, 20),
        door_reading(True, 30, 25),
        door_reading(True, 35, 30),
        door_reading(True, 40, 35),
        door_reading(True, 45, 40),
        door_reading(False, 0, 45),
    ]

    events = [event for reading in stream for event in producer.observe(reading)]

    assert [event["event_type"] for event in events] == [
        "DOOR_OPENED", "DOOR_TIMEOUT", "DOOR_CLOSED"
    ]
    assert events[0]["payload"] == {"door_open": True}
    assert events[1]["payload"] == {"door_open": True, "open_duration_seconds": 30}
    assert events[2]["payload"] == {"door_open": False, "open_duration_seconds": 0}
    assert [event["timestamp"] for event in events] == [
        stream[1]["timestamp"], stream[5]["timestamp"], stream[9]["timestamp"]
    ]
    assert all(event["device_id"] == "FG-ESP32-01" for event in events)
    assert all(event["event_id"] for event in events)
~~~

</details>

<a id="tc-door-008"></a>

#### TC-DOOR-008 — Door close before timeout and repeated open cycles

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-008 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Door close before timeout and repeated open cycles. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>producer = simulator.DoorEventProducer()</code><br><code>events = []</code><br><code>stream = [door_reading(False, 0, 0), door_reading(True, 0, 5), door_reading(True, 10, 10), door_reading(False, 0, 15), door_reading(True, 0, 20), door_reading(True, 30, 25), door_reading(False, 0, 30), door_reading(True, 0, 35), door_reading(True, 30, 40), door_reading(False, 0, 45)]</code><br><code>event_types = [event[&#x27;event_type&#x27;] for event in events]</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>event_types == [&#x27;DOOR_OPENED&#x27;, &#x27;DOOR_CLOSED&#x27;, &#x27;DOOR_OPENED&#x27;, &#x27;DOOR_TIMEOUT&#x27;, &#x27;DOOR_CLOSED&#x27;, &#x27;DOOR_OPENED&#x27;, &#x27;DOOR_TIMEOUT&#x27;, &#x27;DOOR_CLOSED&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_door_close_before_timeout_and_repeated_open_cycles</code> — [source L265](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_door_close_before_timeout_and_repeated_open_cycles():
    producer = simulator.DoorEventProducer()
    events = []
    stream = [
        door_reading(False, 0, 0),
        door_reading(True, 0, 5),
        door_reading(True, 10, 10),
        door_reading(False, 0, 15),
        door_reading(True, 0, 20),
        door_reading(True, 30, 25),
        door_reading(False, 0, 30),
        door_reading(True, 0, 35),
        door_reading(True, 30, 40),
        door_reading(False, 0, 45),
    ]
    for reading in stream:
        events.extend(producer.observe(reading))

    event_types = [event["event_type"] for event in events]
    assert event_types == [
        "DOOR_OPENED", "DOOR_CLOSED",
        "DOOR_OPENED", "DOOR_TIMEOUT", "DOOR_CLOSED",
        "DOOR_OPENED", "DOOR_TIMEOUT", "DOOR_CLOSED",
    ]
~~~

</details>

<a id="tc-door-009"></a>

#### TC-DOOR-009 — Door producer state is scoped per device

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-009 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Door producer state is scoped per device. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>producer = simulator.DoorEventProducer()</code><br><code>producer.observe(door_reading(False, 0, 0, &#x27;device-a&#x27;))</code><br><code>producer.observe(door_reading(False, 0, 0, &#x27;device-b&#x27;))</code><br><code>events = producer.observe(door_reading(True, 0, 5, &#x27;device-a&#x27;))</code><br><code>device_b_events = producer.observe(door_reading(True, 0, 5, &#x27;device-b&#x27;))</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>[event[&#x27;event_type&#x27;] for event in events] == [&#x27;DOOR_OPENED&#x27;]</code><br><code>events[0][&#x27;device_id&#x27;] == &#x27;device-a&#x27;</code><br><code>[event[&#x27;event_type&#x27;] for event in device_b_events] == [&#x27;DOOR_OPENED&#x27;]</code><br><code>device_b_events[0][&#x27;device_id&#x27;] == &#x27;device-b&#x27;</code><br><code>producer.observe(door_reading(True, 5, 10, &#x27;device-b&#x27;)) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_door_producer_state_is_scoped_per_device</code> — [source L291](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_door_producer_state_is_scoped_per_device():
    producer = simulator.DoorEventProducer()
    producer.observe(door_reading(False, 0, 0, "device-a"))
    producer.observe(door_reading(False, 0, 0, "device-b"))

    events = producer.observe(door_reading(True, 0, 5, "device-a"))

    assert [event["event_type"] for event in events] == ["DOOR_OPENED"]
    assert events[0]["device_id"] == "device-a"
    device_b_events = producer.observe(door_reading(True, 0, 5, "device-b"))
    assert [event["event_type"] for event in device_b_events] == ["DOOR_OPENED"]
    assert device_b_events[0]["device_id"] == "device-b"
    assert producer.observe(door_reading(True, 5, 10, "device-b")) == []
~~~

</details>

<a id="tc-door-010"></a>

#### TC-DOOR-010 — First open reading after restart seeds without reemitting episode

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-010 |
| Module | Door Freshness & Producer — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | First open reading after restart seeds without reemitting episode. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>producer = simulator.DoorEventProducer()</code><br><code>closed_events = producer.observe(door_reading(False, 0, 10))</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>producer.observe(door_reading(True, 35, 0)) == []</code><br><code>producer.observe(door_reading(True, 40, 5)) == []</code><br><code>[event[&#x27;event_type&#x27;] for event in closed_events] == [&#x27;DOOR_CLOSED&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_first_open_reading_after_restart_seeds_without_reemitting_episode</code> — [source L306](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-DOOR: Backend: đóng không penalty, mở <30s Fresh về riêng rule door, >=30s Check Food. Simulator sở hữu DOOR_OPENED/TIMEOUT/CLOSED; .ino hiện false/0 placeholder. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_first_open_reading_after_restart_seeds_without_reemitting_episode():
    producer = simulator.DoorEventProducer()

    assert producer.observe(door_reading(True, 35, 0)) == []
    assert producer.observe(door_reading(True, 40, 5)) == []
    closed_events = producer.observe(door_reading(False, 0, 10))
    assert [event["event_type"] for event in closed_events] == ["DOOR_CLOSED"]
~~~

</details>

<a id="tc-door-011"></a>

#### TC-DOOR-011 — Door freshness tại open duration 0

| Field | Value |
|---|---|
| Test Case ID | TC-DOOR-011 |
| Module | Door Freshness & Producer |
| Test Type | Manual |
| Priority | High |
| Objective | Door freshness tại open duration 0 |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | door_open=True, duration=0; sensors valid, không food penalty. |
| Steps | Gọi evaluate_door_timeout và evaluate_freshness. |
| Expected Result | Fresh, reason Door is open.; không Check Food. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-DOOR; backend/app/services/freshness.py::_evaluate_door_rule |
| Notes | Automation door producer có duration 0; không coi đó là test riêng cho freshness ở duration 0. |

### STORAGE — Storage Duration

MEAT=3, DAIRY=14, VEGETABLE=7, FRUIT=14, COOKED_FOOD=4 ngày. Tuổi <max-1 Fresh; max-1..max Use Soon; >max Check Food. Dùng server date.today(), không reading timestamp.

<a id="tc-storage-001"></a>

#### TC-STORAGE-001 — Storage duration flows from food record

| Field | Value |
|---|---|
| Test Case ID | TC-STORAGE-001 |
| Module | Storage Duration — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Storage duration flows from food record. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | 1. <code>stored_days=1; expected_status=&#x27;Fresh / Normal&#x27;</code><br>2. <code>stored_days=2; expected_status=&#x27;Use Soon&#x27;</code><br>3. <code>stored_days=3; expected_status=&#x27;Use Soon&#x27;</code><br>4. <code>stored_days=4; expected_status=&#x27;Check Food&#x27;</code><br>Setup/input cố định: <code>register_food(api_client, &#x27;FG-STORAGE&#x27;, &#x27;MEAT&#x27;, stored_days, 10)</code><br><code>response = post_reading(api_client, food_id=&#x27;FG-STORAGE&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == expected_status</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_storage_duration_flows_from_food_record</code> — [source L83](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-STORAGE: MEAT=3, DAIRY=14, VEGETABLE=7, FRUIT=14, COOKED_FOOD=4 ngày. Tuổi <max-1 Fresh; max-1..max Use Soon; >max Check Food. Dùng server date.today(), không reading timestamp. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("stored_days", "expected_status"),
    [
        (1, "Fresh / Normal"),
        (2, "Use Soon"),
        (3, "Use Soon"),
        (4, "Check Food"),
    ],
)
def test_storage_duration_flows_from_food_record(
    api_client, stored_days, expected_status
):
    register_food(api_client, "FG-STORAGE", "MEAT", stored_days, 10)

    response = post_reading(api_client, food_id="FG-STORAGE")

    assert response.status_code == 201
    assert response.json["freshness"]["status"] == expected_status
~~~

</details>

<a id="tc-storage-002"></a>

#### TC-STORAGE-002 — Storage duration boundaries

| Field | Value |
|---|---|
| Test Case ID | TC-STORAGE-002 |
| Module | Storage Duration — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Storage duration boundaries. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>category=&#x27;MEAT&#x27;; days_stored=1; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>2. <code>category=&#x27;MEAT&#x27;; days_stored=2; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;</code><br>3. <code>category=&#x27;MEAT&#x27;; days_stored=3; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;</code><br>4. <code>category=&#x27;MEAT&#x27;; days_stored=4; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>5. <code>category=&#x27;DAIRY&#x27;; days_stored=13; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;</code><br>6. <code>category=&#x27;DAIRY&#x27;; days_stored=14; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;</code><br>7. <code>category=&#x27;DAIRY&#x27;; days_stored=15; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>Setup/input cố định: <code>result = evaluate_with_optional_food(category, days_stored)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == expected_status</code> |
| Actual Result | Level A — 7/7 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_storage_duration_boundaries</code> — [source L111](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-STORAGE: MEAT=3, DAIRY=14, VEGETABLE=7, FRUIT=14, COOKED_FOOD=4 ngày. Tuổi <max-1 Fresh; max-1..max Use Soon; >max Check Food. Dùng server date.today(), không reading timestamp. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("category", "days_stored", "expected_status"),
    [
        ("MEAT", 1, FreshnessStatus.FRESH),
        ("MEAT", 2, FreshnessStatus.USE_SOON),
        ("MEAT", 3, FreshnessStatus.USE_SOON),
        ("MEAT", 4, FreshnessStatus.CHECK_FOOD),
        ("DAIRY", 13, FreshnessStatus.USE_SOON),
        ("DAIRY", 14, FreshnessStatus.USE_SOON),
        ("DAIRY", 15, FreshnessStatus.CHECK_FOOD),
    ],
)
def test_storage_duration_boundaries(category, days_stored, expected_status):
    result = evaluate_with_optional_food(category, days_stored)

    assert result.status == expected_status
~~~

</details>

<a id="tc-storage-003"></a>

#### TC-STORAGE-003 — Storage profile thresholds for all categories

| Field | Value |
|---|---|
| Test Case ID | TC-STORAGE-003 |
| Module | Storage Duration — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Storage profile thresholds for all categories. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>category=&#x27;MEAT&#x27;; max_days=3</code><br>2. <code>category=&#x27;DAIRY&#x27;; max_days=14</code><br>3. <code>category=&#x27;VEGETABLE&#x27;; max_days=7</code><br>4. <code>category=&#x27;FRUIT&#x27;; max_days=14</code><br>5. <code>category=&#x27;COOKED_FOOD&#x27;; max_days=4</code><br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>evaluate_with_optional_food(category, max_days - 2).status == FreshnessStatus.FRESH</code><br><code>evaluate_with_optional_food(category, max_days - 1).status == FreshnessStatus.USE_SOON</code><br><code>evaluate_with_optional_food(category, max_days).status == FreshnessStatus.USE_SOON</code><br><code>evaluate_with_optional_food(category, max_days + 1).status == FreshnessStatus.CHECK_FOOD</code> |
| Actual Result | Level A — 5/5 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_storage_profile_thresholds_for_all_categories</code> — [source L121](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-STORAGE: MEAT=3, DAIRY=14, VEGETABLE=7, FRUIT=14, COOKED_FOOD=4 ngày. Tuổi <max-1 Fresh; max-1..max Use Soon; >max Check Food. Dùng server date.today(), không reading timestamp. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("category", "max_days"),
    [("MEAT", 3), ("DAIRY", 14), ("VEGETABLE", 7), ("FRUIT", 14), ("COOKED_FOOD", 4)],
)
def test_storage_profile_thresholds_for_all_categories(category, max_days):
    assert evaluate_with_optional_food(category, max_days - 2).status == FreshnessStatus.FRESH
    assert evaluate_with_optional_food(category, max_days - 1).status == FreshnessStatus.USE_SOON
    assert evaluate_with_optional_food(category, max_days).status == FreshnessStatus.USE_SOON
    assert evaluate_with_optional_food(category, max_days + 1).status == FreshnessStatus.CHECK_FOOD
~~~

</details>

<a id="tc-storage-004"></a>

#### TC-STORAGE-004 — Future inserted at is invalid

| Field | Value |
|---|---|
| Test Case ID | TC-STORAGE-004 |
| Module | Storage Duration — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Future inserted at is invalid. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_with_optional_food(&#x27;MEAT&#x27;, days_stored=-1)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code><br><code>&#x27;Invalid food insertion date.&#x27; in result.reason</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_future_inserted_at_is_invalid</code> — [source L406](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-STORAGE: MEAT=3, DAIRY=14, VEGETABLE=7, FRUIT=14, COOKED_FOOD=4 ngày. Tuổi <max-1 Fresh; max-1..max Use Soon; >max Check Food. Dùng server date.today(), không reading timestamp. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_future_inserted_at_is_invalid():
    result = evaluate_with_optional_food(
        "MEAT",
        days_stored=-1,
    )

    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "Invalid food insertion date." in result.reason
~~~

</details>

<a id="tc-storage-005"></a>

#### TC-STORAGE-005 — Storage dùng server date thay vì timestamp reading

| Field | Value |
|---|---|
| Test Case ID | TC-STORAGE-005 |
| Module | Storage Duration |
| Test Type | Manual |
| Priority | High |
| Objective | Storage dùng server date thay vì timestamp reading |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Server day D; MEAT inserted=D-2; timestamp reading=D-10 và D+10, UUID khác; không expiry penalty. |
| Steps | Tạo food/reading trong DB thử nghiệm; so statuses. |
| Expected Result | Cả hai Use Soon theo server day D; không theo ngày reading. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-STORAGE; backend/app/services/freshness.py::_evaluate_storage_duration_rule |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

### EXPIRY — Expiry Date

Expiry hôm nay/ngày mai Use Soon, đã qua Check Food, xa hơn không tăng severity; dùng server date. Không expiry thì không penalty.

<a id="tc-expiry-001"></a>

#### TC-EXPIRY-001 — Expiry flows from food record

| Field | Value |
|---|---|
| Test Case ID | TC-EXPIRY-001 |
| Module | Expiry Date — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Expiry flows from food record. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | 1. <code>expiry_days=5; expected_status=&#x27;Fresh / Normal&#x27;</code><br>2. <code>expiry_days=1; expected_status=&#x27;Use Soon&#x27;</code><br>3. <code>expiry_days=0; expected_status=&#x27;Use Soon&#x27;</code><br>4. <code>expiry_days=-1; expected_status=&#x27;Check Food&#x27;</code><br>Setup/input cố định: <code>register_food(api_client, &#x27;FG-EXPIRY&#x27;, &#x27;MEAT&#x27;, 0, expiry_days)</code><br><code>response = post_reading(api_client, food_id=&#x27;FG-EXPIRY&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == expected_status</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_expiry_flows_from_food_record</code> — [source L103](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-EXPIRY: Expiry hôm nay/ngày mai Use Soon, đã qua Check Food, xa hơn không tăng severity; dùng server date. Không expiry thì không penalty. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("expiry_days", "expected_status"),
    [
        (5, "Fresh / Normal"),
        (1, "Use Soon"),
        (0, "Use Soon"),
        (-1, "Check Food"),
    ],
)
def test_expiry_flows_from_food_record(api_client, expiry_days, expected_status):
    register_food(api_client, "FG-EXPIRY", "MEAT", 0, expiry_days)

    response = post_reading(api_client, food_id="FG-EXPIRY")

    assert response.status_code == 201
    assert response.json["freshness"]["status"] == expected_status
~~~

</details>

<a id="tc-expiry-002"></a>

#### TC-EXPIRY-002 — Expiry date boundaries

| Field | Value |
|---|---|
| Test Case ID | TC-EXPIRY-002 |
| Module | Expiry Date — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Expiry date boundaries. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | 1. <code>expiry_offset=2; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>2. <code>expiry_offset=1; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;</code><br>3. <code>expiry_offset=0; expected_status=&lt;FreshnessStatus.USE_SOON: &#x27;Use Soon&#x27;&gt;</code><br>4. <code>expiry_offset=-1; expected_status=&lt;FreshnessStatus.CHECK_FOOD: &#x27;Check Food&#x27;&gt;</code><br>5. <code>expiry_offset=None; expected_status=&lt;FreshnessStatus.FRESH: &#x27;Fresh / Normal&#x27;&gt;</code><br>Setup/input cố định: <code>result = evaluate_with_optional_food(expiry_offset=expiry_offset)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == expected_status</code> |
| Actual Result | Level A — 5/5 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_expiry_date_boundaries</code> — [source L138](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-EXPIRY: Expiry hôm nay/ngày mai Use Soon, đã qua Check Food, xa hơn không tăng severity; dùng server date. Không expiry thì không penalty. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("expiry_offset", "expected_status"),
    [
        (2, FreshnessStatus.FRESH),
        (1, FreshnessStatus.USE_SOON),
        (0, FreshnessStatus.USE_SOON),
        (-1, FreshnessStatus.CHECK_FOOD),
        (None, FreshnessStatus.FRESH),
    ],
)
def test_expiry_date_boundaries(expiry_offset, expected_status):
    result = evaluate_with_optional_food(expiry_offset=expiry_offset)

    assert result.status == expected_status
~~~

</details>

<a id="tc-expiry-003"></a>

#### TC-EXPIRY-003 — Invalid expiry date is invalid

| Field | Value |
|---|---|
| Test Case ID | TC-EXPIRY-003 |
| Module | Expiry Date — [backend/app/services/freshness.py](../backend/app/services/freshness.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Invalid expiry date is invalid. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-freshness); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>result = evaluate_with_optional_food(expiry_date=&#x27;not-a-date&#x27;)</code> |
| Steps | 1. Tạo input/parameter set từ Input và helper defaults.<br>2. Gọi pure service theo scenario bên dưới.<br>3. Đối chiếu return value/exception và assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result.status == FreshnessStatus.CHECK_FOOD</code><br><code>&#x27;Invalid expiry date.&#x27; in result.reason</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_freshness.py::test_invalid_expiry_date_is_invalid</code> — [source L423](../backend/tests/test_freshness.py) |
| Requirement / Rule | R-EXPIRY: Expiry hôm nay/ngày mai Use Soon, đã qua Check Food, xa hơn không tăng severity; dùng server date. Không expiry thì không penalty. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_invalid_expiry_date_is_invalid():
    result = evaluate_with_optional_food(expiry_date="not-a-date")

    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "Invalid expiry date." in result.reason
~~~

</details>

<a id="tc-expiry-004"></a>

#### TC-EXPIRY-004 — Expiry dùng server date thay vì timestamp reading

| Field | Value |
|---|---|
| Test Case ID | TC-EXPIRY-004 |
| Module | Expiry Date |
| Test Type | Manual |
| Priority | High |
| Objective | Expiry dùng server date thay vì timestamp reading |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Expiry=D+1, server day D; reading timestamp D-10/D+10; sensors normal. |
| Steps | POST từng reading mới gắn food đó. |
| Expected Result | Cả hai Use Soon; timestamp không đổi expiry calculation. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-EXPIRY; backend/app/services/freshness.py::_evaluate_expiry_rule |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

### FOOD — Food Registration / QR

FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique.

<a id="tc-food-001"></a>

#### TC-FOOD-001 — Create food success

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-001 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food success. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/foods&#x27;, json=food_payload())</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;success&#x27;] is True</code><br><code>response.json[&#x27;food&#x27;][&#x27;food_id&#x27;] == &#x27;FG-FOOD-001&#x27;</code><br><code>response.json[&#x27;food&#x27;][&#x27;category&#x27;] == &#x27;DAIRY&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_success</code> — [source L59](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_create_food_success(client):
    response = client.post("/api/v1/foods", json=food_payload())

    assert response.status_code == 201
    assert response.json["success"] is True
    assert response.json["food"]["food_id"] == "FG-FOOD-001"
    assert response.json["food"]["category"] == "DAIRY"
~~~

</details>

<a id="tc-food-002"></a>

#### TC-FOOD-002 — Create food maps fixed qr to category

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-002 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food maps fixed qr to category. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | 1. <code>qr_code=&#x27;FG-MEAT&#x27;; expected_category=&#x27;MEAT&#x27;</code><br>2. <code>qr_code=&#x27;FG-DAIRY&#x27;; expected_category=&#x27;DAIRY&#x27;</code><br>3. <code>qr_code=&#x27;FG-VEGETABLE&#x27;; expected_category=&#x27;VEGETABLE&#x27;</code><br>4. <code>qr_code=&#x27;FG-FRUIT&#x27;; expected_category=&#x27;FRUIT&#x27;</code><br>5. <code>qr_code=&#x27;FG-COOKED&#x27;; expected_category=&#x27;COOKED_FOOD&#x27;</code><br>Setup/input cố định: <code>payload = food_payload(qr_code=qr_code)</code><br><code>payload.pop(&#x27;category&#x27;)</code><br><code>payload.pop(&#x27;food_id&#x27;)</code><br><code>response = client.post(&#x27;/api/v1/foods&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;food&#x27;][&#x27;category&#x27;] == expected_category</code><br><code>response.json[&#x27;food&#x27;][&#x27;food_id&#x27;] == &#x27;FG-FOOD-00001&#x27;</code><br><code>&#x27;qr_code&#x27; not in response.json[&#x27;food&#x27;]</code> |
| Actual Result | Level A — 5/5 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_maps_fixed_qr_to_category</code> — [source L78](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("qr_code", "expected_category"),
    [
        ("FG-MEAT", "MEAT"),
        ("FG-DAIRY", "DAIRY"),
        ("FG-VEGETABLE", "VEGETABLE"),
        ("FG-FRUIT", "FRUIT"),
        ("FG-COOKED", "COOKED_FOOD"),
    ],
)
def test_create_food_maps_fixed_qr_to_category(client, qr_code, expected_category):
    payload = food_payload(qr_code=qr_code)
    payload.pop("category")
    payload.pop("food_id")
    response = client.post(
        "/api/v1/foods",
        json=payload,
    )

    assert response.status_code == 201
    assert response.json["food"]["category"] == expected_category
    assert response.json["food"]["food_id"] == "FG-FOOD-00001"
    assert "qr_code" not in response.json["food"]
~~~

</details>

<a id="tc-food-003"></a>

#### TC-FOOD-003 — Create food rejects unknown qr without saving

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-003 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food rejects unknown qr without saving. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = food_payload(qr_code=&#x27;FG-UNKNOWN&#x27;)</code><br><code>payload.pop(&#x27;category&#x27;)</code><br><code>payload.pop(&#x27;food_id&#x27;)</code><br><code>response = client.post(&#x27;/api/v1/foods&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_QR_CODE&#x27;</code><br><code>client.get(&#x27;/api/v1/foods&#x27;).json[&#x27;data&#x27;] == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_rejects_unknown_qr_without_saving</code> — [source L93](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_create_food_rejects_unknown_qr_without_saving(client):
    payload = food_payload(qr_code="FG-UNKNOWN")
    payload.pop("category")
    payload.pop("food_id")
    response = client.post(
        "/api/v1/foods",
        json=payload,
    )

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_QR_CODE"
    assert client.get("/api/v1/foods").json["data"] == []
~~~

</details>

<a id="tc-food-004"></a>

#### TC-FOOD-004 — Create food rejects qr category conflict without saving

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-004 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food rejects qr category conflict without saving. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(food_id=&#x27;QR-CONFLICT&#x27;, qr_code=&#x27;FG-MEAT&#x27;, category=&#x27;DAIRY&#x27;))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;QR_CATEGORY_CONFLICT&#x27;</code><br><code>client.get(&#x27;/api/v1/foods&#x27;).json[&#x27;data&#x27;] == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_rejects_qr_category_conflict_without_saving</code> — [source L107](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_create_food_rejects_qr_category_conflict_without_saving(client):
    response = client.post(
        "/api/v1/foods",
        json=food_payload(food_id="QR-CONFLICT", qr_code="FG-MEAT", category="DAIRY"),
    )

    assert response.status_code == 400
    assert response.json["error"] == "QR_CATEGORY_CONFLICT"
    assert client.get("/api/v1/foods").json["data"] == []
~~~

</details>

<a id="tc-food-005"></a>

#### TC-FOOD-005 — Create food trims qr whitespace and allows matching category

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-005 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food trims qr whitespace and allows matching category. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(food_id=&#x27;QR-TRIMMED&#x27;, qr_code=&#x27;  FG-MEAT  &#x27;, category=&#x27; MEAT &#x27;))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;food&#x27;][&#x27;category&#x27;] == &#x27;MEAT&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_trims_qr_whitespace_and_allows_matching_category</code> — [source L118](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_create_food_trims_qr_whitespace_and_allows_matching_category(client):
    response = client.post(
        "/api/v1/foods",
        json=food_payload(
            food_id="QR-TRIMMED", qr_code="  FG-MEAT  ", category=" MEAT "
        ),
    )

    assert response.status_code == 201
    assert response.json["food"]["category"] == "MEAT"
~~~

</details>

<a id="tc-food-006"></a>

#### TC-FOOD-006 — Qr with existing food id derives category when category is omitted

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-006 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Qr with existing food id derives category when category is omitted. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = food_payload(food_id=&#x27;EXISTING-FOOD-ID&#x27;, qr_code=&#x27;FG-DAIRY&#x27;)</code><br><code>payload.pop(&#x27;category&#x27;)</code><br><code>response = client.post(&#x27;/api/v1/foods&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;food&#x27;][&#x27;food_id&#x27;] == &#x27;EXISTING-FOOD-ID&#x27;</code><br><code>response.json[&#x27;food&#x27;][&#x27;category&#x27;] == &#x27;DAIRY&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_qr_with_existing_food_id_derives_category_when_category_is_omitted</code> — [source L130](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_qr_with_existing_food_id_derives_category_when_category_is_omitted(client):
    payload = food_payload(food_id="EXISTING-FOOD-ID", qr_code="FG-DAIRY")
    payload.pop("category")
    response = client.post("/api/v1/foods", json=payload)

    assert response.status_code == 201
    assert response.json["food"]["food_id"] == "EXISTING-FOOD-ID"
    assert response.json["food"]["category"] == "DAIRY"
~~~

</details>

<a id="tc-food-007"></a>

#### TC-FOOD-007 — Qr only food ids are unique and increment from sqlite id

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-007 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Qr only food ids are unique and increment from sqlite id. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>first_payload = food_payload(qr_code=&#x27;FG-MEAT&#x27;)</code><br><code>second_payload = food_payload(qr_code=&#x27;FG-FRUIT&#x27;)</code><br><code>first = client.post(&#x27;/api/v1/foods&#x27;, json=first_payload)</code><br><code>second = client.post(&#x27;/api/v1/foods&#x27;, json=second_payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == second.status_code == 201</code><br><code>first.json[&#x27;food&#x27;][&#x27;food_id&#x27;] == &#x27;FG-FOOD-00001&#x27;</code><br><code>second.json[&#x27;food&#x27;][&#x27;food_id&#x27;] == &#x27;FG-FOOD-00002&#x27;</code><br><code>first.json[&#x27;food&#x27;][&#x27;food_id&#x27;] != second.json[&#x27;food&#x27;][&#x27;food_id&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_qr_only_food_ids_are_unique_and_increment_from_sqlite_id</code> — [source L140](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_qr_only_food_ids_are_unique_and_increment_from_sqlite_id(client):
    first_payload = food_payload(qr_code="FG-MEAT")
    second_payload = food_payload(qr_code="FG-FRUIT")
    for payload in (first_payload, second_payload):
        payload.pop("category")
        payload.pop("food_id")

    first = client.post("/api/v1/foods", json=first_payload)
    second = client.post("/api/v1/foods", json=second_payload)

    assert first.status_code == second.status_code == 201
    assert first.json["food"]["food_id"] == "FG-FOOD-00001"
    assert second.json["food"]["food_id"] == "FG-FOOD-00002"
    assert first.json["food"]["food_id"] != second.json["food"]["food_id"]
~~~

</details>

<a id="tc-food-008"></a>

#### TC-FOOD-008 — Qr only food id sequence survives database reinitialization

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-008 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Qr only food id sequence survives database reinitialization. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>first_payload = food_payload(qr_code=&#x27;FG-MEAT&#x27;)</code><br><code>first_payload.pop(&#x27;category&#x27;)</code><br><code>first_payload.pop(&#x27;food_id&#x27;)</code><br><code>first = client.post(&#x27;/api/v1/foods&#x27;, json=first_payload)</code><br><code>init_db_module.init_db()</code><br><code>restarted_client = create_app().test_client()</code><br><code>second_payload = food_payload(qr_code=&#x27;FG-DAIRY&#x27;)</code><br><code>second_payload.pop(&#x27;category&#x27;)</code><br><code>second_payload.pop(&#x27;food_id&#x27;)</code><br><code>second = restarted_client.post(&#x27;/api/v1/foods&#x27;, json=second_payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.json[&#x27;food&#x27;][&#x27;food_id&#x27;] == &#x27;FG-FOOD-00001&#x27;</code><br><code>second.status_code == 201</code><br><code>second.json[&#x27;food&#x27;][&#x27;food_id&#x27;] == &#x27;FG-FOOD-00002&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_qr_only_food_id_sequence_survives_database_reinitialization</code> — [source L156](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_qr_only_food_id_sequence_survives_database_reinitialization(client):
    first_payload = food_payload(qr_code="FG-MEAT")
    first_payload.pop("category")
    first_payload.pop("food_id")
    first = client.post("/api/v1/foods", json=first_payload)
    assert first.json["food"]["food_id"] == "FG-FOOD-00001"

    init_db_module.init_db()
    restarted_client = create_app().test_client()
    second_payload = food_payload(qr_code="FG-DAIRY")
    second_payload.pop("category")
    second_payload.pop("food_id")
    second = restarted_client.post("/api/v1/foods", json=second_payload)

    assert second.status_code == 201
    assert second.json["food"]["food_id"] == "FG-FOOD-00002"
~~~

</details>

<a id="tc-food-009"></a>

#### TC-FOOD-009 — Qr only food id skips existing legacy identifier

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-009 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Qr only food id skips existing legacy identifier. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>legacy = client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(food_id=&#x27;FG-FOOD-00002&#x27;))</code><br><code>payload = food_payload(qr_code=&#x27;FG-MEAT&#x27;)</code><br><code>payload.pop(&#x27;category&#x27;)</code><br><code>payload.pop(&#x27;food_id&#x27;)</code><br><code>generated = client.post(&#x27;/api/v1/foods&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>legacy.status_code == 201</code><br><code>generated.status_code == 201</code><br><code>generated.json[&#x27;food&#x27;][&#x27;food_id&#x27;] == &#x27;FG-FOOD-00003&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_qr_only_food_id_skips_existing_legacy_identifier</code> — [source L174](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_qr_only_food_id_skips_existing_legacy_identifier(client):
    legacy = client.post(
        "/api/v1/foods", json=food_payload(food_id="FG-FOOD-00002")
    )
    payload = food_payload(qr_code="FG-MEAT")
    payload.pop("category")
    payload.pop("food_id")

    generated = client.post("/api/v1/foods", json=payload)

    assert legacy.status_code == 201
    assert generated.status_code == 201
    assert generated.json["food"]["food_id"] == "FG-FOOD-00003"
~~~

</details>

<a id="tc-food-010"></a>

#### TC-FOOD-010 — Food without id or qr is rejected

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-010 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Food without id or qr is rejected. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = food_payload()</code><br><code>payload.pop(&#x27;food_id&#x27;)</code><br><code>response = client.post(&#x27;/api/v1/foods&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>&#x27;food_id&#x27; in response.json[&#x27;fields&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_food_without_id_or_qr_is_rejected</code> — [source L189](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_food_without_id_or_qr_is_rejected(client):
    payload = food_payload()
    payload.pop("food_id")
    response = client.post("/api/v1/foods", json=payload)

    assert response.status_code == 400
    assert "food_id" in response.json["fields"]
~~~

</details>

<a id="tc-food-011"></a>

#### TC-FOOD-011 — Create food rejects unsupported category

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-011 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food rejects unsupported category. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(category=&#x27;POULTRY&#x27;))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_CATEGORY&#x27;</code><br><code>client.get(&#x27;/api/v1/foods&#x27;).json[&#x27;data&#x27;] == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_rejects_unsupported_category</code> — [source L198](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_create_food_rejects_unsupported_category(client):
    response = client.post(
        "/api/v1/foods", json=food_payload(category="POULTRY")
    )

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_CATEGORY"
    assert client.get("/api/v1/foods").json["data"] == []
~~~

</details>

<a id="tc-food-012"></a>

#### TC-FOOD-012 — Create food requires fields

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-012 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food requires fields. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | 1. <code>missing_field=&#x27;food_id&#x27;</code><br>2. <code>missing_field=&#x27;food_name&#x27;</code><br>3. <code>missing_field=&#x27;category&#x27;</code><br>4. <code>missing_field=&#x27;inserted_at&#x27;</code><br>Setup/input cố định: <code>payload = food_payload()</code><br><code>payload.pop(missing_field)</code><br><code>response = client.post(&#x27;/api/v1/foods&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>missing_field in response.json[&#x27;fields&#x27;]</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_requires_fields</code> — [source L209](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("missing_field", ["food_id", "food_name", "category", "inserted_at"])
def test_create_food_requires_fields(client, missing_field):
    payload = food_payload()
    payload.pop(missing_field)

    response = client.post("/api/v1/foods", json=payload)

    assert response.status_code == 400
    assert missing_field in response.json["fields"]
~~~

</details>

<a id="tc-food-013"></a>

#### TC-FOOD-013 — Create food rejects invalid dates

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-013 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food rejects invalid dates. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | 1. <code>field=&#x27;inserted_at&#x27;; value=&#x27;2026-02-30&#x27;</code><br>2. <code>field=&#x27;manufacture_date&#x27;; value=&#x27;not-a-date&#x27;</code><br>3. <code>field=&#x27;expiry_date&#x27;; value=&#x27;2026/10/07&#x27;</code><br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(**{field: value}))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_DATE&#x27;</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_rejects_invalid_dates</code> — [source L227](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("inserted_at", "2026-02-30"),
        ("manufacture_date", "not-a-date"),
        ("expiry_date", "2026/10/07"),
    ],
)
def test_create_food_rejects_invalid_dates(client, field, value):
    response = client.post("/api/v1/foods", json=food_payload(**{field: value}))

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_DATE"
~~~

</details>

<a id="tc-food-014"></a>

#### TC-FOOD-014 — Create food rejects invalid quantity

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-014 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food rejects invalid quantity. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | 1. <code>quantity=&#x27;one&#x27;</code><br>2. <code>quantity=-1</code><br>3. <code>quantity=inf</code><br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(quantity=quantity))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_QUANTITY&#x27;</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_rejects_invalid_quantity</code> — [source L235](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("quantity", ["one", -1, float("inf")])
def test_create_food_rejects_invalid_quantity(client, quantity):
    response = client.post("/api/v1/foods", json=food_payload(quantity=quantity))

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_QUANTITY"
~~~

</details>

<a id="tc-food-015"></a>

#### TC-FOOD-015 — Create food rejects boolean quantity

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-015 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Create food rejects boolean quantity. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(quantity=True))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_QUANTITY&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_create_food_rejects_boolean_quantity</code> — [source L242](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_create_food_rejects_boolean_quantity(client):
    response = client.post("/api/v1/foods", json=food_payload(quantity=True))

    assert response.status_code == 400
    assert response.json["error"] == "INVALID_QUANTITY"
~~~

</details>

<a id="tc-food-016"></a>

#### TC-FOOD-016 — Get foods returns created foods

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-016 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Get foods returns created foods. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>client.post(&#x27;/api/v1/foods&#x27;, json=food_payload())</code><br><code>response = client.get(&#x27;/api/v1/foods&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 200</code><br><code>response.json[&#x27;success&#x27;] is True</code><br><code>len(response.json[&#x27;data&#x27;]) == 1</code><br><code>response.json[&#x27;data&#x27;][0][&#x27;food_id&#x27;] == &#x27;FG-FOOD-001&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_get_foods_returns_created_foods</code> — [source L258](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_get_foods_returns_created_foods(client):
    client.post("/api/v1/foods", json=food_payload())

    response = client.get("/api/v1/foods")

    assert response.status_code == 200
    assert response.json["success"] is True
    assert len(response.json["data"]) == 1
    assert response.json["data"][0]["food_id"] == "FG-FOOD-001"
~~~

</details>

<a id="tc-food-017"></a>

#### TC-FOOD-017 — Get existing food

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-017 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Get existing food. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>client.post(&#x27;/api/v1/foods&#x27;, json=food_payload())</code><br><code>response = client.get(&#x27;/api/v1/foods/FG-FOOD-001&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 200</code><br><code>response.json[&#x27;food&#x27;][&#x27;food_name&#x27;] == &#x27;Milk&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_get_existing_food</code> — [source L269](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_get_existing_food(client):
    client.post("/api/v1/foods", json=food_payload())

    response = client.get("/api/v1/foods/FG-FOOD-001")

    assert response.status_code == 200
    assert response.json["food"]["food_name"] == "Milk"
~~~

</details>

<a id="tc-food-018"></a>

#### TC-FOOD-018 — Get nonexistent food returns 404

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-018 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Get nonexistent food returns 404. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.get(&#x27;/api/v1/foods/UNKNOWN&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 404</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_get_nonexistent_food_returns_404</code> — [source L278](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_get_nonexistent_food_returns_404(client):
    response = client.get("/api/v1/foods/UNKNOWN")

    assert response.status_code == 404
~~~

</details>

<a id="tc-food-019"></a>

#### TC-FOOD-019 — Reading without food id remains supported

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-019 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Reading without food id remains supported. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload())</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_reading_without_food_id_remains_supported</code> — [source L284](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_reading_without_food_id_remains_supported(client):
    response = client.post("/api/v1/readings", json=reading_payload())

    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Fresh / Normal"
~~~

</details>

<a id="tc-food-020"></a>

#### TC-FOOD-020 — Reading with registered food uses food profile

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-020 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Reading with registered food uses food profile. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>inserted_at = date.today() - timedelta(days=4)</code><br><code>client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(category=&#x27;MEAT&#x27;, inserted_at=inserted_at.isoformat(), expiry_date=(date.today() + timedelta(days=5)).isoformat()))</code><br><code>response = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(food_id=&#x27;FG-FOOD-001&#x27;))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code><br><code>&#x27;storage duration&#x27; in response.json[&#x27;freshness&#x27;][&#x27;reason&#x27;].lower()</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_reading_with_registered_food_uses_food_profile</code> — [source L291](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_reading_with_registered_food_uses_food_profile(client):
    inserted_at = date.today() - timedelta(days=4)
    client.post(
        "/api/v1/foods",
        json=food_payload(
            category="MEAT",
            inserted_at=inserted_at.isoformat(),
            expiry_date=(date.today() + timedelta(days=5)).isoformat(),
        ),
    )

    response = client.post(
        "/api/v1/readings",
        json=reading_payload(food_id="FG-FOOD-001"),
    )

    assert response.status_code == 201
    assert response.json["freshness"]["status"] == "Check Food"
    assert "storage duration" in response.json["freshness"]["reason"].lower()
~~~

</details>

<a id="tc-food-021"></a>

#### TC-FOOD-021 — Reading with unknown food id is rejected

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-021 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Reading with unknown food id is rejected. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(food_id=&#x27;UNKNOWN&#x27;))</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 404</code><br><code>response.json[&#x27;error&#x27;] == &#x27;FOOD_NOT_FOUND&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_reading_with_unknown_food_id_is_rejected</code> — [source L333](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_reading_with_unknown_food_id_is_rejected(client):
    response = client.post(
        "/api/v1/readings",
        json=reading_payload(food_id="UNKNOWN"),
    )

    assert response.status_code == 404
    assert response.json["error"] == "FOOD_NOT_FOUND"
~~~

</details>

<a id="tc-food-022"></a>

#### TC-FOOD-022 — Unknown food returns 404 without saving reading

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-022 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Unknown food returns 404 without saving reading. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = post_reading(api_client, food_id=&#x27;DOES-NOT-EXIST&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 404</code><br><code>response.json[&#x27;error&#x27;] == &#x27;FOOD_NOT_FOUND&#x27;</code><br><code>api_client.get(&#x27;/api/v1/readings&#x27;).json[&#x27;count&#x27;] == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_unknown_food_returns_404_without_saving_reading</code> — [source L155](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_unknown_food_returns_404_without_saving_reading(api_client):
    response = post_reading(api_client, food_id="DOES-NOT-EXIST")

    assert response.status_code == 404
    assert response.json["error"] == "FOOD_NOT_FOUND"
    assert api_client.get("/api/v1/readings").json["count"] == 0
~~~

</details>

<a id="tc-food-023"></a>

#### TC-FOOD-023 — Reading without food id keeps response contract

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-023 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Reading without food id keeps response contract. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = post_reading(api_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>response.json[&#x27;success&#x27;] is True</code><br><code>&#x27;freshness&#x27; in response.json</code><br><code>set(response.json[&#x27;freshness&#x27;]) == {&#x27;status&#x27;, &#x27;reason&#x27;}</code><br><code>isinstance(response.json[&#x27;freshness&#x27;][&#x27;reason&#x27;], str)</code><br><code>response.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_reading_without_food_id_keeps_response_contract</code> — [source L163](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_reading_without_food_id_keeps_response_contract(api_client):
    response = post_reading(api_client)

    assert response.status_code == 201
    assert response.json["success"] is True
    assert "freshness" in response.json
    assert set(response.json["freshness"]) == {"status", "reason"}
    assert isinstance(response.json["freshness"]["reason"], str)
    assert response.json["freshness"]["status"] == "Fresh / Normal"
~~~

</details>

<a id="tc-food-024"></a>

#### TC-FOOD-024 — Food id selects the registered category

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-024 |
| Module | Food Registration / QR — [backend/app/routes/readings.py](../backend/app/routes/readings.py); [backend/app/services/qr_category.py](../backend/app/services/qr_category.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Food id selects the registered category. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>register_food(api_client, &#x27;FG-MEAT-001&#x27;, &#x27;MEAT&#x27;, 5, 10)</code><br><code>register_food(api_client, &#x27;FG-VEG-001&#x27;, &#x27;VEGETABLE&#x27;, 5, 10)</code><br><code>meat = post_reading(api_client, food_id=&#x27;FG-MEAT-001&#x27;)</code><br><code>vegetable = post_reading(api_client, food_id=&#x27;FG-VEG-001&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>meat.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code><br><code>vegetable.json[&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Fresh / Normal&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_food_id_selects_the_registered_category</code> — [source L174](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-FOOD: FG-MEAT/DAIRY/VEGETABLE/FRUIT/COOKED -> MEAT/DAIRY/VEGETABLE/FRUIT/COOKED_FOOD. QR thay category và cho phép sinh FG-FOOD-00001... nếu thiếu ID; không có QR vẫn cần food_id/category. Date YYYY-MM-DD; food_id unique. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_food_id_selects_the_registered_category(api_client):
    register_food(api_client, "FG-MEAT-001", "MEAT", 5, 10)
    register_food(api_client, "FG-VEG-001", "VEGETABLE", 5, 10)

    meat = post_reading(api_client, food_id="FG-MEAT-001")
    vegetable = post_reading(api_client, food_id="FG-VEG-001")

    assert meat.json["freshness"]["status"] == "Check Food"
    assert vegetable.json["freshness"]["status"] == "Fresh / Normal"
~~~

</details>

<a id="tc-food-025"></a>

#### TC-FOOD-025 — Giải mã năm PNG QR thật

| Field | Value |
|---|---|
| Test Case ID | TC-FOOD-025 |
| Module | Food Registration / QR |
| Test Type | Manual |
| Priority | High |
| Objective | Giải mã năm PNG QR thật |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | qr/FG-MEAT.png, FG-DAIRY.png, FG-VEGETABLE.png, FG-FRUIT.png, FG-COOKED.png. |
| Steps | Scan/decode từng ảnh bằng scanner độc lập; ghi text thu được và đối chiếu mapping. |
| Expected Result | Nội dung trùng nhãn tương ứng để dùng mapping backend; lưu ảnh/text evidence. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FOOD; backend/app/services/qr_category.py; qr/ |
| Notes | File tồn tại và mapping code đã kiểm tra; chưa decode bitmap trong audit. |

### EVENT — Events

Event ID unique toàn bảng; mới 201, lặp ID 200 duplicate (không so payload). Backend phát gas/exposure/sensor transitions, simulator phát door. Payload lưu str(dict), không mặc định JSON chuẩn.

<a id="tc-event-001"></a>

#### TC-EVENT-001 — Events reject empty malformed and non object json

| Field | Value |
|---|---|
| Test Case ID | TC-EVENT-001 |
| Module | Events — [backend/app/routes/events.py](../backend/app/routes/events.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Events reject empty malformed and non object json. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | 1. <code>kwargs={&#x27;data&#x27;: &#x27;&#x27;, &#x27;content_type&#x27;: &#x27;application/json&#x27;}</code><br>2. <code>kwargs={&#x27;data&#x27;: &#x27;{&#x27;, &#x27;content_type&#x27;: &#x27;application/json&#x27;}</code><br>3. <code>kwargs={&#x27;json&#x27;: []}</code><br>4. <code>kwargs={&#x27;json&#x27;: None}</code><br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/events&#x27;, **kwargs)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_JSON&#x27;</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_events_reject_empty_malformed_and_non_object_json</code> — [source L494](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-EVENT: Event ID unique toàn bảng; mới 201, lặp ID 200 duplicate (không so payload). Backend phát gas/exposure/sensor transitions, simulator phát door. Payload lưu str(dict), không mặc định JSON chuẩn. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "", "content_type": "application/json"},
        {"data": "{", "content_type": "application/json"},
        {"json": []},
        {"json": None},
    ],
)
def test_events_reject_empty_malformed_and_non_object_json(client, kwargs):
    response = client.post("/api/v1/events", **kwargs)
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_JSON"
~~~

</details>

<a id="tc-event-002"></a>

#### TC-EVENT-002 — Events reject missing or invalid fields

| Field | Value |
|---|---|
| Test Case ID | TC-EVENT-002 |
| Module | Events — [backend/app/routes/events.py](../backend/app/routes/events.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Events reject missing or invalid fields. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | 1. <code>payload={&#x27;device_id&#x27;: &#x27;dev&#x27;, &#x27;timestamp&#x27;: &#x27;2026-09-25T12:00:00&#x27;, &#x27;event_type&#x27;: &#x27;door&#x27;}</code><br>2. <code>payload={&#x27;event_id&#x27;: &#x27;e&#x27;, &#x27;timestamp&#x27;: &#x27;2026-09-25T12:00:00&#x27;, &#x27;event_type&#x27;: &#x27;door&#x27;}</code><br>3. <code>payload={&#x27;event_id&#x27;: &#x27;&#x27;, &#x27;device_id&#x27;: &#x27;FG-ESP32-01&#x27;, &#x27;timestamp&#x27;: &#x27;2026-09-25T12:00:00+07:00&#x27;, &#x27;event_type&#x27;: &#x27;door_closed&#x27;, &#x27;payload&#x27;: {&#x27;source&#x27;: &#x27;test&#x27;}}</code><br>4. <code>payload={&#x27;event_id&#x27;: 12, &#x27;device_id&#x27;: &#x27;FG-ESP32-01&#x27;, &#x27;timestamp&#x27;: &#x27;2026-09-25T12:00:00+07:00&#x27;, &#x27;event_type&#x27;: &#x27;door_closed&#x27;, &#x27;payload&#x27;: {&#x27;source&#x27;: &#x27;test&#x27;}}</code><br>5. <code>payload={&#x27;event_id&#x27;: &#x27;event-001&#x27;, &#x27;device_id&#x27;: &#x27; &#x27;, &#x27;timestamp&#x27;: &#x27;2026-09-25T12:00:00+07:00&#x27;, &#x27;event_type&#x27;: &#x27;door_closed&#x27;, &#x27;payload&#x27;: {&#x27;source&#x27;: &#x27;test&#x27;}}</code><br>6. <code>payload={&#x27;event_id&#x27;: &#x27;event-001&#x27;, &#x27;device_id&#x27;: &#x27;FG-ESP32-01&#x27;, &#x27;timestamp&#x27;: &#x27;2026-09-25T12:00:00+07:00&#x27;, &#x27;event_type&#x27;: None, &#x27;payload&#x27;: {&#x27;source&#x27;: &#x27;test&#x27;}}</code><br>7. <code>payload={&#x27;event_id&#x27;: &#x27;event-001&#x27;, &#x27;device_id&#x27;: &#x27;FG-ESP32-01&#x27;, &#x27;timestamp&#x27;: &#x27;yesterday&#x27;, &#x27;event_type&#x27;: &#x27;door_closed&#x27;, &#x27;payload&#x27;: {&#x27;source&#x27;: &#x27;test&#x27;}}</code><br>Setup/input cố định: <code>response = client.post(&#x27;/api/v1/events&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;]</code> |
| Actual Result | Level A — 7/7 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_events_reject_missing_or_invalid_fields</code> — [source L512](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-EVENT: Event ID unique toàn bảng; mới 201, lặp ID 200 duplicate (không so payload). Backend phát gas/exposure/sensor transitions, simulator phát door. Payload lưu str(dict), không mặc định JSON chuẩn. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    "payload",
    [
        {"device_id": "dev", "timestamp": "2026-09-25T12:00:00", "event_type": "door"},
        {"event_id": "e", "timestamp": "2026-09-25T12:00:00", "event_type": "door"},
        event_payload(event_id=""),
        event_payload(event_id=12),
        event_payload(device_id=" "),
        event_payload(event_type=None),
        event_payload(timestamp="yesterday"),
    ],
)
def test_events_reject_missing_or_invalid_fields(client, payload):
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 400
    assert response.json["error"]
~~~

</details>

<a id="tc-event-003"></a>

#### TC-EVENT-003 — Duplicate event remains idempotent

| Field | Value |
|---|---|
| Test Case ID | TC-EVENT-003 |
| Module | Events — [backend/app/routes/events.py](../backend/app/routes/events.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Duplicate event remains idempotent. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>first = client.post(&#x27;/api/v1/events&#x27;, json=event_payload())</code><br><code>duplicate = client.post(&#x27;/api/v1/events&#x27;, json=event_payload())</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>first.status_code == 201</code><br><code>duplicate.status_code == 200</code><br><code>duplicate.json[&#x27;duplicate&#x27;] is True</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_duplicate_event_remains_idempotent</code> — [source L518](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-EVENT: Event ID unique toàn bảng; mới 201, lặp ID 200 duplicate (không so payload). Backend phát gas/exposure/sensor transitions, simulator phát door. Payload lưu str(dict), không mặc định JSON chuẩn. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_duplicate_event_remains_idempotent(client):
    first = client.post("/api/v1/events", json=event_payload())
    duplicate = client.post("/api/v1/events", json=event_payload())
    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json["duplicate"] is True
~~~

</details>

<a id="tc-event-004"></a>

#### TC-EVENT-004 — Event sync lost response retries same id and creates one row

| Field | Value |
|---|---|
| Test Case ID | TC-EVENT-004 |
| Module | Events — [backend/app/routes/events.py](../backend/app/routes/events.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Event sync lost response retries same id and creates one row. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>payload = event_payload(event_id=str(uuid.uuid4()))</code><br><code>calls = []</code><br><code>result = simulator.submit_event(payload, queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>[call[&#x27;event_id&#x27;] for call in calls] == [payload[&#x27;event_id&#x27;]] * 2</code><br><code>calls == [payload, payload]</code><br><code>result.status_code == 200</code><br><code>result.body[&#x27;duplicate&#x27;] is True</code><br><code>_event_count(payload[&#x27;event_id&#x27;]) == 1</code><br><code>simulator.load_pending_events(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_event_sync_lost_response_retries_same_id_and_creates_one_row</code> — [source L526](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-EVENT: Event ID unique toàn bảng; mới 201, lặp ID 200 duplicate (không so payload). Backend phát gas/exposure/sensor transitions, simulator phát door. Payload lưu str(dict), không mặc định JSON chuẩn. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_event_sync_lost_response_retries_same_id_and_creates_one_row(
    client, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_events.jsonl"
    payload = event_payload(event_id=str(uuid.uuid4()))
    calls = []

    class ClientResponse:
        def __init__(self, response):
            self.status_code = response.status_code
            self.body = response.get_json()

        def json(self):
            return self.body

    def post_via_test_client(_url, *, json, timeout):
        calls.append(dict(json))
        response = client.post("/api/v1/events", json=json)
        if len(calls) == 1:
            assert response.status_code == 201
            raise requests.Timeout("backend committed; response lost")
        return ClientResponse(response)

    monkeypatch.setattr(simulator.requests, "post", post_via_test_client)
    result = simulator.submit_event(
        payload, queue_file, sleep_fn=lambda _delay: None
    )

    assert [call["event_id"] for call in calls] == [payload["event_id"]] * 2
    assert calls == [payload, payload]
    assert result.status_code == 200
    assert result.body["duplicate"] is True
    assert _event_count(payload["event_id"]) == 1
    assert simulator.load_pending_events(queue_file) == []
~~~

</details>

<a id="tc-event-005"></a>

#### TC-EVENT-005 — Events missing required field reports 400

| Field | Value |
|---|---|
| Test Case ID | TC-EVENT-005 |
| Module | Events — [backend/app/routes/events.py](../backend/app/routes/events.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Events missing required field reports 400. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>payload = event_payload()</code><br><code>response = client.post(&#x27;/api/v1/events&#x27;, json=payload)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>&#x27;event_id&#x27; in response.json[&#x27;fields&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_events_missing_required_field_reports_400</code> — [source L572](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-EVENT: Event ID unique toàn bảng; mới 201, lặp ID 200 duplicate (không so payload). Backend phát gas/exposure/sensor transitions, simulator phát door. Payload lưu str(dict), không mặc định JSON chuẩn. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_events_missing_required_field_reports_400(client):
    payload = event_payload()
    del payload["event_id"]
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 400
    assert "event_id" in response.json["fields"]
~~~

</details>

<a id="tc-event-006"></a>

#### TC-EVENT-006 — Door events and sensor faults coexist through event queue

| Field | Value |
|---|---|
| Test Case ID | TC-EVENT-006 |
| Module | Events — [backend/app/routes/events.py](../backend/app/routes/events.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Door events and sensor faults coexist through event queue. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>system, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-cross-system-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>producer = simulator.DoorEventProducer()</code><br><code>opened = {&#x27;device_id&#x27;: &#x27;CROSS-DEVICE&#x27;, &#x27;timestamp&#x27;: timestamp(5), &#x27;door_open&#x27;: True, &#x27;open_duration_seconds&#x27;: 5}</code><br><code>door_open_events = producer.observe(opened)</code><br><code>simulator.enqueue_event(door_open_events[0], queue_file)</code><br><code>fault = post_reading(system, 5, door=True, duration=5, temperature=None)</code><br><code>timed_out = {**opened, &#x27;timestamp&#x27;: timestamp(35), &#x27;open_duration_seconds&#x27;: 30}</code><br><code>timeout_events = producer.observe(timed_out)</code><br><code>simulator.enqueue_event(timeout_events[0], queue_file)</code><br><code>recovered = post_reading(system, 40, door=True, duration=35, temperature=4)</code><br><code>closed = {**opened, &#x27;timestamp&#x27;: timestamp(45), &#x27;door_open&#x27;: False, &#x27;open_duration_seconds&#x27;: 0}</code><br><code>close_events = producer.observe(closed)</code><br><code>simulator.enqueue_event(close_events[0], queue_file)</code><br><code>queued = simulator.load_pending_events(queue_file)</code><br><code>stable_ids = [event[&#x27;event_id&#x27;] for event in queued]</code><br><code>first_response_was_lost = {&#x27;done&#x27;: False}</code><br><code>simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)</code><br><code>stored_door = rows(system, &quot;SELECT event_id, event_type FROM events WHERE event_type LIKE &#x27;DOOR_%&#x27; ORDER BY id&quot;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>producer.observe({&#x27;device_id&#x27;: &#x27;CROSS-DEVICE&#x27;, &#x27;timestamp&#x27;: timestamp(0), &#x27;door_open&#x27;: False, &#x27;open_duration_seconds&#x27;: 0}) == []</code><br><code>[event[&#x27;event_type&#x27;] for event in door_open_events] == [&#x27;DOOR_OPENED&#x27;]</code><br><code>fault.status_code == 201</code><br><code>[event[&#x27;event_type&#x27;] for event in timeout_events] == [&#x27;DOOR_TIMEOUT&#x27;]</code><br><code>recovered.status_code == 201</code><br><code>[event[&#x27;event_type&#x27;] for event in close_events] == [&#x27;DOOR_CLOSED&#x27;]</code><br><code>simulator.load_pending_events(queue_file) == []</code><br><code>[event[&#x27;event_id&#x27;] for event in stored_door] == stable_ids</code><br><code>[event[&#x27;event_type&#x27;] for event in stored_door] == [&#x27;DOOR_OPENED&#x27;, &#x27;DOOR_TIMEOUT&#x27;, &#x27;DOOR_CLOSED&#x27;]</code><br><code>event_types(system).count(&#x27;SENSOR_FAULT&#x27;) == 1</code><br><code>event_types(system).count(&#x27;SENSOR_RECOVERED&#x27;) == 1</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_cross_system_integration.py::test_door_events_and_sensor_faults_coexist_through_event_queue</code> — [source L306](../backend/tests/test_cross_system_integration.py) |
| Requirement / Rule | R-EVENT: Event ID unique toàn bảng; mới 201, lặp ID 200 duplicate (không so payload). Backend phát gas/exposure/sensor transitions, simulator phát door. Payload lưu str(dict), không mặc định JSON chuẩn. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_door_events_and_sensor_faults_coexist_through_event_queue(system, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    producer = simulator.DoorEventProducer()
    assert producer.observe({"device_id": "CROSS-DEVICE", "timestamp": timestamp(0),
                             "door_open": False, "open_duration_seconds": 0}) == []
    opened = {"device_id": "CROSS-DEVICE", "timestamp": timestamp(5),
              "door_open": True, "open_duration_seconds": 5}
    door_open_events = producer.observe(opened)
    assert [event["event_type"] for event in door_open_events] == ["DOOR_OPENED"]
    simulator.enqueue_event(door_open_events[0], queue_file)
    fault = post_reading(system, 5, door=True, duration=5, temperature=None)
    assert fault.status_code == 201

    timed_out = {**opened, "timestamp": timestamp(35), "open_duration_seconds": 30}
    timeout_events = producer.observe(timed_out)
    assert [event["event_type"] for event in timeout_events] == ["DOOR_TIMEOUT"]
    simulator.enqueue_event(timeout_events[0], queue_file)
    recovered = post_reading(system, 40, door=True, duration=35, temperature=4)
    assert recovered.status_code == 201

    closed = {**opened, "timestamp": timestamp(45), "door_open": False,
              "open_duration_seconds": 0}
    close_events = producer.observe(closed)
    assert [event["event_type"] for event in close_events] == ["DOOR_CLOSED"]
    simulator.enqueue_event(close_events[0], queue_file)
    queued = simulator.load_pending_events(queue_file)
    stable_ids = [event["event_id"] for event in queued]

    first_response_was_lost = {"done": False}

    def post_to_flask(url, *, json, timeout):
        response = system.post("/api/v1/events", json=json)
        result = _Response(response.status_code, response.json)
        if not first_response_was_lost["done"]:
            first_response_was_lost["done"] = True
            raise simulator.requests.Timeout("response lost after backend commit")
        return result

    monkeypatch.setattr(simulator.requests, "post", post_to_flask)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert simulator.load_pending_events(queue_file) == []
    stored_door = rows(system,
        "SELECT event_id, event_type FROM events WHERE event_type LIKE 'DOOR_%' ORDER BY id")
    assert [event["event_id"] for event in stored_door] == stable_ids
    assert [event["event_type"] for event in stored_door] == [
        "DOOR_OPENED", "DOOR_TIMEOUT", "DOOR_CLOSED"
    ]
    assert event_types(system).count("SENSOR_FAULT") == 1
    assert event_types(system).count("SENSOR_RECOVERED") == 1
~~~

</details>

<a id="tc-event-007"></a>

#### TC-EVENT-007 — Duplicate event đổi payload vẫn ACK ID cũ

| Field | Value |
|---|---|
| Test Case ID | TC-EVENT-007 |
| Module | Events |
| Test Type | Manual |
| Priority | High |
| Objective | Duplicate event đổi payload vẫn ACK ID cũ |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | POST cùng event_id hai lần, lần hai đổi payload/event_type hợp lệ. |
| Steps | Đọc HTTP và events row trong DB thử nghiệm. |
| Expected Result | 201 rồi 200 duplicate; chỉ row đầu được lưu; không tự kỳ vọng 409 như reading. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-EVENT; backend/app/routes/events.py::create_event |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

### DB — Database Transaction / Migration

Reading, state update và backend event nằm cùng transaction; event insert failure rollback. Migration thêm columns/index, giữ legacy; init không tự chạy từ run.py. Schema events thực tế khác schema khởi tạo mới.

<a id="tc-db-001"></a>

#### TC-DB-001 — Backend reinitialization preserves active gas exposure and fault

| Field | Value |
|---|---|
| Test Case ID | TC-DB-001 |
| Module | Database Transaction / Migration — [backend/app/init_db.py](../backend/app/init_db.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Backend reinitialization preserves active gas exposure and fault. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>system</code>; [fixture/helper defaults](#fixture-test-cross-system-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>connection = sqlite3.connect(system.application.config[&#x27;TEST_DB_PATH&#x27;])</code><br><code>connection.execute(&quot;UPDATE temperature_exposure_state\n           SET exposure_seconds = 7200, exposure_exceeded = 0,\n               last_valid_temperature_timestamp = ?\n           WHERE device_id = &#x27;CROSS-DEVICE&#x27; AND food_id = &#x27;&#x27;&quot;, (timestamp(45),))</code><br><code>connection.commit()</code><br><code>connection.close()</code><br><code>post_reading(system, 65, gas=None, temperature=None)</code><br><code>init_db_module.init_db()</code><br><code>restarted = system.application.test_client()</code><br><code>exposure = rows(restarted, &#x27;SELECT * FROM temperature_exposure_state&#x27;)[0]</code><br><code>before = event_types(restarted)</code><br><code>post_reading(restarted, 70, gas=None, temperature=None)</code><br><code>post_reading(restarted, 75, gas=100, temperature=6)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>event_types(system).count(&#x27;TEMPERATURE_EXPOSURE_EXCEEDED&#x27;) == 1</code><br><code>rows(restarted, &#x27;SELECT anomaly_active FROM gas_anomaly_state&#x27;)[0][&#x27;anomaly_active&#x27;] == 1</code><br><code>exposure[&#x27;exposure_seconds&#x27;] == 7215</code><br><code>exposure[&#x27;exposure_exceeded&#x27;] == 1</code><br><code>event_types(restarted).count(&#x27;TEMPERATURE_EXPOSURE_EXCEEDED&#x27;) == 1</code><br><code>rows(restarted, &quot;SELECT fault_active FROM sensor_fault_state WHERE sensor_name=&#x27;gas&#x27;&quot;)[0][&#x27;fault_active&#x27;] == 1</code><br><code>rows(restarted, &quot;SELECT fault_active FROM sensor_fault_state WHERE sensor_name=&#x27;temperature&#x27;&quot;)[0][&#x27;fault_active&#x27;] == 1</code><br><code>event_types(restarted) == before</code><br><code>event_types(restarted).count(&#x27;TEMPERATURE_EXPOSURE_EXCEEDED&#x27;) == 1</code><br><code>event_types(restarted).count(&#x27;GAS_ANOMALY_RECOVERED&#x27;) == 1</code><br><code>event_types(restarted).count(&#x27;SENSOR_RECOVERED&#x27;) == 2</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_cross_system_integration.py::test_backend_reinitialization_preserves_active_gas_exposure_and_fault</code> — [source L223](../backend/tests/test_cross_system_integration.py) |
| Requirement / Rule | R-DB: Reading, state update và backend event nằm cùng transaction; event insert failure rollback. Migration thêm columns/index, giữ legacy; init không tự chạy từ run.py. Schema events thực tế khác schema khởi tạo mới. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_backend_reinitialization_preserves_active_gas_exposure_and_fault(system):
    for index in range(10):
        post_reading(system, index * 5, gas=100, temperature=6)
    connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
    connection.execute(
        """UPDATE temperature_exposure_state
           SET exposure_seconds = 7200, exposure_exceeded = 0,
               last_valid_temperature_timestamp = ?
           WHERE device_id = 'CROSS-DEVICE' AND food_id = ''""",
        (timestamp(45),),
    )
    connection.commit()
    connection.close()
    for index in range(3):
        post_reading(system, 50 + index * 5, gas=130, temperature=6)
    assert event_types(system).count("TEMPERATURE_EXPOSURE_EXCEEDED") == 1
    post_reading(system, 65, gas=None, temperature=None)
    init_db_module.init_db()
    restarted = system.application.test_client()

    assert rows(restarted, "SELECT anomaly_active FROM gas_anomaly_state")[0]["anomaly_active"] == 1
    exposure = rows(restarted, "SELECT * FROM temperature_exposure_state")[0]
    assert exposure["exposure_seconds"] == 7215
    assert exposure["exposure_exceeded"] == 1
    assert event_types(restarted).count("TEMPERATURE_EXPOSURE_EXCEEDED") == 1
    assert rows(restarted, "SELECT fault_active FROM sensor_fault_state WHERE sensor_name='gas'")[0]["fault_active"] == 1
    assert rows(restarted, "SELECT fault_active FROM sensor_fault_state WHERE sensor_name='temperature'")[0]["fault_active"] == 1
    before = event_types(restarted)
    post_reading(restarted, 70, gas=None, temperature=None)
    assert event_types(restarted) == before
    assert event_types(restarted).count("TEMPERATURE_EXPOSURE_EXCEEDED") == 1
    post_reading(restarted, 75, gas=100, temperature=6)
    assert event_types(restarted).count("GAS_ANOMALY_RECOVERED") == 1
    assert event_types(restarted).count("SENSOR_RECOVERED") == 2
~~~

</details>

<a id="tc-db-002"></a>

#### TC-DB-002 — Food and null food contexts do not share transition state

| Field | Value |
|---|---|
| Test Case ID | TC-DB-002 |
| Module | Database Transaction / Migration — [backend/app/init_db.py](../backend/app/init_db.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Food and null food contexts do not share transition state. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>system</code>; [fixture/helper defaults](#fixture-test-cross-system-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>post_reading(system, 70, food_id=&#x27;FOOD-B&#x27;, gas=100, temperature=6)</code><br><code>post_reading(system, 72, food_id=&#x27;FOOD-B&#x27;, gas=100, temperature=None)</code><br><code>post_reading(system, 75, food_id=None, gas=100, temperature=4)</code><br><code>post_reading(system, 80, food_id=&#x27;FOOD-A&#x27;, gas=130, temperature=4)</code><br><code>states = rows(system, &#x27;SELECT device_id, food_id, anomaly_active FROM gas_anomaly_state&#x27;)</code><br><code>events = rows(system, &quot;SELECT event_type FROM events WHERE event_type LIKE &#x27;GAS_%&#x27;&quot;)</code><br><code>faults = rows(system, &quot;SELECT food_id, sensor_name, fault_active FROM sensor_fault_state WHERE sensor_name = &#x27;temperature&#x27;&quot;)</code><br><code>exposure_contexts = rows(system, &quot;SELECT food_id, exposure_seconds FROM temperature_exposure_state WHERE device_id = &#x27;CROSS-DEVICE&#x27;&quot;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>{(state[&#x27;food_id&#x27;], state[&#x27;anomaly_active&#x27;]) for state in states} == {(&#x27;FOOD-A&#x27;, 1), (&#x27;FOOD-B&#x27;, 0), (&#x27;&#x27;, 0)}</code><br><code>[event[&#x27;event_type&#x27;] for event in events] == [&#x27;GAS_ANOMALY_STARTED&#x27;]</code><br><code>{(fault[&#x27;food_id&#x27;], fault[&#x27;fault_active&#x27;]) for fault in faults} == {(&#x27;FOOD-A&#x27;, 0), (&#x27;FOOD-B&#x27;, 1), (None, 0)}</code><br><code>{context[&#x27;food_id&#x27;] for context in exposure_contexts} == {&#x27;FOOD-A&#x27;, &#x27;FOOD-B&#x27;, &#x27;&#x27;}</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_cross_system_integration.py::test_food_and_null_food_contexts_do_not_share_transition_state</code> — [source L259](../backend/tests/test_cross_system_integration.py) |
| Requirement / Rule | R-DB: Reading, state update và backend event nằm cùng transaction; event insert failure rollback. Migration thêm columns/index, giữ legacy; init không tự chạy từ run.py. Schema events thực tế khác schema khởi tạo mới. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_food_and_null_food_contexts_do_not_share_transition_state(system):
    for food_id in ("FOOD-A", "FOOD-B"):
        response = system.post("/api/v1/foods", json={
            "food_id": food_id, "food_name": food_id, "category": "MEAT",
            "inserted_at": "2026-09-26", "expiry_date": "2027-09-26",
        })
        assert response.status_code == 201
    for index in range(10):
        post_reading(system, index * 5, food_id="FOOD-A", gas=100)
    for index in range(3):
        post_reading(system, 50 + index * 5, food_id="FOOD-A", gas=130,
                     temperature=None if index == 2 else 5)
    post_reading(system, 70, food_id="FOOD-B", gas=100, temperature=6)
    post_reading(system, 72, food_id="FOOD-B", gas=100, temperature=None)
    post_reading(system, 75, food_id=None, gas=100, temperature=4)
    post_reading(system, 80, food_id="FOOD-A", gas=130, temperature=4)

    states = rows(system, "SELECT device_id, food_id, anomaly_active FROM gas_anomaly_state")
    assert {(state["food_id"], state["anomaly_active"]) for state in states} == {
        ("FOOD-A", 1), ("FOOD-B", 0), ("", 0)
    }
    events = rows(system, "SELECT event_type FROM events WHERE event_type LIKE 'GAS_%'")
    assert [event["event_type"] for event in events] == ["GAS_ANOMALY_STARTED"]

    faults = rows(system,
        "SELECT food_id, sensor_name, fault_active FROM sensor_fault_state "
        "WHERE sensor_name = 'temperature'")
    assert {(fault["food_id"], fault["fault_active"]) for fault in faults} == {
        ("FOOD-A", 0), ("FOOD-B", 1), (None, 0)
    }
    exposure_contexts = rows(system,
        "SELECT food_id, exposure_seconds FROM temperature_exposure_state "
        "WHERE device_id = 'CROSS-DEVICE'")
    assert {context["food_id"] for context in exposure_contexts} == {
        "FOOD-A", "FOOD-B", ""
    }
~~~

</details>

<a id="tc-db-003"></a>

#### TC-DB-003 — Event insert failure rolls back combined reading and transition

| Field | Value |
|---|---|
| Test Case ID | TC-DB-003 |
| Module | Database Transaction / Migration — [backend/app/init_db.py](../backend/app/init_db.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Event insert failure rolls back combined reading and transition. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>system</code>; [fixture/helper defaults](#fixture-test-cross-system-integration); không dùng DB vận hành. |
| Input | 1. <code>event_type=&#x27;GAS_ANOMALY_STARTED&#x27;</code><br>2. <code>event_type=&#x27;TEMPERATURE_EXPOSURE_EXCEEDED&#x27;</code><br>3. <code>event_type=&#x27;SENSOR_FAULT&#x27;</code><br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>connection = sqlite3.connect(system.application.config[&#x27;TEST_DB_PATH&#x27;])</code><br><code>connection.execute(f&quot;CREATE TRIGGER reject_transition_event BEFORE INSERT ON events\n        WHEN NEW.event_type = &#x27;{event_type}&#x27;\n        BEGIN SELECT RAISE(ABORT, &#x27;event insert failure&#x27;); END&quot;)</code><br><code>connection.commit()</code><br><code>connection.close()</code><br><code>kwargs = {&#x27;gas&#x27;: 130}</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(sqlite3.IntegrityError)</code><br><code>rows(system, &#x27;SELECT COUNT(*) AS n FROM sensor_readings&#x27;)[0][&#x27;n&#x27;] == 0</code><br><code>rows(system, &#x27;SELECT event_type FROM events&#x27;) == []</code><br><code>state[&#x27;anomaly_active&#x27;] == 0 and state[&#x27;consecutive_anomaly_count&#x27;] == 2</code><br><code>state[&#x27;exposure_seconds&#x27;] == 7200 and state[&#x27;exposure_exceeded&#x27;] == 0</code><br><code>rows(system, &#x27;SELECT * FROM sensor_fault_state&#x27;) == []</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_cross_system_integration.py::test_event_insert_failure_rolls_back_combined_reading_and_transition</code> — [source L360](../backend/tests/test_cross_system_integration.py) |
| Requirement / Rule | R-DB: Reading, state update và backend event nằm cùng transaction; event insert failure rollback. Migration thêm columns/index, giữ legacy; init không tự chạy từ run.py. Schema events thực tế khác schema khởi tạo mới. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("event_type", [
    "GAS_ANOMALY_STARTED", "TEMPERATURE_EXPOSURE_EXCEEDED", "SENSOR_FAULT"
])
def test_event_insert_failure_rolls_back_combined_reading_and_transition(system, event_type):
    reading_id = str(uuid.uuid4())
    if event_type == "GAS_ANOMALY_STARTED":
        connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
        connection.execute(
            """INSERT INTO gas_anomaly_state (
                   device_id, food_id, baseline, baseline_sample_count,
                   baseline_sum, consecutive_anomaly_count, anomaly_active
               ) VALUES ('CROSS-DEVICE', '', 100, 10, 1000, 2, 0)"""
        )
        connection.commit()
        connection.close()
    elif event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
        connection.execute(
            """INSERT INTO temperature_exposure_state (
                   device_id, food_id, exposure_seconds, exposure_active,
                   exposure_exceeded, last_valid_temperature_timestamp,
                   continuity_broken
               ) VALUES ('CROSS-DEVICE', '', 7200, 1, 0, ?, 0)""",
            (timestamp(0),),
        )
        connection.commit()
        connection.close()

    connection = sqlite3.connect(system.application.config["TEST_DB_PATH"])
    connection.execute(f"""CREATE TRIGGER reject_transition_event BEFORE INSERT ON events
        WHEN NEW.event_type = '{event_type}'
        BEGIN SELECT RAISE(ABORT, 'event insert failure'); END""")
    connection.commit()
    connection.close()

    kwargs = {"gas": 130}
    if event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        kwargs["temperature"] = 6
    elif event_type == "SENSOR_FAULT":
        kwargs["temperature"] = None
    with pytest.raises(sqlite3.IntegrityError):
        post_reading(system, 5, reading_id=reading_id, **kwargs)
    assert rows(system, "SELECT COUNT(*) AS n FROM sensor_readings")[0]["n"] == 0
    assert rows(system, "SELECT event_type FROM events") == []

    if event_type == "GAS_ANOMALY_STARTED":
        state = rows(system, "SELECT * FROM gas_anomaly_state")[0]
        assert state["anomaly_active"] == 0 and state["consecutive_anomaly_count"] == 2
    elif event_type == "TEMPERATURE_EXPOSURE_EXCEEDED":
        state = rows(system, "SELECT * FROM temperature_exposure_state")[0]
        assert state["exposure_seconds"] == 7200 and state["exposure_exceeded"] == 0
    else:
        assert rows(system, "SELECT * FROM sensor_fault_state") == []
~~~

</details>

<a id="tc-db-004"></a>

#### TC-DB-004 — Init db migrates existing readings without data loss

| Field | Value |
|---|---|
| Test Case ID | TC-DB-004 |
| Module | Database Transaction / Migration — [backend/app/init_db.py](../backend/app/init_db.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Init db migrates existing readings without data loss. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>database_path = tmp_path / &#x27;legacy.db&#x27;</code><br><code>legacy = connect_to_legacy_db()</code><br><code>legacy.execute(&#x27;\n        CREATE TABLE sensor_readings (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            device_id TEXT NOT NULL,\n            timestamp TEXT NOT NULL,\n            temperature_c REAL,\n            humidity_pct REAL,\n            gas_raw INTEGER,\n            door_open INTEGER NOT NULL,\n            created_at TEXT DEFAULT CURRENT_TIMESTAMP\n        )\n        &#x27;)</code><br><code>legacy.execute(&#x27;CREATE TABLE food_items (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            food_id TEXT UNIQUE NOT NULL,\n            food_name TEXT NOT NULL,\n            category TEXT NOT NULL,\n            quantity REAL,\n            inserted_at TEXT NOT NULL,\n            manufacture_date TEXT,\n            expiry_date TEXT,\n            storage_location TEXT,\n            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n        )&#x27;)</code><br><code>legacy.execute(&#x27;CREATE TABLE events (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            event_id TEXT NOT NULL UNIQUE,\n            device_id TEXT NOT NULL,\n            timestamp TEXT NOT NULL,\n            event_type TEXT NOT NULL,\n            payload TEXT,\n            door_open INTEGER NOT NULL,\n            open_duration_seconds INTEGER NOT NULL DEFAULT 0,\n            created_at TEXT DEFAULT CURRENT_TIMESTAMP\n        )&#x27;)</code><br><code>legacy.execute(&quot;INSERT INTO sensor_readings\n           (device_id, timestamp, temperature_c, humidity_pct, gas_raw, door_open)\n           VALUES (&#x27;FG-ESP32-01&#x27;, &#x27;2026-09-25T12:00:00+07:00&#x27;, 5, 60, 300, 0)&quot;)</code><br><code>legacy.execute(&quot;INSERT INTO food_items (food_id, food_name, category, inserted_at)\n           VALUES (&#x27;legacy-food&#x27;, &#x27;Legacy food&#x27;, &#x27;MEAT&#x27;, &#x27;2026-09-24&#x27;)&quot;)</code><br><code>legacy.execute(&quot;INSERT INTO events (event_id, device_id, timestamp, event_type, door_open)\n           VALUES (&#x27;legacy-event&#x27;, &#x27;device&#x27;, &#x27;2026-09-25T12:00:00&#x27;, &#x27;door&#x27;, 0)&quot;)</code><br><code>legacy.commit()</code><br><code>legacy.close()</code><br><code>init_db_module.init_db()</code><br><code>migrated = connect_to_legacy_db()</code><br><code>columns = {row[1] for row in migrated.execute(&#x27;PRAGMA table_info(sensor_readings)&#x27;)}</code><br><code>row = migrated.execute(&#x27;SELECT device_id, temperature_c, open_duration_seconds, food_id FROM sensor_readings WHERE id = 1&#x27;).fetchone()</code><br><code>food_table = migrated.execute(&quot;SELECT name FROM sqlite_master WHERE type = &#x27;table&#x27; AND name = &#x27;food_items&#x27;&quot;).fetchone()</code><br><code>index = migrated.execute(&quot;SELECT sql FROM sqlite_master WHERE type = &#x27;index&#x27; AND name = &#x27;idx_sensor_readings_device_reading_id&#x27;&quot;).fetchone()</code><br><code>migrated.close()</code><br><code>init_db_module.init_db()</code><br><code>migrated = connect_to_legacy_db()</code><br><code>historical = migrated.execute(&#x27;SELECT device_reading_id FROM sensor_readings WHERE id = 1&#x27;).fetchone()</code><br><code>preserved_food = migrated.execute(&quot;SELECT food_name FROM food_items WHERE food_id = &#x27;legacy-food&#x27;&quot;).fetchone()</code><br><code>preserved_event = migrated.execute(&quot;SELECT event_type FROM events WHERE event_id = &#x27;legacy-event&#x27;&quot;).fetchone()</code><br><code>migrated.close()</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>{&#x27;open_duration_seconds&#x27;, &#x27;food_id&#x27;, &#x27;device_reading_id&#x27;, &#x27;freshness_status&#x27;, &#x27;freshness_reason&#x27;, &#x27;freshness_evaluated_at&#x27;}.issubset(columns)</code><br><code>tuple(row) == (&#x27;FG-ESP32-01&#x27;, 5.0, 0, None)</code><br><code>food_table is not None</code><br><code>index is not None</code><br><code>tuple(historical) == (None,)</code><br><code>tuple(preserved_food) == (&#x27;Legacy food&#x27;,)</code><br><code>tuple(preserved_event) == (&#x27;door&#x27;,)</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_init_db_migrates_existing_readings_without_data_loss</code> — [source L343](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-DB: Reading, state update và backend event nằm cùng transaction; event insert failure rollback. Migration thêm columns/index, giữ legacy; init không tự chạy từ run.py. Schema events thực tế khác schema khởi tạo mới. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_init_db_migrates_existing_readings_without_data_loss(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.db"

    def connect_to_legacy_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    legacy = connect_to_legacy_db()
    legacy.execute(
        """
        CREATE TABLE sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            temperature_c REAL,
            humidity_pct REAL,
            gas_raw INTEGER,
            door_open INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    legacy.execute(
        """CREATE TABLE food_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_id TEXT UNIQUE NOT NULL,
            food_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity REAL,
            inserted_at TEXT NOT NULL,
            manufacture_date TEXT,
            expiry_date TEXT,
            storage_location TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    legacy.execute(
        """CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            device_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT,
            door_open INTEGER NOT NULL,
            open_duration_seconds INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    legacy.execute(
        """INSERT INTO sensor_readings
           (device_id, timestamp, temperature_c, humidity_pct, gas_raw, door_open)
           VALUES ('FG-ESP32-01', '2026-09-25T12:00:00+07:00', 5, 60, 300, 0)"""
    )
    legacy.execute(
        """INSERT INTO food_items (food_id, food_name, category, inserted_at)
           VALUES ('legacy-food', 'Legacy food', 'MEAT', '2026-09-24')"""
    )
    legacy.execute(
        """INSERT INTO events (event_id, device_id, timestamp, event_type, door_open)
           VALUES ('legacy-event', 'device', '2026-09-25T12:00:00', 'door', 0)"""
    )
    legacy.commit()
    legacy.close()

    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_legacy_db)
    init_db_module.init_db()

    migrated = connect_to_legacy_db()
    columns = {row[1] for row in migrated.execute("PRAGMA table_info(sensor_readings)")}
    row = migrated.execute(
        "SELECT device_id, temperature_c, open_duration_seconds, food_id "
        "FROM sensor_readings WHERE id = 1"
    ).fetchone()
    food_table = migrated.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'food_items'"
    ).fetchone()
    index = migrated.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_sensor_readings_device_reading_id'"
    ).fetchone()
    migrated.close()

    # Re-running initialization must leave the schema and historical row intact.
    init_db_module.init_db()
    migrated = connect_to_legacy_db()
    historical = migrated.execute(
        "SELECT device_reading_id FROM sensor_readings WHERE id = 1"
    ).fetchone()
    preserved_food = migrated.execute(
        "SELECT food_name FROM food_items WHERE food_id = 'legacy-food'"
    ).fetchone()
    preserved_event = migrated.execute(
        "SELECT event_type FROM events WHERE event_id = 'legacy-event'"
    ).fetchone()
    migrated.close()

    assert {
        "open_duration_seconds", "food_id", "device_reading_id",
        "freshness_status", "freshness_reason", "freshness_evaluated_at",
    }.issubset(columns)
    assert tuple(row) == ("FG-ESP32-01", 5.0, 0, None)
    assert food_table is not None
    assert index is not None
    assert tuple(historical) == (None,)
    assert tuple(preserved_food) == ("Legacy food",)
    assert tuple(preserved_event) == ("door",)
~~~

</details>

<a id="tc-db-005"></a>

#### TC-DB-005 — Event insert failure rolls back reading and fault state

| Field | Value |
|---|---|
| Test Case ID | TC-DB-005 |
| Module | Database Transaction / Migration — [backend/app/init_db.py](../backend/app/init_db.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Event insert failure rolls back reading and fault state. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>sensor_client</code>; [fixture/helper defaults](#fixture-test-sensor-fault); không dùng DB vận hành. |
| Input | 1. <code>event_type=&#x27;SENSOR_FAULT&#x27;; temperature=None</code><br>2. <code>event_type=&#x27;SENSOR_RECOVERED&#x27;; temperature=4.0</code><br>Setup/input cố định: <code>connection = connect(sensor_client)</code><br><code>reading_id = str(uuid.uuid4())</code><br><code>state = fault_state(sensor_client, &#x27;temperature&#x27;)</code><br><code>connection = connect(sensor_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(sqlite3.IntegrityError)</code><br><code>state[&#x27;fault_active&#x27;] == 1</code><br><code>state is None</code><br><code>connection.execute(&#x27;SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?&#x27;, (reading_id,)).fetchone()[0] == 0</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_sensor_fault.py::test_event_insert_failure_rolls_back_reading_and_fault_state</code> — [source L240](../backend/tests/test_sensor_fault.py) |
| Requirement / Rule | R-DB: Reading, state update và backend event nằm cùng transaction; event insert failure rollback. Migration thêm columns/index, giữ legacy; init không tự chạy từ run.py. Schema events thực tế khác schema khởi tạo mới. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("event_type,temperature", [("SENSOR_FAULT", None), ("SENSOR_RECOVERED", 4.0)])
def test_event_insert_failure_rolls_back_reading_and_fault_state(
    sensor_client, event_type, temperature
):
    if event_type == "SENSOR_RECOVERED":
        post_reading(sensor_client, seconds=1, temperature_c=None)
    connection = connect(sensor_client)
    try:
        connection.execute(f"""CREATE TRIGGER reject_sensor_event
            BEFORE INSERT ON events WHEN NEW.event_type = '{event_type}'
            BEGIN SELECT RAISE(ABORT, 'event insert failure'); END""")
        connection.commit()
    finally:
        connection.close()

    reading_id = str(uuid.uuid4())
    with pytest.raises(sqlite3.IntegrityError):
        post_reading(sensor_client, seconds=2, temperature_c=temperature,
                     device_reading_id=reading_id)

    state = fault_state(sensor_client, "temperature")
    if event_type == "SENSOR_RECOVERED":
        assert state["fault_active"] == 1
    else:
        assert state is None
    connection = connect(sensor_client)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE device_reading_id = ?",
            (reading_id,),
        ).fetchone()[0] == 0
    finally:
        connection.close()
~~~

</details>

<a id="tc-db-006"></a>

#### TC-DB-006 — Event failure rolls back reading and exposure state

| Field | Value |
|---|---|
| Test Case ID | TC-DB-006 |
| Module | Database Transaction / Migration — [backend/app/init_db.py](../backend/app/init_db.py); [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Event failure rolls back reading and exposure state. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_exposure_state(temperature_client)</code><br><code>connection = db_connect(temperature_client)</code><br><code>state = state_for(temperature_client)</code><br><code>connection = db_connect(temperature_client)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(sqlite3.IntegrityError)</code><br><code>state[&#x27;exposure_seconds&#x27;] == 7200</code><br><code>connection.execute(&#x27;SELECT COUNT(*) FROM sensor_readings WHERE timestamp = ?&#x27;, (iso_time(5),)).fetchone()[0] == 0</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_event_failure_rolls_back_reading_and_exposure_state</code> — [source L294](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-DB: Reading, state update và backend event nằm cùng transaction; event insert failure rollback. Migration thêm columns/index, giữ legacy; init không tự chạy từ run.py. Schema events thực tế khác schema khởi tạo mới. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_event_failure_rolls_back_reading_and_exposure_state(temperature_client):
    prime_exposure_state(temperature_client)
    connection = db_connect(temperature_client)
    try:
        connection.execute("""CREATE TRIGGER reject_temperature_event
            BEFORE INSERT ON events
            WHEN NEW.event_type = 'TEMPERATURE_EXPOSURE_EXCEEDED'
            BEGIN SELECT RAISE(ABORT, 'event insert failure'); END""")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(sqlite3.IntegrityError):
        post_temperature(temperature_client, 6, seconds=5, reading_id=str(uuid.uuid4()))

    state = state_for(temperature_client)
    assert state["exposure_seconds"] == 7200
    connection = db_connect(temperature_client)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM sensor_readings WHERE timestamp = ?",
            (iso_time(5),),
        ).fetchone()[0] == 0
    finally:
        connection.close()
~~~

</details>

<a id="tc-db-007"></a>

#### TC-DB-007 — Tương thích events legacy có sync_status

| Field | Value |
|---|---|
| Test Case ID | TC-DB-007 |
| Module | Database Transaction / Migration |
| Test Type | Manual |
| Priority | High |
| Objective | Tương thích events legacy có sync_status |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Bản sao DB thử nghiệm dùng schema events thực tế: sync_status DEFAULT synced, không door columns. |
| Steps | Gửi event client và reading phát SENSOR_FAULT vào bản sao; kiểm tra rows. |
| Expected Result | Insert thành công; sync_status nhận default synced; không yêu cầu door columns. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-DB; backend/app/routes/events.py::create_event; backend/app/routes/readings.py::_persist_sensor_fault_event |
| Notes | Audit chỉ đọc DB hiện tại; chưa gửi request vào DB thật. init_db mới tạo schema khác; tests hiện dùng schema mới. |

### GET — GET API / Snapshot

Latest global ORDER BY id DESC, không theo device; history mặc định 20/max100. Snapshot được lưu và trả lại; chỉ legacy freshness_status NULL mới fallback; không tự aging snapshot.

<a id="tc-get-001"></a>

#### TC-GET-001 — Snapshot 003 persists after database reopen

| Field | Value |
|---|---|
| Test Case ID | TC-GET-001 |
| Module | GET API / Snapshot — [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | Snapshot 003 persists after database reopen. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_id = str(uuid.uuid4())</code><br><code>response = client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(device_reading_id=reading_id))</code><br><code>row = _stored_reading(&#x27;FG-ESP32-01&#x27;, reading_id)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>row[&#x27;freshness_status&#x27;] == response.json[&#x27;freshness&#x27;][&#x27;status&#x27;]</code><br><code>row[&#x27;freshness_reason&#x27;] == response.json[&#x27;freshness&#x27;][&#x27;reason&#x27;]</code><br><code>row[&#x27;freshness_evaluated_at&#x27;]</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_snapshot_003_persists_after_database_reopen</code> — [source L445](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-GET: Latest global ORDER BY id DESC, không theo device; history mặc định 20/max100. Snapshot được lưu và trả lại; chỉ legacy freshness_status NULL mới fallback; không tự aging snapshot. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_snapshot_003_persists_after_database_reopen(client):
    reading_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/readings", json=reading_payload(device_reading_id=reading_id)
    )
    row = _stored_reading("FG-ESP32-01", reading_id)
    assert response.status_code == 201
    assert row["freshness_status"] == response.json["freshness"]["status"]
    assert row["freshness_reason"] == response.json["freshness"]["reason"]
    assert row["freshness_evaluated_at"]
~~~

</details>

<a id="tc-get-002"></a>

#### TC-GET-002 — History rejects non positive limit

| Field | Value |
|---|---|
| Test Case ID | TC-GET-002 |
| Module | GET API / Snapshot — [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | History rejects non positive limit. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | 1. <code>limit=&#x27;0&#x27;</code><br>2. <code>limit=&#x27;-1&#x27;</code><br>Setup/input cố định: <code>response = client.get(f&#x27;/api/v1/readings?limit={limit}&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 400</code><br><code>response.json[&#x27;error&#x27;] == &#x27;INVALID_LIMIT&#x27;</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_history_rejects_non_positive_limit</code> — [source L465](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-GET: Latest global ORDER BY id DESC, không theo device; history mặc định 20/max100. Snapshot được lưu và trả lại; chỉ legacy freshness_status NULL mới fallback; không tự aging snapshot. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("limit", ["0", "-1"])
def test_history_rejects_non_positive_limit(client, limit):
    response = client.get(f"/api/v1/readings?limit={limit}")
    assert response.status_code == 400
    assert response.json["error"] == "INVALID_LIMIT"
~~~

</details>

<a id="tc-get-003"></a>

#### TC-GET-003 — History uses default limit for missing or unparseable limit

| Field | Value |
|---|---|
| Test Case ID | TC-GET-003 |
| Module | GET API / Snapshot — [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | History uses default limit for missing or unparseable limit. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | 1. <code>limit=None</code><br>2. <code>limit=&#x27;abc&#x27;</code><br>3. <code>limit=&#x27;null&#x27;</code><br>Setup/input cố định: <code>url = &#x27;/api/v1/readings&#x27; if limit is None else f&#x27;/api/v1/readings?limit={limit}&#x27;</code><br><code>response = client.get(url)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 200</code><br><code>response.json[&#x27;limit&#x27;] == 20</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_history_uses_default_limit_for_missing_or_unparseable_limit</code> — [source L472](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-GET: Latest global ORDER BY id DESC, không theo device; history mặc định 20/max100. Snapshot được lưu và trả lại; chỉ legacy freshness_status NULL mới fallback; không tự aging snapshot. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("limit", [None, "abc", "null"])
def test_history_uses_default_limit_for_missing_or_unparseable_limit(client, limit):
    url = "/api/v1/readings" if limit is None else f"/api/v1/readings?limit={limit}"
    response = client.get(url)
    assert response.status_code == 200
    assert response.json["limit"] == 20
~~~

</details>

<a id="tc-get-004"></a>

#### TC-GET-004 — History caps oversized limit

| Field | Value |
|---|---|
| Test Case ID | TC-GET-004 |
| Module | GET API / Snapshot — [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | History caps oversized limit. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-api-hardening); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>response = client.get(&#x27;/api/v1/readings?limit=999999999&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 200</code><br><code>response.json[&#x27;limit&#x27;] == 100</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_api_hardening.py::test_history_caps_oversized_limit</code> — [source L479](../backend/tests/test_api_hardening.py) |
| Requirement / Rule | R-GET: Latest global ORDER BY id DESC, không theo device; history mặc định 20/max100. Snapshot được lưu và trả lại; chỉ legacy freshness_status NULL mới fallback; không tự aging snapshot. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_history_caps_oversized_limit(client):
    response = client.get("/api/v1/readings?limit=999999999")
    assert response.status_code == 200
    assert response.json["limit"] == 100
~~~

</details>

<a id="tc-get-005"></a>

#### TC-GET-005 — History/latest trả Check Food của reading đã liên kết MEAT quá tuổi

| Field | Value |
|---|---|
| Test Case ID | TC-GET-005 |
| Module | GET API / Snapshot — [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | History/latest trả Check Food của reading đã liên kết MEAT quá tuổi. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>client</code>; [fixture/helper defaults](#fixture-test-food-api); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>client.post(&#x27;/api/v1/foods&#x27;, json=food_payload(category=&#x27;MEAT&#x27;, inserted_at=(date.today() - timedelta(days=4)).isoformat(), expiry_date=(date.today() + timedelta(days=5)).isoformat()))</code><br><code>client.post(&#x27;/api/v1/readings&#x27;, json=reading_payload(food_id=&#x27;FG-FOOD-001&#x27;))</code><br><code>history = client.get(&#x27;/api/v1/readings&#x27;)</code><br><code>latest = client.get(&#x27;/api/v1/readings/latest&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>history.status_code == 200</code><br><code>history.json[&#x27;data&#x27;][0][&#x27;food_id&#x27;] == &#x27;FG-FOOD-001&#x27;</code><br><code>history.json[&#x27;data&#x27;][0][&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code><br><code>latest.status_code == 200</code><br><code>latest.json[&#x27;data&#x27;][&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_api.py::test_reading_history_recomputes_freshness_from_linked_food</code> — [source L312](../backend/tests/test_food_api.py) |
| Requirement / Rule | R-GET: Latest global ORDER BY id DESC, không theo device; history mặc định 20/max100. Snapshot được lưu và trả lại; chỉ legacy freshness_status NULL mới fallback; không tự aging snapshot. |
| Notes | Không thay food hoặc xóa snapshot; tên recomputes không chứng minh tính lại freshness hay legacy fallback. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_reading_history_recomputes_freshness_from_linked_food(client):
    client.post(
        "/api/v1/foods",
        json=food_payload(
            category="MEAT",
            inserted_at=(date.today() - timedelta(days=4)).isoformat(),
            expiry_date=(date.today() + timedelta(days=5)).isoformat(),
        ),
    )
    client.post("/api/v1/readings", json=reading_payload(food_id="FG-FOOD-001"))

    history = client.get("/api/v1/readings")
    latest = client.get("/api/v1/readings/latest")

    assert history.status_code == 200
    assert history.json["data"][0]["food_id"] == "FG-FOOD-001"
    assert history.json["data"][0]["freshness"]["status"] == "Check Food"
    assert latest.status_code == 200
    assert latest.json["data"]["freshness"]["status"] == "Check Food"
~~~

</details>

<a id="tc-get-006"></a>

#### TC-GET-006 — Latest/history trả food_id và freshness của reading đã tạo

| Field | Value |
|---|---|
| Test Case ID | TC-GET-006 |
| Module | GET API / Snapshot — [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | Latest/history trả food_id và freshness của reading đã tạo. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>api_client</code>; [fixture/helper defaults](#fixture-test-food-freshness-integration); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>register_food(api_client, &#x27;FG-LATEST&#x27;, &#x27;MEAT&#x27;, 4, 10)</code><br><code>post_reading(api_client, food_id=&#x27;FG-LATEST&#x27;)</code><br><code>latest = api_client.get(&#x27;/api/v1/readings/latest&#x27;)</code><br><code>history = api_client.get(&#x27;/api/v1/readings&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>latest.status_code == 200</code><br><code>latest.json[&#x27;data&#x27;][&#x27;food_id&#x27;] == &#x27;FG-LATEST&#x27;</code><br><code>latest.json[&#x27;data&#x27;][&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code><br><code>history.status_code == 200</code><br><code>history.json[&#x27;data&#x27;][0][&#x27;food_id&#x27;] == &#x27;FG-LATEST&#x27;</code><br><code>history.json[&#x27;data&#x27;][0][&#x27;freshness&#x27;][&#x27;status&#x27;] == &#x27;Check Food&#x27;</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_food_freshness_integration.py::test_latest_and_history_reload_linked_food_for_freshness</code> — [source L185](../backend/tests/test_food_freshness_integration.py) |
| Requirement / Rule | R-GET: Latest global ORDER BY id DESC, không theo device; history mặc định 20/max100. Snapshot được lưu và trả lại; chỉ legacy freshness_status NULL mới fallback; không tự aging snapshot. |
| Notes | Không kiểm chứng reload sau thay metadata, aging hoặc legacy fallback. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_latest_and_history_reload_linked_food_for_freshness(api_client):
    register_food(api_client, "FG-LATEST", "MEAT", 4, 10)
    post_reading(api_client, food_id="FG-LATEST")

    latest = api_client.get("/api/v1/readings/latest")
    history = api_client.get("/api/v1/readings")

    assert latest.status_code == 200
    assert latest.json["data"]["food_id"] == "FG-LATEST"
    assert latest.json["data"]["freshness"]["status"] == "Check Food"
    assert history.status_code == 200
    assert history.json["data"][0]["food_id"] == "FG-LATEST"
    assert history.json["data"][0]["freshness"]["status"] == "Check Food"
~~~

</details>

<a id="tc-get-007"></a>

#### TC-GET-007 — Post latest and history return persisted exposure freshness

| Field | Value |
|---|---|
| Test Case ID | TC-GET-007 |
| Module | GET API / Snapshot — [backend/app/routes/readings.py](../backend/app/routes/readings.py) |
| Test Type | Automated |
| Priority | Medium |
| Objective | Post latest and history return persisted exposure freshness. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>temperature_client</code>; [fixture/helper defaults](#fixture-test-temperature-exposure); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>prime_exposure_state(temperature_client, exposure_seconds=7200, exceeded=True)</code><br><code>response = post_temperature(temperature_client, 6, seconds=5)</code><br><code>expected = response.json[&#x27;freshness&#x27;]</code><br><code>latest = temperature_client.get(&#x27;/api/v1/readings/latest&#x27;)</code><br><code>history = temperature_client.get(&#x27;/api/v1/readings&#x27;)</code> |
| Steps | 1. Tạo DB/fixture tạm và input.<br>2. Thực hiện POST/GET/service/SQL setup/fault injection đúng thứ tự scenario bên dưới.<br>3. Kiểm tra response, rows, state/events; fixture cô lập từng invocation. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>expected[&#x27;status&#x27;] == &#x27;Check Food&#x27;</code><br><code>latest.status_code == 200</code><br><code>latest.json[&#x27;data&#x27;][&#x27;freshness&#x27;] == expected</code><br><code>history.status_code == 200</code><br><code>history.json[&#x27;data&#x27;][0][&#x27;freshness&#x27;] == expected</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>backend/tests/test_temperature_exposure.py::test_post_latest_and_history_return_persisted_exposure_freshness</code> — [source L261](../backend/tests/test_temperature_exposure.py) |
| Requirement / Rule | R-GET: Latest global ORDER BY id DESC, không theo device; history mặc định 20/max100. Snapshot được lưu và trả lại; chỉ legacy freshness_status NULL mới fallback; không tự aging snapshot. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_post_latest_and_history_return_persisted_exposure_freshness(temperature_client):
    prime_exposure_state(temperature_client, exposure_seconds=7200, exceeded=True)
    response = post_temperature(temperature_client, 6, seconds=5)
    assert response.status_code == 201
    expected = response.json["freshness"]
    assert expected["status"] == "Check Food"

    latest = temperature_client.get("/api/v1/readings/latest")
    history = temperature_client.get("/api/v1/readings")
    assert latest.status_code == 200
    assert latest.json["data"]["freshness"] == expected
    assert history.status_code == 200
    assert history.json["data"][0]["freshness"] == expected
~~~

</details>

<a id="tc-get-008"></a>

#### TC-GET-008 — Legacy fallback không có snapshot

| Field | Value |
|---|---|
| Test Case ID | TC-GET-008 |
| Module | GET API / Snapshot |
| Test Type | Manual |
| Priority | High |
| Objective | Legacy fallback không có snapshot |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | DB tạm: row có freshness_status=NULL, sensors normal, linked MEAT inserted=D-4. |
| Steps | GET latest và history; inspect DB sau GET. |
| Expected Result | Fallback trả Check Food vì storage; không tự backfill snapshot, không tái dựng exposure lịch sử. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-GET; backend/app/routes/readings.py::get_latest_reading/get_readings |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-get-009"></a>

#### TC-GET-009 — Snapshot không tự aging qua ngày mới

| Field | Value |
|---|---|
| Test Case ID | TC-GET-009 |
| Module | GET API / Snapshot |
| Test Type | Manual |
| Priority | High |
| Objective | Snapshot không tự aging qua ngày mới |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Lưu Fresh snapshot tại server day D; tiến môi trường test sang D+5 mà không gửi reading mới. |
| Steps | GET latest/history tại D+5; đối chiếu response POST gốc. |
| Expected Result | Giữ snapshot cũ; không tự tính storage/expiry mới khi snapshot đã có. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-GET; backend/app/routes/readings.py::get_latest_reading/get_readings |
| Notes | Chưa có automated clock-advance assertion; persistence test không chứng minh aging. |

<a id="tc-get-010"></a>

#### TC-GET-010 — Latest global theo insertion id

| Field | Value |
|---|---|
| Test Case ID | TC-GET-010 |
| Module | GET API / Snapshot |
| Test Type | Manual |
| Priority | High |
| Objective | Latest global theo insertion id |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | POST device A timestamp mới; POST device B timestamp cũ hơn sau A. |
| Steps | GET latest, thử thêm query device_id=A, đọc history. |
| Expected Result | Latest trả B vì id lớn nhất; query device_id không được route dùng để lọc; history global. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-GET; backend/app/routes/readings.py::get_latest_reading/get_readings |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-get-011"></a>

#### TC-GET-011 — GET khi chưa có reading

| Field | Value |
|---|---|
| Test Case ID | TC-GET-011 |
| Module | GET API / Snapshot |
| Test Type | Manual |
| Priority | High |
| Objective | GET khi chưa có reading |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | DB thử nghiệm initialized và sensor_readings rỗng. |
| Steps | GET latest và GET readings. |
| Expected Result | Latest 404 NO_DATA; history 200, count=0, data=[]. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-GET; backend/app/routes/readings.py::get_latest_reading/get_readings |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

### SIM — Simulator Reliability / Polling / AUTO_TEST

Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses.

<a id="tc-sim-001"></a>

#### TC-SIM-001 — Auto test runs fresh use soon check food in order

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-001 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Auto test runs fresh use soon check food in order. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch, capsys</code>; [fixture/helper defaults](#fixture-test-simulator-auto-test-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>posted, food_ids = install_auto_test_backend(monkeypatch, [PollResponse(&#x27;Fresh / Normal&#x27;), PollResponse(&#x27;Use Soon&#x27;), PollResponse(&#x27;Check Food&#x27;)])</code><br><code>output = capsys.readouterr().out</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.run_auto_test() is True</code><br><code>len(posted) == 3</code><br><code>len({reading[&#x27;device_reading_id&#x27;] for reading in posted}) == 3</code><br><code>len({reading[&#x27;device_id&#x27;] for reading in posted}) == 1</code><br><code>all((reading[&#x27;gas_raw&#x27;] == 300 for reading in posted))</code><br><code>[reading[&#x27;open_duration_seconds&#x27;] for reading in posted] == [0, 0, 30]</code><br><code>&#x27;food_id&#x27; not in posted[0]</code><br><code>posted[1][&#x27;food_id&#x27;] == food_ids[0]</code><br><code>&#x27;freshness&#x27; not in posted[0]</code><br><code>&#x27;BACKEND STATUS: Fresh / Normal&#x27; in output</code><br><code>&#x27;BACKEND STATUS: Use Soon&#x27; in output</code><br><code>&#x27;BACKEND STATUS: Check Food&#x27; in output</code><br><code>&#x27;AUTO TEST RESULT: 3/3 PASS&#x27; in output</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_auto_test.py::test_auto_test_runs_fresh_use_soon_check_food_in_order</code> — [source L52](../firmware/tests/test_simulator_auto_test.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_auto_test_runs_fresh_use_soon_check_food_in_order(monkeypatch, capsys):
    posted, food_ids = install_auto_test_backend(
        monkeypatch,
        [
            PollResponse("Fresh / Normal"),
            PollResponse("Use Soon"),
            PollResponse("Check Food"),
        ],
    )

    assert simulator.run_auto_test() is True

    assert len(posted) == 3
    assert len({reading["device_reading_id"] for reading in posted}) == 3
    assert len({reading["device_id"] for reading in posted}) == 1
    assert all(reading["gas_raw"] == 300 for reading in posted)
    assert [reading["open_duration_seconds"] for reading in posted] == [0, 0, 30]
    assert "food_id" not in posted[0]
    assert posted[1]["food_id"] == food_ids[0]
    assert "freshness" not in posted[0]
    output = capsys.readouterr().out
    assert "BACKEND STATUS: Fresh / Normal" in output
    assert "BACKEND STATUS: Use Soon" in output
    assert "BACKEND STATUS: Check Food" in output
    assert "AUTO TEST RESULT: 3/3 PASS" in output
~~~

</details>

<a id="tc-sim-002"></a>

#### TC-SIM-002 — Auto test reports poll failure without faking expected status

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-002 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Auto test reports poll failure without faking expected status. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch, capsys</code>; [fixture/helper defaults](#fixture-test-simulator-auto-test-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>posted, _food_ids = install_auto_test_backend(monkeypatch, [PollResponse(&#x27;Fresh / Normal&#x27;), http_500_response(), PollResponse(&#x27;Check Food&#x27;)])</code><br><code>output = capsys.readouterr().out</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.run_auto_test() is False</code><br><code>len(posted) == 3</code><br><code>&#x27;HTTP 500&#x27; in output</code><br><code>&#x27;EXPECTED STATUS: Use Soon&#x27; in output</code><br><code>&#x27;ACTUAL LED: GREEN&#x27; in output</code><br><code>&#x27;AUTO TEST RESULT: FAIL (2/3 PASS)&#x27; in output</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_auto_test.py::test_auto_test_reports_poll_failure_without_faking_expected_status</code> — [source L79](../firmware/tests/test_simulator_auto_test.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_auto_test_reports_poll_failure_without_faking_expected_status(
    monkeypatch, capsys
):
    posted, _food_ids = install_auto_test_backend(
        monkeypatch,
        [
            PollResponse("Fresh / Normal"),
            http_500_response(),
            PollResponse("Check Food"),
        ],
    )

    assert simulator.run_auto_test() is False
    assert len(posted) == 3
    output = capsys.readouterr().out
    assert "HTTP 500" in output
    assert "EXPECTED STATUS: Use Soon" in output
    assert "ACTUAL LED: GREEN" in output
    assert "AUTO TEST RESULT: FAIL (2/3 PASS)" in output
~~~

</details>

<a id="tc-sim-003"></a>

#### TC-SIM-003 — Encoder maps fields and preserves timestamp and id

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-003 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Encoder maps fields and preserves timestamp and id. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>original = deepcopy(canonical_payload)</code><br><code>compact = simulator.encode_compact_reading(canonical_payload)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>compact == {&#x27;id&#x27;: original[&#x27;device_reading_id&#x27;], &#x27;d&#x27;: &#x27;esp32_01&#x27;, &#x27;t&#x27;: 1790323200, &#x27;tc&#x27;: 5.2, &#x27;h&#x27;: 61.5, &#x27;g&#x27;: 302, &#x27;o&#x27;: 0, &#x27;od&#x27;: 0, &#x27;f&#x27;: &#x27;FOOD001&#x27;}</code><br><code>canonical_payload == original</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_encoder_maps_fields_and_preserves_timestamp_and_id</code> — [source L25](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_encoder_maps_fields_and_preserves_timestamp_and_id(canonical_payload):
    original = deepcopy(canonical_payload)

    compact = simulator.encode_compact_reading(canonical_payload)

    assert compact == {
        "id": original["device_reading_id"],
        "d": "esp32_01",
        "t": 1790323200,
        "tc": 5.2,
        "h": 61.5,
        "g": 302,
        "o": 0,
        "od": 0,
        "f": "FOOD001",
    }
    assert canonical_payload == original
~~~

</details>

<a id="tc-sim-004"></a>

#### TC-SIM-004 — Encoder maps boolean door values

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-004 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Encoder maps boolean door values. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | 1. <code>door_open=False; expected=0</code><br>2. <code>door_open=True; expected=1</code><br>Setup/input cố định: <code>canonical_payload[&#x27;door_open&#x27;] = door_open</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.encode_compact_reading(canonical_payload)[&#x27;o&#x27;] == expected</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_encoder_maps_boolean_door_values</code> — [source L45](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(("door_open", "expected"), [(False, 0), (True, 1)])
def test_encoder_maps_boolean_door_values(canonical_payload, door_open, expected):
    canonical_payload["door_open"] = door_open
    assert simulator.encode_compact_reading(canonical_payload)["o"] == expected
~~~

</details>

<a id="tc-sim-005"></a>

#### TC-SIM-005 — Encoder rejects non boolean door values

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-005 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Encoder rejects non boolean door values. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | 1. <code>door_open=0</code><br>2. <code>door_open=1</code><br>3. <code>door_open=&#x27;true&#x27;</code><br>4. <code>door_open=None</code><br>Setup/input cố định: <code>canonical_payload[&#x27;door_open&#x27;] = door_open</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ValueError, match=&#x27;door_open must be a boolean&#x27;)</code> |
| Actual Result | Level A — 4/4 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_encoder_rejects_non_boolean_door_values</code> — [source L51](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("door_open", [0, 1, "true", None])
def test_encoder_rejects_non_boolean_door_values(canonical_payload, door_open):
    canonical_payload["door_open"] = door_open
    with pytest.raises(ValueError, match="door_open must be a boolean"):
        simulator.encode_compact_reading(canonical_payload)
~~~

</details>

<a id="tc-sim-006"></a>

#### TC-SIM-006 — Encoder rejects invalid timestamp

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-006 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Encoder rejects invalid timestamp. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>canonical_payload[&#x27;timestamp&#x27;] = &#x27;2026-09-25&#x27;</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(ValueError, match=&#x27;valid ISO datetime&#x27;)</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_encoder_rejects_invalid_timestamp</code> — [source L57](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_encoder_rejects_invalid_timestamp(canonical_payload):
    canonical_payload["timestamp"] = "2026-09-25"
    with pytest.raises(ValueError, match="valid ISO datetime"):
        simulator.encode_compact_reading(canonical_payload)
~~~

</details>

<a id="tc-sim-007"></a>

#### TC-SIM-007 — Encoder defaults duration and omits absent food id

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-007 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Encoder defaults duration and omits absent food id. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>canonical_payload.pop(&#x27;open_duration_seconds&#x27;)</code><br><code>canonical_payload.pop(&#x27;food_id&#x27;)</code><br><code>compact = simulator.encode_compact_reading(canonical_payload)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>compact[&#x27;od&#x27;] == 0</code><br><code>&#x27;f&#x27; not in compact</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_encoder_defaults_duration_and_omits_absent_food_id</code> — [source L63](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_encoder_defaults_duration_and_omits_absent_food_id(canonical_payload):
    canonical_payload.pop("open_duration_seconds")
    canonical_payload.pop("food_id")

    compact = simulator.encode_compact_reading(canonical_payload)

    assert compact["od"] == 0
    assert "f" not in compact
~~~

</details>

<a id="tc-sim-008"></a>

#### TC-SIM-008 — Send reading posts compact body and leaves input unchanged

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-008 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Send reading posts compact body and leaves input unchanged. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>captured = {}</code><br><code>original = deepcopy(canonical_payload)</code><br><code>response = simulator.send_reading(canonical_payload)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>captured[&#x27;url&#x27;] == simulator.API_URL</code><br><code>captured[&#x27;timeout&#x27;] == 5</code><br><code>set(captured[&#x27;body&#x27;]) == {&#x27;id&#x27;, &#x27;d&#x27;, &#x27;t&#x27;, &#x27;tc&#x27;, &#x27;h&#x27;, &#x27;g&#x27;, &#x27;o&#x27;, &#x27;od&#x27;, &#x27;f&#x27;}</code><br><code>not {&#x27;device_id&#x27;, &#x27;timestamp&#x27;, &#x27;temperature_c&#x27;, &#x27;humidity_pct&#x27;, &#x27;gas_raw&#x27;, &#x27;door_open&#x27;, &#x27;device_reading_id&#x27;} &amp; captured[&#x27;body&#x27;].keys()</code><br><code>captured[&#x27;body&#x27;][&#x27;id&#x27;] == original[&#x27;device_reading_id&#x27;]</code><br><code>canonical_payload == original</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_send_reading_posts_compact_body_and_leaves_input_unchanged</code> — [source L73](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_send_reading_posts_compact_body_and_leaves_input_unchanged(
    canonical_payload, monkeypatch
):
    captured = {}

    class Response:
        status_code = 201
        text = "{}"

        @staticmethod
        def json():
            return {"device_reading_id": canonical_payload["device_reading_id"]}

    def fake_post(url, *, json, timeout):
        captured.update(url=url, body=deepcopy(json), timeout=timeout)
        return Response()

    original = deepcopy(canonical_payload)
    monkeypatch.setattr(simulator.requests, "post", fake_post)

    response = simulator.send_reading(canonical_payload)

    assert response.status_code == 201
    assert captured["url"] == simulator.API_URL
    assert captured["timeout"] == 5
    assert set(captured["body"]) == {"id", "d", "t", "tc", "h", "g", "o", "od", "f"}
    assert not ({"device_id", "timestamp", "temperature_c", "humidity_pct", "gas_raw", "door_open", "device_reading_id"} & captured["body"].keys())
    assert captured["body"]["id"] == original["device_reading_id"]
    assert canonical_payload == original
~~~

</details>

<a id="tc-sim-009"></a>

#### TC-SIM-009 — Queue stays canonical and retries send identical compact body

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-009 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Queue stays canonical and retries send identical compact body. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_readings.jsonl&#x27;</code><br><code>queued_json = json.loads(queue_file.read_text(encoding=&#x27;utf-8&#x27;).strip())</code><br><code>bodies = []</code><br><code>statuses = iter((503, 201))</code><br><code>simulator.send_with_retry(simulator.load_pending_readings(queue_file)[0], queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.enqueue_reading(canonical_payload, queue_file)</code><br><code>queued_json == canonical_payload</code><br><code>&#x27;device_reading_id&#x27; in queued_json and &#x27;id&#x27; not in queued_json</code><br><code>bodies[0] == bodies[1]</code><br><code>bodies[0][&#x27;id&#x27;] == canonical_payload[&#x27;device_reading_id&#x27;]</code><br><code>simulator.load_pending_readings(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_queue_stays_canonical_and_retries_send_identical_compact_body</code> — [source L104](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_queue_stays_canonical_and_retries_send_identical_compact_body(
    canonical_payload, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_readings.jsonl"
    assert simulator.enqueue_reading(canonical_payload, queue_file)
    queued_json = json.loads(queue_file.read_text(encoding="utf-8").strip())
    assert queued_json == canonical_payload
    assert "device_reading_id" in queued_json and "id" not in queued_json

    bodies = []
    statuses = iter((503, 201))

    class Response:
        text = "{}"

        def __init__(self, status_code):
            self.status_code = status_code

        def json(self):
            return {"device_reading_id": canonical_payload["device_reading_id"]}

    def fake_post(_url, *, json, timeout):
        bodies.append(deepcopy(json))
        return Response(next(statuses))

    monkeypatch.setattr(simulator.requests, "post", fake_post)

    simulator.send_with_retry(
        simulator.load_pending_readings(queue_file)[0],
        queue_file,
        sleep_fn=lambda _delay: None,
    )

    assert bodies[0] == bodies[1]
    assert bodies[0]["id"] == canonical_payload["device_reading_id"]
    assert simulator.load_pending_readings(queue_file) == []
~~~

</details>

<a id="tc-sim-010"></a>

#### TC-SIM-010 — Restart recovery encodes original queued identity

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-010 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Restart recovery encodes original queued identity. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_readings.jsonl&#x27;</code><br><code>simulator.enqueue_reading(canonical_payload, queue_file)</code><br><code>recovered = simulator.load_pending_readings(queue_file)[0]</code><br><code>captured = []</code><br><code>simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>captured[0][&#x27;id&#x27;] == canonical_payload[&#x27;device_reading_id&#x27;]</code><br><code>simulator.load_pending_readings(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_restart_recovery_encodes_original_queued_identity</code> — [source L142](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_restart_recovery_encodes_original_queued_identity(canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    recovered = simulator.load_pending_readings(queue_file)[0]
    captured = []

    class Response:
        status_code = 201
        text = "{}"

        @staticmethod
        def json():
            return {"device_reading_id": canonical_payload["device_reading_id"]}

    def fake_post(_url, *, json, timeout):
        captured.append(deepcopy(json))
        return Response()

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert captured[0]["id"] == canonical_payload["device_reading_id"]
    assert simulator.load_pending_readings(queue_file) == []
~~~

</details>

<a id="tc-sim-011"></a>

#### TC-SIM-011 — Transient http statuses retry

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-011 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Transient http statuses retry. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | 1. <code>transient_status=408</code><br>2. <code>transient_status=429</code><br>3. <code>transient_status=503</code><br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_readings.jsonl&#x27;</code><br><code>simulator.enqueue_reading(canonical_payload, queue_file)</code><br><code>calls = []</code><br><code>responses = iter((StubResponse(transient_status), StubResponse(201)))</code><br><code>simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>len(calls) == 2</code><br><code>calls[0] == calls[1]</code><br><code>calls[0][&#x27;id&#x27;] == canonical_payload[&#x27;device_reading_id&#x27;]</code><br><code>simulator.load_pending_readings(queue_file) == []</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_transient_http_statuses_retry</code> — [source L179](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("transient_status", [408, 429, 503])
def test_transient_http_statuses_retry(transient_status, canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    calls = []
    responses = iter((StubResponse(transient_status), StubResponse(201)))

    def fake_post(_url, *, json, timeout):
        calls.append(deepcopy(json))
        return next(responses)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0]["id"] == canonical_payload["device_reading_id"]
    assert simulator.load_pending_readings(queue_file) == []
~~~

</details>

<a id="tc-sim-012"></a>

#### TC-SIM-012 — Permanent or conflict status dead letters and removes

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-012 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Permanent or conflict status dead letters and removes. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | 1. <code>status=400</code><br>2. <code>status=409</code><br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_readings.jsonl&#x27;</code><br><code>simulator.enqueue_reading(canonical_payload, queue_file)</code><br><code>calls = []</code><br><code>simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)</code><br><code>dead_letters = queue_file.parent / &#x27;dead_letter_readings.jsonl&#x27;</code><br><code>record = json.loads(dead_letters.read_text(encoding=&#x27;utf-8&#x27;))</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>len(calls) == 1</code><br><code>simulator.load_pending_readings(queue_file) == []</code><br><code>record[&#x27;payload&#x27;] == canonical_payload</code><br><code>record[&#x27;http_status&#x27;] == status</code><br><code>record[&#x27;payload&#x27;][&#x27;device_reading_id&#x27;] == canonical_payload[&#x27;device_reading_id&#x27;]</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_permanent_or_conflict_status_dead_letters_and_removes</code> — [source L199](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("status", [400, 409])
def test_permanent_or_conflict_status_dead_letters_and_removes(status, canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    calls = []

    def fake_post(_url, *, json, timeout):
        calls.append(deepcopy(json))
        return StubResponse(status)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert len(calls) == 1
    assert simulator.load_pending_readings(queue_file) == []
    dead_letters = queue_file.parent / "dead_letter_readings.jsonl"
    record = json.loads(dead_letters.read_text(encoding="utf-8"))
    assert record["payload"] == canonical_payload
    assert record["http_status"] == status
    assert record["payload"]["device_reading_id"] == canonical_payload["device_reading_id"]
~~~

</details>

<a id="tc-sim-013"></a>

#### TC-SIM-013 — Duplicate ack removes item after lost response

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-013 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Duplicate ack removes item after lost response. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_readings.jsonl&#x27;</code><br><code>simulator.enqueue_reading(canonical_payload, queue_file)</code><br><code>stored_ids = set()</code><br><code>calls = []</code><br><code>simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>len(stored_ids) == 1</code><br><code>len(calls) == 2</code><br><code>calls[0] == calls[1]</code><br><code>simulator.load_pending_readings(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_duplicate_ack_removes_item_after_lost_response</code> — [source L220](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_duplicate_ack_removes_item_after_lost_response(canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    stored_ids = set()
    calls = []

    def fake_post(_url, *, json, timeout):
        reading_id = json["id"]
        calls.append(deepcopy(json))
        already_stored = reading_id in stored_ids
        stored_ids.add(reading_id)
        if not already_stored:
            raise simulator.requests.Timeout("response lost after commit")
        return StubResponse(200, {"duplicate": True})

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert len(stored_ids) == 1
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert simulator.load_pending_readings(queue_file) == []
~~~

</details>

<a id="tc-sim-014"></a>

#### TC-SIM-014 — Pending readings flush in fifo and pause when head fails

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-014 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Pending readings flush in fifo and pause when head fails. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_readings.jsonl&#x27;</code><br><code>readings = []</code><br><code>attempted_ids = []</code><br><code>backend_online = False</code><br><code>simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)</code><br><code>attempted_ids.clear()</code><br><code>backend_online = True</code><br><code>simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>attempted_ids == [readings[0][&#x27;device_reading_id&#x27;]] * simulator.MAX_RETRIES</code><br><code>simulator.load_pending_readings(queue_file) == readings</code><br><code>attempted_ids == [reading[&#x27;device_reading_id&#x27;] for reading in readings]</code><br><code>simulator.load_pending_readings(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_pending_readings_flush_in_fifo_and_pause_when_head_fails</code> — [source L244](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_pending_readings_flush_in_fifo_and_pause_when_head_fails(
    canonical_payload, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_readings.jsonl"
    readings = []
    for index in range(3):
        reading = deepcopy(canonical_payload)
        reading["device_reading_id"] = str(uuid.uuid4())
        reading["temperature_c"] += index
        readings.append(reading)
        simulator.enqueue_reading(reading, queue_file)

    attempted_ids = []
    backend_online = False

    def fake_post(_url, *, json, timeout):
        attempted_ids.append(json["id"])
        if not backend_online:
            return StubResponse(503)
        return StubResponse(201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)

    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)
    assert attempted_ids == [readings[0]["device_reading_id"]] * simulator.MAX_RETRIES
    assert simulator.load_pending_readings(queue_file) == readings

    attempted_ids.clear()
    backend_online = True
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    assert attempted_ids == [reading["device_reading_id"] for reading in readings]
    assert simulator.load_pending_readings(queue_file) == []
~~~

</details>

<a id="tc-sim-015"></a>

#### TC-SIM-015 — Permanent reading does not block following readings

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-015 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Permanent reading does not block following readings. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_readings.jsonl&#x27;</code><br><code>bad = deepcopy(canonical_payload)</code><br><code>good = deepcopy(canonical_payload)</code><br><code>bad[&#x27;device_reading_id&#x27;] = str(uuid.uuid4())</code><br><code>good[&#x27;device_reading_id&#x27;] = str(uuid.uuid4())</code><br><code>simulator.enqueue_reading(bad, queue_file)</code><br><code>simulator.enqueue_reading(good, queue_file)</code><br><code>attempted = []</code><br><code>simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>attempted == [bad[&#x27;device_reading_id&#x27;], good[&#x27;device_reading_id&#x27;]]</code><br><code>simulator.load_pending_readings(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_permanent_reading_does_not_block_following_readings</code> — [source L279](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_permanent_reading_does_not_block_following_readings(canonical_payload, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_readings.jsonl"
    bad = deepcopy(canonical_payload)
    good = deepcopy(canonical_payload)
    bad["device_reading_id"] = str(uuid.uuid4())
    good["device_reading_id"] = str(uuid.uuid4())
    simulator.enqueue_reading(bad, queue_file)
    simulator.enqueue_reading(good, queue_file)
    attempted = []

    def fake_post(_url, *, json, timeout):
        attempted.append(json["device_reading_id"] if "device_reading_id" in json else json["id"])
        return StubResponse(400) if len(attempted) == 1 else StubResponse(201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)
    assert attempted == [bad["device_reading_id"], good["device_reading_id"]]
    assert simulator.load_pending_readings(queue_file) == []
~~~

</details>

<a id="tc-sim-016"></a>

#### TC-SIM-016 — Dead letter survives restart window without duplicate record

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-016 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Dead letter survives restart window without duplicate record. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_payload, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_readings.jsonl&#x27;</code><br><code>simulator.enqueue_reading(canonical_payload, queue_file)</code><br><code>response = StubResponse(400)</code><br><code>simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)</code><br><code>dead_letters = queue_file.parent / &#x27;dead_letter_readings.jsonl&#x27;</code><br><code>records = [json.loads(line) for line in dead_letters.read_text(encoding=&#x27;utf-8&#x27;).splitlines()]</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator._persist_dead_letter(canonical_payload, response, queue_file, &#x27;reading&#x27;)</code><br><code>len(records) == 1</code><br><code>records[0][&#x27;payload&#x27;] == canonical_payload</code><br><code>simulator.load_pending_readings(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_dead_letter_survives_restart_window_without_duplicate_record</code> — [source L299](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_dead_letter_survives_restart_window_without_duplicate_record(
    canonical_payload, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_readings.jsonl"
    simulator.enqueue_reading(canonical_payload, queue_file)
    response = StubResponse(400)
    assert simulator._persist_dead_letter(canonical_payload, response, queue_file, "reading")

    monkeypatch.setattr(simulator.requests, "post", lambda *_args, **_kwargs: StubResponse(400))
    simulator.process_pending_readings(queue_file, sleep_fn=lambda _delay: None)

    dead_letters = queue_file.parent / "dead_letter_readings.jsonl"
    records = [json.loads(line) for line in dead_letters.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["payload"] == canonical_payload
    assert simulator.load_pending_readings(queue_file) == []
~~~

</details>

<a id="tc-sim-017"></a>

#### TC-SIM-017 — Main checks pending queue each sampling cycle

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-017 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Main checks pending queue each sampling cycle. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-compact-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>flushes = []</code><br><code>sleeps = []</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(StopLoop)</code><br><code>len(flushes) == 2</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_compact.py::test_main_checks_pending_queue_each_sampling_cycle</code> — [source L317](../firmware/tests/test_simulator_compact.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_main_checks_pending_queue_each_sampling_cycle(monkeypatch):
    class StopLoop(Exception):
        pass

    flushes = []
    sleeps = []

    class StubThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    def stop_after_first_sample(delay):
        sleeps.append(delay)
        if len(sleeps) == 2:
            raise StopLoop

    monkeypatch.setattr(simulator, "process_pending_readings", lambda *args, **kwargs: flushes.append(True))
    monkeypatch.setattr(simulator, "process_pending_events", lambda: None)
    monkeypatch.setattr(simulator, "freshness_polling_loop", lambda: None)
    monkeypatch.setattr(simulator.threading, "Thread", StubThread)
    monkeypatch.setattr(simulator, "create_reading_payload", lambda **kwargs: {"device_reading_id": "test"})
    monkeypatch.setattr(simulator, "enqueue_reading", lambda _reading: True)
    monkeypatch.setattr(simulator, "DOOR_OPEN_DURATION", 0)
    monkeypatch.setattr(simulator.time, "sleep", stop_after_first_sample)

    with pytest.raises(StopLoop):
        simulator.main()

    assert len(flushes) == 2  # startup recovery and the running sampling cycle
~~~

</details>

<a id="tc-sim-018"></a>

#### TC-SIM-018 — Reading and event queues recover independently after restart

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-018 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Reading and event queues recover independently after restart. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-cross-system-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>reading_file = tmp_path / &#x27;pending_readings.jsonl&#x27;</code><br><code>event_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>reading = {&#x27;device_id&#x27;: &#x27;RESTART-DEVICE&#x27;, &#x27;device_reading_id&#x27;: str(uuid.uuid4()), &#x27;timestamp&#x27;: &#x27;2026-09-26T12:00:00+00:00&#x27;, &#x27;temperature_c&#x27;: 6, &#x27;humidity_pct&#x27;: 60, &#x27;gas_raw&#x27;: 130, &#x27;door_open&#x27;: False}</code><br><code>event = {&#x27;event_id&#x27;: str(uuid.uuid4()), &#x27;device_id&#x27;: &#x27;RESTART-DEVICE&#x27;, &#x27;timestamp&#x27;: reading[&#x27;timestamp&#x27;], &#x27;event_type&#x27;: &#x27;DOOR_OPENED&#x27;, &#x27;payload&#x27;: {&#x27;door_open&#x27;: True}}</code><br><code>simulator.enqueue_reading(reading, reading_file)</code><br><code>simulator.enqueue_event(event, event_file)</code><br><code>restored_reading = simulator.load_pending_readings(reading_file)[0]</code><br><code>restored_event = simulator.load_pending_events(event_file)[0]</code><br><code>simulator.process_pending_readings(reading_file, sleep_fn=lambda _delay: None)</code><br><code>dead_letter = json.loads((tmp_path / &#x27;dead_letter_readings.jsonl&#x27;).read_text(encoding=&#x27;utf-8&#x27;))</code><br><code>simulator.process_pending_events(event_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>restored_reading == reading</code><br><code>restored_event == event</code><br><code>simulator.load_pending_readings(reading_file) == []</code><br><code>simulator.load_pending_events(event_file) == [event]</code><br><code>dead_letter[&#x27;payload&#x27;] == reading</code><br><code>dead_letter[&#x27;payload&#x27;][&#x27;device_reading_id&#x27;] == reading[&#x27;device_reading_id&#x27;]</code><br><code>simulator.load_pending_readings(reading_file) == []</code><br><code>simulator.load_pending_events(event_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_cross_system.py::test_reading_and_event_queues_recover_independently_after_restart</code> — [source L18](../firmware/tests/test_simulator_cross_system.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
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
~~~

</details>

<a id="tc-sim-019"></a>

#### TC-SIM-019 — Event được queue rồi ACK 201 và dequeue

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-019 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Event được queue rồi ACK 201 và dequeue. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_event, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>sent = []</code><br><code>response = simulator.submit_event(canonical_event, queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 201</code><br><code>sent == [(simulator.EVENTS_API_URL, canonical_event, 5)]</code><br><code>simulator.load_pending_events(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_successful_event_is_acknowledged_without_queue</code> — [source L31](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | Tên without_queue chỉ đúng với queue cuối cùng rỗng; submit_event thực tế enqueue trước gửi. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_successful_event_is_acknowledged_without_queue(canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    sent = []

    def fake_post(url, *, json, timeout):
        sent.append((url, deepcopy(json), timeout))
        return StubResponse(201, {"event_id": canonical_event["event_id"]})

    monkeypatch.setattr(simulator.requests, "post", fake_post)

    response = simulator.submit_event(canonical_event, queue_file, sleep_fn=lambda _delay: None)

    assert response.status_code == 201
    assert sent == [(simulator.EVENTS_API_URL, canonical_event, 5)]
    assert simulator.load_pending_events(queue_file) == []
~~~

</details>

<a id="tc-sim-020"></a>

#### TC-SIM-020 — Offline event is durably queued and survives reload

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-020 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Offline event is durably queued and survives reload. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_event, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>attempts = []</code><br><code>backend_online = False</code><br><code>simulator.submit_event(canonical_event, queue_file, sleep_fn=lambda _delay: None)</code><br><code>lines = queue_file.read_text(encoding=&#x27;utf-8&#x27;).splitlines()</code><br><code>backend_online = True</code><br><code>simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>len(attempts) == simulator.MAX_RETRIES</code><br><code>len(lines) == 1</code><br><code>json.loads(lines[0]) == canonical_event</code><br><code>simulator.load_pending_events(queue_file) == [canonical_event]</code><br><code>attempts[-1] == canonical_event</code><br><code>simulator.load_pending_events(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_offline_event_is_durably_queued_and_survives_reload</code> — [source L48](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_offline_event_is_durably_queued_and_survives_reload(canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    attempts = []
    backend_online = False

    def offline_post(url, *, json, timeout):
        attempts.append(deepcopy(json))
        if not backend_online:
            raise requests.ConnectionError("backend offline")
        return StubResponse(201)

    monkeypatch.setattr(simulator.requests, "post", offline_post)
    simulator.submit_event(canonical_event, queue_file, sleep_fn=lambda _delay: None)

    lines = queue_file.read_text(encoding="utf-8").splitlines()
    assert len(attempts) == simulator.MAX_RETRIES
    assert len(lines) == 1
    assert json.loads(lines[0]) == canonical_event
    assert simulator.load_pending_events(queue_file) == [canonical_event]

    # Simulate a new process after recovery: state is reconstructed from JSONL.
    backend_online = True
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert attempts[-1] == canonical_event
    assert simulator.load_pending_events(queue_file) == []
~~~

</details>

<a id="tc-sim-021"></a>

#### TC-SIM-021 — Transient http status retries same canonical event

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-021 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Transient http status retries same canonical event. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_event, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | 1. <code>transient_status=408</code><br>2. <code>transient_status=429</code><br>3. <code>transient_status=503</code><br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>simulator.enqueue_event(canonical_event, queue_file)</code><br><code>sent = []</code><br><code>responses = iter((StubResponse(transient_status), StubResponse(201)))</code><br><code>simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>sent == [canonical_event, canonical_event]</code><br><code>simulator.load_pending_events(queue_file) == []</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_transient_http_status_retries_same_canonical_event</code> — [source L76](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("transient_status", [408, 429, 503])
def test_transient_http_status_retries_same_canonical_event(
    transient_status, canonical_event, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_events.jsonl"
    simulator.enqueue_event(canonical_event, queue_file)
    sent = []
    responses = iter((StubResponse(transient_status), StubResponse(201)))

    def fake_post(_url, *, json, timeout):
        sent.append(deepcopy(json))
        return next(responses)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)

    assert sent == [canonical_event, canonical_event]
    assert simulator.load_pending_events(queue_file) == []
~~~

</details>

<a id="tc-sim-022"></a>

#### TC-SIM-022 — Nonretryable or conflict event is dead lettered

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-022 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Nonretryable or conflict event is dead lettered. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_event, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | 1. <code>status=400</code><br>2. <code>status=409</code><br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>simulator.enqueue_event(canonical_event, queue_file)</code><br><code>attempts = []</code><br><code>simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)</code><br><code>record = json.loads((queue_file.parent / &#x27;dead_letter_events.jsonl&#x27;).read_text(encoding=&#x27;utf-8&#x27;))</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>attempts == [canonical_event]</code><br><code>simulator.load_pending_events(queue_file) == []</code><br><code>record[&#x27;payload&#x27;] == canonical_event</code><br><code>record[&#x27;http_status&#x27;] == status</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_nonretryable_or_conflict_event_is_dead_lettered</code> — [source L96](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("status", [400, 409])
def test_nonretryable_or_conflict_event_is_dead_lettered(status, canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    simulator.enqueue_event(canonical_event, queue_file)
    attempts = []

    def fake_post(_url, *, json, timeout):
        attempts.append(deepcopy(json))
        return StubResponse(status)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)

    assert attempts == [canonical_event]
    assert simulator.load_pending_events(queue_file) == []
    record = json.loads((queue_file.parent / "dead_letter_events.jsonl").read_text(encoding="utf-8"))
    assert record["payload"] == canonical_event
    assert record["http_status"] == status
~~~

</details>

<a id="tc-sim-023"></a>

#### TC-SIM-023 — Permanent event does not block later event

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-023 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Permanent event does not block later event. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_event, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>bad = deepcopy(canonical_event)</code><br><code>good = deepcopy(canonical_event)</code><br><code>good[&#x27;event_id&#x27;] = &#x27;event-later&#x27;</code><br><code>simulator.enqueue_event(bad, queue_file)</code><br><code>simulator.enqueue_event(good, queue_file)</code><br><code>sent_ids = []</code><br><code>simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>sent_ids == [bad[&#x27;event_id&#x27;], good[&#x27;event_id&#x27;]]</code><br><code>simulator.load_pending_events(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_permanent_event_does_not_block_later_event</code> — [source L115](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_permanent_event_does_not_block_later_event(canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    bad = deepcopy(canonical_event)
    good = deepcopy(canonical_event)
    good["event_id"] = "event-later"
    simulator.enqueue_event(bad, queue_file)
    simulator.enqueue_event(good, queue_file)
    sent_ids = []

    def fake_post(_url, *, json, timeout):
        sent_ids.append(json["event_id"])
        return StubResponse(400) if len(sent_ids) == 1 else StubResponse(201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert sent_ids == [bad["event_id"], good["event_id"]]
    assert simulator.load_pending_events(queue_file) == []
~~~

</details>

<a id="tc-sim-024"></a>

#### TC-SIM-024 — Fifo recovery stops at failed head then syncs all in order

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-024 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Fifo recovery stops at failed head then syncs all in order. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_event, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>events = []</code><br><code>sent_ids = []</code><br><code>backend_online = False</code><br><code>simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)</code><br><code>sent_ids.clear()</code><br><code>backend_online = True</code><br><code>simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>sent_ids == [events[0][&#x27;event_id&#x27;]] * simulator.MAX_RETRIES</code><br><code>simulator.load_pending_events(queue_file) == events</code><br><code>sent_ids == [event[&#x27;event_id&#x27;] for event in events]</code><br><code>simulator.load_pending_events(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_fifo_recovery_stops_at_failed_head_then_syncs_all_in_order</code> — [source L134](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_fifo_recovery_stops_at_failed_head_then_syncs_all_in_order(
    canonical_event, tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_events.jsonl"
    events = []
    for index in range(3):
        event = deepcopy(canonical_event)
        event["event_id"] = f"event-{index}"
        event["payload"]["sequence"] = index
        events.append(event)
        simulator.enqueue_event(event, queue_file)

    sent_ids = []
    backend_online = False

    def fake_post(_url, *, json, timeout):
        sent_ids.append(json["event_id"])
        return StubResponse(503 if not backend_online else 201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert sent_ids == [events[0]["event_id"]] * simulator.MAX_RETRIES
    assert simulator.load_pending_events(queue_file) == events

    sent_ids.clear()
    backend_online = True
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert sent_ids == [event["event_id"] for event in events]
    assert simulator.load_pending_events(queue_file) == []
~~~

</details>

<a id="tc-sim-025"></a>

#### TC-SIM-025 — Duplicate ack removes event

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-025 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Duplicate ack removes event. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_event, tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>simulator.enqueue_event(canonical_event, queue_file)</code><br><code>sent = []</code><br><code>response = simulator.send_event_with_retry(canonical_event, queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>response.status_code == 200</code><br><code>sent == [canonical_event]</code><br><code>simulator.load_pending_events(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_duplicate_ack_removes_event</code> — [source L165](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_duplicate_ack_removes_event(canonical_event, tmp_path, monkeypatch):
    queue_file = tmp_path / "pending_events.jsonl"
    simulator.enqueue_event(canonical_event, queue_file)
    sent = []
    monkeypatch.setattr(
        simulator,
        "send_event",
        lambda event: (sent.append(deepcopy(event)) or StubResponse(200, {"duplicate": True})),
    )

    response = simulator.send_event_with_retry(
        canonical_event, queue_file, sleep_fn=lambda _delay: None
    )

    assert response.status_code == 200
    assert sent == [canonical_event]
    assert simulator.load_pending_events(queue_file) == []
~~~

</details>

<a id="tc-sim-026"></a>

#### TC-SIM-026 — Corrupt event queue line is skipped without crashing

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-026 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Corrupt event queue line is skipped without crashing. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>canonical_event, tmp_path, capsys</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>queue_file.write_text(&#x27;{not-json}\n&#x27; + json.dumps(canonical_event) + &#x27;\n&#x27;, encoding=&#x27;utf-8&#x27;)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.load_pending_events(queue_file) == [canonical_event]</code><br><code>&#x27;invalid JSON in event queue line 1&#x27; in capsys.readouterr().out</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_corrupt_event_queue_line_is_skipped_without_crashing</code> — [source L184](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_corrupt_event_queue_line_is_skipped_without_crashing(canonical_event, tmp_path, capsys):
    queue_file = tmp_path / "pending_events.jsonl"
    queue_file.write_text("{not-json}\n" + json.dumps(canonical_event) + "\n", encoding="utf-8")

    assert simulator.load_pending_events(queue_file) == [canonical_event]
    assert "invalid JSON in event queue line 1" in capsys.readouterr().out
~~~

</details>

<a id="tc-sim-027"></a>

#### TC-SIM-027 — Main flushes event queue at startup and during sampling

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-027 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Main flushes event queue at startup and during sampling. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>flushes = []</code><br><code>sleeps = []</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br>Expected exception: <code>pytest.raises(StopLoop)</code><br><code>len(flushes) == 2</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_main_flushes_event_queue_at_startup_and_during_sampling</code> — [source L192](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_main_flushes_event_queue_at_startup_and_during_sampling(monkeypatch):
    class StopLoop(Exception):
        pass

    flushes = []
    sleeps = []

    class StubThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    def stop_after_one_sample(delay):
        sleeps.append(delay)
        if len(sleeps) == 2:
            raise StopLoop

    monkeypatch.setattr(simulator, "process_pending_readings", lambda: None)
    monkeypatch.setattr(simulator, "process_pending_events", lambda: flushes.append(True))
    monkeypatch.setattr(simulator, "freshness_polling_loop", lambda: None)
    monkeypatch.setattr(simulator.threading, "Thread", StubThread)
    monkeypatch.setattr(simulator, "create_reading_payload", lambda **_kwargs: {"event_id": "sample"})
    monkeypatch.setattr(simulator, "enqueue_reading", lambda _reading: True)
    monkeypatch.setattr(simulator, "DOOR_OPEN_DURATION", 0)
    monkeypatch.setattr(simulator.time, "sleep", stop_after_one_sample)

    with pytest.raises(StopLoop):
        simulator.main()

    assert len(flushes) == 2
~~~

</details>

<a id="tc-sim-028"></a>

#### TC-SIM-028 — Produced event uses shared queue and keeps id across retry

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-028 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Produced event uses shared queue and keeps id across retry. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>tmp_path, monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-events-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>queue_file = tmp_path / &#x27;pending_events.jsonl&#x27;</code><br><code>producer = simulator.DoorEventProducer()</code><br><code>closed = door_reading(False, 0, 0)</code><br><code>opened = door_reading(True, 0, 5)</code><br><code>simulator.submit_door_events(closed, producer, queue_file)</code><br><code>generated = simulator.submit_door_events(opened, producer, queue_file)</code><br><code>queued = simulator.load_pending_events(queue_file)</code><br><code>attempts = []</code><br><code>backend_online = False</code><br><code>simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)</code><br><code>backend_online = True</code><br><code>simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>len(generated) == 1</code><br><code>queued == generated</code><br><code>len(attempts) == simulator.MAX_RETRIES</code><br><code>all((attempt == generated[0] for attempt in attempts))</code><br><code>simulator.load_pending_events(queue_file) == generated</code><br><code>attempts[-1] == generated[0]</code><br><code>simulator.load_pending_events(queue_file) == []</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_events.py::test_produced_event_uses_shared_queue_and_keeps_id_across_retry</code> — [source L315](../firmware/tests/test_simulator_events.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_produced_event_uses_shared_queue_and_keeps_id_across_retry(
    tmp_path, monkeypatch
):
    queue_file = tmp_path / "pending_events.jsonl"
    producer = simulator.DoorEventProducer()
    monkeypatch.setattr(simulator, "submit_event", simulator.submit_event)
    closed = door_reading(False, 0, 0)
    opened = door_reading(True, 0, 5)
    simulator.submit_door_events(closed, producer, queue_file)
    generated = simulator.submit_door_events(opened, producer, queue_file)
    assert len(generated) == 1
    queued = simulator.load_pending_events(queue_file)
    assert queued == generated

    attempts = []
    backend_online = False

    def fake_post(_url, *, json, timeout):
        attempts.append(deepcopy(json))
        return StubResponse(503 if not backend_online else 201)

    monkeypatch.setattr(simulator.requests, "post", fake_post)
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert len(attempts) == simulator.MAX_RETRIES
    assert all(attempt == generated[0] for attempt in attempts)
    assert simulator.load_pending_events(queue_file) == generated

    backend_online = True
    simulator.process_pending_events(queue_file, sleep_fn=lambda _delay: None)
    assert attempts[-1] == generated[0]
    assert simulator.load_pending_events(queue_file) == []
~~~

</details>

<a id="tc-sim-029"></a>

#### TC-SIM-029 — Status maps to led from business status only

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-029 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Status maps to led from business status only. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-freshness-poll-fw); không dùng DB vận hành. |
| Input | 1. <code>status=&#x27;Fresh / Normal&#x27;; expected_led=&#x27;GREEN&#x27;</code><br>2. <code>status=&#x27;Use Soon&#x27;; expected_led=&#x27;YELLOW&#x27;</code><br>3. <code>status=&#x27;Check Food&#x27;; expected_led=&#x27;RED&#x27;</code><br>Setup/input cố định: <code>captured = {}</code><br><code>state = simulator.LedStateMachine()</code><br><code>result = simulator.poll_latest_freshness(state)</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>result == expected_led</code><br><code>state.last_led_state == expected_led</code><br><code>captured == {&#x27;url&#x27;: simulator.LATEST_READING_URL, &#x27;timeout&#x27;: simulator.FRESHNESS_POLL_TIMEOUT}</code><br><code>simulator.FRESHNESS_POLL_INTERVAL == 5</code> |
| Actual Result | Level A — 3/3 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_freshness_poll.py::test_status_maps_to_led_from_business_status_only</code> — [source L27](../firmware/tests/test_simulator_freshness_poll.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    ("status", "expected_led"),
    [
        ("Fresh / Normal", simulator.LED_GREEN),
        ("Use Soon", simulator.LED_YELLOW),
        ("Check Food", simulator.LED_RED),
    ],
)
def test_status_maps_to_led_from_business_status_only(
    status, expected_led, monkeypatch
):
    captured = {}

    def fake_get(url, *, timeout):
        captured.update(url=url, timeout=timeout)
        return FakeResponse(
            body={
                "success": True,
                "data": {
                    "freshness": {"status": status, "reason": "High humidity warning"},
                    "gas_anomaly_active": 1 if status == "Fresh / Normal" else 0,
                },
            }
        )

    monkeypatch.setattr(simulator.requests, "get", fake_get)
    state = simulator.LedStateMachine()

    result = simulator.poll_latest_freshness(state)

    assert result == expected_led
    assert state.last_led_state == expected_led
    assert captured == {
        "url": simulator.LATEST_READING_URL,
        "timeout": simulator.FRESHNESS_POLL_TIMEOUT,
    }
    assert simulator.FRESHNESS_POLL_INTERVAL == 5
~~~

</details>

<a id="tc-sim-030"></a>

#### TC-SIM-030 — Initial led state is unknown not red

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-030 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Initial led state is unknown not red. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>không có</code>; [fixture/helper defaults](#fixture-test-simulator-freshness-poll-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: Xem calls/loop trong scenario nguyên bản ngay dưới bảng. |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.LedStateMachine().last_led_state == simulator.LED_UNKNOWN</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_freshness_poll.py::test_initial_led_state_is_unknown_not_red</code> — [source L58](../firmware/tests/test_simulator_freshness_poll.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_initial_led_state_is_unknown_not_red():
    assert simulator.LedStateMachine().last_led_state == simulator.LED_UNKNOWN
~~~

</details>

<a id="tc-sim-031"></a>

#### TC-SIM-031 — Unknown status does not change last led

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-031 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Unknown status does not change last led. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch, capsys</code>; [fixture/helper defaults](#fixture-test-simulator-freshness-poll-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>state = simulator.LedStateMachine()</code><br><code>state.last_led_state = simulator.LED_YELLOW</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.poll_latest_freshness(state) == simulator.LED_YELLOW</code><br><code>&#x27;keep LED=YELLOW&#x27; in capsys.readouterr().out</code><br><code>simulator.status_to_led(&#x27;Freshly normal&#x27;) is None</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_freshness_poll.py::test_unknown_status_does_not_change_last_led</code> — [source L62](../firmware/tests/test_simulator_freshness_poll.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_unknown_status_does_not_change_last_led(monkeypatch, capsys):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_YELLOW
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(
            body={"success": True, "data": {"freshness": {"status": "Unknown"}}}
        ),
    )

    assert simulator.poll_latest_freshness(state) == simulator.LED_YELLOW
    assert "keep LED=YELLOW" in capsys.readouterr().out
    assert simulator.status_to_led("Freshly normal") is None
~~~

</details>

<a id="tc-sim-032"></a>

#### TC-SIM-032 — Poll request errors keep last led

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-032 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Poll request errors keep last led. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch, capsys</code>; [fixture/helper defaults](#fixture-test-simulator-freshness-poll-fw); không dùng DB vận hành. |
| Input | 1. <code>error=Timeout(&#x27;late&#x27;)</code><br>2. <code>error=ConnectionError(&#x27;offline&#x27;)</code><br>Setup/input cố định: <code>state = simulator.LedStateMachine()</code><br><code>state.last_led_state = simulator.LED_GREEN</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.poll_latest_freshness(state) == simulator.LED_GREEN</code><br><code>&#x27;keep LED=GREEN&#x27; in capsys.readouterr().out</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_freshness_poll.py::test_poll_request_errors_keep_last_led</code> — [source L79](../firmware/tests/test_simulator_freshness_poll.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("error", [requests.Timeout("late"), requests.ConnectionError("offline")])
def test_poll_request_errors_keep_last_led(error, monkeypatch, capsys):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_GREEN

    def fail_get(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(simulator.requests, "get", fail_get)

    assert simulator.poll_latest_freshness(state) == simulator.LED_GREEN
    assert "keep LED=GREEN" in capsys.readouterr().out
~~~

</details>

<a id="tc-sim-033"></a>

#### TC-SIM-033 — Http failure keeps last led

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-033 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Http failure keeps last led. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch, capsys</code>; [fixture/helper defaults](#fixture-test-simulator-freshness-poll-fw); không dùng DB vận hành. |
| Input | 1. <code>status_code=404</code><br>2. <code>status_code=500</code><br>Setup/input cố định: <code>state = simulator.LedStateMachine()</code><br><code>state.last_led_state = simulator.LED_RED</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.poll_latest_freshness(state) == simulator.LED_RED</code><br><code>f&#x27;HTTP {status_code}&#x27; in capsys.readouterr().out</code><br><code>state.last_led_state == simulator.LED_RED</code> |
| Actual Result | Level A — 2/2 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_freshness_poll.py::test_http_failure_keeps_last_led</code> — [source L93](../firmware/tests/test_simulator_freshness_poll.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize("status_code", [404, 500])
def test_http_failure_keeps_last_led(status_code, monkeypatch, capsys):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_RED
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(status_code=status_code),
    )

    assert simulator.poll_latest_freshness(state) == simulator.LED_RED
    assert f"HTTP {status_code}" in capsys.readouterr().out
    assert state.last_led_state == simulator.LED_RED
~~~

</details>

<a id="tc-sim-034"></a>

#### TC-SIM-034 — Missing or invalid response fields keep last led

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-034 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Missing or invalid response fields keep last led. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch</code>; [fixture/helper defaults](#fixture-test-simulator-freshness-poll-fw); không dùng DB vận hành. |
| Input | 1. <code>body=None</code><br>2. <code>body={&#x27;success&#x27;: True}</code><br>3. <code>body={&#x27;success&#x27;: True, &#x27;data&#x27;: {}}</code><br>4. <code>body={&#x27;success&#x27;: True, &#x27;data&#x27;: {&#x27;freshness&#x27;: {}}}</code><br>5. <code>body={&#x27;success&#x27;: False, &#x27;data&#x27;: {&#x27;freshness&#x27;: {&#x27;status&#x27;: &#x27;Check Food&#x27;}}}</code><br>Setup/input cố định: <code>state = simulator.LedStateMachine()</code><br><code>state.last_led_state = simulator.LED_YELLOW</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.poll_latest_freshness(state) == simulator.LED_YELLOW</code><br><code>state.last_led_state == simulator.LED_YELLOW</code> |
| Actual Result | Level A — 5/5 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_freshness_poll.py::test_missing_or_invalid_response_fields_keep_last_led</code> — [source L117](../firmware/tests/test_simulator_freshness_poll.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
@pytest.mark.parametrize(
    "body",
    [
        None,
        {"success": True},
        {"success": True, "data": {}},
        {"success": True, "data": {"freshness": {}}},
        {"success": False, "data": {"freshness": {"status": "Check Food"}}},
    ],
)
def test_missing_or_invalid_response_fields_keep_last_led(body, monkeypatch):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_YELLOW
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(body=body),
    )

    assert simulator.poll_latest_freshness(state) == simulator.LED_YELLOW
    assert state.last_led_state == simulator.LED_YELLOW
~~~

</details>

<a id="tc-sim-035"></a>

#### TC-SIM-035 — Malformed json keeps last led

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-035 |
| Module | Simulator Reliability / Polling / AUTO_TEST — [firmware/simulator.py](../firmware/simulator.py) |
| Test Type | Automated |
| Priority | High |
| Objective | Malformed json keeps last led. Phạm vi chính xác là input và assertions dưới đây. |
| Preconditions | Môi trường mục1; fixtures <code>monkeypatch, capsys</code>; [fixture/helper defaults](#fixture-test-simulator-freshness-poll-fw); không dùng DB vận hành. |
| Input | Không parametrization; một invocation.<br>Setup/input cố định: <code>state = simulator.LedStateMachine()</code><br><code>state.last_led_state = simulator.LED_GREEN</code> |
| Steps | 1. Tạo fixtures/mocks/queue tạm theo scenario.<br>2. Gọi encoder/worker/producer/poll/AUTO_TEST theo thứ tự nguyên bản bên dưới.<br>3. So payload, queue, response/LED/log bằng assertions. |
| Expected Result | Điều kiện đúng theo nhánh/loop của scenario:<br><code>simulator.poll_latest_freshness(state) == simulator.LED_GREEN</code><br><code>&#x27;malformed JSON&#x27; in capsys.readouterr().out</code> |
| Actual Result | Level A — 1/1 collected invocation(s) của function PASS trong suite 424 passed / 16.30s. Không có output hardware/browser. |
| Status | PASS |
| Automated Test | <code>firmware/tests/test_simulator_freshness_poll.py::test_malformed_json_keeps_last_led</code> — [source L130](../firmware/tests/test_simulator_freshness_poll.py) |
| Requirement / Rule | R-SIM: Canonical JSONL queue, fsync, atomic replace khi dequeue; compact reading transport. Tối đa 5 lần/batch, backoff 2/4/8/16; network/408/429/5xx retry; permanent/409 dead-letter. Poll latest 5s, lỗi giữ LED; AUTO_TEST dùng backend statuses. |
| Notes | PASS chỉ xác minh scenario/assertions hiện có; không suy ra input chưa có hoặc deployment thật. |

<details>
<summary>Scenario nguyên bản — input, thao tác và assertion context</summary>

~~~python
def test_malformed_json_keeps_last_led(monkeypatch, capsys):
    state = simulator.LedStateMachine()
    state.last_led_state = simulator.LED_GREEN
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(
            json_error=requests.exceptions.JSONDecodeError("bad json", "{", 0)
        ),
    )

    assert simulator.poll_latest_freshness(state) == simulator.LED_GREEN
    assert "malformed JSON" in capsys.readouterr().out
~~~

</details>

<a id="tc-sim-036"></a>

#### TC-SIM-036 — Backoff đúng 2/4/8/16 và 5 lần thử

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-036 |
| Module | Simulator Reliability / Polling / AUTO_TEST |
| Test Type | Manual |
| Priority | High |
| Objective | Backoff đúng 2/4/8/16 và 5 lần thử |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Mock trả network failure hoặc 503 cho cả reading/event; ghi nhận sleep_fn và request count. |
| Steps | Chạy mỗi retry worker với queue tạm; kiểm tra mảng sleep và số lần gửi. |
| Expected Result | 5 attempts; delays [2,4,8,16]; item giữ pending sau exhaustion. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-SIM; firmware/simulator.py::calculate_backoff/send_with_retry/send_event_with_retry |
| Notes | Tests hiện đối chiếu attempts với MAX_RETRIES; chưa assert literal 5 và đủ mảng delay. |

<a id="tc-sim-037"></a>

#### TC-SIM-037 — fsync và atomic replace dưới lỗi I/O

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-037 |
| Module | Simulator Reliability / Polling / AUTO_TEST |
| Test Type | Manual |
| Priority | High |
| Objective | fsync và atomic replace dưới lỗi I/O |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Queue tạm có nhiều items; quan sát fsync/os.replace, lỗi ghi/dequeue và restart window. |
| Steps | Dùng môi trường fault-injection độc lập; lưu log thứ tự flush/fsync/replace; reload queue. |
| Expected Result | Append có fsync; dequeue dùng temp+fsync+replace; ghi nhận hành vi lỗi thực tế, không kết luận power-loss guarantee chỉ từ source. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-SIM; firmware/simulator.py::enqueue_reading/remove_reading/enqueue_event/remove_event |
| Notes | Source xác nhận calls; existing restart tests không phải cắt điện/filesystem crash test. |

<a id="tc-sim-038"></a>

#### TC-SIM-038 — Live polling cadence và AUTO_TEST

| Field | Value |
|---|---|
| Test Case ID | TC-SIM-038 |
| Module | Simulator Reliability / Polling / AUTO_TEST |
| Test Type | Manual |
| Priority | High |
| Objective | Live polling cadence và AUTO_TEST |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | Backend thử nghiệm riêng, simulator AUTO_TEST hoặc polling loop; không thiết bị khác gửi readings. |
| Steps | Chạy AUTO_TEST thật qua HTTP; đo polling timestamps riêng với backend bình thường/chậm. |
| Expected Result | AUTO_TEST báo trạng thái lấy từ backend; ba scenarios Fresh/Use Soon/Check Food. Poll target 5s nhưng request chậm có thể kéo dài chu kỳ. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-SIM; firmware/simulator.py::run_auto_test/freshness_polling_loop |
| Notes | pytest dùng mocked HTTP; interval constant=5 đã có assertion, wall-clock cadence chưa đo. |

### FW — Firmware ESP32 Static Validation

READ -> SEND -> RECEIVE STATUS -> ACT. DHT4, DS3231 SDA21/SCL22, MQ34, LEDs23/25/26. Canonical payload + UUID v4 + ISO +07:00; sensor null. ENABLE_BACKEND=false, door placeholder, FOOD_ID rỗng.

<a id="tc-fw-001"></a>

#### TC-FW-001 — UUID v4 và identity một reading

| Field | Value |
|---|---|
| Test Case ID | TC-FW-001 |
| Module | Firmware ESP32 Static Validation |
| Test Type | Manual |
| Priority | High |
| Objective | UUID v4 và identity một reading |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | createReadingId(), sensorCycle(). |
| Steps | Review bit masks, format và nơi gọi; sau này capture nhiều UUID trên Serial. |
| Expected Result | 16 random bytes; version4 và RFC variant bits; canonical 36-char; một ID được dùng cho payload/log của chu kỳ. |
| Actual Result | Level B — Static Code Verified: code review xác nhận nhánh/cấu hình mô tả. Manual / Not Yet Validated trên board; chưa có execution log. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FW; firmware/ESP32-WROOM-32.ino::createReadingId |
| Notes | Static Code Verified; chưa chạy random generator trên board. |

<a id="tc-fw-002"></a>

#### TC-FW-002 — ISO timestamp RTC và UTC+7

| Field | Value |
|---|---|
| Test Case ID | TC-FW-002 |
| Module | Firmware ESP32 Static Validation |
| Test Type | Manual |
| Priority | High |
| Objective | ISO timestamp RTC và UTC+7 |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | getRTCTimestamp(), GMT_OFFSET_SEC=7*3600. |
| Steps | Review format; theo flow NTP -> rtc.adjust -> payload. |
| Expected Result | ISO YYYY-MM-DDTHH:MM:SS+07:00; thiếu RTC/time valid trả empty và skip sending. |
| Actual Result | Level B — Static Code Verified: code review xác nhận nhánh/cấu hình mô tả. Manual / Not Yet Validated trên board; chưa có execution log. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FW; firmware/ESP32-WROOM-32.ino::getRTCTimestamp/syncRTCFromNTP |
| Notes | Không chứng minh RTC chính xác hoặc NTP đã sync. |

<a id="tc-fw-003"></a>

#### TC-FW-003 — DHT field lỗi độc lập thành JSON null

| Field | Value |
|---|---|
| Test Case ID | TC-FW-003 |
| Module | Firmware ESP32 Static Validation |
| Test Type | Manual |
| Priority | High |
| Objective | DHT field lỗi độc lập thành JSON null |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | readDHT11 và buildReadingPayload, valid/invalid mỗi field. |
| Steps | Review isfinite riêng cho temperature/humidity và chuỗi JSON. |
| Expected Result | Field invalid thành null không quotes, field còn valid vẫn gửi; không gửi NaN. |
| Actual Result | Level B — Static Code Verified: code review xác nhận nhánh/cấu hình mô tả. Manual / Not Yet Validated trên board; chưa có execution log. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FW; firmware/ESP32-WROOM-32.ino::readDHT11/buildReadingPayload |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-fw-004"></a>

#### TC-FW-004 — MQ average 20 và saturation boundary

| Field | Value |
|---|---|
| Test Case ID | TC-FW-004 |
| Module | Firmware ESP32 Static Validation |
| Test Type | Manual |
| Priority | High |
| Objective | MQ average 20 và saturation boundary |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | readMQ135; average 4079/4080. |
| Steps | Review loop 20 mẫu, delay10ms, average nguyên và gasValid. |
| Expected Result | Average20; >=4080 invalid -> gas_raw null; 4079 không bị saturation check; không quy đổi ppm hoặc tự tính anomaly. |
| Actual Result | Level B — Static Code Verified: code review xác nhận nhánh/cấu hình mô tả. Manual / Not Yet Validated trên board; chưa có execution log. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FW; firmware/ESP32-WROOM-32.ino::readMQ135/buildReadingPayload |
| Notes | MQ_BASELINE_READY=false chỉ diagnostic; mqReadable=true không chứng minh sensor hiện diện. |

<a id="tc-fw-005"></a>

#### TC-FW-005 — Canonical payload và optional food

| Field | Value |
|---|---|
| Test Case ID | TC-FW-005 |
| Module | Firmware ESP32 Static Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Canonical payload và optional food |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | DEVICE_ID; FOOD_ID rỗng hoặc ID có đăng ký; door placeholder. |
| Steps | Review buildReadingPayload đối chiếu route required_fields. |
| Expected Result | Có đủ 7 required fields, duration0, door=false; food_id bỏ nếu rỗng. Firmware không gửi compact, backend vẫn nhận canonical. |
| Actual Result | Level B — Static Code Verified: code review xác nhận nhánh/cấu hình mô tả. Manual / Not Yet Validated trên board; chưa có execution log. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FW; firmware/ESP32-WROOM-32.ino::buildReadingPayload |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-fw-006"></a>

#### TC-FW-006 — HTTP accepted response -> LED mapping

| Field | Value |
|---|---|
| Test Case ID | TC-FW-006 |
| Module | Firmware ESP32 Static Validation |
| Test Type | Manual |
| Priority | High |
| Objective | HTTP accepted response -> LED mapping |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | HTTP 200/201 và body chứa Fresh / Normal, Use Soon, Check Food. |
| Steps | Review sendReadingToBackend/updateLedFromBackend và show* pin writes. |
| Expected Result | Green23/Yellow25/Red26; tắt LEDs khác trước bật LED được chọn; chỉ 200/201 gọi mapping. |
| Actual Result | Level B — Static Code Verified: code review xác nhận nhánh/cấu hình mô tả. Manual / Not Yet Validated trên board; chưa có execution log. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FW; firmware/ESP32-WROOM-32.ino::updateLedFromBackend/sendReadingToBackend |
| Notes | Parser hiện dùng substring toàn body, không deserialize freshness.status; không mô tả parser này như JSON schema validation. |

<a id="tc-fw-007"></a>

#### TC-FW-007 — HTTP failure/unknown body giữ LED

| Field | Value |
|---|---|
| Test Case ID | TC-FW-007 |
| Module | Firmware ESP32 Static Validation |
| Test Type | Manual |
| Priority | High |
| Objective | HTTP failure/unknown body giữ LED |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | WiFi unavailable, HTTP lỗi, unknown body. |
| Steps | Review các return branches và updateLedFromBackend. |
| Expected Result | Giữ LED trước đó; không tự kết luận Fresh/Check Food khi mất mạng; chưa có stale timeout. |
| Actual Result | Level B — Static Code Verified: code review xác nhận nhánh/cấu hình mô tả. Manual / Not Yet Validated trên board; chưa có execution log. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FW; firmware/ESP32-WROOM-32.ino::sendReadingToBackend/updateLedFromBackend |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-fw-008"></a>

#### TC-FW-008 — Backend source of truth và diagnostic khác business fault

| Field | Value |
|---|---|
| Test Case ID | TC-FW-008 |
| Module | Firmware ESP32 Static Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Backend source of truth và diagnostic khác business fault |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | sensorCycle, printSensorData, LED flow. |
| Steps | Review toàn firmware và tìm freshness/anomaly/exposure/storage decisions. |
| Expected Result | Không tính business freshness/gas/exposure/food/fault transitions trên ESP32; isfinite/ADC validity chỉ mã hóa sensor null và log local. |
| Actual Result | Level B — Static Code Verified: code review xác nhận nhánh/cấu hình mô tả. Manual / Not Yet Validated trên board; chưa có execution log. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FW; firmware/ESP32-WROOM-32.ino |
| Notes | Door=false/0; không có reed switch, QR scanner, offline queue. Không biến các tính năng thiếu thành expected PASS. |

<a id="tc-fw-009"></a>

#### TC-FW-009 — Cấu hình backend disabled hiện tại

| Field | Value |
|---|---|
| Test Case ID | TC-FW-009 |
| Module | Firmware ESP32 Static Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Cấu hình backend disabled hiện tại |
| Preconditions | Môi trường test độc lập, fixtures/DB thử nghiệm riêng; không thay DB hiện tại trong audit. |
| Input | ENABLE_BACKEND=false; SERVER_IP hiện 10.140.67.4. |
| Steps | Review early return của sendReadingToBackend. |
| Expected Result | Không gửi HTTP khi disabled; log Backend disabled; không tuyên bố hardware path đã hoạt động. |
| Actual Result | Level B — Static Code Verified: code review xác nhận nhánh/cấu hình mô tả. Manual / Not Yet Validated trên board; chưa có execution log. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-FW; firmware/ESP32-WROOM-32.ino::sendReadingToBackend |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

### DASH — Dashboard Manual Validation

GET latest/history/food mỗi 2s, freshness từ backend, null -> Data Unavailable; không có fourth business status. Base URL loopback; chưa browser validation.

<a id="tc-dash-001"></a>

#### TC-DASH-001 — Latest và backend freshness

| Field | Value |
|---|---|
| Test Case ID | TC-DASH-001 |
| Module | Dashboard Manual Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Latest và backend freshness |
| Preconditions | Browser chạy dashboard với backend/fixtures thử nghiệm riêng; không dùng DB production; cần ảnh + Network/Console evidence. |
| Input | GET latest trả đủ sensors, freshness status/reason. |
| Steps | Mở dashboard, quan sát sensors/status/reason và Network. |
| Expected Result | UI dùng chính backend freshness; không suy luận status từ temperature/gas riêng. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-DASH; dashboard/index.html::renderReading/loadDashboard |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-dash-002"></a>

#### TC-DASH-002 — History và food linkage

| Field | Value |
|---|---|
| Test Case ID | TC-DASH-002 |
| Module | Dashboard Manual Validation |
| Test Type | Manual |
| Priority | High |
| Objective | History và food linkage |
| Preconditions | Browser chạy dashboard với backend/fixtures thử nghiệm riêng; không dùng DB production; cần ảnh + Network/Console evidence. |
| Input | Latest food_id hợp lệ, history 20 readings; rồi food_id=null và food endpoint lỗi. |
| Steps | Quan sát bảng lịch sử, GET foods/<id>, labels metadata. |
| Expected Result | History dùng canonical fields; food đúng ID; null -> No food linked; lookup lỗi -> Food information unavailable. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-DASH; dashboard/index.html::loadHistory/loadFood |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-dash-003"></a>

#### TC-DASH-003 — Null sensor và fault reason

| Field | Value |
|---|---|
| Test Case ID | TC-DASH-003 |
| Module | Dashboard Manual Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Null sensor và fault reason |
| Preconditions | Browser chạy dashboard với backend/fixtures thử nghiệm riêng; không dùng DB production; cần ảnh + Network/Console evidence. |
| Input | Latest có temperature_c/humidity_pct/gas_raw=null; freshness Check Food. |
| Steps | Mở/refresh dashboard; đối chiếu từng ô và alert. |
| Expected Result | Null -> Data Unavailable; status/reason vẫn từ backend; unavailable không thành business status thứ tư. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-DASH; dashboard/index.html::formatNullable/renderReading |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-dash-004"></a>

#### TC-DASH-004 — Polling 2s và tránh request chồng

| Field | Value |
|---|---|
| Test Case ID | TC-DASH-004 |
| Module | Dashboard Manual Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Polling 2s và tránh request chồng |
| Preconditions | Browser chạy dashboard với backend/fixtures thử nghiệm riêng; không dùng DB production; cần ảnh + Network/Console evidence. |
| Input | Backend nhanh rồi delayed response. |
| Steps | Ghi Network timestamps và refreshInProgress behavior. |
| Expected Result | Target interval 2000ms; không chạy refresh mới khi cờ đang true; không cam kết chính xác 2s khi server chậm. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-DASH; dashboard/index.html::loadDashboard/setInterval |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-dash-005"></a>

#### TC-DASH-005 — No data/backend unavailable/malformed response

| Field | Value |
|---|---|
| Test Case ID | TC-DASH-005 |
| Module | Dashboard Manual Validation |
| Test Type | Manual |
| Priority | High |
| Objective | No data/backend unavailable/malformed response |
| Preconditions | Browser chạy dashboard với backend/fixtures thử nghiệm riêng; không dùng DB production; cần ảnh + Network/Console evidence. |
| Input | 404 NO_DATA, network fail, invalid JSON ở latest. |
| Steps | Lần lượt trả từng tình huống ở backend test; chụp UI. |
| Expected Result | No data thông báo chờ reading; lỗi hiển thị Backend unavailable/Unable to load data; không giữ UI như thể sensor hiện tại hợp lệ. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-DASH; dashboard/index.html::renderNoData/renderLoadError/loadDashboard |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-dash-006"></a>

#### TC-DASH-006 — Remote browser và loopback URL

| Field | Value |
|---|---|
| Test Case ID | TC-DASH-006 |
| Module | Dashboard Manual Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Remote browser và loopback URL |
| Preconditions | Browser chạy dashboard với backend/fixtures thử nghiệm riêng; không dùng DB production; cần ảnh + Network/Console evidence. |
| Input | Mở trang trên thiết bị khác laptop backend. |
| Steps | Kiểm tra Network request target và connection message. |
| Expected Result | Request vẫn đi tới 127.0.0.1 của thiết bị browser theo hardcode; nếu không có server local sẽ unavailable. Đây là limitation hiện tại. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-DASH; dashboard/index.html::API_BASE_URL |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-dash-007"></a>

#### TC-DASH-007 — Reading cũ nhưng API còn trả lời

| Field | Value |
|---|---|
| Test Case ID | TC-DASH-007 |
| Module | Dashboard Manual Validation |
| Test Type | Manual |
| Priority | High |
| Objective | Reading cũ nhưng API còn trả lời |
| Preconditions | Browser chạy dashboard với backend/fixtures thử nghiệm riêng; không dùng DB production; cần ảnh + Network/Console evidence. |
| Input | DB test chỉ có một reading cũ. |
| Steps | Refresh và xem Connected/Last updated so với reading timestamp. |
| Expected Result | UI không tự đánh dấu stale; Last updated là giờ fetch, không phải giờ đo. Ghi hạn chế thay vì suy diễn freshness mới. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-DASH; dashboard/index.html::loadDashboard |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

### HW — Physical Hardware End-to-End

Đo và gửi thật -> backend/SQLite/freshness -> response -> LED thật. Chưa compile/upload hoặc có physical evidence; không suy diễn hardware PASS từ pytest.

<a id="tc-hw-001"></a>

#### TC-HW-001 — Build/upload và pin wiring

| Field | Value |
|---|---|
| Test Case ID | TC-HW-001 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | Build/upload và pin wiring |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. |
| Input | DHT4; RTC21/22; MQ34; LEDs23/25/26. |
| Steps | Compile đúng board/libraries; upload; đối chiếu wiring; ghi build log/Serial. |
| Expected Result | Build/upload thành công và các chân đúng source; lỗi thực tế phải ghi lại, không lấy pytest thay thế. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-hw-002"></a>

#### TC-HW-002 — WiFi connection và reconnect thật

| Field | Value |
|---|---|
| Test Case ID | TC-HW-002 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | WiFi connection và reconnect thật |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. |
| Input | Mạng WiFi test; ngắt rồi phục hồi AP. |
| Steps | Khởi động board; ghi IP/RSSI; ngắt mạng và quan sát reconnect. |
| Expected Result | Có kết nối/reconnect theo code; ghi timing thực tế. Không kỳ vọng replay readings vì hardware queue chưa có. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino::connectWiFi/maintainWiFi |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-hw-003"></a>

#### TC-HW-003 — RTC/NTP, reboot và lostPower

| Field | Value |
|---|---|
| Test Case ID | TC-HW-003 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | RTC/NTP, reboot và lostPower |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. |
| Input | DS3231 có pin backup; NTP reachable/unreachable; tình huống lostPower. |
| Steps | Đối chiếu giờ chuẩn, reboot, mất RTC power; capture timestamp, flags và behavior skip/send. |
| Expected Result | Timestamp +07:00 khi RTC valid; ghi accuracy và lostPower behavior thực tế. Có rủi ro sensorCycle revalidate date sau lostPower; chưa coi là đồng bộ thành công. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino::initializeRTC/sensorCycle |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-hw-004"></a>

#### TC-HW-004 — DHT11 normal và lỗi thật

| Field | Value |
|---|---|
| Test Case ID | TC-HW-004 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | DHT11 normal và lỗi thật |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. Backend upload được bật có chủ đích trong build integration riêng. |
| Input | DHT11 kết nối rồi mô phỏng lỗi đọc an toàn. |
| Steps | Capture từng field Serial/HTTP; kiểm tra null và backend fault events ở DB test. |
| Expected Result | Valid đo được; invalid field gửi null; backend Check Food và SENSOR_FAULT, hồi phục SENSOR_RECOVERED theo transitions. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino::readDHT11; backend/app/services/sensor_fault.py |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-hw-005"></a>

#### TC-HW-005 — MQ135 ổn định và dữ liệu ADC thật

| Field | Value |
|---|---|
| Test Case ID | TC-HW-005 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | MQ135 ổn định và dữ liệu ADC thật |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. |
| Input | MQ135 warm-up, ADC wiring đúng; thay đổi tín hiệu trong miền input phù hợp. |
| Steps | Ghi 20-sample averages và saturation behavior; so payload/DB; ghi điều kiện calibration. |
| Expected Result | Đo được ADC và null khi saturated theo code; chưa có target ppm/calibration accuracy trong implementation để tự ghi PASS. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino::readMQ135 |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-hw-006"></a>

#### TC-HW-006 — ESP32 -> HTTP -> SQLite -> freshness thật

| Field | Value |
|---|---|
| Test Case ID | TC-HW-006 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | ESP32 -> HTTP -> SQLite -> freshness thật |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. Cấu hình hiện tại false là blocker; không thay đổi trong audit. |
| Input | Build integration bật backend; food_id bỏ; UUID/timestamp/sensors hợp lệ. |
| Steps | Capture request/201 response, query row bằng UUID ở DB test, so snapshot/status với Serial. |
| Expected Result | Một reading được commit cùng state/events cần thiết; response status trùng snapshot. Lưu log request/response/DB. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino::sendReadingToBackend; backend/app/routes/readings.py::create_reading |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

<a id="tc-hw-007"></a>

#### TC-HW-007 — Physical LED Green từ backend Fresh / Normal

| Field | Value |
|---|---|
| Test Case ID | TC-HW-007 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | Physical LED Green từ backend Fresh / Normal |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. Cần build integration và setup dữ liệu riêng; Use Soon cần food phù hợp hoặc controlled response fixture. |
| Input | Response accepted có freshness.status=Fresh / Normal. |
| Steps | Dùng test backend fixture/scenario có kiểm soát và cùng HTTP response path; chụp LED + Serial + response. |
| Expected Result | Chỉ Green GPIO23 sáng theo backend status; không tự tính status trên board. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino::updateLedFromBackend |
| Notes | Controlled response fixture chỉ chứng minh response->LED; không thay bằng chứng toàn luồng sensor->freshness. Không dùng 5/10/15 C để giả định ba status. |

<a id="tc-hw-008"></a>

#### TC-HW-008 — Physical LED Yellow từ backend Use Soon

| Field | Value |
|---|---|
| Test Case ID | TC-HW-008 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | Physical LED Yellow từ backend Use Soon |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. Cần build integration và setup dữ liệu riêng; Use Soon cần food phù hợp hoặc controlled response fixture. |
| Input | Response accepted có freshness.status=Use Soon. |
| Steps | Dùng test backend fixture/scenario có kiểm soát và cùng HTTP response path; chụp LED + Serial + response. |
| Expected Result | Chỉ Yellow GPIO25 sáng theo backend status; không tự tính status trên board. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino::updateLedFromBackend |
| Notes | Controlled response fixture chỉ chứng minh response->LED; không thay bằng chứng toàn luồng sensor->freshness. Không dùng 5/10/15 C để giả định ba status. |

<a id="tc-hw-009"></a>

#### TC-HW-009 — Physical LED Red từ backend Check Food

| Field | Value |
|---|---|
| Test Case ID | TC-HW-009 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | Physical LED Red từ backend Check Food |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. Cần build integration và setup dữ liệu riêng; Use Soon cần food phù hợp hoặc controlled response fixture. |
| Input | Response accepted có freshness.status=Check Food. |
| Steps | Dùng test backend fixture/scenario có kiểm soát và cùng HTTP response path; chụp LED + Serial + response. |
| Expected Result | Chỉ Red GPIO26 sáng theo backend status; không tự tính status trên board. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino::updateLedFromBackend |
| Notes | Controlled response fixture chỉ chứng minh response->LED; không thay bằng chứng toàn luồng sensor->freshness. Không dùng 5/10/15 C để giả định ba status. |

<a id="tc-hw-010"></a>

#### TC-HW-010 — Mất HTTP response và mất mạng: ghi giới hạn hiện tại

| Field | Value |
|---|---|
| Test Case ID | TC-HW-010 |
| Module | Physical Hardware End-to-End |
| Test Type | Manual |
| Priority | High |
| Objective | Mất HTTP response và mất mạng: ghi giới hạn hiện tại |
| Preconditions | Board ESP32-WROOM-32 và wiring thực tế; firmware build đã xác định. Chỉ chạy ở phase hardware riêng, chưa thực hiện trong audit. |
| Input | Sau một response đã đổi LED, ngắt backend/WiFi. |
| Steps | Quan sát Serial, LED, readings bị bỏ và reconnect; lưu evidence. |
| Expected Result | LED giữ trạng thái cũ; không có queue/replay/idempotent retry trên board. Ghi missing-readings là limitation hiện tại, không đòi behavior chưa implement. |
| Actual Result | Level D — Not Yet Validated: chưa chạy scenario; chưa có ảnh/log/đo đạc manual. Expected từ source review, không phải actual observed. |
| Status | NOT VALIDATED |
| Automated Test | — Không có automated test chuyên biệt được gán cho scenario này. |
| Requirement / Rule | R-HW; firmware/ESP32-WROOM-32.ino::sendReadingToBackend |
| Notes | Cần evidence + người/ngày chạy trước khi đổi status; không coi static review là execution PASS. |

## 5. Test Coverage Matrix

Rule IDs truy vết implementation, không phải line/branch coverage measurement. Audit không chạy coverage instrumentation.

| Requirement / Rule | Test Case IDs | Automated? | Current Evidence |
|---|---|---|---|
| R-API: API Input Validation | [TC-API-001](#tc-api-001), [TC-API-002](#tc-api-002), [TC-API-003](#tc-api-003), [TC-API-004](#tc-api-004), [TC-API-005](#tc-api-005), [TC-API-006](#tc-api-006), [TC-API-007](#tc-api-007), [TC-API-008](#tc-api-008), [TC-API-009](#tc-api-009), [TC-API-010](#tc-api-010), [TC-API-011](#tc-api-011), [TC-API-012](#tc-api-012), [TC-API-013](#tc-api-013), [TC-API-014](#tc-api-014), [TC-API-015](#tc-api-015), [TC-API-016](#tc-api-016), [TC-API-017](#tc-api-017), [TC-API-018](#tc-api-018), [TC-API-019](#tc-api-019), [TC-API-020](#tc-api-020), [TC-API-021](#tc-api-021), [TC-API-022](#tc-api-022), [TC-API-023](#tc-api-023), [TC-API-024](#tc-api-024), [TC-API-025](#tc-api-025), [TC-API-026](#tc-api-026), [TC-API-027](#tc-api-027), [TC-API-028](#tc-api-028), [TC-API-029](#tc-api-029), [TC-API-030](#tc-api-030), [TC-API-031](#tc-api-031), [TC-API-032](#tc-api-032), [TC-API-033](#tc-api-033) | 30 automated records; 3 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-IDEMP: Reading Idempotency | [TC-IDEMP-001](#tc-idemp-001), [TC-IDEMP-002](#tc-idemp-002), [TC-IDEMP-003](#tc-idemp-003), [TC-IDEMP-004](#tc-idemp-004), [TC-IDEMP-005](#tc-idemp-005), [TC-IDEMP-006](#tc-idemp-006), [TC-IDEMP-007](#tc-idemp-007), [TC-IDEMP-008](#tc-idemp-008), [TC-IDEMP-009](#tc-idemp-009), [TC-IDEMP-010](#tc-idemp-010), [TC-IDEMP-011](#tc-idemp-011), [TC-IDEMP-012](#tc-idemp-012), [TC-IDEMP-013](#tc-idemp-013), [TC-IDEMP-014](#tc-idemp-014), [TC-IDEMP-015](#tc-idemp-015) | 15 automated records; 0 manual | Level A pytest; Assertions listed in each case |
| R-FRESH: Freshness Severity Aggregation | [TC-FRESH-001](#tc-fresh-001), [TC-FRESH-002](#tc-fresh-002), [TC-FRESH-003](#tc-fresh-003), [TC-FRESH-004](#tc-fresh-004), [TC-FRESH-005](#tc-fresh-005), [TC-FRESH-006](#tc-fresh-006), [TC-FRESH-007](#tc-fresh-007), [TC-FRESH-008](#tc-fresh-008), [TC-FRESH-009](#tc-fresh-009), [TC-FRESH-010](#tc-fresh-010), [TC-FRESH-011](#tc-fresh-011), [TC-FRESH-012](#tc-fresh-012), [TC-FRESH-013](#tc-fresh-013), [TC-FRESH-014](#tc-fresh-014), [TC-FRESH-015](#tc-fresh-015), [TC-FRESH-016](#tc-fresh-016), [TC-FRESH-017](#tc-fresh-017), [TC-FRESH-018](#tc-fresh-018), [TC-FRESH-019](#tc-fresh-019), [TC-FRESH-020](#tc-fresh-020), [TC-FRESH-021](#tc-fresh-021) | 21 automated records; 0 manual | Level A pytest; Assertions listed in each case |
| R-TEMP: Temperature Exposure | [TC-TEMP-001](#tc-temp-001), [TC-TEMP-002](#tc-temp-002), [TC-TEMP-003](#tc-temp-003), [TC-TEMP-004](#tc-temp-004), [TC-TEMP-005](#tc-temp-005), [TC-TEMP-006](#tc-temp-006), [TC-TEMP-007](#tc-temp-007), [TC-TEMP-008](#tc-temp-008), [TC-TEMP-009](#tc-temp-009), [TC-TEMP-010](#tc-temp-010), [TC-TEMP-011](#tc-temp-011), [TC-TEMP-012](#tc-temp-012), [TC-TEMP-013](#tc-temp-013), [TC-TEMP-014](#tc-temp-014), [TC-TEMP-015](#tc-temp-015), [TC-TEMP-016](#tc-temp-016), [TC-TEMP-017](#tc-temp-017), [TC-TEMP-018](#tc-temp-018), [TC-TEMP-019](#tc-temp-019) | 17 automated records; 2 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-GAS: Gas Baseline & Anomaly | [TC-GAS-001](#tc-gas-001), [TC-GAS-002](#tc-gas-002), [TC-GAS-003](#tc-gas-003), [TC-GAS-004](#tc-gas-004), [TC-GAS-005](#tc-gas-005), [TC-GAS-006](#tc-gas-006), [TC-GAS-007](#tc-gas-007), [TC-GAS-008](#tc-gas-008), [TC-GAS-009](#tc-gas-009), [TC-GAS-010](#tc-gas-010), [TC-GAS-011](#tc-gas-011), [TC-GAS-012](#tc-gas-012), [TC-GAS-013](#tc-gas-013), [TC-GAS-014](#tc-gas-014), [TC-GAS-015](#tc-gas-015), [TC-GAS-016](#tc-gas-016), [TC-GAS-017](#tc-gas-017), [TC-GAS-018](#tc-gas-018), [TC-GAS-019](#tc-gas-019), [TC-GAS-020](#tc-gas-020), [TC-GAS-021](#tc-gas-021) | 19 automated records; 2 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-SENSOR: Sensor Fault | [TC-SENSOR-001](#tc-sensor-001), [TC-SENSOR-002](#tc-sensor-002), [TC-SENSOR-003](#tc-sensor-003), [TC-SENSOR-004](#tc-sensor-004), [TC-SENSOR-005](#tc-sensor-005), [TC-SENSOR-006](#tc-sensor-006), [TC-SENSOR-007](#tc-sensor-007), [TC-SENSOR-008](#tc-sensor-008), [TC-SENSOR-009](#tc-sensor-009), [TC-SENSOR-010](#tc-sensor-010), [TC-SENSOR-011](#tc-sensor-011), [TC-SENSOR-012](#tc-sensor-012), [TC-SENSOR-013](#tc-sensor-013) | 12 automated records; 1 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-HUM: Humidity | [TC-HUM-001](#tc-hum-001), [TC-HUM-002](#tc-hum-002), [TC-HUM-003](#tc-hum-003), [TC-HUM-004](#tc-hum-004), [TC-HUM-005](#tc-hum-005) | 3 automated records; 2 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-DOOR: Door Freshness & Producer | [TC-DOOR-001](#tc-door-001), [TC-DOOR-002](#tc-door-002), [TC-DOOR-003](#tc-door-003), [TC-DOOR-004](#tc-door-004), [TC-DOOR-005](#tc-door-005), [TC-DOOR-006](#tc-door-006), [TC-DOOR-007](#tc-door-007), [TC-DOOR-008](#tc-door-008), [TC-DOOR-009](#tc-door-009), [TC-DOOR-010](#tc-door-010), [TC-DOOR-011](#tc-door-011) | 10 automated records; 1 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-STORAGE: Storage Duration | [TC-STORAGE-001](#tc-storage-001), [TC-STORAGE-002](#tc-storage-002), [TC-STORAGE-003](#tc-storage-003), [TC-STORAGE-004](#tc-storage-004), [TC-STORAGE-005](#tc-storage-005) | 4 automated records; 1 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-EXPIRY: Expiry Date | [TC-EXPIRY-001](#tc-expiry-001), [TC-EXPIRY-002](#tc-expiry-002), [TC-EXPIRY-003](#tc-expiry-003), [TC-EXPIRY-004](#tc-expiry-004) | 3 automated records; 1 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-FOOD: Food Registration / QR | [TC-FOOD-001](#tc-food-001), [TC-FOOD-002](#tc-food-002), [TC-FOOD-003](#tc-food-003), [TC-FOOD-004](#tc-food-004), [TC-FOOD-005](#tc-food-005), [TC-FOOD-006](#tc-food-006), [TC-FOOD-007](#tc-food-007), [TC-FOOD-008](#tc-food-008), [TC-FOOD-009](#tc-food-009), [TC-FOOD-010](#tc-food-010), [TC-FOOD-011](#tc-food-011), [TC-FOOD-012](#tc-food-012), [TC-FOOD-013](#tc-food-013), [TC-FOOD-014](#tc-food-014), [TC-FOOD-015](#tc-food-015), [TC-FOOD-016](#tc-food-016), [TC-FOOD-017](#tc-food-017), [TC-FOOD-018](#tc-food-018), [TC-FOOD-019](#tc-food-019), [TC-FOOD-020](#tc-food-020), [TC-FOOD-021](#tc-food-021), [TC-FOOD-022](#tc-food-022), [TC-FOOD-023](#tc-food-023), [TC-FOOD-024](#tc-food-024), [TC-FOOD-025](#tc-food-025) | 24 automated records; 1 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-EVENT: Events | [TC-EVENT-001](#tc-event-001), [TC-EVENT-002](#tc-event-002), [TC-EVENT-003](#tc-event-003), [TC-EVENT-004](#tc-event-004), [TC-EVENT-005](#tc-event-005), [TC-EVENT-006](#tc-event-006), [TC-EVENT-007](#tc-event-007) | 6 automated records; 1 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-DB: Database Transaction / Migration | [TC-DB-001](#tc-db-001), [TC-DB-002](#tc-db-002), [TC-DB-003](#tc-db-003), [TC-DB-004](#tc-db-004), [TC-DB-005](#tc-db-005), [TC-DB-006](#tc-db-006), [TC-DB-007](#tc-db-007) | 6 automated records; 1 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-GET: GET API / Snapshot | [TC-GET-001](#tc-get-001), [TC-GET-002](#tc-get-002), [TC-GET-003](#tc-get-003), [TC-GET-004](#tc-get-004), [TC-GET-005](#tc-get-005), [TC-GET-006](#tc-get-006), [TC-GET-007](#tc-get-007), [TC-GET-008](#tc-get-008), [TC-GET-009](#tc-get-009), [TC-GET-010](#tc-get-010), [TC-GET-011](#tc-get-011) | 7 automated records; 4 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-SIM: Simulator Reliability / Polling / AUTO_TEST | [TC-SIM-001](#tc-sim-001), [TC-SIM-002](#tc-sim-002), [TC-SIM-003](#tc-sim-003), [TC-SIM-004](#tc-sim-004), [TC-SIM-005](#tc-sim-005), [TC-SIM-006](#tc-sim-006), [TC-SIM-007](#tc-sim-007), [TC-SIM-008](#tc-sim-008), [TC-SIM-009](#tc-sim-009), [TC-SIM-010](#tc-sim-010), [TC-SIM-011](#tc-sim-011), [TC-SIM-012](#tc-sim-012), [TC-SIM-013](#tc-sim-013), [TC-SIM-014](#tc-sim-014), [TC-SIM-015](#tc-sim-015), [TC-SIM-016](#tc-sim-016), [TC-SIM-017](#tc-sim-017), [TC-SIM-018](#tc-sim-018), [TC-SIM-019](#tc-sim-019), [TC-SIM-020](#tc-sim-020), [TC-SIM-021](#tc-sim-021), [TC-SIM-022](#tc-sim-022), [TC-SIM-023](#tc-sim-023), [TC-SIM-024](#tc-sim-024), [TC-SIM-025](#tc-sim-025), [TC-SIM-026](#tc-sim-026), [TC-SIM-027](#tc-sim-027), [TC-SIM-028](#tc-sim-028), [TC-SIM-029](#tc-sim-029), [TC-SIM-030](#tc-sim-030), [TC-SIM-031](#tc-sim-031), [TC-SIM-032](#tc-sim-032), [TC-SIM-033](#tc-sim-033), [TC-SIM-034](#tc-sim-034), [TC-SIM-035](#tc-sim-035), [TC-SIM-036](#tc-sim-036), [TC-SIM-037](#tc-sim-037), [TC-SIM-038](#tc-sim-038) | 35 automated records; 3 manual | Level A pytest; Level B static / Level D pending; no Level C |
| R-FW: Firmware ESP32 Static Validation | [TC-FW-001](#tc-fw-001), [TC-FW-002](#tc-fw-002), [TC-FW-003](#tc-fw-003), [TC-FW-004](#tc-fw-004), [TC-FW-005](#tc-fw-005), [TC-FW-006](#tc-fw-006), [TC-FW-007](#tc-fw-007), [TC-FW-008](#tc-fw-008), [TC-FW-009](#tc-fw-009) | 0 automated records; 9 manual | Level B static / Level D pending; no Level C |
| R-DASH: Dashboard Manual Validation | [TC-DASH-001](#tc-dash-001), [TC-DASH-002](#tc-dash-002), [TC-DASH-003](#tc-dash-003), [TC-DASH-004](#tc-dash-004), [TC-DASH-005](#tc-dash-005), [TC-DASH-006](#tc-dash-006), [TC-DASH-007](#tc-dash-007) | 0 automated records; 7 manual | Level B static / Level D pending; no Level C |
| R-HW: Physical Hardware End-to-End | [TC-HW-001](#tc-hw-001), [TC-HW-002](#tc-hw-002), [TC-HW-003](#tc-hw-003), [TC-HW-004](#tc-hw-004), [TC-HW-005](#tc-hw-005), [TC-HW-006](#tc-hw-006), [TC-HW-007](#tc-hw-007), [TC-HW-008](#tc-hw-008), [TC-HW-009](#tc-hw-009), [TC-HW-010](#tc-hw-010) | 0 automated records; 10 manual | Level B static / Level D pending; no Level C |

### Critical boundaries and evidence limits

| Requirement / Rule | Test Case IDs | Automated? | Current Evidence |
|---|---|---|---|
| Temperature accumulation / >7200s / gap<=10s | [TC-TEMP-010](#tc-temp-010) | Yes | 10-second sample loop;7200 false,7210 true. |
| Reset <=5 / event each episode | [TC-TEMP-007](#tc-temp-007), [TC-TEMP-008](#tc-temp-008), [TC-TEMP-012](#tc-temp-012) | Yes | Persistent state/events. |
| Temperature stale vs equal timestamp | [TC-TEMP-016](#tc-temp-016), [TC-TEMP-018](#tc-temp-018) | Partial | Stale automated; equal pending. |
| Null continuity / long-gap positive balance | [TC-TEMP-001](#tc-temp-001), [TC-TEMP-013](#tc-temp-013), [TC-TEMP-015](#tc-temp-015), [TC-TEMP-019](#tc-temp-019) | Partial | Null/zero-base gap automated; positive-base gap pending. |
| Gas baseline 9/10/fixed/zero | [TC-GAS-001](#tc-gas-001), [TC-GAS-002](#tc-gas-002), [TC-GAS-003](#tc-gas-003) | Yes | 9 no baseline; mean10; fixed; zero remains. |
| Gas >=30%,3 consecutive,recovery | [TC-GAS-004](#tc-gas-004), [TC-GAS-005](#tc-gas-005), [TC-GAS-019](#tc-gas-019) | Yes | 129.99/130/150/50 at baseline100. |
| Invalid before baseline / gas arrival order | [TC-GAS-020](#tc-gas-020), [TC-GAS-021](#tc-gas-021) | No dedicated test | Source-backed manual scenarios pending. |
| Sensor faults/recovery vs negative gas | [TC-SENSOR-006](#tc-sensor-006), [TC-SENSOR-007](#tc-sensor-007), [TC-SENSOR-013](#tc-sensor-013) | Partial | Null transitions automated; negative fault semantics pending. |
| Humidity five boundaries / both produce categories | [TC-HUM-001](#tc-hum-001), [TC-HUM-002](#tc-hum-002), [TC-HUM-004](#tc-hum-004), [TC-HUM-005](#tc-hum-005) | Partial | VEGETABLE severity partly automated; FRUIT/inside/no-warning pending. |
| Door0/29/30/31 | [TC-DOOR-005](#tc-door-005), [TC-DOOR-011](#tc-door-011) | Partial | 29/30/31 automated; open0 freshness pending. |
| Storage all categories max-2/max-1/max/max+1 | [TC-STORAGE-003](#tc-storage-003) | Yes | 5 invocations each assert4 boundaries. |
| Storage/expiry server date vs reading timestamp | [TC-STORAGE-005](#tc-storage-005), [TC-EXPIRY-004](#tc-expiry-004) | No dedicated contrast test | Code date.today; manual contrast pending. |
| Expiry yesterday/today/tomorrow/future | [TC-EXPIRY-001](#tc-expiry-001), [TC-EXPIRY-002](#tc-expiry-002) | Yes | Engine + API integration. |
| Snapshot persistence vs aging/legacy/global latest | [TC-GET-001](#tc-get-001), [TC-GET-007](#tc-get-007), [TC-GET-008](#tc-get-008), [TC-GET-009](#tc-get-009), [TC-GET-010](#tc-get-010) | Partial | Persistence automated; other scenarios pending. |
| Reading/state/event rollback | [TC-DB-003](#tc-db-003), [TC-DB-005](#tc-db-005), [TC-DB-006](#tc-db-006) | Yes | Trigger IntegrityError; rollback assertions. |
| Legacy events.sync_status | [TC-DB-007](#tc-db-007) | Static only | Read-only schema; request execution pending. |
| Simulator retry/FIFO/dead-letter/lost response | [TC-SIM-011](#tc-sim-011), [TC-SIM-012](#tc-sim-012), [TC-SIM-013](#tc-sim-013), [TC-SIM-014](#tc-sim-014), [TC-SIM-016](#tc-sim-016), [TC-SIM-021](#tc-sim-021), [TC-SIM-022](#tc-sim-022), [TC-SIM-024](#tc-sim-024), [TC-SIM-025](#tc-sim-025) | Yes | Mocked HTTP/temp JSONL. |
| fsync/atomic replace/crash/backoff literals | [TC-SIM-036](#tc-sim-036), [TC-SIM-037](#tc-sim-037) | Static only / partial | Calls exist; dedicated failure/timing assertions pending. |
| Polling5s | [TC-SIM-029](#tc-sim-029), [TC-SIM-038](#tc-sim-038) | Partial | Constant/request args asserted; actual cadence pending. |
| ESP32 parser/pins | [TC-FW-006](#tc-fw-006) | Static only | Substring parser, Level B. |
| Physical LED / ESP32 persistence | [TC-HW-006](#tc-hw-006), [TC-HW-007](#tc-hw-007), [TC-HW-008](#tc-hw-008), [TC-HW-009](#tc-hw-009) | No | Level D; ENABLE_BACKEND=false. |
| Dashboard polling/null/backend status | [TC-DASH-001](#tc-dash-001), [TC-DASH-003](#tc-dash-003), [TC-DASH-004](#tc-dash-004) | No | Source reviewed, browser pending. |

### Storage boundary inputs

| Category | Max days | Fresh sample | Use Soon samples | Check Food sample | Evidence |
|---|---:|---:|---|---:|---|
| MEAT | 3 | 1 | 2, 3 | 4 | [TC-STORAGE-003](#tc-storage-003) — Level A |
| DAIRY | 14 | 12 | 13, 14 | 15 | [TC-STORAGE-003](#tc-storage-003) — Level A |
| VEGETABLE | 7 | 5 | 6, 7 | 8 | [TC-STORAGE-003](#tc-storage-003) — Level A |
| FRUIT | 14 | 12 | 13, 14 | 15 | [TC-STORAGE-003](#tc-storage-003) — Level A |
| COOKED_FOOD | 4 | 2 | 3, 4 | 5 | [TC-STORAGE-003](#tc-storage-003) — Level A |

## 6. Fixture / Helper Reference

Setup/defaults nguyên bản để giải nghĩa Input/Steps; không phải testcase bổ sung. Imports/helper có assert vẫn chỉ là dependency của test gọi nó.

<a id="fixture-test-api-hardening"></a>

### backend/tests/test_api_hardening.py

[Source đầy đủ](../backend/tests/test_api_hardening.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
import sqlite3

from concurrent.futures import ThreadPoolExecutor

from threading import Barrier

import uuid

import pytest

import requests

from app import create_app

from app import init_db as init_db_module

from app.routes import events as events_module

from app.routes import readings as readings_module

from app.services.reading_protocol import decode_compact_reading

from firmware import simulator

@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "hardening-test.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(events_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    init_db_module.init_db()

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()

def reading_payload(**overrides):
    payload = {
        "device_id": "FG-ESP32-01",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": "2026-09-25T12:00:00+07:00",
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": 300,
        "door_open": False,
    }
    payload.update(overrides)
    return payload

def event_payload(**overrides):
    payload = {
        "event_id": "event-001",
        "device_id": "FG-ESP32-01",
        "timestamp": "2026-09-25T12:00:00+07:00",
        "event_type": "door_closed",
        "payload": {"source": "test"},
    }
    payload.update(overrides)
    return payload

def compact_reading_payload(**overrides):
    payload = {
        "id": str(uuid.uuid4()),
        "d": "FG-ESP32-01",
        "t": 1727253000,
        "tc": 5.2,
        "h": 61.5,
        "g": 302,
        "o": 0,
    }
    payload.update(overrides)
    return payload

def _reading_count():
    connection = readings_module.get_db_connection()
    try:
        return connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
    finally:
        connection.close()

def _stored_reading(device_id, reading_id):
    connection = readings_module.get_db_connection()
    try:
        return connection.execute(
            "SELECT * FROM sensor_readings WHERE device_id = ? AND device_reading_id = ?",
            (device_id, reading_id),
        ).fetchone()
    finally:
        connection.close()

def _event_count(event_id):
    connection = events_module.get_db_connection()
    try:
        return connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()[0]
    finally:
        connection.close()
~~~

</details>

<a id="fixture-test-cross-system-integration"></a>

### backend/tests/test_cross_system_integration.py

[Source đầy đủ](../backend/tests/test_cross_system_integration.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
"""Cross-service reliability integration checks using a temporary SQLite DB."""

import ast

from datetime import datetime, timedelta, timezone

import sqlite3

import uuid

import pytest

from app import create_app

from app import init_db as init_db_module

from app.routes import events as events_module

from app.routes import readings as readings_module

from firmware import simulator

@pytest.fixture
def system(tmp_path, monkeypatch):
    database_path = tmp_path / "cross-system.db"

    def connect():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect)
    monkeypatch.setattr(events_module, "get_db_connection", connect)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect)
    init_db_module.init_db()
    app = create_app()
    app.config.update(TESTING=True, TEST_DB_PATH=str(database_path))
    return app.test_client()

def timestamp(second):
    return (datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
            + timedelta(seconds=second)).isoformat()

def post_reading(client, second, *, reading_id=None, device="CROSS-DEVICE",
                 food_id=None, temperature=5, humidity=60, gas=100, door=False,
                 duration=0):
    payload = {
        "device_id": device,
        "device_reading_id": reading_id or str(uuid.uuid4()),
        "timestamp": timestamp(second),
        "temperature_c": temperature,
        "humidity_pct": humidity,
        "gas_raw": gas,
        "door_open": door,
        "open_duration_seconds": duration,
    }
    if food_id is not None:
        payload["food_id"] = food_id
    return client.post("/api/v1/readings", json=payload)

def rows(client, sql, params=()):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql, params)]
    finally:
        connection.close()

def event_types(client):
    return [row["event_type"] for row in rows(
        client, "SELECT event_type FROM events ORDER BY id"
    )]

class _Response:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body or {}

    def json(self):
        return self.body
~~~

</details>

<a id="fixture-test-food-api"></a>

### backend/tests/test_food_api.py

[Source đầy đủ](../backend/tests/test_food_api.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
import sqlite3

from datetime import date, timedelta

import uuid

import pytest

from app import create_app

from app import init_db as init_db_module

from app.routes import readings as readings_module

@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "freshguard-test.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    init_db_module.init_db()

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()

def food_payload(**overrides):
    payload = {
        "food_id": "FG-FOOD-001",
        "food_name": "Milk",
        "category": "DAIRY",
        "quantity": 1,
        "inserted_at": date.today().isoformat(),
        "manufacture_date": (date.today() - timedelta(days=2)).isoformat(),
        "expiry_date": (date.today() + timedelta(days=12)).isoformat(),
        "storage_location": "FRIDGE-01",
    }
    payload.update(overrides)
    return payload

def reading_payload(**overrides):
    payload = {
        "device_id": "FG-ESP32-01",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": "2026-09-25T12:00:00+07:00",
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": 300,
        "door_open": False,
    }
    payload.update(overrides)
    return payload
~~~

</details>

<a id="fixture-test-food-freshness-integration"></a>

### backend/tests/test_food_freshness_integration.py

[Source đầy đủ](../backend/tests/test_food_freshness_integration.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
import sqlite3

from datetime import date, timedelta

import uuid

import pytest

from app import create_app

from app import init_db as init_db_module

from app.routes import readings as readings_module

@pytest.fixture
def api_client(tmp_path, monkeypatch):
    database_path = tmp_path / "food-freshness-integration.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    init_db_module.init_db()

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()

def register_food(client, food_id, category="MEAT", stored_days=0, expiry_days=10):
    today = date.today()
    response = client.post(
        "/api/v1/foods",
        json={
            "food_id": food_id,
            "food_name": f"Test {category.title()}",
            "category": category,
            "quantity": 1,
            "inserted_at": (today - timedelta(days=stored_days)).isoformat(),
            "manufacture_date": today.isoformat(),
            "expiry_date": (today + timedelta(days=expiry_days)).isoformat(),
            "storage_location": "TEST",
        },
    )
    assert response.status_code == 201
    return response.json["food"]

def post_reading(client, **overrides):
    reading = {
        "device_id": "FG-TEST-DEVICE",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": "2026-09-25T12:00:00+07:00",
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": 100,
        "door_open": False,
        "open_duration_seconds": 0,
    }
    reading.update(overrides)
    return client.post("/api/v1/readings", json=reading)
~~~

</details>

<a id="fixture-test-freshness"></a>

### backend/tests/test_freshness.py

[Source đầy đủ](../backend/tests/test_freshness.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
from datetime import date, timedelta

import pytest

from app.services.freshness import (
    FreshnessStatus,
    evaluate_temperature,
    evaluate_humidity,
    evaluate_gas,
    evaluate_freshness,
    evaluate_door,
    evaluate_door_timeout,
)

def evaluate_with_optional_food(category=None, days_stored=None, expiry_offset=None, **overrides):
    today = date.today()
    arguments = {
        "temperature_c": 5,
        "humidity_pct": 70,
        "gas_raw": 150,
        "door_open": False,
        "open_duration_seconds": 0,
        "category": category,
        "inserted_at": today - timedelta(days=days_stored) if days_stored is not None else None,
        "expiry_date": today + timedelta(days=expiry_offset) if expiry_offset is not None else None,
    }
    arguments.update(overrides)
    return evaluate_freshness(**arguments)
~~~

</details>

<a id="fixture-test-gas-anomaly"></a>

### backend/tests/test_gas_anomaly.py

[Source đầy đủ](../backend/tests/test_gas_anomaly.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
import sqlite3

import uuid

from datetime import date, timedelta

import pytest

from app import create_app

from app import init_db as init_db_module

from app.routes import readings as readings_module

from app.services.freshness import FreshnessStatus, evaluate_freshness

from app.services.gas_anomaly import (
    GAS_ANOMALY_DEVIATION,
    GAS_BASELINE_SAMPLE_COUNT,
    GAS_REQUIRED_CONSECUTIVE_READINGS,
    update_gas_anomaly_state,
)

@pytest.fixture
def gas_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE gas_anomaly_state (
        device_id TEXT NOT NULL, food_id TEXT NOT NULL DEFAULT '',
        baseline REAL NULL, baseline_sample_count INTEGER NOT NULL DEFAULT 0,
        baseline_sum REAL NOT NULL DEFAULT 0,
        consecutive_anomaly_count INTEGER NOT NULL DEFAULT 0,
        anomaly_active INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (device_id, food_id)
    )""")
    yield connection
    connection.close()

def update(connection, gas, device="device-a", food="food-a"):
    return update_gas_anomaly_state(connection, device, food, gas)

def state(connection, device="device-a", food="food-a"):
    return connection.execute(
        "SELECT * FROM gas_anomaly_state WHERE device_id = ? AND food_id = ?",
        (device, food or ""),
    ).fetchone()

def establish_baseline(connection, value=100, device="device-a", food="food-a"):
    for _ in range(GAS_BASELINE_SAMPLE_COUNT):
        update(connection, value, device, food)

@pytest.fixture
def api_client(tmp_path, monkeypatch):
    database_path = tmp_path / "gas-anomaly-integration.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    init_db_module.init_db()
    app = create_app()
    app.config["TESTING"] = True
    app.config["TEST_DB_PATH"] = str(database_path)
    return app.test_client()

def post_gas(client, gas, food_id=None, device="FG-GAS-DEVICE", reading_id=None, timestamp=None):
    payload = {
        "device_id": device,
        "device_reading_id": reading_id or str(uuid.uuid4()),
        "timestamp": timestamp or "2026-09-26T12:00:00+07:00",
        "temperature_c": 5,
        "humidity_pct": 60,
        "gas_raw": gas,
        "door_open": False,
    }
    if food_id is not None:
        payload["food_id"] = food_id
    return client.post("/api/v1/readings", json=payload)

def gas_events(client):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM events WHERE event_type LIKE 'GAS_%' ORDER BY id"
        )]
    finally:
        connection.close()

def gas_state(client, device="FG-GAS-DEVICE", food_id=None):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            "SELECT * FROM gas_anomaly_state WHERE device_id = ? AND food_id = ?",
            (device, food_id or ""),
        ).fetchone()
    finally:
        connection.close()

def prime_and_activate(client, food_id=None, device="FG-GAS-DEVICE"):
    for _ in range(10):
        post_gas(client, 100, food_id=food_id, device=device)
    post_gas(client, 130, food_id=food_id, device=device)
    post_gas(client, 130, food_id=food_id, device=device)
    return post_gas(client, 130, food_id=food_id, device=device)
~~~

</details>

<a id="fixture-test-reading-protocol"></a>

### backend/tests/test_reading_protocol.py

[Source đầy đủ](../backend/tests/test_reading_protocol.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
from copy import deepcopy

import math

import uuid

import pytest

from app.services.reading_protocol import (
    ReadingProtocolError,
    decode_compact_reading,
)

@pytest.fixture
def compact_payload():
    return {
        "id": str(uuid.uuid4()),
        "d": "esp32_01",
        "t": 1727253000,
        "tc": 5.2,
        "h": 61.5,
        "g": 302,
        "o": 0,
        "od": 0,
        "f": "FOOD001",
    }
~~~

</details>

<a id="fixture-test-sensor-fault"></a>

### backend/tests/test_sensor_fault.py

[Source đầy đủ](../backend/tests/test_sensor_fault.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
import ast

import sqlite3

import uuid

import pytest

from app import create_app

from app import init_db as init_db_module

from app.routes import readings as readings_module

SENSORS = {
    "temperature": "temperature_c",
    "humidity": "humidity_pct",
    "gas": "gas_raw",
}

@pytest.fixture
def sensor_client(tmp_path, monkeypatch):
    database_path = tmp_path / "sensor-fault.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    init_db_module.init_db()
    app = create_app()
    app.config["TESTING"] = True
    app.config["TEST_DB_PATH"] = str(database_path)
    return app.test_client()

def reading_payload(seconds=0, **overrides):
    payload = {
        "device_id": "SENSOR-DEVICE",
        "device_reading_id": str(uuid.uuid4()),
        "timestamp": f"2026-09-26T10:00:{seconds:02d}+07:00",
        "temperature_c": 4.0,
        "humidity_pct": 60.0,
        "gas_raw": 300,
        "door_open": False,
    }
    payload.update(overrides)
    return payload

def post_reading(client, seconds=0, **overrides):
    return client.post("/api/v1/readings", json=reading_payload(seconds, **overrides))

def connect(client):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    return connection

def events(client):
    connection = connect(client)
    try:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM events WHERE event_type IN "
            "('SENSOR_FAULT', 'SENSOR_RECOVERED') ORDER BY id"
        )]
    finally:
        connection.close()

def fault_state(client, sensor_name, device="SENSOR-DEVICE", food_id=None):
    connection = connect(client)
    try:
        return connection.execute(
            """SELECT * FROM sensor_fault_state
               WHERE device_id = ? AND food_id IS ? AND sensor_name = ?""",
            (device, food_id, sensor_name),
        ).fetchone()
    finally:
        connection.close()

def fault_events(client):
    return [event for event in events(client) if event["event_type"] == "SENSOR_FAULT"]

def recovered_events(client):
    return [event for event in events(client) if event["event_type"] == "SENSOR_RECOVERED"]
~~~

</details>

<a id="fixture-test-temperature-exposure"></a>

### backend/tests/test_temperature_exposure.py

[Source đầy đủ](../backend/tests/test_temperature_exposure.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
import sqlite3

from datetime import datetime, timedelta, timezone

import uuid

import pytest

from app import create_app

from app import init_db as init_db_module

from app.routes import readings as readings_module

from app.services.temperature_exposure import (
    TEMPERATURE_EXPOSURE_LIMIT_SECONDS,
    update_temperature_exposure,
)

@pytest.fixture
def temperature_client(tmp_path, monkeypatch):
    database_path = tmp_path / "temperature-exposure.db"

    def connect_to_test_db():
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(readings_module, "get_db_connection", connect_to_test_db)
    monkeypatch.setattr(init_db_module, "get_db_connection", connect_to_test_db)
    init_db_module.init_db()
    app = create_app()
    app.config["TESTING"] = True
    app.config["TEST_DB_PATH"] = str(database_path)
    return app.test_client()

def iso_time(seconds=0):
    return (datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
            + timedelta(seconds=seconds)).isoformat()

def post_temperature(client, temperature, seconds=0, food_id=None, device="TEMP-DEVICE",
                     reading_id=None):
    payload = {
        "device_id": device,
        "timestamp": iso_time(seconds),
        "temperature_c": temperature,
        "humidity_pct": 60,
        "gas_raw": 100,
        "door_open": False,
    }
    if food_id is not None:
        payload["food_id"] = food_id
    payload["device_reading_id"] = reading_id or str(uuid.uuid4())
    return client.post("/api/v1/readings", json=payload)

def db_connect(client):
    connection = sqlite3.connect(client.application.config["TEST_DB_PATH"])
    connection.row_factory = sqlite3.Row
    return connection

def state_for(client, device="TEMP-DEVICE", food_id=None):
    connection = db_connect(client)
    try:
        return connection.execute(
            "SELECT * FROM temperature_exposure_state "
            "WHERE device_id = ? AND food_id = ?",
            (device, food_id or ""),
        ).fetchone()
    finally:
        connection.close()

def temperature_events(client):
    connection = db_connect(client)
    try:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM events WHERE event_type = "
            "'TEMPERATURE_EXPOSURE_EXCEEDED' ORDER BY id"
        )]
    finally:
        connection.close()

def prime_exposure_state(client, *, device="TEMP-DEVICE", food_id=None,
                         exposure_seconds=7200, exceeded=False, last_seconds=0):
    connection = db_connect(client)
    try:
        connection.execute(
            """INSERT INTO temperature_exposure_state (
                   device_id, food_id, exposure_seconds, exposure_active,
                   exposure_exceeded, last_valid_temperature_timestamp
               ) VALUES (?, ?, ?, 1, ?, ?)""",
            (device, food_id or "", exposure_seconds, int(exceeded), iso_time(last_seconds)),
        )
        connection.commit()
    finally:
        connection.close()
~~~

</details>

<a id="fixture-test-simulator-auto-test-fw"></a>

### firmware/tests/test_simulator_auto_test.py

[Source đầy đủ](../firmware/tests/test_simulator_auto_test.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
from firmware import simulator

class PostResponse:
    status_code = 201

    def __init__(self, reading_id):
        self.reading_id = reading_id

    def json(self):
        return {"success": True, "device_reading_id": self.reading_id}

class PollResponse:
    status_code = 200

    def __init__(self, status):
        self.status = status

    def json(self):
        return {
            "success": True,
            "data": {
                "freshness": {"status": self.status, "reason": "test warning"},
                "gas_anomaly_active": 1,
            },
        }

def install_auto_test_backend(monkeypatch, poll_responses):
    posted = []
    food_ids = []

    def fake_send_reading(payload):
        posted.append(payload.copy())
        return PostResponse(payload["device_reading_id"])

    def fake_create_food(food_id):
        food_ids.append(food_id)
        return True

    monkeypatch.setattr(simulator, "send_reading", fake_send_reading)
    monkeypatch.setattr(simulator, "_create_auto_test_food", fake_create_food)
    monkeypatch.setattr(
        simulator.requests,
        "get",
        lambda *_args, **_kwargs: poll_responses.pop(0),
    )
    return posted, food_ids

def http_500_response():
    class ErrorResponse:
        status_code = 500

        def json(self):
            raise AssertionError("HTTP error response should not be parsed")

    return ErrorResponse()
~~~

</details>

<a id="fixture-test-simulator-compact-fw"></a>

### firmware/tests/test_simulator_compact.py

[Source đầy đủ](../firmware/tests/test_simulator_compact.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
from copy import deepcopy

import json

import uuid

import pytest

from firmware import simulator

@pytest.fixture
def canonical_payload():
    return {
        "device_reading_id": str(uuid.uuid4()),
        "device_id": "esp32_01",
        "timestamp": "2026-09-25T15:00:00+07:00",
        "temperature_c": 5.2,
        "humidity_pct": 61.5,
        "gas_raw": 302,
        "door_open": False,
        "open_duration_seconds": 0,
        "food_id": "FOOD001",
    }

class StubResponse:
    text = "{}"

    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body or {}

    def json(self):
        return self.body
~~~

</details>

<a id="fixture-test-simulator-cross-system-fw"></a>

### firmware/tests/test_simulator_cross_system.py

[Source đầy đủ](../firmware/tests/test_simulator_cross_system.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
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
~~~

</details>

<a id="fixture-test-simulator-events-fw"></a>

### firmware/tests/test_simulator_events.py

[Source đầy đủ](../firmware/tests/test_simulator_events.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
from copy import deepcopy

import json

import uuid

import pytest

import requests

from firmware import simulator

@pytest.fixture
def canonical_event():
    return {
        "event_id": str(uuid.uuid4()),
        "device_id": "FG-ESP32-01",
        "timestamp": "2026-09-25T12:00:00+07:00",
        "event_type": "door_closed",
        "payload": {"source": "simulator", "door_open": False},
    }

class StubResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body or {}

    def json(self):
        return self.body

def door_reading(door_open, duration, second, device_id="FG-ESP32-01"):
    return {
        "device_id": device_id,
        "timestamp": f"2026-09-25T12:00:{second:02d}+07:00",
        "door_open": door_open,
        "open_duration_seconds": duration,
    }
~~~

</details>

<a id="fixture-test-simulator-freshness-poll-fw"></a>

### firmware/tests/test_simulator_freshness_poll.py

[Source đầy đủ](../firmware/tests/test_simulator_freshness_poll.py)

<details>
<summary>Imports, fixtures và helpers</summary>

~~~python
import pytest

import requests

from firmware import simulator

class FakeResponse:
    def __init__(self, status_code=200, body=None, json_error=None):
        self.status_code = status_code
        self.body = body
        self.json_error = json_error

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.body
~~~

</details>

## Test Findings

### Phần mạnh

- 212 automated functions /424 pytest invocations PASS; validation canonical/compact, UUID/snapshot, isolation, transition-only và transaction rollback.
- Storage đầy đủ max−2/max−1/max/max+1 cho năm category; expiry yesterday/today/tomorrow/future.
- Cross-service chứng minh gas/sensor fault độc lập, null ngắt exposure continuity, restart giữ state và retry không replay transition.
- Simulator có JSONL reload/FIFO/retry/dead-letter/lost-response tests. Firmware source có READ/SEND/status/LED path.

### Coverage gaps / evidence limits

- Không đo line/branch coverage; 424 PASS không nghĩa mọi input/nhánh đã covered.
- Tên test có thể rộng hơn assertions: temperature_use_soon assert Fresh; trimmed_food_id không truyền food; history_recomputes/reload không đổi metadata/xóa snapshot; invalid_gas_does_not_seed chạy sau baseline đủ; recovery_does_not_clear_other_conditions không bật rule khác. Notes đã chỉ rõ.
- Thiếu dedicated coverage cho một số canonical missing/type fields, equal timestamp, positive exposure sau gap dài, invalid khi baseline chưa đủ, arrival order, negative gas/null-fault distinction, FRUIT humidity và absence-of-warning tại biên.
- Snapshot qua ngày mới, legacy fallback, global latest, server-date/reading-date contrast chưa thực thi; source-backed manual plans không phải PASS.
- fsync/atomic replace có trong source; reload trong test không phải process-kill/power-loss guarantee. Literal backoff [2,4,8,16] chưa assert trực tiếp. Test transient5xx dùng503, không mọi mã500..599.
- Poll constant5 đã assert, wall-clock cadence chưa đo. AUTO_TEST tests mock backend, chưa live HTTP.
- Event payload là str(dict), duplicate event chỉ so ID. Existing automation chủ yếu dùng events schema mới; legacy sync_status request execution chưa verified.
- QR API mapping có test; chưa decode QR bitmap hoặc có scanner ESP32.

### Hardware / dashboard gaps

- ENABLE_BACKEND=false; chưa compile/upload, chưa có WiFi/LAN/RTC-NTP/HTTP/SQLite/physical LED evidence.
- Hardware queue/retry, real door và QR scanner chưa implement; không tạo expected PASS cho tính năng chưa có.
- MQ averaging/saturation không phải calibration/ppm accuracy; mqReadable=true không phát hiện đủ lỗi vật lý.
- RTC lostPower có thể được sensorCycle revalidate theo date-range; cần kiểm thử. LED parser tìm substring toàn body; HTTP lỗi giữ LED cũ, chưa stale timeout.
- Dashboard chưa browser-test, hardcode loopback, chưa stale reading detection. Last updated là fetch time.

### Mismatch với tài liệu cũ — các file cũ không bị sửa

| Old document | Old statement | Current evidence |
|---|---|---|
| architecture.md | Không có ESP32/LED source | .ino có drivers/WiFi/HTTP/LED; chưa physical validation |
| architecture.md | Compact chỉ đề xuất, API chưa hỗ trợ | Decoder/API tests và simulator compact transport đã có |
| architecture.md | Reading idempotency chưa implement | UUIDv4 required, unique composite index, 201/200/409 + snapshot |
| architecture.md / iot-test-matrix.md | Simulator không queue/retry/AUTO_TEST | Queue reading/event, backoff, dead-letter, poll, AUTO_TEST có code/tests |
| freshness-decision-rule-matrix.md | Humidity chỉ validity | VEGETABLE/FRUIT ngoài80–95 thêm warning, không tăng severity |
| food-threshold-matrix.md | Category-specific humidity chưa có | Produce warning đã có; calibrated gas/ppm vẫn chưa có |
| iot-test-matrix.md | 130 passed, QR/LED/reliability chưa implement | Audit hiện424 passed; QR backend/LED source/simulator reliability có, hardware pending |
| architecture.md | Schema thiếu state/snapshot/UUID | Ba state tables + snapshot/UUID/index; actual events có sync_status |

Không dùng tài liệu cũ ghi đè rules/ownership hiện tại.

## Overall Test Status

**PARTIAL — Software automated test coverage is passing, but physical ESP32 end-to-end hardware validation remains incomplete.**

424/424 pytest invocations PASS; manual/hardware/browser evidence chưa có. Phase demo tiếp theo: controlled ESP32 → WiFi → backend → SQLite → freshness → response → ba LED, thu log/ảnh riêng. Document scenario không đồng nghĩa đã thực thi.
