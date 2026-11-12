// Waveshare e-Paper ESP32 Driver Board + 5.83" (G) 648x480, 4-colour panel.
//
// Daily flow:
//   * Wake at 05:05 Chicago time and download/cache all four raw frames.
//   * Refresh only at 06:00, 11:00, 16:00, and 21:00 Chicago time.
//   * Deep-sleep until the next cache or display transition.
//   * If Wi-Fi/download fails, keep using the last complete cached frame set.
//
// Required firmware files/libraries are the same Waveshare driver files already
// used by this project. Keep secrets.h out of git; it must define WIFI_SSID and
// WIFI_PASSWORD.

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <time.h>

#include "secrets.h"
#include "DEV_Config.h"
#include "EPD_5in83g.h"

static const char* BASE_URL =
    "https://raw.githubusercontent.com/alvaropicazo/app-epaper/main/output/";

static const size_t FRAME_BYTES = 648UL / 4UL * 480UL;  // 77,760 bytes
static const unsigned long WIFI_TIMEOUT_MS = 25000;
static const unsigned long HTTP_TIMEOUT_MS = 30000;
static const char* TZ_INFO = "CST6CDT,M3.2.0,M11.1.0";

struct PeriodFile {
    const char* name;
    const char* filename;
};

static const PeriodFile PERIODS[] = {
    {"morning", "/morning.bin"},
    {"afternoon", "/afternoon.bin"},
    {"evening", "/evening.bin"},
    {"night", "/night.bin"},
};
static const int PERIOD_COUNT = sizeof(PERIODS) / sizeof(PERIODS[0]);

static bool connectWiFi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to Wi-Fi");
    const unsigned long started = millis();
    while (WiFi.status() != WL_CONNECTED &&
           millis() - started < WIFI_TIMEOUT_MS) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Wi-Fi connection failed.");
        return false;
    }
    Serial.print("Connected: ");
    Serial.println(WiFi.localIP());
    return true;
}

static bool getChicagoTime(struct tm& localTime) {
    configTzTime(TZ_INFO, "pool.ntp.org", "time.nist.gov", "time.google.com");
    return getLocalTime(&localTime, 15000);
}

static String dateString(const struct tm& t) {
    char buffer[11];
    strftime(buffer, sizeof(buffer), "%Y-%m-%d", &t);
    return String(buffer);
}

static int currentPeriod(const struct tm& t) {
    const int minutes = t.tm_hour * 60 + t.tm_min;
    if (minutes >= 6 * 60 && minutes < 11 * 60) return 0;  // morning
    if (minutes >= 11 * 60 && minutes < 16 * 60) return 1; // afternoon
    if (minutes >= 16 * 60 && minutes < 21 * 60) return 2; // evening
    return 3;                                               // night
}

static bool cacheIsForToday(const String& today) {
    File file = LittleFS.open("/cache_date.txt", "r");
    if (!file) return false;
    String saved = file.readString();
    file.close();
    saved.trim();
    return saved == today;
}

// Stream one exact-size raw panel frame into a temporary LittleFS file.
static bool downloadFrame(const PeriodFile& period) {
    const String url = String(BASE_URL) + period.name + ".bin";
    // Stage every download separately so a failed later download does not
    // overwrite any member of the previously complete cache set.
    const String temporary = String("/staged_") + period.name + ".bin";

    WiFiClientSecure client;
    // Kept consistent with the original sketch. For production, pin/verify the
    // GitHub certificate rather than disabling TLS certificate verification.
    client.setInsecure();

    HTTPClient http;
    if (!http.begin(client, url)) {
        Serial.printf("Could not start request for %s\n", period.name);
        return false;
    }
    http.setTimeout(HTTP_TIMEOUT_MS);
    const int status = http.GET();
    if (status != HTTP_CODE_OK) {
        Serial.printf("Download %s failed: HTTP %d\n", period.name, status);
        http.end();
        return false;
    }

    const int length = http.getSize();
    if (length != static_cast<int>(FRAME_BYTES)) {
        Serial.printf("Wrong frame size for %s: %d\n", period.name, length);
        http.end();
        return false;
    }

    File output = LittleFS.open(temporary, "w");
    if (!output) {
        http.end();
        return false;
    }

    WiFiClient* stream = http.getStreamPtr();
    uint8_t buffer[1024];
    size_t received = 0;
    const unsigned long started = millis();

    while (received < FRAME_BYTES &&
           millis() - started < HTTP_TIMEOUT_MS) {
        const int available = stream->available();
        if (available > 0) {
            const size_t wanted = min(static_cast<size_t>(available),
                                      sizeof(buffer));
            const int count = stream->readBytes(buffer, wanted);
            if (count > 0) {
                output.write(buffer, count);
                received += count;
            }
        } else if (!http.connected()) {
            break;
        } else {
            delay(2);
        }
    }

    output.flush();
    output.close();
    http.end();

    if (received != FRAME_BYTES) {
        Serial.printf("Incomplete %s frame: %u bytes\n",
                      period.name, static_cast<unsigned>(received));
        LittleFS.remove(temporary);
        return false;
    }

    LittleFS.remove(period.filename);
    if (!LittleFS.rename(temporary.c_str(), period.filename)) {
        LittleFS.remove(temporary);
        return false;
    }
    Serial.printf("Cached %s (%u bytes)\n",
                  period.name, static_cast<unsigned>(received));
    return true;
}

static bool downloadAllFrames(const String& today) {
    Serial.println("Downloading all four daily frames...");
    // First stage all four files. A failed download leaves the active cache untouched.
    for (int i = 0; i < PERIOD_COUNT; ++i) {
        if (!downloadFrame(PERIODS[i])) {
            Serial.println("Frame set incomplete; keeping the previous cache active.");
            return false;
        }
    }

    // Promote the complete staged set only after all four downloads validate.
    for (int i = 0; i < PERIOD_COUNT; ++i) {
        const String staged = String("/staged_") + PERIODS[i].name + ".bin";
        LittleFS.remove(PERIODS[i].filename);
        if (!LittleFS.rename(staged.c_str(), PERIODS[i].filename)) {
            Serial.println("Could not promote the staged frame set.");
            return false;
        }
    }

    File marker = LittleFS.open("/cache_date.tmp", "w");
    if (!marker) return false;
    marker.print(today);
    marker.flush();
    marker.close();
    LittleFS.remove("/cache_date.txt");
    if (!LittleFS.rename("/cache_date.tmp", "/cache_date.txt")) {
        LittleFS.remove("/cache_date.tmp");
        return false;
    }
    Serial.println("All four frames cached for today.");
    return true;
}

static bool loadFrame(int period, uint8_t* frame) {
    File file = LittleFS.open(PERIODS[period].filename, "r");
    if (!file || file.size() != FRAME_BYTES) {
        if (file) file.close();
        return false;
    }
    const size_t count = file.read(frame, FRAME_BYTES);
    file.close();
    return count == FRAME_BYTES;
}

static String lastShownKey() {
    File file = LittleFS.open("/last_shown.txt", "r");
    if (!file) return "";
    String key = file.readString();
    file.close();
    key.trim();
    return key;
}

static void saveLastShownKey(const String& key) {
    File file = LittleFS.open("/last_shown.tmp", "w");
    if (!file) return;
    file.print(key);
    file.flush();
    file.close();
    LittleFS.remove("/last_shown.txt");
    LittleFS.rename("/last_shown.tmp", "/last_shown.txt");
}

static bool showPeriodIfNeeded(int period, const String& today) {
    // At 05:05 we refresh the cache but deliberately keep showing the night
    // frame until the 06:00 morning transition.
    const String key = today + "-" + PERIODS[period].name;
    const String previous = lastShownKey();
    if (previous.endsWith(String("-") + PERIODS[period].name) &&
        period == 3) {
        Serial.println("Night period is already on screen; no refresh needed.");
        return true;
    }
    if (previous == key) {
        Serial.println("This period is already on screen; no refresh needed.");
        return true;
    }

    uint8_t* frame = static_cast<uint8_t*>(malloc(FRAME_BYTES));
    if (!frame) {
        Serial.println("Not enough RAM for a panel frame.");
        return false;
    }
    if (!loadFrame(period, frame)) {
        Serial.printf("No valid cached frame for %s.\n", PERIODS[period].name);
        free(frame);
        return false;
    }

    Serial.printf("Refreshing panel for %s...\n", PERIODS[period].name);
    DEV_Module_Init();
    EPD_5IN83G_Init();
    EPD_5IN83G_Display(frame);
    EPD_5IN83G_Sleep();
    DEV_Module_Exit();
    free(frame);
    saveLastShownKey(key);
    Serial.println("Panel updated.");
    return true;
}

// Return the next local wake event: 05:05 cache refresh, then 06/11/16/21
// display transitions. mktime applies the Chicago daylight-saving rules.
static time_t nextWakeTime(const struct tm& nowLocal) {
    const int events[][2] = {
        {5, 5}, {6, 0}, {11, 0}, {16, 0}, {21, 0}
    };
    const time_t nowEpoch = mktime(const_cast<struct tm*>(&nowLocal));

    for (int i = 0; i < 5; ++i) {
        struct tm candidate = nowLocal;
        candidate.tm_hour = events[i][0];
        candidate.tm_min = events[i][1];
        candidate.tm_sec = 0;
        const time_t candidateEpoch = mktime(&candidate);
        if (candidateEpoch > nowEpoch + 2) return candidateEpoch;
    }

    struct tm tomorrow = nowLocal;
    tomorrow.tm_mday += 1;
    tomorrow.tm_hour = 5;
    tomorrow.tm_min = 5;
    tomorrow.tm_sec = 0;
    return mktime(&tomorrow);
}

static void sleepUntilNextEvent(const struct tm& nowLocal) {
    const time_t nowEpoch = mktime(const_cast<struct tm*>(&nowLocal));
    const time_t wakeEpoch = nextWakeTime(nowLocal);
    uint64_t seconds = static_cast<uint64_t>(difftime(wakeEpoch, nowEpoch));
    if (seconds < 20) seconds = 20;
    Serial.printf("Deep-sleeping for %llu seconds.\n",
                  static_cast<unsigned long long>(seconds));
    Serial.flush();
    esp_sleep_enable_timer_wakeup(seconds * 1000000ULL);
    esp_deep_sleep_start();
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== ePaper four-period display ===");

    if (!LittleFS.begin(false)) {
        Serial.println("LittleFS mount failed; refusing to format cached frames.");
        delay(1000);
        esp_sleep_enable_timer_wakeup(15ULL * 60ULL * 1000000ULL);
        esp_deep_sleep_start();
    }

    const bool wifiConnected = connectWiFi();
    struct tm localTime;
    bool haveTime = wifiConnected && getChicagoTime(localTime);

    if (!haveTime) {
        // The ESP32's RTC may retain time over deep sleep. Try it before giving up.
        haveTime = getLocalTime(&localTime, 1000);
    }

    if (!haveTime) {
        Serial.println("Local time unavailable; retrying in 15 minutes.");
        WiFi.disconnect(true);
        WiFi.mode(WIFI_OFF);
        Serial.flush();
        esp_sleep_enable_timer_wakeup(15ULL * 60ULL * 1000000ULL);
        esp_deep_sleep_start();
    }

    const String today = dateString(localTime);
    const int minuteOfDay = localTime.tm_hour * 60 + localTime.tm_min;

    if (wifiConnected && minuteOfDay >= (5 * 60 + 5) &&
        !cacheIsForToday(today)) {
        downloadAllFrames(today);
    }

    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);

    const int period = currentPeriod(localTime);
    showPeriodIfNeeded(period, today);
    sleepUntilNextEvent(localTime);
}

void loop() {}
