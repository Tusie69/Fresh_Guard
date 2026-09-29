#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <DHT.h>
#include <RTClib.h>
#include <LiquidCrystal.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include <esp_system.h>
#include <time.h>
#include <math.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/stat.h>
#include <errno.h>

// READ -> SEND -> RECEIVE STATUS -> ACT. Backend owns ALL freshness rules.
// Libraries: ArduinoJson 7; DHT sensor library + Adafruit Unified Sensor;
// RTClib + Adafruit BusIO; LiquidCrystal. Others belong to ESP32 Arduino core.

// ======================== DEMO CONFIG ========================
const char* WIFI_SSID = "Tutuong";
const char* WIFI_PASSWORD = "12345678"; // Never printed to Serial.
// PC Wi-Fi IPv4 observed during setup. Update after changing networks.
// ESP32 and PC need a reachable LAN; never use localhost here.
const char* SERVER_URL = "http://10.24.51.175:5000/api/v1/readings";
const char* DEVICE_ID = "FG-ESP32-01";
const char* FOOD_ID = ""; // Empty: omit. Otherwise use a registered backend food_id.
const bool ENABLE_BACKEND = true;
const bool AUTO_TEST = false; // No synthetic values are implemented.
const uint32_t SEND_INTERVAL_MS = 60000;
const uint32_t SYNC_INTERVAL_MS = 60000;
const size_t MAX_SYNC_PER_CYCLE = 5;
const size_t MAX_OFFLINE_RECORDS = 1000;
const size_t MAX_OFFLINE_BYTES = 384 * 1024;
const size_t MAX_REJECTED_BYTES = 64 * 1024;
// First provision LittleFS. Enable ONLY deliberately on a new/empty board,
// then disable and reflash. Mount failure must not erase an existing log.
const bool FORMAT_FS_ON_MOUNT_FAILURE = false;

// Tested wiring supplied by user. LCD is PARALLEL, not I2C.
#define DHT_PIN 4
#define DHT_TYPE DHT11
#define I2C_SDA 21
#define I2C_SCL 22
#define MQ135_PIN 34
#define GREEN_LED 23
#define YELLOW_LED 25
#define RED_LED 26
#define BUZZER_PIN 17 // User confirmed ACTIVE buzzer, HIGH = on.
#define DOOR_SENSOR_PIN 16 // MC-38 reed switch: RX2 / GPIO16
#define LCD_RS 13
#define LCD_EN 14
#define LCD_D4 27
#define LCD_D5 33
#define LCD_D6 32
#define LCD_D7 18

const uint32_t SENSOR_INTERVAL_MS = 5000; // Local display only; POST every 60s.
const uint32_t WIFI_RETRY_MS = 15000;
const uint32_t LCD_REFRESH_MS = 250;
const uint32_t DOOR_DEBOUNCE_MS = 50;
const uint32_t DOOR_THRESHOLD_SECONDS = 30;
const size_t MAX_RECORD_BYTES = 768;
const char* PENDING_PATH = "/littlefs/pending_readings.jsonl";
const char* TEMP_PATH = "/littlefs/pending_readings.tmp";
const char* REJECTED_PATH = "/littlefs/rejected_readings.jsonl";
const size_t FS_RESERVE_BYTES = 32768; // Also reserve a second copy for compaction.

DHT dht(DHT_PIN, DHT_TYPE);
RTC_DS3231 rtc;
LiquidCrystal lcd(LCD_RS, LCD_EN, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

struct PostRequest { char payload[MAX_RECORD_BYTES]; };
struct PostResult {
  int code;
  bool confirmed;
  char status[20];
  char reason[256];
};
QueueHandle_t requestQueue = nullptr, resultQueue = nullptr;
bool httpReady = false, inFlight = false;
PostRequest activeRequest = {};
uint32_t attempts = 0;
float temperature = NAN, humidity = NAN;
int gasRaw = 0;
bool gasValid = false, gasSampling = false, gasSamplesValid = true;
uint32_t gasTotal = 0, lastGasSample = 0;
uint8_t gasSamples = 0;
bool captureReading = false;
bool rtcDetected = false, ntpStarted = false, rtcSynced = false;
bool timeUnavailable = true;
String captureTimestamp, deferredReading;
bool deferredPersistAttempted = false, deferredHeldLogged = false;
String freshnessStatus = "Status: Pending";
bool backendOnline = false, apiError = false;
uint32_t statusChangedAt = 0;
bool warningBeepPending = false;

// MC-38 state: INPUT_PULLUP, LOW = magnet near/door closed,
// HIGH = magnet away/door open. The switch is wired between GPIO16 and GND.
bool doorRawOpen = false;
bool doorOpen = false;
bool doorReadingPending = false;
bool doorThresholdReported = false;
uint32_t doorRawChangedAt = 0;
uint32_t doorOpenedAt = 0;

bool storageReady = false, storageFull = false;
size_t pendingCount = 0, pendingBytes = 0, effectiveMaxBytes = 0;
size_t acknowledgedBytes = 0, nextRecordEnd = 0;
size_t cycleSent = 0, cycleTotal = 0;
bool syncActive = false;
bool syncRequested = false;
FILE* compactInput = nullptr;
FILE* compactOutput = nullptr;
size_t compactBytes = 0;
uint32_t lastSensorRead = 0, lastReading = 0, lastSync = 0;
uint32_t lastWiFiRetry = 0, lastLCD = 0;
bool wasWiFiConnected = false;

void storageError(const char* message) {
  Serial.printf("STORAGE ERROR: %s; logs preserved, reboot after repair.\n", message);
  storageReady = false;
  syncActive = false;
}

bool getFileSize(const char* path, size_t& size, bool allowMissing) {
  struct stat info;
  if (stat(path, &info) == 0) {
    if (!S_ISREG(info.st_mode)) return false;
    size = static_cast<size_t>(info.st_size);
    return true;
  }
  if (errno == ENOENT && allowMissing) { size = 0; return true; }
  return false;
}

int fileState(const char* path) {
  // ESP LittleFS VFS implements stat, but not access(). Never treat an
  // unsupported access() call as permission to truncate an existing log.
  struct stat info;
  if (stat(path, &info) == 0) return S_ISREG(info.st_mode) ? 1 : -1;
  return errno == ENOENT ? 0 : -1;
}

// POSIX exposes sync/close errors, unlike File.flush().
bool durableClose(FILE* file) {
  bool ok = fflush(file) == 0;
  if (fsync(fileno(file)) != 0) ok = false;
  if (fclose(file) != 0) ok = false;
  return ok;
}

// Never discard a partial line or join it to a new record silently.
bool readRecord(FILE* file, char* buffer) {
  if (!fgets(buffer, MAX_RECORD_BYTES, file)) return false;
  size_t length = strlen(buffer);
  if (!length || buffer[length - 1] != '\n') return false;
  buffer[length - 1] = '\0';
  JsonDocument doc;
  if (deserializeJson(doc, buffer) || !doc.is<JsonObject>()) return false;
  return doc["device_id"].is<const char*>() &&
         doc["device_reading_id"].is<const char*>() &&
         doc["timestamp"].is<const char*>() && doc["door_open"].is<bool>() &&
         doc.as<JsonObject>().containsKey("temperature_c") &&
         doc.as<JsonObject>().containsKey("humidity_pct") &&
         doc.as<JsonObject>().containsKey("gas_raw");
}

bool countPendingReadings() {
  FILE* file = fopen(PENDING_PATH, "rb");
  if (!file) return false;
  char record[MAX_RECORD_BYTES];
  pendingCount = 0;
  bool ok = true;
  while (static_cast<size_t>(ftell(file)) < pendingBytes) {
    if (!readRecord(file, record)) { ok = false; break; }
    ++pendingCount;
    vTaskDelay(1); // Boot recovery can scan a large log without starving RTOS.
  }
  fclose(file);
  return ok;
}

void initStorage() {
  if (!LittleFS.begin(FORMAT_FS_ON_MOUNT_FAILURE)) {
    storageError("LittleFS mount failed; auto-format disabled by default");
    return;
  }
  size_t total = LittleFS.totalBytes();
  if (total <= MAX_REJECTED_BYTES + FS_RESERVE_BYTES) {
    storageError("LittleFS partition too small");
    return;
  }
  effectiveMaxBytes = (total - MAX_REJECTED_BYTES - FS_RESERVE_BYTES) / 2;
  if (effectiveMaxBytes > MAX_OFFLINE_BYTES) effectiveMaxBytes = MAX_OFFLINE_BYTES;
  // After interrupted compaction original is authoritative. Missing original
  // plus an orphan temp requires inspection instead of guessing recovery state.
  int pendingState = fileState(PENDING_PATH);
  int tempState = fileState(TEMP_PATH);
  if (pendingState < 0 || tempState < 0) {
    storageError("cannot inspect existing logs");
    return;
  }
  if (pendingState == 0) {
    if (tempState == 1) {
      storageError("orphan temp log requires inspection");
      return;
    }
    FILE* empty = fopen(PENDING_PATH, "wb");
    if (!empty || !durableClose(empty)) {
      storageError("cannot create pending log");
      return;
    }
  }
  if (!getFileSize(PENDING_PATH, pendingBytes, false) || !countPendingReadings()) {
    storageError("incomplete/corrupt pending record; recover log manually");
    return;
  }
  if (tempState == 1 && remove(TEMP_PATH) != 0) {
    storageError("cannot remove abandoned replacement log");
    return;
  }
  storageReady = true;
  storageFull = pendingCount >= MAX_OFFLINE_RECORDS || pendingBytes >= effectiveMaxBytes;
  Serial.printf("LittleFS recovered: %u records, %u bytes, limit %u bytes\n",
                unsigned(pendingCount), unsigned(pendingBytes), unsigned(effectiveMaxBytes));
}

bool appendOfflineReading(const String& payload) {
  if (!storageReady || compactOutput) {
    Serial.println("NOT PERSISTED: storage unavailable; new reading cannot be sent safely");
    return false;
  }
  size_t bytes = payload.length() + 1;
  if (pendingCount >= MAX_OFFLINE_RECORDS || pendingBytes + bytes > effectiveMaxBytes ||
      LittleFS.totalBytes() - LittleFS.usedBytes() < pendingBytes + bytes + FS_RESERVE_BYTES) {
    storageFull = true;
    Serial.println("STORAGE FULL: preserving unsent records; new reading NOT persisted");
    return false;
  }
  FILE* file = fopen(PENDING_PATH, "ab");
  if (!file) { storageError("append open failed"); return false; }
  bool ok = fwrite(payload.c_str(), 1, payload.length(), file) == payload.length();
  if (fputc('\n', file) == EOF) ok = false;
  if (!durableClose(file)) ok = false;
  if (!ok) { storageError("append/sync failed; possible partial final line"); return false; }
  pendingBytes += bytes;
  ++pendingCount;
  storageFull = false;
  Serial.printf("READING PERSISTED Q:%u %s\n", unsigned(pendingCount), payload.c_str());
  return true;
}

void maintainDeferredReading() {
  if (!deferredReading.length()) return;
  // One attempt per captured reading, then retry only after successful
  // compaction frees space. Fatal errors stay latched until manual repair.
  if (storageReady && !compactOutput && !deferredPersistAttempted) {
    deferredPersistAttempted = true;
    if (appendOfflineReading(deferredReading)) {
      deferredReading = "";
      deferredPersistAttempted = false;
      deferredHeldLogged = false;
      return;
    }
  }
  if (!deferredHeldLogged) {
    Serial.println("READING HELD IN RAM: not durable; new reading capture paused");
    deferredHeldLogged = true;
  }
}

// Copy remaining records over successive loop ticks, using bounded RAM.
// LittleFS replacement rename is atomic. NEVER unlink original before rename.
void beginCompaction() {
  syncActive = false;
  if (!acknowledgedBytes || !storageReady) return;
  compactInput = fopen(PENDING_PATH, "rb");
  compactOutput = fopen(TEMP_PATH, "wb");
  if (!compactInput || !compactOutput ||
      fseek(compactInput, acknowledgedBytes, SEEK_SET) != 0) {
    if (compactInput) fclose(compactInput);
    if (compactOutput) fclose(compactOutput);
    compactInput = compactOutput = nullptr;
    storageError("cannot start log compaction");
    return;
  }
  compactBytes = 0;
  Serial.printf("COMPACTION START: retiring %u bytes\n", unsigned(acknowledgedBytes));
}

void maintainCompaction() {
  if (!compactOutput) return;
  uint8_t buffer[1024];
  size_t count = fread(buffer, 1, sizeof(buffer), compactInput);
  bool ok = !ferror(compactInput);
  if (count && fwrite(buffer, 1, count, compactOutput) != count) ok = false;
  compactBytes += count;
  if (ok && count == sizeof(buffer)) return;
  fclose(compactInput);
  compactInput = nullptr;
  if (!durableClose(compactOutput)) ok = false;
  compactOutput = nullptr;
  if (compactBytes != pendingBytes - acknowledgedBytes) ok = false;
  if (ok && rename(TEMP_PATH, PENDING_PATH) != 0) ok = false;
  if (!ok) { storageError("replacement failed; original retained"); return; }
  pendingBytes = compactBytes;
  acknowledgedBytes = 0;
  storageFull = pendingCount >= MAX_OFFLINE_RECORDS || pendingBytes >= effectiveMaxBytes;
  deferredPersistAttempted = false; // Retry the held payload before another sync cycle.
  // Continue draining the durable FIFO immediately instead of waiting for
  // the normal 60-second sync interval between bounded batches.
  syncRequested = pendingCount > 0 && WiFi.status() == WL_CONNECTED;
  Serial.printf("COMPACTION COMPLETE; durable pending Q:%u\n", unsigned(pendingCount));
}

bool handlePermanentFailure(int code) {
  // Quarantine before retiring a FIFO record. A crash can duplicate the
  // rejection record, but cannot silently erase the rejected reading.
  JsonDocument rejected, reading;
  if (deserializeJson(reading, activeRequest.payload)) return false;
  rejected["http_code"] = code;
  rejected["reading"] = reading.as<JsonObject>();
  String line;
  size_t written = serializeJson(rejected, line);
  size_t rejectedBytes;
  if (rejected.overflowed() || written != measureJson(rejected) ||
      line.length() != written || !getFileSize(REJECTED_PATH, rejectedBytes, true)) {
    storageError("cannot prepare rejection record");
    return false;
  }
  if (rejectedBytes + line.length() + 1 > MAX_REJECTED_BYTES) {
    storageError("rejected log full; manual export/repair required");
    return false;
  }
  FILE* file = fopen(REJECTED_PATH, "ab");
  if (!file) { storageError("cannot open rejected log"); return false; }
  bool ok = fwrite(line.c_str(), 1, line.length(), file) == line.length();
  if (fputc('\n', file) == EOF) ok = false;
  if (!durableClose(file)) ok = false;
  if (!ok) storageError("cannot persist permanent failure");
  Serial.printf("PERMANENT HTTP %d: %s\n", code, activeRequest.payload);
  return ok;
}

// Network worker has no FS/sensor/LCD/LED access; all timeouts stay off loop().
void httpWorker(void*) {
  PostRequest request;
  for (;;) {
    if (xQueueReceive(requestQueue, &request, portMAX_DELAY) != pdTRUE) continue;
    PostResult result = {};
    result.code = -1;
    HTTPClient http;
    http.setConnectTimeout(2000);
    http.setTimeout(2000);
    http.useHTTP10(true);
    if (WiFi.status() == WL_CONNECTED && http.begin(SERVER_URL)) {
      http.addHeader("Content-Type", "application/json");
      result.code = http.POST(String(request.payload));
      if (result.code == 200 || result.code == 201) {
        char body[2048]; // Bounded even when Content-Length is absent.
        auto* stream = http.getStreamPtr();
        stream->setTimeout(2000);
        int expected = http.getSize();
        if (expected < int(sizeof(body))) {
          size_t wanted = expected >= 0 ? size_t(expected) : sizeof(body) - 1;
          size_t got = stream->readBytes(body, wanted);
          body[got] = '\0';
          JsonDocument doc, sent;
          if ((expected < 0 || got == size_t(expected)) && got < sizeof(body) - 1 &&
              !deserializeJson(doc, body) && !deserializeJson(sent, request.payload)) {
            const char* status = doc["freshness"]["status"] | "";
            const char* responseId = doc["device_reading_id"] | "";
            const char* sentId = sent["device_reading_id"] | "";
            bool recognized = strcmp(status, "Fresh / Normal") == 0 ||
                              strcmp(status, "Use Soon") == 0 ||
                              strcmp(status, "Check Food") == 0;
            result.confirmed = doc["success"].is<bool>() && doc["success"].as<bool>() &&
                               strcmp(responseId, sentId) == 0 && recognized;
            if (result.confirmed) {
              strlcpy(result.status, status, sizeof(result.status));
              strlcpy(result.reason, doc["freshness"]["reason"] | "", sizeof(result.reason));
            }
          }
        }
      }
    }
    http.end();
    xQueueSend(resultQueue, &result, portMAX_DELAY);
  }
}

void setStatusLED(const char* status) {
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(YELLOW_LED, LOW);
  digitalWrite(RED_LED, LOW);
  if (strcmp(status, "Fresh / Normal") == 0) digitalWrite(GREEN_LED, HIGH);
  else if (strcmp(status, "Use Soon") == 0) digitalWrite(YELLOW_LED, HIGH);
  else if (strcmp(status, "Check Food") == 0) digitalWrite(RED_LED, HIGH);
}

void handleBackendResponse(const PostResult& result) {
  if (freshnessStatus != result.status) {
    freshnessStatus = result.status;
    statusChangedAt = millis();
    warningBeepPending = freshnessStatus == "Use Soon";
  }
  setStatusLED(result.status);
  Serial.printf("BACKEND: %s | %s\n", result.status, result.reason);
}

void updateBuzzer() {
  uint32_t age = millis() - statusChangedAt;
  bool on = false;
  if (freshnessStatus == "Check Food") {
    uint32_t phase = age % 5000;
    on = phase < 180 || (phase >= 360 && phase < 540);
  } else if (warningBeepPending) {
    on = age < 150;
    if (!on) warningBeepPending = false;
  }
  // Offline alone does not alarm; LCD conveys communication errors.
  digitalWrite(BUZZER_PIN, on ? HIGH : LOW);
}

void processRetryQueue() {
  if (inFlight) {
    PostResult result;
    if (xQueueReceive(resultQueue, &result, 0) != pdTRUE) return;
    inFlight = false;
    Serial.printf("HTTP %d attempt:%lu\n", result.code, static_cast<unsigned long>(attempts));
    // An append can fail while HTTP is in flight. Consume the result, but
    // do not quarantine, advance the FIFO or compact a suspect filesystem.
    if (!storageReady) {
      Serial.println("STORAGE ERROR: HTTP result consumed; original retained for recovery");
      return;
    }
    bool retired = false;
    if (result.confirmed) {
      Serial.println("BACKEND CONFIRMED: validated acknowledgement");
      backendOnline = true;
      apiError = false;
      handleBackendResponse(result);
      retired = true;
    } else {
      backendOnline = false;
      apiError = true;
      bool permanent = result.code >= 400 && result.code < 500 &&
                       result.code != 408 && result.code != 429;
      if (permanent) retired = handlePermanentFailure(result.code);
      else Serial.println("DELIVERY UNCONFIRMED: original kept for next sync cycle");
    }
    if (retired) {
      acknowledgedBytes = nextRecordEnd;
      --pendingCount;
      ++cycleSent;
      attempts = 0;
    } else {
      beginCompaction();
      return;
    }
  }
  if (!syncActive || !storageReady) return;
  if (cycleSent >= MAX_SYNC_PER_CYCLE || pendingCount == 0 ||
      WiFi.status() != WL_CONNECTED) {
    beginCompaction();
    return;
  }
  FILE* file = fopen(PENDING_PATH, "rb");
  if (!file) { storageError("cannot read pending log"); return; }
  bool ok = fseek(file, acknowledgedBytes, SEEK_SET) == 0 &&
            readRecord(file, activeRequest.payload);
  nextRecordEnd = ftell(file);
  fclose(file);
  if (!ok) { storageError("invalid pending record"); return; }
  if (xQueueSend(requestQueue, &activeRequest, 0) == pdTRUE) {
    inFlight = true;
    ++attempts;
    Serial.printf("POST attempt:%lu %s\n", static_cast<unsigned long>(attempts), activeRequest.payload);
  }
}

String generateUuidV4() {
  uint8_t bytes[16];
  esp_fill_random(bytes, sizeof(bytes));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  char id[37];
  snprintf(id, sizeof(id),
           "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
           bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
           bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]);
  return String(id);
}

bool validRTCDateTime(const DateTime& value) {
  return value.isValid() && value.year() >= 2025 && value.year() <= 2099;
}

String getTimestamp() {
  char value[32];
  // RTC stores Vietnam LOCAL calendar time, matching the tested sketch.
  if (rtcDetected && !rtc.lostPower()) {
    DateTime now = rtc.now();
    if (validRTCDateTime(now)) {
      snprintf(value, sizeof(value), "%04d-%02d-%02dT%02d:%02d:%02d+07:00",
               now.year(), now.month(), now.day(), now.hour(), now.minute(), now.second());
      timeUnavailable = false;
      return String(value);
    }
  }
  struct tm local;
  if (ntpStarted && getLocalTime(&local, 0) && local.tm_year >= 125) {
    strftime(value, sizeof(value), "%Y-%m-%dT%H:%M:%S+07:00", &local);
    timeUnavailable = false;
    return String(value);
  }
  timeUnavailable = true;
  return ""; // No fabricated/build-time timestamp.
}

void maintainWiFi() {
  bool connected = WiFi.status() == WL_CONNECTED;
  if (connected != wasWiFiConnected) {
    wasWiFiConnected = connected;
    if (connected) {
      Serial.printf("WIFI CONNECTED/RECONNECTED: %s\n", WiFi.localIP().toString().c_str());
      if (pendingCount > 0) {
        syncRequested = true;
        Serial.println("SYNC REQUESTED: WiFi available with pending records");
      }
    }
    else { backendOnline = false; Serial.println("WiFi disconnected"); }
  }
  if (!connected && millis() - lastWiFiRetry >= WIFI_RETRY_MS) {
    lastWiFiRetry = millis();
    Serial.println("WiFi reconnect attempt");
    WiFi.reconnect();
  }
  if (connected && !ntpStarted) {
    configTime(7 * 3600, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
    ntpStarted = true;
  }
  static uint32_t lastTimeCheck = 0;
  if (ntpStarted && !rtcSynced && millis() - lastTimeCheck >= 1000) {
    lastTimeCheck = millis();
    struct tm local;
    if (getLocalTime(&local, 0) && local.tm_year >= 125) {
      if (rtcDetected) rtc.adjust(DateTime(local.tm_year + 1900, local.tm_mon + 1,
                                         local.tm_mday, local.tm_hour, local.tm_min, local.tm_sec));
      rtcSynced = true;
      timeUnavailable = false;
      Serial.println("NTP ready; DS3231 synchronized if present");
    }
  }
}

uint32_t getDoorOpenDurationSeconds() {
  if (!doorOpen) return 0;
  return (millis() - doorOpenedAt) / 1000UL;
}

void maintainDoorSensor() {
  uint32_t now = millis();
  bool rawOpen = digitalRead(DOOR_SENSOR_PIN) == HIGH;
  if (rawOpen != doorRawOpen) {
    doorRawOpen = rawOpen;
    doorRawChangedAt = now;
  }
  if (doorRawOpen != doorOpen && now - doorRawChangedAt >= DOOR_DEBOUNCE_MS) {
    doorOpen = doorRawOpen;
    if (doorOpen) {
      doorOpenedAt = now;
      doorThresholdReported = false;
      Serial.println("MC-38: DOOR OPEN");
    } else {
      uint32_t openSeconds = doorOpenedAt ? (now - doorOpenedAt) / 1000UL : 0;
      Serial.printf("MC-38: DOOR CLOSED | previous open duration:%lu s\n",
                    static_cast<unsigned long>(openSeconds));
      doorOpenedAt = 0;
      doorThresholdReported = false;
    }
  }
  bool thresholdReached = doorOpen && doorOpenedAt != 0 &&
                          now - doorOpenedAt >= DOOR_THRESHOLD_SECONDS * 1000UL;
  if (thresholdReached && !doorThresholdReported) {
    doorThresholdReported = true;
    doorReadingPending = true;
    Serial.printf("MC-38: door threshold reached (%lu s); priority reading queued\n",
                  static_cast<unsigned long>(DOOR_THRESHOLD_SECONDS));
  }
}

String buildReading(const String& timestamp) {
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["device_reading_id"] = generateUuidV4();
  doc["timestamp"] = timestamp;
  doc["temperature_c"] = nullptr;
  doc["humidity_pct"] = nullptr;
  doc["gas_raw"] = nullptr;
  if (isfinite(temperature)) doc["temperature_c"] = temperature;
  if (isfinite(humidity)) doc["humidity_pct"] = humidity;
  if (gasValid) doc["gas_raw"] = gasRaw;
  doc["door_open"] = doorOpen;
  doc["open_duration_seconds"] = getDoorOpenDurationSeconds();
  if (FOOD_ID && FOOD_ID[0]) doc["food_id"] = FOOD_ID;
  String payload;
  size_t written = serializeJson(doc, payload);
  if (doc.overflowed() || written != measureJson(doc) || payload.length() != written ||
      payload.length() + 2 > MAX_RECORD_BYTES) {
    Serial.println("ERROR: payload allocation/size; reading not queued");
    return "";
  }
  return payload;
}

void startSensorRead(bool forReading) {
  humidity = dht.readHumidity();
  temperature = dht.readTemperature();
  if (!isfinite(temperature)) temperature = NAN;
  if (!isfinite(humidity)) humidity = NAN;
  captureReading = forReading;
  captureTimestamp = forReading ? getTimestamp() : String("");
  gasTotal = gasSamples = 0;
  gasSamplesValid = true;
  gasSampling = true;
  lastGasSample = millis() - 10;
}

void maintainSensorRead() {
  if (!gasSampling || millis() - lastGasSample < 10) return;
  lastGasSample = millis();
  int value = analogRead(MQ135_PIN);
  if (value < 0 || value > 4095) gasSamplesValid = false;
  else gasTotal += value;
  if (++gasSamples < 20) return;
  gasSampling = false;
  gasRaw = gasTotal / 20;
  // Tested sketch's electrical validity checks, NOT gas anomaly rules.
  gasValid = gasSamplesValid && gasRaw > 5 && gasRaw < 4080;
  Serial.printf("SENSORS T:%s H:%s Gas:%s\n",
                isfinite(temperature) ? String(temperature, 1).c_str() : "null",
                isfinite(humidity) ? String(humidity, 1).c_str() : "null",
                gasValid ? String(gasRaw).c_str() : "null");
  Serial.printf("MC-38 Door:%s Open:%lu s Alert:%s\n",
                doorOpen ? "OPEN" : "CLOSED",
                static_cast<unsigned long>(getDoorOpenDurationSeconds()),
                doorThresholdReported ? "THRESHOLD_REPORTED" : "NO");
  if (!captureReading || !ENABLE_BACKEND) return;
  if (!captureTimestamp.length()) {
    Serial.println("TIME ERROR: no valid RTC/NTP time; new reading skipped");
    return;
  }
  if (deferredReading.length()) {
    Serial.println("ERROR: storage busy; previous captured reading still pending in RAM");
    return;
  }
  deferredReading = buildReading(captureTimestamp);
  deferredPersistAttempted = false;
  deferredHeldLogged = false;
}

void lcdPrintLine(uint8_t row, String text) {
  text = text.substring(0, 16);
  while (text.length() < 16) text += ' ';
  lcd.setCursor(0, row);
  lcd.print(text);
}

void updateLCD() {
  if (millis() - lastLCD < LCD_REFRESH_MS) return;
  lastLCD = millis();
  bool statusPage = (millis() / 3000) % 2;
  String measurements = "T:" + (isfinite(temperature) ? String(temperature, 1) : String("N/A"));
  measurements += " H:" + (isfinite(humidity) ? String(humidity, 0) : String("N/A"));
  lcdPrintLine(0, statusPage ? freshnessStatus : measurements);
  String connection;
  if (!storageReady) connection = "Storage Error";
  else if (storageFull) connection = "STORAGE FULL";
  else if (!httpReady) connection = "HTTP Task Error";
  else if (timeUnavailable) connection = "Time Error";
  else if (!ENABLE_BACKEND) connection = "Backend OFF";
  else if (syncActive || compactOutput) connection = "SYNC " + String(cycleSent) + "/" + String(cycleTotal);
  else if (WiFi.status() != WL_CONNECTED) connection = "OFFLINE Q:" + String(pendingCount);
  else if (apiError) connection = "Backend Error";
  else if (!backendOnline) connection = "API Pending Q:" + String(pendingCount);
  else connection = "ONLINE Q:" + String(pendingCount);
  lcdPrintLine(1, connection);
}

void setup() {
  Serial.begin(115200);
  Serial.println("FreshGuard boot: real sensors, backend authoritative, durable FIFO");
  for (int pin : {GREEN_LED, YELLOW_LED, RED_LED, BUZZER_PIN}) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  pinMode(DOOR_SENSOR_PIN, INPUT_PULLUP);
  doorRawOpen = digitalRead(DOOR_SENSOR_PIN) == HIGH;
  doorOpen = doorRawOpen;
  doorRawChangedAt = millis();
  if (doorOpen) doorOpenedAt = millis();
  Serial.printf("MC-38 initial state: %s\n", doorOpen ? "DOOR OPEN" : "DOOR CLOSED");
  lcd.begin(16, 2);
  lcdPrintLine(0, "FreshGuard");
  lcdPrintLine(1, "BOOTING...");
  dht.begin();
  pinMode(MQ135_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(MQ135_PIN, ADC_11db);
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setTimeOut(50);
  rtcDetected = rtc.begin();
  Serial.println(rtcDetected ? "DS3231 detected" : "DS3231 missing; waiting for NTP");
  getTimestamp();
  initStorage();
  requestQueue = xQueueCreate(1, sizeof(PostRequest));
  resultQueue = xQueueCreate(1, sizeof(PostResult));
  if (requestQueue && resultQueue) {
    httpReady = xTaskCreate(httpWorker, "freshguard-http", 12288, nullptr, 1, nullptr) == pdPASS;
  }
  if (!httpReady) Serial.println("ERROR: HTTP worker allocation failed; readings remain durable");
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastReading = lastSync = lastSensorRead = lastWiFiRetry = millis();
  Serial.printf("Backend: %s | device:%s | interval:%lu ms\n", SERVER_URL, DEVICE_ID,
                static_cast<unsigned long>(SEND_INTERVAL_MS));
  Serial.println("Ready. First reading after 60s; recovered queue syncs on WiFi connection; boot self-tests disabled.");
}

void loop() {
  maintainDoorSensor();
  maintainWiFi();
  maintainCompaction();
  uint32_t now = millis();
  if (!gasSampling && !deferredReading.length() && now - lastReading >= SEND_INTERVAL_MS) {
    lastReading = lastSensorRead = now;
    startSensorRead(true);
  } else if (doorReadingPending && !gasSampling && !deferredReading.length()) {
    doorReadingPending = false;
    lastSensorRead = now;
    startSensorRead(true);
  } else if (!gasSampling && now - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = now;
    startSensorRead(false);
  }
  maintainSensorRead();
  maintainDeferredReading();
  // Finish this cycle's sensor capture before starting the bounded FIFO batch.
  // A full queue may still drain while the single RAM slot waits for space.
  if (ENABLE_BACKEND && httpReady && storageReady && !gasSampling &&
      !syncActive && !inFlight && !compactOutput && pendingCount > 0 &&
      WiFi.status() == WL_CONNECTED &&
      (syncRequested || now - lastSync >= SYNC_INTERVAL_MS)) {
    lastSync = now;
    cycleSent = 0;
    cycleTotal = pendingCount;
    syncActive = true;
    syncRequested = false;
    Serial.printf("SYNC START Q:%u batch limit:%u\n",
                  unsigned(pendingCount), unsigned(MAX_SYNC_PER_CYCLE));
  }
  processRetryQueue();
  updateBuzzer();
  updateLCD();
  delay(1); // Yield one tick; no blocking reconnect or alarm loops.
}
