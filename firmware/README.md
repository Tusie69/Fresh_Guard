# FreshGuard ESP32 demo

Firmware hoàn chỉnh: `ESP32-WROOM-32.ino`. Dựa trên sơ đồ chân của sketch người dùng đã chạy thành công; buzzer được xác nhận là **ACTIVE**. Backend là nơi duy nhất quyết định freshness. Không sửa backend, protocol hoặc business rules.

## Cấu hình và chạy

1. Chọn ESP32 Dev Module / ESP32-WROOM-32 và phân vùng có filesystem (ví dụ Default 4MB with SPIFFS trong Arduino ESP32; LittleFS dùng phân vùng có nhãn `spiffs`). Không dùng cấu hình không có filesystem.
2. Cài các thư viện bên dưới. Mở sketch trong thư mục cùng tên `ESP32-WROOM-32` nếu Arduino IDE yêu cầu.
3. Sửa `WIFI_SSID`, `WIFI_PASSWORD`, `SERVER_IP` và `SERVER_PORT` ở đầu file. Giữ `ENABLE_BACKEND=true`. ESP32 phải truy cập được máy chạy Flask trên cổng 5000.
4. Sketch giữ Wi-Fi `Tutuong` từ file đã test. Máy PC lúc kiểm tra đang ở mạng **FPL STUDENTS**, IP **10.24.51.175**; URL mặc định theo IP này. Hai cấu hình hiện thuộc các mạng khác nhau: trước demo, đưa PC và ESP32 lên cùng mạng/hotspot rồi cập nhật URL theo IPv4 của PC trên mạng đó. Không mặc định IP hotspot cũ `172.20.10.2` còn đúng. Cấu hình WiFi.begin(ssid,password) trong sketch không cấu hình WPA2-Enterprise của mạng trường.
5. Chạy tại thư mục gốc project:

   ```powershell
   .\backend\.venv\Scripts\python.exe -B .\backend\run.py
   ```

   `run.py` đã bind `0.0.0.0:5000`. Cho phép Python/cổng 5000 qua Windows Firewall trên mạng demo nếu Windows chặn. Có thể kiểm tra từ thiết bị khác cùng mạng bằng `http://<PC_IP>:5000/api/v1/readings/latest`; phản hồi JSON 404 khi chưa có dữ liệu vẫn chứng tỏ API truy cập được.
6. LittleFS **không tự format**. Với board mới chưa có LittleFS, chỉ khi chắc chắn không có dữ liệu cần giữ, đặt `FORMAT_FS_ON_MOUNT_FAILURE=true` để khởi tạo một lần, sau đó đặt lại `false` và nạp lại. Không bật tùy chọn erase-all-flash khi cập nhật board đang chứa dữ liệu offline. Thay đổi partition scheme có thể làm mất dữ liệu.
7. Nạp firmware, mở Serial 115200. Lần tạo reading/đồng bộ đầu tiên sau 60 giây. Cảm biến/LCD cập nhật cục bộ mỗi 5 giây. Không có giá trị giả hoặc self-test LED/buzzer khi boot.

## Sơ đồ chân giữ nguyên

| Thiết bị | GPIO | Chế độ |
|---|---|---|
| DHT11 | 4 | Digital, DHT11 |
| MQ-135 AO | 34 | ADC1, input-only, 12-bit, ADC_11db |
| DS3231 SDA / SCL | 21 / 22 | I2C |
| LED xanh / vàng / đỏ | 23 / 25 / 26 | Output, HIGH bật |
| Buzzer ACTIVE | 17 | Output, HIGH bật; giữ mạch đã test |
| LCD1602 RS / EN | 13 / 14 | Song song 4-bit |
| LCD1602 D4 / D5 / D6 / D7 | 27 / 33 / 32 / 18 | Song song 4-bit |
| Reed switch | Không có | `door_open=false`, `open_duration_seconds=0` |

Không có GPIO trùng, không dùng chân strapping hoặc chân flash. GPIO34 chỉ dùng input; các output không dùng chân input-only. LCD không dùng I2C, vì vậy không cần đoán địa chỉ LCD và không có xung đột địa chỉ LCD/DS3231. Còi ACTIVE dùng digitalWrite, không chiếm PWM/tone. Không tích hợp cảm biến mưa/nước hoặc cảm biến khác vì sketch được cung cấp không có chúng. Cần kiểm tra thực tế sơ đồ điện, nguồn và mức điện áp; đây là kiểm tra source, không phải xác nhận phần cứng.

## Đọc cảm biến và thời gian

- DHT11: đọc hai trường riêng; trường không hữu hạn gửi `null`, không dùng lại giá trị cũ.
- MQ-135: giữ trung bình 20 mẫu ADC cách nhau ít nhất 10ms, nhưng lấy mẫu bằng millis thay vì vòng delay. Giữ tiêu chí điện của file mới: trung bình `<=5` hoặc `>=4080` gửi `null`. Không tự quyết định gas anomaly/baseline.
- DS3231: lưu giờ địa phương Việt Nam như sketch gốc, kiểm tra lostPower và ngày hợp lệ. NTP đồng bộ RTC khi có giờ mạng; có thể dùng NTP làm nguồn dự phòng nếu RTC vắng/lỗi.
- Timestamp có offset `+07:00`. Không có giờ hợp lệ: ghi lỗi Serial/LCD và bỏ lần tạo reading mới; vẫn có thể gửi các reading cũ đã có timestamp hợp lệ. Không dùng giờ build hoặc thời gian cố định.
- `FOOD_ID=""` được bỏ khỏi JSON; ID được cấu hình phải tồn tại trong backend. UUID v4 mới cho mỗi reading, giữ nguyên toàn bộ payload khi gửi lại.

Ví dụ payload (minh họa, firmware lấy giá trị và thời gian thực):

```json
{"device_id":"FG-ESP32-01","device_reading_id":"2af96931-2e7d-4c37-bca9-79c59ac576ce","timestamp":"2026-09-28T10:40:00+07:00","temperature_c":4.7,"humidity_pct":86,"gas_raw":510,"door_open":false,"open_duration_seconds":0}
```

POST `/api/v1/readings`, `Content-Type: application/json`. Không trộn compact payload. Phản hồi thành công phải có `success=true`, `device_reading_id` khớp và `freshness.status` thuộc ba giá trị chính xác. Đọc `freshness.reason` để log Serial. Không tìm substring trong response và không đọc status ở top-level.

## LED, LCD, buzzer và kết nối

| Backend status | LED | Buzzer |
|---|---|---|
| Fresh / Normal | Xanh | Tắt |
| Use Soon | Vàng | Một tiếng 150ms khi chuyển vào trạng thái |
| Check Food | Đỏ | Hai tiếng 180ms mỗi 5 giây |

Tắt cả ba LED trước khi áp trạng thái mới. Trước phản hồi đầu tiên, LED tắt, LCD `Status: Pending`. Không có điều kiện MQ_BASELINE_READY/LED_TEST_MODE chặn hoặc thay thế quyết định backend. Khi lỗi mạng/API, giữ trạng thái backend cuối cùng; không đổi sang Fresh. Còi không báo chỉ vì offline, nhưng tiếp tục nhịp cảnh báo của trạng thái Check Food đã được backend xác nhận.

LCD1602: dòng đầu luân phiên số đo T/H và trạng thái backend mỗi 3 giây; từng cảm biến lỗi hiện N/A riêng. Dòng hai hiện ONLINE/OFFLINE và Q, SYNC, Backend Error, Time Error hoặc Storage Error/FULL. Đang gửi backlog thì freshness là kết quả backend của reading lịch sử vừa xác nhận, chưa nhất thiết là tình trạng của mẫu mới nhất.

Wi-Fi kết nối không có vòng chờ, retry mỗi 15 giây. HTTP chạy trong tác vụ FreeRTOS riêng, buffer cố định, timeout connect/read 2 giây; không chặn loop LCD/còi. Chỉ loop chính truy cập cảm biến, RTC, LCD và filesystem. Lấy mẫu DHT và từng thao tác flash vẫn có độ trễ ngắn phụ thuộc thư viện/phần cứng.

## Offline và tính bền vững

- Filesystem: LittleFS. Log chính `/pending_readings.jsonl`, log tạm `/pending_readings.tmp`, log lỗi vĩnh viễn `/rejected_readings.jsonl`. Prefix `/littlefs` trong code là điểm mount VFS.
- Write-ahead: serialize một JSON object gọn + newline, append, fflush/fsync/close thành công **trước POST**. Không lưu response trong identity.
- Giới hạn: 1.000 bản ghi hoặc 384KiB, lấy giới hạn nào tới trước; tự giảm giới hạn byte theo partition để chừa một bản sao compact, log lỗi 64KiB và 32KiB dự phòng.
- Đầy: giữ toàn bộ bản ghi chưa gửi, ngừng append mẫu mới và báo rõ Serial/LCD. Những mẫu mới bị từ chối lưu sẽ bị mất; không giả vờ đã lưu hoặc âm thầm xóa bản ghi cũ.
- Mỗi 60 giây lấy reading mới và append vào cuối FIFO, rồi xử lý tối đa 5 bản ghi từ đầu. Nếu còn backlog, reading mới chờ lượt; không vượt lên trước dữ liệu cũ. Một lỗi tạm thời dừng batch tới chu kỳ sau.
- `200`/`201` với JSON xác nhận đúng: đánh dấu đã giao. Lỗi transport, `408`, `429`, `5xx` và phản hồi thành công không hợp lệ: giữ nguyên, retry chu kỳ sau. Không tự theo redirect.
- `400`, `404`, `409` và các `4xx` khác ngoài `408`/`429`: ghi nguyên reading cùng HTTP code vào log lỗi, rồi loại khỏi FIFO. Không retry vô hạn. Log lỗi đầy/ghi lỗi: dừng xử lý và yêu cầu kiểm tra, không âm thầm bỏ dữ liệu.
- Sau batch, copy phần còn lại sang temp bằng buffer 1KiB qua nhiều vòng loop; fsync/close rồi rename đè nguyên tử. Không unlink log gốc trước rename. Trong khi compact, một mẫu mới có thể tạm chờ trong RAM; chưa có thông báo PERSISTED thì chưa được coi là bền vững.
- Mất điện trước commit compact: có thể gửi lại bản đã được backend lưu; UUID/payload giống nhau nên backend trả duplicate `200`. Sau reboot, đếm log và bắt đầu từ bản cũ nhất. Trạng thái LED trước reboot không được lưu, nên khởi động lại ở Pending.
- Log gốc hợp lệ + temp bỏ dở: dùng log gốc. Dòng thiếu newline/JSON hỏng hoặc chỉ có temp mà mất log gốc: báo lỗi và giữ file để phục hồi thủ công. Không tự format hoặc lặng lẽ bỏ dòng hỏng. Độ bền sau cắt nguồn thực tế cần test trên board.

Atomic rename/sync dựa trên [LittleFS upstream](https://github.com/littlefs-project/littlefs#usage); parsing dùng [ArduinoJson 7](https://arduinojson.org/v7/api/json/deserializejson/).

## Thư viện

| Thư viện ngoài core | Mục đích |
|---|---|
| ArduinoJson 7 | Serialize JSON đúng kiểu, parse freshness lồng nhau |
| DHT sensor library (Adafruit) | DHT11 |
| Adafruit Unified Sensor | Dependency của thư viện DHT |
| RTClib (Adafruit) | DS3231 |
| Adafruit BusIO | Dependency của RTClib |
| LiquidCrystal (Arduino) | LCD1602 song song |

WiFi, HTTPClient, Wire, LittleFS, FreeRTOS và các API thời gian thuộc ESP32 Arduino core. Buzzer ACTIVE không cần thư viện. Không cần LiquidCrystal_I2C.

## Giới hạn backend cần biết

Chu kỳ POST 60s được giữ theo yêu cầu. Backend hiện chỉ cộng temperature exposure khi hai mẫu liên tiếp cách nhau tối đa **10s**, nên chu kỳ này không tích lũy exposure. Critical temperature tức thời vẫn do backend xử lý. Firmware không sửa ngưỡng hoặc gửi dữ liệu giả để bù khoảng trống.

Backend xử lý storage/expiry theo ngày hiện tại lúc nhận dữ liệu. FIFO giữ thứ tự các mẫu của thiết bị; firmware không tính lại quyết định cho dữ liệu lịch sử.

## Kiểm tra thủ công trên board

1. **Online:** API chạy, chờ 60s, Serial có PERSISTED → POST → HTTP 201 → BACKEND, Q trở về 0. Đối chiếu UUID trong DB/API và LED/LCD/còi.
2. **Offline + reboot:** dừng Flask, chờ đúng 3 chu kỳ để có Q:3; reboot. Serial phải báo recovered 3 records trước chu kỳ mới, UUID/timestamp cũ không đổi.
3. **Recovery:** bật Flask, chu kỳ tiếp theo gửi FIFO, Q giảm; tối đa 5 bản/chu kỳ, cộng thêm một mẫu mới mỗi phút.
4. **Lost response:** qua proxy thử nghiệm cho request vào backend nhưng bỏ response; retry cùng UUID phải nhận 200, DB không có hàng trùng.
5. **Permanent:** trên môi trường test trả 400/404/409; bản đó chuyển sang rejected log, mẫu sau tiếp tục, không gửi mãi bản lỗi.
6. **Long outage:** tạo hơn 5 bản pending, khôi phục mạng; kiểm tra chỉ tối đa 5 POST thành công/permanent mỗi chu kỳ, LCD/còi vẫn cập nhật trong timeout.
7. **Storage/power:** giảm capacity trong bản test để thấy FULL không xóa pending; cắt nguồn sau append, sau backend ACK, giữa compact và rename; kiểm tra UUID/DB/log sau reboot. Kiểm tra mount failure không format, dòng hỏng báo lỗi.
8. **Sensors/time:** tháo từng cảm biến để thấy null riêng; mất RTC/NTP phải báo Time Error, không tạo timestamp giả. Xác minh RTC đang lưu giờ Việt Nam, dây và nguồn ổn định.

Các bước trên là quy trình cần chạy thực tế, không phải tuyên bố đã kiểm thử phần cứng.

## Kiểm tra trên máy phát triển

- Kiểm tra tĩnh: tất cả GPIO là duy nhất; door placeholder, chu kỳ 60s, batch 5 và mặc định không format đúng cấu hình.
- Toolchain dùng để build: ESP32 Arduino core **3.3.8**, FQBN `esp32:esp32:esp32`; ArduinoJson **7.4.2**, DHT **1.4.7**, Adafruit Unified Sensor **1.1.15**, RTClib **2.1.4**, Adafruit BusIO **1.17.4**, LiquidCrystal **1.0.7**.
- Bản cuối **biên dịch thành công**, bật `--warnings all`, không có cảnh báo được in ra. Flash chương trình **1.153.728 / 1.310.720 byte (88%)**; RAM tĩnh **51.608 / 327.680 byte (15%)**. Heap và stack runtime vẫn cần theo dõi trên board; phần trăm RAM tĩnh không phải mức dùng RAM cao nhất.
- Lệnh regression theo yêu cầu:

  ```powershell
  .\backend\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -o pythonpath=C:/Users/TuNgu/freshguard/backend backend/tests firmware/tests -q
  ```

- Kết quả: **522 passed, 1 failed**. `test_api_gas_context_separates_devices_and_foods` (`backend/tests/test_gas_anomaly.py:298`) dùng MEAT inserted_at cố định `2026-09-26`, nhưng ngày chạy `2026-09-28` đã vào cửa sổ cảnh báo storage nên nhận `Use Soon`. Đây là lỗi có từ trước thay đổi firmware. Không sửa backend/test để làm xanh suite.
- Các pytest trong `firmware/tests` kiểm tra Python simulator, không chạy mã `.ino`. Kiểm tra runtime LittleFS, reboot/cắt điện, điện áp và giao tiếp thật ESP32 → Flask vẫn cần thực hiện theo quy trình bên trên.
- Không commit/push; không thay backend hoặc dashboard.
