# Backend offline reading ingest

## Review trước thay đổi

- `POST /api/v1/readings` lưu nguyên timestamp canonical vào
  `sensor_readings.timestamp`. Compact payload được decoder chuyển Unix time
  thành ISO với offset +07:00 trước bước validation.
- `created_at TEXT DEFAULT CURRENT_TIMESTAMP` là giờ insert của SQLite (UTC,
  không có offset trong chuỗi), không phải thời điểm route bắt đầu nhận request.
  `freshness_evaluated_at` lưu giờ đánh giá UTC ISO. Chưa có `received_at` hoặc
  `server_timestamp` riêng.
- `device_reading_id` đã được lưu. Unique index hiện có trên
  `(device_id, device_reading_id)`; UUID bắt buộc ở API, nullable ở DB để giữ
  dữ liệu legacy.
- Route dùng `BEGIN IMMEDIATE`, kiểm tra duplicate trước cập nhật state,
  freshness, events, snapshots và notification outbox. Cùng identity và payload
  trả existing reading với HTTP 200; identity trùng nhưng payload khác trả 409.
  Reading mới trả 201. Duplicate không đánh giá freshness hoặc tạo side effect lại.
- GET list/latest trả `timestamp`, `created_at`, freshness; chưa trả metadata
  độ trễ. `freshness_evaluated_at` có trong DB nhưng chưa được chọn trong hai GET này.
- Dashboard dùng timestamp capture và freshness; chưa có phân loại ingest.
  Admin overview chỉ tổng hợp số reading và timestamp/freshness của bản ghi mới
  insert nhất. Route chưa có logging chuyên biệt cho duplicate/offline recovery.

## Schema và migration

Giữ nguyên tất cả cột hiện có: `id`, `device_id`, `timestamp`, `temperature_c`,
`humidity_pct`, `gas_raw`, `door_open`, `open_duration_seconds`, `food_id`,
`device_reading_id`, `freshness_status`, `freshness_reason`,
`freshness_evaluated_at`, `gas_anomaly_active`, `created_at`.

Thêm vào `sensor_readings`:

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| received_at | TEXT NULL | UTC ISO tại đầu route của request đầu tiên được lưu thành công |
| delivery_delay_seconds | REAL NULL | received_at trừ timestamp capture, tính bằng giây |
| ingest_status | TEXT NULL | LIVE, DELAYED, OFFLINE_RECOVERED hoặc CLOCK_SKEW |

Không thêm `device_timestamp` vì `timestamp` đã có cùng ý nghĩa. `created_at`
vẫn giữ ý nghĩa giờ insert. `init_db()` dùng PRAGMA table_info và ALTER TABLE
ADD COLUMN theo cơ chế migration sẵn có; chạy lại không xóa dữ liệu. Startup
gọi migration. Không cần framework migration mới.

Các bản ghi cũ giữ NULL ở ba cột mới: không lấy created_at giả làm thời điểm nhận
HTTP chính xác. Duplicate của dữ liệu legacy cũng giữ metadata NULL.

## Timestamp và policy

`received_at` được lấy trước JSON parsing và trước chờ DB lock, không phải giờ
socket nhận byte đầu tiên. Timestamp thiết bị được giữ nguyên chuỗi; bản parsed
được đổi sang UTC chỉ để tính toán. Không ghi đè timestamp bằng giờ server.

Constants tập trung tại `backend/app/services/reading_ingest.py`:

| Điều kiện | Xử lý |
|---|---|
| 0 <= delay <= 10 | LIVE |
| 10 < delay <= 120 | DELAYED |
| delay > 120 | OFFLINE_RECOVERED |
| -30 <= delay < 0 | CLOCK_SKEW, giữ delay âm và log rõ |
| delay < -30 | HTTP 400 INVALID_TIMESTAMP, không insert |

Timestamp mới phải là ISO có ngày, giờ/phút/giây và Z hoặc offset ±HH:MM.
Thiếu/sai timezone, ngày không hợp lệ, chuỗi rỗng hoặc vượt phạm vi datetime
trả 400 theo convention validation. Đây là thay đổi có chủ đích so với validation
cũ vốn chấp nhận datetime thiếu timezone; firmware hiện gửi +07:00 nên tương thích.

`OFFLINE_RECOVERED` là suy luận độ trễ, không chứng minh mất WiFi. Backend chậm,
thiết bị lệch đồng hồ, hoặc backlog cũng có thể tạo độ trễ. Duplicate độc lập
với ingest status và không tự biến thành offline.

## Transaction, ACK và logging

Unique index và transaction hiện có được giữ nguyên. Metadata được lưu cùng
reading và side effects trong một transaction. Duplicate giữ nguyên received_at,
delay, ingest status và freshness của lần lưu đầu; không cập nhật theo giờ retry.
Kiểm tra future skew cho bản ghi mới thực hiện sau duplicate lookup để việc
đồng hồ server bị chỉnh không phá ACK của một record hợp lệ đã commit.

Lỗi SQLite ở route trả 503 DATABASE_ERROR sau rollback, để firmware giữ record
và retry UUID cũ. Không biến lỗi DB thành permanent 4xx. Duplicate hợp lệ log INFO;
validation/conflict/DB failure log ERROR. App logger bật INFO để demo thấy log.

Log thực tế từ `test_recorded_demo` với đồng hồ test cố định:

```text
[READING OFFLINE_RECOVERED] device='FG-ESP32-01' id=2af96931-2e7d-4c37-bca9-79c59ac576ce captured_at=2026-09-29T01:00:00+07:00 received_at=2026-09-28T18:20:00+00:00 delay=1200.0s freshness=Fresh / Normal
[DUPLICATE REPLAY] device='FG-ESP32-01' id=2af96931-2e7d-4c37-bca9-79c59ac576ce action=reused_existing_reading
```

Response thực tế của lần POST đầu (HTTP 201):

```json
{
  "success": true,
  "message": "Reading saved",
  "reading_id": 1,
  "device_reading_id": "2af96931-2e7d-4c37-bca9-79c59ac576ce",
  "duplicate": false,
  "timestamp": "2026-09-29T01:00:00+07:00",
  "received_at": "2026-09-28T18:20:00+00:00",
  "delivery_delay_seconds": 1200.0,
  "ingest_status": "OFFLINE_RECOVERED",
  "freshness": {
    "status": "Fresh / Normal",
    "reason": "All sensor readings are available"
  }
}
```

Retry cùng payload trả HTTP 200 với toàn bộ giá trị trên giữ nguyên, chỉ đổi
`duplicate` thành `true` và `message` thành `Reading already exists`.

## Dashboard và giới hạn

GET `/api/v1/readings` và `/api/v1/readings/latest` đều thêm ba metadata field.
UI có thể map Captured=`timestamp`, Received=`received_at`,
Delay=`delivery_delay_seconds`, Sync Status=`ingest_status`,
Freshness=`freshness.status`. Với NULL, hiển thị không xác định. UI/admin overview
không được sửa trong task này; thứ tự GET vẫn theo ID insert giảm dần.

Không thay freshness rules. Engine đánh giá theo rules và active foods tại thời
điểm xử lý; storage duration/expiry dùng ngày hiện tại. Gas/sensor-fault state
vẫn xử lý theo thứ tự nhận, temperature exposure có guard cho timestamp cũ.
Task này không tái dựng đầy đủ trạng thái lịch sử hoặc sửa semantics out-of-order.

Backend idempotency ngăn lặp logical reading và side effects trong transaction;
không chứng minh gửi Telegram exactly-once nếu dịch vụ bên ngoài nhận tin nhưng
ACK thất lạc. Đồng hồ server/thiết bị cần đúng để delay có ý nghĩa. Firmware
quarantine permanent 400, nên timestamp tương lai quá mức cần kiểm tra RTC/NTP.

## Kiểm thử

`backend/tests/test_reading_ingest.py` dùng SQLite tạm và đồng hồ cố định, không
gửi Telegram. Bao phủ live/delayed/recovered, các biên 10/120 giây, future skew,
timezone tương đương/sai/thiếu, timestamp invalid, metadata GET, duplicate,
side effects, composite identity/conflict, migration lặp và rollback/DB failure.

Test rollback event hiện có được cập nhật từ mong đợi Python exception sang
HTTP 503 JSON; các kiểm tra dữ liệu/state rollback vẫn giữ nguyên.

Kết quả đã chạy ngày 2026-09-29:

- Nhóm ingest/API hardening/notification outbox: 116 passed.
- `test_recorded_demo`: 1 passed; response/log ở trên lấy từ lần chạy này.
- Toàn bộ backend sau cập nhật kỳ vọng lỗi DB: **534 passed in 66.78s**.
- `git diff --check` cho các file tracked đã sửa: không có lỗi whitespace.

Lệnh chạy toàn bộ từ thư mục gốc dự án:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q -c backend/pytest.ini backend/tests
```

Chưa kiểm thử ESP32 thật, mất mạng thật, hoặc cắt nguồn thật trong task backend.
