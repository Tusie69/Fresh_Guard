#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <DHT.h>
#include <RTClib.h>
#include <time.h>
#include <esp_system.h>
#include <math.h>

// ======================================================
// FRESHGUARD
// DHT11 + DS3231 + MQ-135 + WiFi + NTP
// ======================================================


// ======================================================
// PIN CONFIG
// ======================================================

// DHT11
#define DHT_PIN 4
#define DHT_TYPE DHT11

// DS3231 I2C
#define I2C_SDA 21
#define I2C_SCL 22

// MQ-135 Analog
#define MQ135_PIN 34

// LEDs
#define GREEN_LED  23
#define YELLOW_LED 25
#define RED_LED    26


// ======================================================
// OBJECTS
// ======================================================

DHT dht(DHT_PIN, DHT_TYPE);

RTC_DS3231 rtc;


// ======================================================
// WIFI
// ======================================================

// SỬA 2 DÒNG NÀY

const char* WIFI_SSID =
  "Nói Ít Thôi";

const char* WIFI_PASSWORD =
  "nochodau";


// ======================================================
// BACKEND
// ======================================================

// Test hardware trước:
// false = không gọi Flask
//
// Sau khi 3 sensor ổn:
// đổi thành true

const bool ENABLE_BACKEND =
  false;


// IP laptop chạy Flask

const char* SERVER_IP =
  "10.140.67.4";


const char* DEVICE_ID =
  "FG-ESP32-01";

// Leave empty until a food item is explicitly selected.
const char* FOOD_ID = "";


// ======================================================
// MQ-135 BASELINE
// ======================================================

/*
   GIỮ FALSE ở giai đoạn hiện tại.

   Chỉ đổi thành true sau khi:
   - MQ-135 đã warm-up/stabilize
   - bạn đã ghi baseline
   - divider 10k/10k không thay đổi
   - ADC settings không thay đổi
*/

const bool MQ_BASELINE_READY =
  false;


// ======================================================
// TIMEZONE
// ======================================================

// Việt Nam UTC+7

const long GMT_OFFSET_SEC =
  7 * 3600;

const int DAYLIGHT_OFFSET_SEC =
  0;


// ======================================================
// INTERVAL
// ======================================================

const unsigned long SENSOR_INTERVAL =
  5000;

const unsigned long WIFI_RETRY_INTERVAL =
  15000;

const unsigned long NTP_RETRY_INTERVAL =
  30000;


unsigned long lastSensorRead =
  0;

unsigned long lastWiFiRetry =
  0;

unsigned long lastNtpAttempt =
  0;


// ======================================================
// SENSOR STATES
// ======================================================

// DHT11

float temperature =
  NAN;

float humidity =
  NAN;

bool temperatureValid =
  false;

bool humidityValid =
  false;

bool dhtValid =
  false;


// RTC

bool rtcDetected =
  false;

bool rtcTimeValid =
  false;

bool ntpSynced =
  false;


// MQ-135

int gasRaw =
  0;

bool mqReadable =
  false;

bool gasValid =
  false;

bool mqSaturated =
  false;


// ======================================================
// LEDs
// ======================================================

void allLedsOff() {

  digitalWrite(
    GREEN_LED,
    LOW
  );

  digitalWrite(
    YELLOW_LED,
    LOW
  );

  digitalWrite(
    RED_LED,
    LOW
  );
}


void showFresh() {

  allLedsOff();

  digitalWrite(
    GREEN_LED,
    HIGH
  );

  Serial.println(
    "LED: GREEN -> Fresh"
  );
}


void showUseSoon() {

  allLedsOff();

  digitalWrite(
    YELLOW_LED,
    HIGH
  );

  Serial.println(
    "LED: YELLOW -> Use Soon"
  );
}


void showCheckFood() {

  allLedsOff();

  digitalWrite(
    RED_LED,
    HIGH
  );

  Serial.println(
    "LED: RED -> Check Food"
  );
}


// ======================================================
// DHT11
// ======================================================

bool readDHT11() {

  float h =
    dht.readHumidity();

  float t =
    dht.readTemperature();


  temperatureValid = isfinite(t);
  humidityValid = isfinite(h);

  temperature = temperatureValid ? t : NAN;
  humidity = humidityValid ? h : NAN;
  dhtValid = temperatureValid && humidityValid;

  if (!temperatureValid) {
    Serial.println("ERROR: DHT11 temperature read failed");
  }
  if (!humidityValid) {
    Serial.println("ERROR: DHT11 humidity read failed");
  }

  // A failure in either field must not prevent the other field from being sent.
  return dhtValid;
}


// ======================================================
// MQ-135
// ======================================================

int readMQ135() {

  /*
     Lấy trung bình nhiều mẫu
     để giảm noise.
  */

  const int SAMPLE_COUNT =
    20;

  unsigned long total =
    0;


  for (
    int i = 0;
    i < SAMPLE_COUNT;
    i++
  ) {

    int value =
      analogRead(
        MQ135_PIN
      );


    total +=
      value;


    delay(
      10
    );
  }


  int average =
    total / SAMPLE_COUNT;


  gasRaw =
    average;


  mqReadable =
    true;


  // ADC gần full scale.
  // Không kết luận đây là khí nguy hiểm;
  // chỉ đánh dấu ADC có thể đang saturation.

  mqSaturated =
    gasRaw >= 4080;

  gasValid = mqReadable && !mqSaturated;


  return gasRaw;
}


// ======================================================
// RTC VALIDATION
// ======================================================

bool validateRTCDateTime(
  DateTime value
) {

  if (
    value.year() < 2025 ||
    value.year() > 2035
  ) {

    return false;
  }


  if (
    value.month() < 1 ||
    value.month() > 12
  ) {

    return false;
  }


  if (
    value.day() < 1 ||
    value.day() > 31
  ) {

    return false;
  }


  return true;
}


// ======================================================
// RTC TIMESTAMP
// ======================================================

String getRTCTimestamp() {

  if (
    !rtcDetected ||
    !rtcTimeValid
  ) {

    return "";
  }


  DateTime now =
    rtc.now();


  char buffer[32];


  snprintf(
    buffer,
    sizeof(buffer),

    "%04d-%02d-%02dT%02d:%02d:%02d+07:00",

    now.year(),
    now.month(),
    now.day(),

    now.hour(),
    now.minute(),
    now.second()
  );


  return String(
    buffer
  );
}


// ======================================================
// RTC INIT
// ======================================================

void initializeRTC() {

  Serial.println();

  Serial.println(
    "================================"
  );

  Serial.println(
    "DS3231 INITIALIZATION"
  );

  Serial.println(
    "================================"
  );


  if (
    !rtc.begin()
  ) {

    Serial.println(
      "ERROR: DS3231 NOT FOUND"
    );


    rtcDetected =
      false;

    rtcTimeValid =
      false;


    return;
  }


  rtcDetected =
    true;


  Serial.println(
    "DS3231 detected."
  );


  if (
    rtc.lostPower()
  ) {

    Serial.println(
      "RTC lost power."
    );

    Serial.println(
      "Waiting for NTP synchronization."
    );


    rtcTimeValid =
      false;


    return;
  }


  DateTime current =
    rtc.now();


  if (
    validateRTCDateTime(
      current
    )
  ) {

    rtcTimeValid =
      true;


    Serial.print(
      "RTC retained time: "
    );

    Serial.println(
      getRTCTimestamp()
    );

  }

  else {

    rtcTimeValid =
      false;


    Serial.println(
      "RTC time invalid."
    );
  }
}


// ======================================================
// WIFI CONNECTION
// ======================================================

bool connectWiFi() {

  if (
    WiFi.status() ==
    WL_CONNECTED
  ) {

    return true;
  }


  Serial.println();

  Serial.println(
    "================================"
  );

  Serial.println(
    "WIFI CONNECTION"
  );

  Serial.println(
    "================================"
  );


  Serial.print(
    "SSID: "
  );

  Serial.println(
    WIFI_SSID
  );


  WiFi.mode(
    WIFI_STA
  );


  WiFi.persistent(
    false
  );


  WiFi.setAutoReconnect(
    true
  );


  WiFi.setSleep(
    false
  );


  WiFi.begin(
    WIFI_SSID,
    WIFI_PASSWORD
  );


  unsigned long started =
    millis();


  while (
    WiFi.status() !=
    WL_CONNECTED
  ) {

    delay(
      500
    );


    Serial.print(
      "."
    );


    if (
      millis() -
      started >
      20000
    ) {

      Serial.println();

      Serial.println(
        "WiFi connection timeout."
      );


      return false;
    }
  }


  Serial.println();

  Serial.println(
    "WiFi connected!"
  );


  Serial.print(
    "IP: "
  );

  Serial.println(
    WiFi.localIP()
  );


  Serial.print(
    "RSSI: "
  );

  Serial.print(
    WiFi.RSSI()
  );

  Serial.println(
    " dBm"
  );


  return true;
}


// ======================================================
// WIFI RECONNECT
// ======================================================

void maintainWiFi() {

  if (
    WiFi.status() ==
    WL_CONNECTED
  ) {

    return;
  }


  unsigned long now =
    millis();


  if (
    now -
    lastWiFiRetry <
    WIFI_RETRY_INTERVAL
  ) {

    return;
  }


  lastWiFiRetry =
    now;


  Serial.println(
    "WiFi disconnected -> reconnecting..."
  );


  WiFi.disconnect();


  delay(
    200
  );


  WiFi.begin(
    WIFI_SSID,
    WIFI_PASSWORD
  );
}


// ======================================================
// NTP -> DS3231
// ======================================================

bool syncRTCFromNTP() {

  if (
    !rtcDetected
  ) {

    return false;
  }


  if (
    WiFi.status() !=
    WL_CONNECTED
  ) {

    return false;
  }


  Serial.println();

  Serial.println(
    "================================"
  );

  Serial.println(
    "NTP TIME SYNC"
  );

  Serial.println(
    "================================"
  );


  configTime(
    GMT_OFFSET_SEC,
    DAYLIGHT_OFFSET_SEC,

    "pool.ntp.org",
    "time.google.com",
    "time.cloudflare.com"
  );


  struct tm timeInfo;


  if (
    !getLocalTime(
      &timeInfo,
      15000
    )
  ) {

    Serial.println(
      "NTP synchronization failed."
    );


    ntpSynced =
      false;


    return false;
  }


  Serial.printf(
    "NTP time: %04d-%02d-%02d %02d:%02d:%02d\r\n",

    timeInfo.tm_year + 1900,
    timeInfo.tm_mon + 1,
    timeInfo.tm_mday,

    timeInfo.tm_hour,
    timeInfo.tm_min,
    timeInfo.tm_sec
  );


  // Write NTP into DS3231

  rtc.adjust(

    DateTime(

      timeInfo.tm_year + 1900,

      timeInfo.tm_mon + 1,

      timeInfo.tm_mday,

      timeInfo.tm_hour,

      timeInfo.tm_min,

      timeInfo.tm_sec
    )
  );


  delay(
    200
  );


  DateTime verify =
    rtc.now();


  Serial.printf(
    "RTC readback: %04d-%02d-%02d %02d:%02d:%02d\r\n",

    verify.year(),
    verify.month(),
    verify.day(),

    verify.hour(),
    verify.minute(),
    verify.second()
  );


  rtcTimeValid =
    validateRTCDateTime(
      verify
    );


  ntpSynced =
    rtcTimeValid;


  if (
    ntpSynced
  ) {

    Serial.println(
      "NTP: SYNCED"
    );
  }


  return ntpSynced;
}


// ======================================================
// NTP RETRY
// ======================================================

void maintainNTP() {

  if (
    ntpSynced
  ) {

    return;
  }


  if (
    !rtcDetected
  ) {

    return;
  }


  if (
    WiFi.status() !=
    WL_CONNECTED
  ) {

    return;
  }


  unsigned long now =
    millis();


  if (
    lastNtpAttempt != 0 &&
    now -
    lastNtpAttempt <
    NTP_RETRY_INTERVAL
  ) {

    return;
  }


  lastNtpAttempt =
    now;


  syncRTCFromNTP();
}


// ======================================================
// PRINT SENSOR DATA
// ======================================================

void printSensorData(const String& readingTimestamp) {

  Serial.println();

  Serial.println(
    "================================"
  );

  Serial.println(
    "FRESHGUARD SENSOR DATA"
  );

  Serial.println(
    "================================"
  );


  // ====================================================
  // TIME
  // ====================================================

  Serial.print(
    "Time        : "
  );


  if (readingTimestamp.length() > 0) {
    Serial.println(readingTimestamp);

  }

  else {

    Serial.println(
      "DATA UNAVAILABLE"
    );
  }


  // ====================================================
  // TEMPERATURE
  // ====================================================

  Serial.print(
    "Temperature : "
  );


  if (temperatureValid) {

    Serial.print(
      temperature,
      1
    );

    Serial.println(
      " C"
    );

  }

  else {

    Serial.println(
      "DATA UNAVAILABLE"
    );
  }


  // ====================================================
  // HUMIDITY
  // ====================================================

  Serial.print(
    "Humidity    : "
  );


  if (humidityValid) {

    Serial.print(
      humidity,
      1
    );

    Serial.println(
      " %"
    );

  }

  else {

    Serial.println(
      "DATA UNAVAILABLE"
    );
  }


  // ====================================================
  // MQ-135
  // ====================================================

  Serial.print(
    "Gas raw     : "
  );


  if (gasValid) {

    Serial.println(
      gasRaw
    );

  }

  else {

    Serial.println(
      "DATA UNAVAILABLE"
    );
  }


  // ====================================================
  // STATUS
  // ====================================================

  Serial.println();


  Serial.println(
    dhtValid
      ? "DHT11       : OK"
      : "DHT11       : FAULT"
  );


  Serial.println(
    rtcDetected
      ? "DS3231      : DETECTED"
      : "DS3231      : NOT FOUND"
  );


  Serial.println(
    rtcTimeValid
      ? "RTC TIME    : VALID"
      : "RTC TIME    : INVALID"
  );


  Serial.println(
    ntpSynced
      ? "NTP         : SYNCED"
      : "NTP         : NOT SYNCED"
  );


  if (
    !mqReadable
  ) {

    Serial.println(
      "MQ-135      : DATA UNAVAILABLE"
    );

  }

  else if (
    mqSaturated
  ) {

    Serial.println(
      "MQ-135      : ADC SATURATED"
    );

  }

  else if (
    !MQ_BASELINE_READY
  ) {

    Serial.println(
      "MQ-135      : WARMING / BASELINE NOT READY"
    );

  }

  else {

    Serial.println(
      "MQ-135      : OK"
    );
  }


  Serial.print(
    "WiFi        : "
  );


  if (
    WiFi.status() ==
    WL_CONNECTED
  ) {

    Serial.print(
      "CONNECTED | "
    );

    Serial.println(
      WiFi.localIP()
    );

  }

  else {

    Serial.println(
      "DISCONNECTED"
    );
  }


  // ====================================================
  // SAFETY STATUS
  // ====================================================

  if (
    !temperatureValid ||
    !humidityValid ||
    !rtcTimeValid ||
    !gasValid ||
    !MQ_BASELINE_READY
  ) {
    Serial.println(
      "Freshness   : DATA UNAVAILABLE"
    );

  }

  else {

    Serial.println(
      "Freshness   : sensors ready"
    );
  }
}


// ======================================================
// BACKEND STATUS -> LED
// ======================================================

void updateLedFromBackend(
  String response
) {
  if (
    response.indexOf(
      "Fresh / Normal"
    ) >= 0
  ) {

    showFresh();

    return;
  }


  if (
    response.indexOf(
      "Use Soon"
    ) >= 0
  ) {

    showUseSoon();

    return;
  }


  if (
    response.indexOf(
      "Check Food"
    ) >= 0
  ) {

    showCheckFood();

    return;
  }


  // Keep the current LED state if the backend body has no recognized status.
}


// ======================================================
// READING ID AND PAYLOAD
// ======================================================

String createReadingId() {
  // The backend validates canonical UUID v4 values. Use the ESP32 hardware
  // random generator without adding a library dependency.
  uint8_t bytes[16];
  for (int wordIndex = 0; wordIndex < 4; wordIndex++) {
    uint32_t randomWord = esp_random();
    for (int byteIndex = 0; byteIndex < 4; byteIndex++) {
      bytes[wordIndex * 4 + byteIndex] =
        (randomWord >> (byteIndex * 8)) & 0xFF;
    }
  }

  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;

  char id[37];
  snprintf(
    id, sizeof(id),
    "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
    bytes[0], bytes[1], bytes[2], bytes[3],
    bytes[4], bytes[5], bytes[6], bytes[7],
    bytes[8], bytes[9], bytes[10], bytes[11],
    bytes[12], bytes[13], bytes[14], bytes[15]
  );
  return String(id);
}

String buildReadingPayload(
  const String& readingId,
  const String& readingTimestamp
) {
  // Door sensing is not installed in Phase 6.1.
  const bool doorOpen = false;
  const uint32_t openDurationSeconds = 0;

  String json = "{";
  json += "\"device_reading_id\":\"" + readingId + "\",";
  json += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"timestamp\":\"" + readingTimestamp + "\",";

  json += "\"temperature_c\":";
  json += temperatureValid ? String(temperature, 1) : String("null");
  json += ",\"humidity_pct\":";
  json += humidityValid ? String(humidity, 1) : String("null");
  json += ",\"gas_raw\":";
  json += gasValid ? String(gasRaw) : String("null");
  json += ",\"door_open\":";
  json += doorOpen ? "true" : "false";
  json += ",\"open_duration_seconds\":";
  json += String(openDurationSeconds);

  if (FOOD_ID != nullptr && FOOD_ID[0] != '\0') {
    json += ",\"food_id\":\"";
    json += FOOD_ID;
    json += "\"";
  }

  json += "}";
  return json;
}

void logReading(
  const String& readingId,
  const String& readingTimestamp,
  const String& payload
) {
  Serial.println("[READING]");
  Serial.print("ID: ");
  Serial.println(readingId);
  Serial.print("Timestamp: ");
  Serial.println(readingTimestamp);

  Serial.print("Temperature: ");
  if (temperatureValid) Serial.println(temperature, 1);
  else Serial.println("NULL");

  Serial.print("Humidity: ");
  if (humidityValid) Serial.println(humidity, 1);
  else Serial.println("NULL");

  Serial.print("Gas: ");
  if (gasValid) Serial.println(gasRaw);
  else Serial.println("NULL");

  Serial.print("Food ID: ");
  if (FOOD_ID != nullptr && FOOD_ID[0] != '\0') Serial.println(FOOD_ID);
  else Serial.println("NONE");

  Serial.print("Payload: ");
  Serial.println(payload);
}


// ======================================================
// BACKEND POST
// ======================================================

void sendReadingToBackend(
  const String& payload,
  const String& readingId,
  const String& readingTimestamp
) {
  if (!ENABLE_BACKEND) {
    Serial.println("Backend disabled; reading was not sent.");
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Backend skipped: WiFi unavailable");
    return;
  }

  if (readingTimestamp.length() == 0) {
    Serial.println("Backend skipped: DS3231 timestamp unavailable");
    return;
  }

  String url = "http://" + String(SERVER_IP) + ":5000/api/v1/readings";
  HTTPClient http;
  http.setTimeout(5000);

  if (!http.begin(url)) {
    Serial.println("http.begin failed");
    return;
  }

  http.addHeader("Content-Type", "application/json");
  Serial.print("Sending reading ID: ");
  Serial.println(readingId);
  int statusCode = http.POST(payload);

  Serial.print("HTTP status: ");
  Serial.println(statusCode);

  if (statusCode < 0) {
    Serial.println(http.errorToString(statusCode));
    http.end();
    return;
  }

  String response = http.getString();
  Serial.println(response);

  // Apply only recognized backend states from accepted create/duplicate replies.
  // Errors or unrecognized bodies leave the current LED state unchanged.
  if (statusCode == 200 || statusCode == 201) {
    updateLedFromBackend(response);
  }

  http.end();
}

// ======================================================
// SENSOR CYCLE
// ======================================================

void sensorCycle() {

  // DHT11

  readDHT11();


  // MQ-135

  readMQ135();


  // RTC

  if (
    rtcDetected
  ) {

    DateTime current =
      rtc.now();


    rtcTimeValid =
      validateRTCDateTime(
        current
      );
  }


  // Capture one DS3231 timestamp for logging and the exact reading payload.
  String readingTimestamp = getRTCTimestamp();
  printSensorData(readingTimestamp);

  // Without an RTC timestamp the backend cannot accept this reading. Sensor
  // failures do not stop the cycle; their individual values are sent as null.
  if (readingTimestamp.length() == 0) {
    Serial.println("Reading not sent: DS3231 timestamp unavailable");
    return;
  }

  String readingId = createReadingId();
  String payload = buildReadingPayload(readingId, readingTimestamp);
  logReading(readingId, readingTimestamp, payload);
  sendReadingToBackend(payload, readingId, readingTimestamp);
}


// ======================================================
// SETUP
// ======================================================

void setup() {

  Serial.begin(
    115200
  );


  delay(
    1000
  );


  Serial.println();

  Serial.println(
    "================================"
  );

  Serial.println(
    "          FRESHGUARD"
  );

  Serial.println(
    " DHT11 + DS3231 + MQ-135"
  );

  Serial.println(
    "================================"
  );


  // ====================================================
  // LEDs
  // ====================================================

  pinMode(
    GREEN_LED,
    OUTPUT
  );

  pinMode(
    YELLOW_LED,
    OUTPUT
  );

  pinMode(
    RED_LED,
    OUTPUT
  );


  allLedsOff();


  // ====================================================
  // DHT11
  // ====================================================

  dht.begin();


  delay(
    2000
  );


  if (
    readDHT11()
  ) {

    Serial.println(
      "DHT11: PASS"
    );

  }

  else {

    Serial.println(
      "DHT11: FAIL"
    );
  }


  // ====================================================
  // MQ-135 ADC
  // ====================================================

  Serial.println();

  Serial.println(
    "Starting MQ-135..."
  );


  pinMode(
    MQ135_PIN,
    INPUT
  );


  // ESP32 12-bit ADC:
  // 0 -> 4095

  analogReadResolution(
    12
  );


  analogSetPinAttenuation(
    MQ135_PIN,
    ADC_11db
  );


  int initialGas =
    readMQ135();


  Serial.print(
    "MQ-135 initial raw: "
  );

  Serial.println(
    initialGas
  );


  Serial.println(
    "MQ-135: WARMING / BASELINE NOT READY"
  );


  // ====================================================
  // I2C
  // ====================================================

  Wire.begin(
    I2C_SDA,
    I2C_SCL
  );


  // ====================================================
  // RTC
  // ====================================================

  initializeRTC();


  // ====================================================
  // Wi-Fi
  // ====================================================

  bool wifiConnected =
    connectWiFi();


  // ====================================================
  // NTP
  // ====================================================

  if (
    wifiConnected &&
    rtcDetected
  ) {

    lastNtpAttempt =
      millis();


    syncRTCFromNTP();
  }


  // ====================================================
  // READY
  // ====================================================

  Serial.println();

  Serial.println(
    "================================"
  );

  Serial.println(
    "FreshGuard ready"
  );

  Serial.println(
    "================================"
  );
}


// ======================================================
// LOOP
// ======================================================

void loop() {

  maintainWiFi();

  maintainNTP();


  unsigned long now =
    millis();


  if (
    now -
    lastSensorRead >=
    SENSOR_INTERVAL
  ) {

    lastSensorRead =
      now;


    sensorCycle();
  }
}
