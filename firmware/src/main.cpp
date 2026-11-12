
// Waveshare e-Paper ESP32 Driver Board + 5.83" (G) 648x480, 4-colour panel.
//
// Daily flow:
//   * Wake at 05:45 Chicago time and download/cache all four raw frames.
//   * Retry incomplete downloads every 10 minutes.
//   * Refresh only at 06:00, 11:00, 16:00, and 21:00 Chicago time.
//   * Deep-sleep until the next cache retry or display transition.
//   * If Wi-Fi/download fails, keep using the last complete cached frame set.
//
// Required firmware files/libraries are the same Waveshare driver files already
// used by this project. Keep secrets.h out of git; it must define WIFI_SSID
// and WIFI_PASSWORD.

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

static const size_t FRAME_BYTES = 648UL / 4UL * 480UL;
static const unsigned long WIFI_TIMEOUT_MS = 25000;
static const unsigned long HTTP_TIMEOUT_MS = 30000;
static const char* TZ_INFO = "CST6CDT,M3.2.0,M11.1.0";

static const int DOWNLOAD_HOUR = 5;
static const int DOWNLOAD_MINUTE = 45;
static const int RETRY_MINUTES = 10;

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

static const int PERIOD_COUNT =
    sizeof(PERIODS) / sizeof(PERIODS[0]);

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
    configTzTime(
        TZ_INFO,
        "pool.ntp.org",
        "time.nist.gov",
        "time.google.com"
    );

    return getLocalTime(&localTime, 15000);
}

static String dateString(const struct tm& t) {
    char buffer[11];
    strftime(buffer, sizeof(buffer), "%Y-%m-%d", &t);
    return String(buffer);
}

static int currentPeriod(const struct tm& t) {
    const int minutes = t.tm_hour * 60 + t.tm_min;

    if (minutes >= 6 * 60 && minutes < 11 * 60) return 0;
    if (minutes >= 11 * 60 && minutes < 16 * 60) return 1;
    if (minutes >= 16 * 60 && minutes < 21 * 60) return 2;

    return 3;
}

static bool cacheIsForToday(const String& today) {
    File file = LittleFS.open("/cache_date.txt", "r");

    if (!file) return false;

    String saved = file.readString();
    file.close();
    saved.trim();

    return saved == today;
}

// Download one frame into a staging file.
// Do not replace the active cached frame here.
// The four files are promoted only after all downloads succeed.
static bool downloadFrame(const PeriodFile& period) {
    const String url = String(BASE_URL) + period.name + ".bin";

    const String temporary =
        String("/staged_") + period.name + ".bin";

    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;

    if (!http.begin(client, url)) {
        Serial.printf("Could not start request for %s\n", period.name);
        return false;
    }

    http.setTimeout(HTTP_TIMEOUT_MS);

    const int status = http.GET();

    if (status != HTTP_CODE_OK) {
        Serial.printf(
            "Download %s failed: HTTP %d\n",
            period.name,
            status
        );

        http.end();
        return false;
    }

    const int length = http.getSize();

    if (length != static_cast<int>(FRAME_BYTES)) {
        Serial.printf(
            "Wrong frame size for %s: %d\n",
            period.name,
            length
        );

        http.end();
        return false;
    }

    File output = LittleFS.open(temporary, "w");

    if (!output) {
        Serial.printf("Could not create staging file for %s\n",
                      period.name);
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
            const size_t wanted = min(
                static_cast<size_t>(available),
                sizeof(buffer)
            );

            const int count = stream->readBytes(buffer, wanted);

            if (count > 0) {
                const size_t written =
                    output.write(buffer, static_cast<size_t>(count));

                received += written;

                if (written != static_cast<size_t>(count)) {
                    Serial.printf(
                        "Filesystem write failed for %s\n",
                        period.name
                    );
                    break;
                }
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
        Serial.printf(
            "Incomplete %s frame: %u bytes\n",
            period.name,
            static_cast<unsigned>(received)
        );

        LittleFS.remove(temporary);
        return false;
    }

    Serial.printf(
        "Staged %s (%u bytes)\n",
        period.name,
        static_cast<unsigned>(received)
    );

    return true;
}

// Download all four frames before activating the new daily set.
static bool downloadAllFrames(const String& today) {
    Serial.println("Downloading all four daily frames...");

    // First download and validate every frame.
    for (int i = 0; i < PERIOD_COUNT; ++i) {
        if (!downloadFrame(PERIODS[i])) {
            Serial.println(
                "Frame set incomplete; keeping previous cache active."
            );

            for (int j = 0; j < PERIOD_COUNT; ++j) {
                const String staged =
                    String("/staged_") + PERIODS[j].name + ".bin";

                LittleFS.remove(staged);
            }

            return false;
        }
    }

    // Back up the previous active files before promoting the new set.
    bool backedUp[PERIOD_COUNT] = {false};
    bool promoted[PERIOD_COUNT] = {false};

    for (int i = 0; i < PERIOD_COUNT; ++i) {
        const String backup =
            String("/backup_") + PERIODS[i].name + ".bin";

        LittleFS.remove(backup);

        if (LittleFS.exists(PERIODS[i].filename)) {
            if (!LittleFS.rename(PERIODS[i].filename, backup)) {
                Serial.println("Could not back up previous frame set.");

                for (int j = 0; j < PERIOD_COUNT; ++j) {
                    if (backedUp[j]) {
                        const String oldBackup =
                            String("/backup_") + PERIODS[j].name + ".bin";

                        LittleFS.rename(
                            oldBackup,
                            PERIODS[j].filename
                        );
                    }
                }

                return false;
            }

            backedUp[i] = true;
        }
    }

    // Promote the new complete set.
    for (int i = 0; i < PERIOD_COUNT; ++i) {
        const String staged =
            String("/staged_") + PERIODS[i].name + ".bin";

        if (!LittleFS.rename(staged, PERIODS[i].filename)) {
            Serial.println("Could not promote new frame set; restoring backup.");

            for (int j = 0; j < PERIOD_COUNT; ++j) {
                if (promoted[j]) {
                    LittleFS.remove(PERIODS[j].filename);
                }

                if (backedUp[j]) {
                    const String backup =
                        String("/backup_") + PERIODS[j].name + ".bin";

                    LittleFS.rename(backup, PERIODS[j].filename);
                }
            }

            for (int j = 0; j < PERIOD_COUNT; ++j) {
                const String remaining =
                    String("/staged_") + PERIODS[j].name + ".bin";

                LittleFS.remove(remaining);
            }

            return false;
        }

        promoted[i] = true;
    }

    // All four files are active. Remove the old backups.
    for (int i = 0; i < PERIOD_COUNT; ++i) {
        const String backup =
            String("/backup_") + PERIODS[i].name + ".bin";

        LittleFS.remove(backup);
    }

    // Write the date marker only after all four files are promoted.
    File marker = LittleFS.open("/cache_date.tmp", "w");

    if (!marker) {
        Serial.println("Could not write cache date marker.");
        return false;
    }

    marker.print(today);
    marker.flush();
    marker.close();

    LittleFS.remove("/cache_date.txt");

    if (!LittleFS.rename("/cache_date.tmp", "/cache_date.txt")) {
        LittleFS.remove("/cache_date.tmp");
        Serial.println("Could not activate cache date marker.");
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

    LittleFS.rename(
        "/last_shown.tmp",
        "/last_shown.txt"
    );
}

static bool showPeriodIfNeeded(int period, const String& today) {
    const String key =
        today + "-" + PERIODS[period].name;

    const String previous = lastShownKey();

    if (previous == key) {
        Serial.println("This period is already on screen; no refresh needed.");
        return true;
    }

    uint8_t* frame =
        static_cast<uint8_t*>(malloc(FRAME_BYTES));

    if (!frame) {
        Serial.println("Not enough RAM for a panel frame.");
        return false;
    }

    if (!loadFrame(period, frame)) {
        Serial.printf(
            "No valid cached frame for %s.\n",
            PERIODS[period].name
        );

        free(frame);
        return false;
    }

    Serial.printf(
        "Refreshing panel for %s...\n",
        PERIODS[period].name
    );

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

// Return the next local wake event.
// mktime applies Chicago daylight-saving rules.
static time_t nextWakeTime(
    const struct tm& nowLocal,
    bool retryCache
) {
    const int events[][2] = {
        {5, 45},
        {6, 0},
        {11, 0},
        {16, 0},
        {21, 0}
    };

    struct tm nowCopy = nowLocal;
    const time_t nowEpoch = mktime(&nowCopy);

    time_t nextEvent = 0;

    for (int i = 0; i < 5; ++i) {
        struct tm candidate = nowLocal;

        candidate.tm_hour = events[i][0];
        candidate.tm_min = events[i][1];
        candidate.tm_sec = 0;

        const time_t candidateEpoch = mktime(&candidate);

        if (candidateEpoch > nowEpoch + 2) {
            nextEvent = candidateEpoch;
            break;
        }
    }

    if (nextEvent == 0) {
        struct tm tomorrow = nowLocal;

        tomorrow.tm_mday += 1;
        tomorrow.tm_hour = DOWNLOAD_HOUR;
        tomorrow.tm_min = DOWNLOAD_MINUTE;
        tomorrow.tm_sec = 0;

        nextEvent = mktime(&tomorrow);
    }

    const int minuteOfDay =
        nowLocal.tm_hour * 60 + nowLocal.tm_min;

    // Retry failed daily downloads every 10 minutes after 05:45.
    if (retryCache && minuteOfDay >= 345) {
        const time_t retryTime =
            nowEpoch + RETRY_MINUTES * 60;

        if (retryTime < nextEvent) {
            nextEvent = retryTime;
        }
    }

    return nextEvent;
}

static void sleepUntilNextEvent(
    const struct tm& nowLocal,
    bool retryCache
) {
    struct tm nowCopy = nowLocal;
    const time_t nowEpoch = mktime(&nowCopy);

    const time_t wakeEpoch =
        nextWakeTime(nowLocal, retryCache);

    uint64_t seconds =
        static_cast<uint64_t>(difftime(wakeEpoch, nowEpoch));

    if (seconds < 20) seconds = 20;

    Serial.printf(
        "Deep-sleeping for %llu seconds.\n",
        static_cast<unsigned long long>(seconds)
    );

    Serial.flush();

    esp_sleep_enable_timer_wakeup(
        seconds * 1000000ULL
    );

    esp_deep_sleep_start();
}

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println("\n=== ePaper four-period display ===");

    if (!LittleFS.begin(false)) {
        Serial.println(
            "LittleFS mount failed; refusing to format cached frames."
        );

        delay(1000);

        esp_sleep_enable_timer_wakeup(
            15ULL * 60ULL * 1000000ULL
        );

        esp_deep_sleep_start();
    }

    const bool wifiConnected = connectWiFi();

    struct tm localTime;

    bool haveTime =
        wifiConnected && getChicagoTime(localTime);

    if (!haveTime) {
        // Try the RTC time retained over deep sleep.
        haveTime = getLocalTime(&localTime, 1000);
    }

    if (!haveTime) {
        Serial.println(
            "Local time unavailable; retrying in 15 minutes."
        );

        WiFi.disconnect(true);
        WiFi.mode(WIFI_OFF);

        Serial.flush();

        esp_sleep_enable_timer_wakeup(
            15ULL * 60ULL * 1000000ULL
        );

        esp_deep_sleep_start();
    }

    const String today = dateString(localTime);

    const int minuteOfDay =
        localTime.tm_hour * 60 + localTime.tm_min;

    Serial.printf(
        "Chicago local time: %04d-%02d-%02d %02d:%02d:%02d\n",
        localTime.tm_year + 1900,
        localTime.tm_mon + 1,
        localTime.tm_mday,
        localTime.tm_hour,
        localTime.tm_min,
        localTime.tm_sec
    );

    bool cacheUpdated = false;

    const int downloadStart =
        DOWNLOAD_HOUR * 60 + DOWNLOAD_MINUTE;

    if (wifiConnected &&
        minuteOfDay >= downloadStart &&
        !cacheIsForToday(today)) {

        cacheUpdated = downloadAllFrames(today);
    }

    const bool cacheNeedsRetry =
        !cacheIsForToday(today) &&
        minuteOfDay >= downloadStart;

    // If today's frames have just been downloaded, force the current
    // period to refresh with the new images, even if it was shown earlier.
    if (cacheUpdated) {
        saveLastShownKey("");
    }

    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);

    const int period = currentPeriod(localTime);

    showPeriodIfNeeded(period, today);

    sleepUntilNextEvent(localTime, cacheNeedsRetry);
}

void loop() {
    // The device uses deep sleep between scheduled events.
}
