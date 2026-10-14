# Kịch bản demo FreshGuard — 7 phút

## Chuẩn bị trước demo

- Backend chạy trên `0.0.0.0:5000`.
- Điện thoại và ESP32 cùng mạng LAN.
- ESP32 dùng device `FG-ESP32-01` và queue đang bằng 0.
- Telegram token/chat ID đã cấu hình.
- Food cũ không cần thiết đã được deactivate.
- Không dùng gas để tạo trạng thái trong live demo nếu baseline chưa `READY`.

Mở sẵn dashboard, Serial Monitor và Telegram.

## 0:00–0:30 — Mở đầu

“Em xin demo luồng hoạt động chính của FreshGuard. ESP32 thu thập dữ liệu cảm biến, backend đánh giá freshness, dashboard hiển thị kết quả và Telegram gửi thông báo khi có chuyển trạng thái. Khi mất mạng, ESP32 vẫn lưu reading cục bộ và tự đồng bộ lại khi kết nối trở lại.”

Cho hội đồng thấy:

```text
Device: FG-ESP32-01
Backend: running
Queue: 0
```

## 0:30–1:30 — QR Add Food

“Đầu tiên, em thêm một thực phẩm và gắn nó với thiết bị bằng QR.”

### QR hợp lệ

Để prefill cả mã Apple và category, QR phải chứa URL FreshGuard dạng:

```text
/add-food?food_id=FG-APPLE-001&category=FRUIT
```

Các QR category hợp lệ khác là:

```text
FG-MEAT
FG-DAIRY
FG-VEGETABLE
FG-FRUIT
FG-COOKED
```

QR ngoài các định dạng này bị từ chối ngay với:

```text
Invalid FreshGuard QR code
```

### Thao tác

1. Scan QR Apple.
2. Browser mở luồng Add Food.
3. Kiểm tra:

```text
Food ID: FG-APPLE-001
Category: FRUIT
Device: FG-ESP32-01
```

4. Nhập hoặc xác nhận tên `Apple`.
5. Bấm `Add Food`.

Request này tạo food, activate food cho `FG-ESP32-01` và enqueue notification `FOOD_ADDED` trong cùng transaction. Không cần nạp lại firmware. Dashboard tự refresh khoảng 5 giây; Telegram worker poll outbox mỗi 5 giây.

Kết quả cần thấy:

```text
Active Food: Apple
Device: FG-ESP32-01
```

Telegram có nội dung tương ứng `Food Added`, `Apple`, `FG-APPLE-001` và device.

## 1:30–2:20 — Luồng sensor

“ESP32 chỉ đọc cảm biến, tạo reading và gửi lên backend. Backend mới là source of truth cho freshness.”

Reading gồm:

```text
Temperature
Humidity
Gas raw
Door
device_reading_id
timestamp
```

Reading bình thường được tạo mỗi 60 giây. Sensor local được đọc thường xuyên hơn, khoảng 5 giây, nhưng không phải mỗi lần đọc đều gửi backend.

Backend kết hợp reading với active food và đánh giá nhiệt độ, độ ẩm, gas, cửa, storage, expiry và sensor fault. Kết quả cuối cùng là severity cao nhất trong ba trạng thái:

```text
Fresh / Normal
Use Soon
Check Food
```

## 2:20–3:20 — Freshness và LED

“Firmware không tự tính freshness. Firmware nhận kết quả từ backend và cập nhật LED.”

### Fresh / Normal

```text
Backend: Fresh / Normal
LED: Green
```

### Use Soon

Dùng điều kiện đã chuẩn bị trong rehearsal, ví dụ expiry/storage phù hợp; không dùng gas nếu baseline chưa `READY`.

```text
Backend: Use Soon
LED: Yellow
Telegram: FOOD_USE_SOON
```

### Check Food

Dùng điều kiện đã chuẩn bị, ví dụ nhiệt độ/exposure, cửa mở quá thời gian, expiry hoặc sensor fault.

```text
Backend: Check Food
LED: Red
Telegram: FOOD_CHECK_FOOD
```

Nếu các reading tiếp theo giữ nguyên status, hệ thống không gửi lại Telegram liên tục. Chỉ transition mới tạo notification.

## 3:20–3:45 — Gas baseline

“MQ-135 không dùng một ngưỡng ADC cố định. Baseline được tách theo device và food.”

Lifecycle hiện tại:

```text
WARMING_UP → LEARNING → READY
```

Rule:

```text
Warm-up tối thiểu: 5 phút
Stability window: 5 readings
Max - min: không quá 100 ADC
Baseline learning: 10 mẫu hợp lệ
Anomaly: baseline tăng ít nhất 30% trong 3 mẫu liên tiếp
```

“Trong demo này, em không dùng gas làm trigger nếu baseline chưa READY để tránh false alarm khi cảm biến mới khởi động.”

## 3:45–4:45 — Mất mạng

“Bây giờ em mô phỏng mất WiFi.”

Trước khi tắt mạng:

```text
Queue: 0
ESP32: online
```

Tắt WiFi hoặc hotspot. ESP32 vẫn đọc cảm biến. Mỗi reading mới được ghi vào LittleFS trước khi gửi.

Log thực tế cần quan sát:

```text
WiFi disconnected
READING PERSISTED Q:1 ...
```

LCD hiển thị:

```text
OFFLINE Q:1
```

Reading mới chỉ được tạo mỗi 60 giây, nên cần chờ đến chu kỳ tiếp theo. Không reset board trong bước này.

Dashboard chưa thấy reading offline vì backend chưa nhận được dữ liệu.

## 4:45–5:45 — Reconnect và replay

“Em bật mạng trở lại. Firmware tự reconnect và tự yêu cầu đồng bộ, không cần reset ESP32.”

Log thực tế có thể gồm:

```text
WIFI CONNECTED/RECONNECTED: <IP>
SYNC REQUESTED: WiFi available with pending records
SYNC START Q:1 batch limit:5
POST attempt:1 ...
BACKEND CONFIRMED: validated acknowledgement
QUEUE REMOVE remaining:0
COMPACTION COMPLETE; durable pending Q:0
```

Nếu có nhiều hơn 5 records, firmware gửi theo nhiều batch. Queue chỉ remove sau khi backend trả acknowledgement hợp lệ gồm `success`, cùng `device_reading_id` và freshness status hợp lệ.

## 5:45–6:30 — Chứng minh offline replay

Mở bảng history trên dashboard và tìm các reading vừa replay.

“Hệ thống giữ hai mốc thời gian riêng biệt.”

```text
timestamp   = thời điểm ESP32 đo
received_at = thời điểm backend nhận sau reconnect
```

History hiển thị badge:

```text
Offline replay
```

Timeline được sắp theo `timestamp`, không theo thời điểm backend nhận. Nếu reading cuối đã cũ hơn 90 giây, dashboard có thể hiện thêm cảnh báo `Device Stale`; đây là cảnh báo freshness của kết nối, không làm thay đổi timestamp gốc.

## 6:30–7:00 — Kết luận

“Qua demo, FreshGuard thể hiện bốn khả năng chính:

Thứ nhất, food được tạo và gắn với thiết bị bằng QR hợp lệ.

Thứ hai, ESP32 gửi dữ liệu còn backend tập trung đánh giá freshness.

Thứ ba, LED phản hồi tại thiết bị và Telegram chỉ thông báo khi có transition, tránh spam.

Cuối cùng, khi mất mạng, reading được lưu bền vững trên LittleFS, replay theo FIFO và vẫn giữ đúng measured timestamp.”

“Đó là luồng hoạt động chính của FreshGuard.”

## Plan B

### Camera không hoạt động

Mở URL đã chuẩn bị sẵn:

```text
/add-food?food_id=FG-APPLE-001&category=FRUIT
```

Nói:

“Em chuyển sang URL FreshGuard đã decode sẵn để không phụ thuộc camera permission.”

### Telegram chưa gửi ngay

Mở outbox hoặc dashboard và nói:

“Notification đã được ghi vào outbox tách khỏi transaction chính. Vì vậy lỗi Telegram không làm thất bại việc tạo food hay lưu reading.”

### Gas baseline chưa READY

Nói:

“Gas đang ở giai đoạn warm-up hoặc learning, nên em không dùng gas làm trigger trực tiếp trong demo.”

### ESP32 chưa reconnect ngay

Chờ theo chu kỳ retry 15 giây và quan sát log `WIFI CONNECTED/RECONNECTED`. Không reset ngay.

### Queue chưa tăng

Nhắc rằng sensor đọc khoảng 5 giây nhưng reading gửi backend theo chu kỳ 60 giây. Chờ đến reading cycle tiếp theo.
