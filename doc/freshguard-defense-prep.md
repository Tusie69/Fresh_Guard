# FreshGuard — tài liệu chuẩn bị bảo vệ

## 1. Câu giới thiệu 30 giây

FreshGuard là hệ thống IoT theo dõi độ tươi thực phẩm. ESP32 đọc nhiệt độ, độ ẩm, nồng độ gas và trạng thái cửa; dữ liệu được lưu bền vững khi mất mạng, sau đó gửi về backend Flask. Backend là nơi quyết định freshness, lưu lịch sử vào SQLite, phát sinh event và gửi cảnh báo Telegram. Dashboard hiển thị trạng thái hiện tại, lịch sử và thông tin thực phẩm.

## 2. Kiến trúc phải trình bày

```text
ESP32 + sensors
  -> LittleFS FIFO / retry
  -> HTTP POST /api/v1/readings
  -> Flask validation + protocol normalization
  -> stateful rules: temperature, humidity, gas, door, expiry
  -> SQLite transaction
  -> Dashboard / Telegram outbox / events
```

Các thành phần chính:

- Firmware: DHT11, DS3231/NTP, MQ-135, MC-38, LED, buzzer, LCD, Wi-Fi và LittleFS.
- Backend: Flask route, validation, freshness engine, food lifecycle, sensor-fault state, gas baseline, temperature exposure, authentication và admin rule management.
- Dashboard: HTML/CSS/JavaScript được Flask phục vụ trực tiếp; không cần frontend build riêng.
- Simulator: mô phỏng HTTP device, offline queue, retry, event queue và freshness polling.

## 3. Luồng xử lý một reading

1. Thiết bị tạo `device_reading_id` UUID và timestamp từ RTC/NTP.
2. Reading được ghi vào LittleFS trước khi gửi; vì vậy mất mạng không làm mất dữ liệu.
3. Backend nhận JSON, kiểm tra kiểu dữ liệu, timestamp, sensor và trạng thái cửa.
4. Nếu có `food_id`, backend kiểm tra food tồn tại và lấy category/expiry.
5. Các stateful processor cập nhật gas baseline, nhiệt exposure và sensor fault.
6. Freshness engine lấy mức nghiêm trọng lớn nhất: `Fresh / Normal`, `Use Soon` hoặc `Check Food`.
7. Backend lưu reading và event trong cùng transaction rồi trả acknowledgement.
8. Thiết bị chỉ xóa bản ghi khỏi FIFO khi response hợp lệ xác nhận đúng `device_reading_id` và freshness status.

## 4. Những điểm mạnh nên nhấn mạnh

- Backend là source of truth; thiết bị không tự nhân bản freshness rule nên tránh lệch logic giữa firmware và server.
- Offline-first: FIFO bền vững, replay theo thứ tự, retry bounded, dead-letter cho lỗi vĩnh viễn và recovery sau reboot.
- Idempotency ở reading/event: retry cùng `device_reading_id` hoặc `event_id` không tạo bản ghi/event trùng; payload khác cùng identity trả conflict.
- Event transition có ngữ nghĩa: gas anomaly start/recovery, temperature exposure exceeded, sensor fault/recovered, door opened/timeout/closed.
- Gas baseline được scope theo `device_id + food_id`; state của từng loại thực phẩm không trộn lẫn.
- Có authentication, phân quyền ADMIN/USER, audit user/rule change và bảo vệ không để mất admin cuối cùng.
- Rule có thể chỉnh trong admin, có audit reason và reset state liên quan khi rule thay đổi.
- Có 573 test case đang được thu thập trong test suite; `compileall` và `git diff --check` đều đạt.

## 5. Điểm phải nói trung thực nếu bị hỏi sâu

### Firmware thật hay simulator?

Repo hiện có firmware Arduino thực tế và Python simulator. Simulator dùng để kiểm thử protocol/offline behavior nhanh; nó không thay thế bằng chứng đo đạc từ phần cứng. Khi demo phần cứng, phải dùng đúng sketch trong `firmware/ESP32-WROOM-32/ESP32-WROOM-32.ino` và nói rõ các cảm biến đã nối.

### Vì sao freshness không chạy ở ESP32?

Để tập trung một nguồn quyết định duy nhất. ESP32 chỉ đọc, lưu và gửi dữ liệu; backend tính freshness, lưu lịch sử và trả status. LED/buzzer trên thiết bị chỉ phản ánh status đã được backend xác nhận.

### Mất mạng thì dữ liệu thế nào?

Reading đã capture được append vào LittleFS JSONL trước. Khi có mạng lại, queue gửi FIFO theo batch giới hạn; chỉ khi acknowledgement hợp lệ mới compact/xóa record. Nếu HTTP lỗi tạm thời thì giữ lại; lỗi vĩnh viễn được đưa vào rejected/dead-letter để không âm thầm mất dữ liệu.

### Vì sao có baseline gas?

MQ-135 phụ thuộc môi trường và cảm biến; dùng baseline tương đối theo từng device/food hợp lý hơn một ngưỡng tuyệt đối cố định. Hệ thống warm-up, kiểm tra độ ổn định, học baseline rồi mới phát hiện tăng theo tỷ lệ và yêu cầu nhiều reading liên tiếp.

### Độ ẩm/gas có ngưỡng chất lượng tuyệt đối không?

Hiện humidity/gas sensor fault và gas anomaly được xử lý riêng. Humidity hiện chủ yếu kiểm tra tính hợp lệ; gas anomaly dùng baseline tương đối. Không nên tuyên bố đây là phép đo vi sinh hay kết luận an toàn thực phẩm tuyệt đối.

### Có bảo đảm exactly-once không?

Transport có thể retry và HTTP response có thể bị mất. Hệ thống đạt effectively-once ở backend nhờ identity/idempotency cho reading và event; không tuyên bố mạng tự nó exactly-once.

## 6. Kết quả kiểm thử hiện tại

Lệnh đã chạy:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Kết quả hiện tại: **569 passed, 4 failed**. Bốn lỗi đều nằm trong `test_cross_system_integration.py`, liên quan gas baseline lifecycle/anomaly transition và kỳ vọng state sau reinitialization. Đây là blocker cần xử lý trước khi tuyên bố toàn bộ test xanh; không nên nói “100% test pass”.

Diễn giải kỹ thuật: implementation hiện yêu cầu warm-up/stability lifecycle trước khi baseline ở trạng thái READY, trong khi các test tích hợp cũ đang kỳ vọng baseline legacy đã sẵn sàng sau chuỗi reading ngắn. Cần chọn một contract duy nhất: sửa lifecycle/test theo nhau, rồi chạy lại toàn bộ suite.

## 7. Các việc nên chốt trước ngày bảo vệ

1. Sửa hoặc cập nhật 4 test gas để thống nhất với thiết kế warm-up mới; chạy lại đến khi toàn bộ suite pass.
2. Chỉ giữ một bản firmware chuẩn hoặc ghi rõ bản nào là source of truth; hai file `.ino` hiện đang khác nhau.
3. Cập nhật `doc/architecture.md`: tài liệu này còn mô tả “chưa có ESP32 source”, không khớp với firmware hiện tại.
4. Đưa Wi-Fi password và IP demo ra file cấu hình riêng/secret; không trình chiếu hoặc commit credential thật.
5. Chuẩn bị demo fallback: nếu gas baseline chưa READY, trình bày dashboard + simulator/test thay vì khẳng định anomaly đã kích hoạt.

## 8. Câu kết luận mẫu

Đóng góp chính của FreshGuard là kết hợp sensing, freshness decision tập trung và cơ chế offline durable queue. Thiết kế ưu tiên không mất dữ liệu và không tạo cảnh báo trùng khi retry. Hệ thống là công cụ giám sát hỗ trợ quyết định bảo quản, không thay thế kiểm nghiệm an toàn thực phẩm; hướng phát triển tiếp theo là calibration cảm biến, triển khai secret management và hoàn thiện lifecycle gas trên dữ liệu thực tế.
