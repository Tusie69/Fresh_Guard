# FreshGuard

FreshGuard is an IoT food-freshness monitoring system. An ESP32 reads temperature, humidity, MQ-135 gas level, DS3231 time, and an MC-38 reed switch, then sends readings to a Flask backend. The backend is authoritative for freshness decisions, dashboard data, and Telegram notifications.

## Project layout

- `firmware/ESP32-WROOM-32/ESP32-WROOM-32.ino` — ESP32 firmware with LittleFS offline FIFO, Wi-Fi retry, sensor reads, and MC-38 door monitoring.
- `backend/` — Flask API, SQLite schema initialization, freshness rules, ingest metadata, and Telegram notification outbox.
- `dashboard/` — browser dashboard for readings, freshness status, food records, and events.
- `doc/` — architecture, threshold matrices, offline-ingest, Telegram, and presentation documentation.

## Cách chạy dự án

### 1. Chuẩn bị môi trường

Cài Python 3.11 trở lên và mở PowerShell tại thư mục gốc `freshguard` (thư mục chứa README này). Backend dùng Flask và SQLite; dashboard được Flask phục vụ trực tiếp, không cần chạy frontend riêng hoặc cài Node.js.

Tạo môi trường ảo và cài thư viện:

```powershell
py -3 -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Nếu máy không có lệnh `py`, dùng `python -m venv backend/.venv`. Các lệnh bên dưới gọi trực tiếp Python trong môi trường ảo nên không cần chạy `Activate.ps1`.

### 2. Cấu hình môi trường

Tạo `backend/.env` từ file mẫu nếu chưa có:

```powershell
if (-not (Test-Path backend/.env)) {
    Copy-Item backend/.env.example backend/.env
}
```

Điền `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` nếu cần thông báo Telegram; có thể để trống khi chỉ chạy dashboard/API. File `.env` được Git bỏ qua.

Có thể thêm `FRESHGUARD_SECRET_KEY=<chuỗi ngẫu nhiên riêng của bạn>` vào `.env` để giữ khóa phiên đăng nhập ổn định giữa các lần khởi động. Nếu không cấu hình, backend tự tạo khóa mới mỗi lần chạy và người dùng cần đăng nhập lại.

### 3. Tạo tài khoản admin

**Dự án không tạo sẵn tài khoản hoặc mật khẩu admin mặc định.** Trước lần đăng nhập đầu tiên, chạy:

```powershell
.\backend\.venv\Scripts\python.exe backend/create_admin.py
```

Nhập thông tin theo yêu cầu:

| Thông tin | Giá trị |
|---|---|
| `Admin username` | Tên đăng nhập tự chọn, ví dụ `admin` |
| `Admin password` | Mật khẩu tự đặt, không được để trống |
| `Confirm password` | Nhập lại đúng mật khẩu vừa đặt |
| Quyền tài khoản | `ADMIN` (script tự gán) |

Mật khẩu không hiển thị khi gõ. Khi thấy `Created ADMIN user: admin` (hoặc tên bạn đã chọn), tài khoản đã được tạo. Dùng chính tên đăng nhập và mật khẩu này để đăng nhập; không có mật khẩu mẫu dùng chung.

Script tự khởi tạo SQLite tại `backend/freshguard.db` và lưu mật khẩu dưới dạng hash. Chỉ cần tạo tài khoản một lần cho mỗi cơ sở dữ liệu; chạy lại với cùng tên sẽ báo lỗi trùng username. Nếu đã có tài khoản, bỏ qua bước tạo và dùng tài khoản hiện có. Sau khi đăng nhập, admin có thể quản lý tài khoản và các quy tắc trên trang quản trị.

### 4. Khởi động backend và mở dashboard

```powershell
.\backend\.venv\Scripts\python.exe -B .\backend\run.py
```

Giữ cửa sổ PowerShell này mở trong khi sử dụng. Backend tự khởi tạo/cập nhật cấu trúc cơ sở dữ liệu khi chạy và lắng nghe tại `0.0.0.0:5000`.

| Trang | Địa chỉ trên máy chạy dự án |
|---|---|
| Đăng nhập | http://localhost:5000/login |
| Quản trị admin | http://localhost:5000/admin |
| Dashboard | http://localhost:5000/ |

Mở trang đăng nhập và nhập tài khoản đã tạo ở bước 3. Tài khoản `ADMIN` được chuyển đến trang quản trị sau khi đăng nhập thành công. Dùng `Ctrl+C` trong PowerShell để dừng backend. Những lần chạy sau chỉ cần thực hiện bước 4.

Dashboard có thể chưa có số liệu nếu ESP32 chưa gửi dữ liệu.

### 5. Kết nối ESP32 (khi chạy với phần cứng)

Mở sketch [`firmware/ESP32-WROOM-32/ESP32-WROOM-32.ino`](firmware/ESP32-WROOM-32/ESP32-WROOM-32.ino) bằng Arduino IDE, cài các thư viện nêu trong phần ESP32 wiring bên dưới, rồi sửa:

- `WIFI_SSID` và `WIFI_PASSWORD`: Wi-Fi mà ESP32 sẽ kết nối.
- `SERVER_URL`: `http://<IP_LAN_CUA_MAY_CHAY_BACKEND>:5000/api/v1/readings`. Dùng `ipconfig` trên Windows để xem địa chỉ IPv4 của máy.

Máy chạy Flask và ESP32 phải ở cùng mạng có thể truy cập nhau. Không dùng `localhost` trong firmware. Nếu Windows Firewall chặn kết nối, cho phép Python/cổng 5000 trên mạng đang dùng. Nạp firmware và mở Serial Monitor ở 115200 baud; lần đọc thông thường đầu tiên được tạo sau 60 giây khi có thời gian RTC/NTP hợp lệ.

## Test Telegram

With the backend environment installed and `backend/.env` configured:

```powershell
.\backend\.venv\Scripts\python.exe backend/check_telegram.py --send-test
```

See [`doc/telegram-notifications.md`](doc/telegram-notifications.md) for transition rules and retry behavior.

## ESP32 wiring

The current firmware uses:

| Device | ESP32 pin |
|---|---:|
| DHT11 | GPIO 4 |
| DS3231 SDA/SCL | GPIO 21 / 22 |
| MQ-135 analog output | GPIO 34 |
| MC-38 reed switch | GPIO 16 / RX2 to GND |
| LEDs | GPIO 23 / 25 / 26 |
| Active buzzer | GPIO 17 |
| LCD1602 parallel | RS 13, EN 14, D4 27, D5 33, D6 32, D7 18 |

The reed input uses `INPUT_PULLUP`: LOW means the magnet is near and the door is closed; HIGH means the door is open. The firmware debounces the switch and creates a priority reading after 30 seconds continuously open.

Install the Arduino libraries listed in the firmware comments (ArduinoJson 7, DHT sensor library, Adafruit Unified Sensor, RTClib, Adafruit BusIO, and LiquidCrystal), select an ESP32-WROOM-32/ESP32 Dev Module with a LittleFS-capable partition, and open Serial Monitor at 115200 baud. The first normal reading is captured after 60 seconds. The ESP32 must have a valid RTC or NTP timestamp before a new reading can be queued.

## Offline demonstration

1. Start Flask and confirm the ESP32 reports Wi-Fi and backend connectivity.
2. Let at least one reading be acknowledged.
3. Stop Flask or disconnect the ESP32 from Wi-Fi.
4. The ESP32 keeps readings in LittleFS at `pending_readings.jsonl`; it does not discard them when delivery is unconfirmed.
5. Reboot while offline and verify `LittleFS recovered: ... records` in Serial output.
6. Restore Flask/Wi-Fi. The durable FIFO is sent in order in bounded batches of five; the next batch starts immediately after compaction, and records are removed only after a validated backend acknowledgement.

Detailed acceptance checks are in [`doc/offline-reading-ingest.md`](doc/offline-reading-ingest.md).

## Tests

Run the backend test suite with:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install pytest
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Do not commit `backend/.env`, SQLite databases, virtual environments, or generated caches. Use [`backend/.env.example`](backend/.env.example) as the configuration template.
