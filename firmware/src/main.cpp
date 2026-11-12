// Waveshare e-Paper ESP32 Driver Board + 5.83" e-Paper (G) 648x480, 4 colors.
//
// Every wake-up: connect to WiFi, ask GitHub for output/display.bin (only downloads it if
// the ETag changed), draw it on the panel, put the panel to sleep, then deep-sleep the ESP32.
//
// display.bin is the raw frame made by render.py: 2 bits per pixel, 77,760 bytes.
 
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
 
#include "secrets.h"      // WIFI_SSID, WIFI_PASSWORD (keep it out of git)
#include "DEV_Config.h"   // Waveshare driver: pins + SPI
#include "EPD_5in83g.h"   // Waveshare driver: the 5.83" (G) panel
 
static const char* IMAGE_URL =
    "https://raw.githubusercontent.com/alvaropicazo/app-epaper/main/output/display.bin";
 
static const size_t FRAME_BYTES = 648UL / 4UL * 480UL;                   // 77,760
static const uint64_t SLEEP_US = 15ULL * 60ULL * 1000000ULL;             // check every 15 min
static const unsigned long WIFI_TIMEOUT_MS = 30000;
static const unsigned long DOWNLOAD_TIMEOUT_MS = 30000;
 
// Survives deep sleep (not a power cycle): lets us skip the download when nothing changed.
RTC_DATA_ATTR static char lastETag[96] = "";
 
enum class FetchResult { NewImage, Unchanged, Failed };
 
static bool connectWiFi() {
    Serial.println("Connecting to WiFi...");
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
 
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_TIMEOUT_MS) {
        delay(250);
        Serial.print(".");
    }
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("\nWiFi connection failed.");
        return false;
    }
    Serial.print("\nWiFi connected, IP: ");
    Serial.println(WiFi.localIP());
    return true;
}
 
// Downloads the frame straight into `frame`. Only returns NewImage for a complete 77,760-byte file.
static FetchResult fetchFrame(uint8_t* frame, String& etagOut) {
    WiFiClientSecure client;
    client.setInsecure();  // TEMPORARY: replace with certificate verification before deployment
 
    HTTPClient http;
    const char* keys[] = {"ETag"};
    http.collectHeaders(keys, 1);
 
    if (!http.begin(client, IMAGE_URL)) {
        Serial.println("Could not start the HTTPS request.");
        return FetchResult::Failed;
    }
    http.setTimeout(20000);
    if (lastETag[0] != '\0') {
        http.addHeader("If-None-Match", lastETag);
    }
 
    int code = http.GET();
    Serial.printf("HTTP %d\n", code);
 
    if (code == HTTP_CODE_NOT_MODIFIED) {
        http.end();
        return FetchResult::Unchanged;
    }
    if (code != HTTP_CODE_OK) {
        Serial.printf("Download failed: %s\n", http.errorToString(code).c_str());
        http.end();
        return FetchResult::Failed;
    }
 
    int len = http.getSize();
    Serial.printf("Content-Length: %d (expected %u)\n", len, (unsigned)FRAME_BYTES);
    if (len != (int)FRAME_BYTES) {
        Serial.println("Unexpected size, ignoring this file.");
        http.end();
        return FetchResult::Failed;
    }
 
    WiFiClient* stream = http.getStreamPtr();
    size_t got = 0;
    unsigned long start = millis();
    while (got < FRAME_BYTES && millis() - start < DOWNLOAD_TIMEOUT_MS) {
        size_t avail = stream->available();
        if (avail > 0) {
            got += stream->readBytes(frame + got, min<size_t>(avail, FRAME_BYTES - got));
        } else if (!http.connected()) {
            break;
        } else {
            delay(1);
        }
    }
 
    etagOut = http.header("ETag");
    http.end();
 
    Serial.printf("Downloaded %u bytes\n", (unsigned)got);
    return got == FRAME_BYTES ? FetchResult::NewImage : FetchResult::Failed;
}
 
static void showFrame(uint8_t* frame) {
    Serial.println("Refreshing the panel (about 20 s, it flashes)...");
    DEV_Module_Init();
    EPD_5IN83G_Init();
    EPD_5IN83G_Display(frame);   // sends all 77,760 bytes and triggers the refresh
    EPD_5IN83G_Sleep();          // never leave the panel powered after a refresh
    DEV_Module_Exit();
    Serial.println("Panel updated and asleep.");
}
 
static void goToSleep() {
    Serial.printf("Sleeping for %llu minutes.\n", SLEEP_US / 60000000ULL);
    Serial.flush();
    esp_sleep_enable_timer_wakeup(SLEEP_US);
    esp_deep_sleep_start();
}
 
void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n=== e-Paper morning display ===");
 
    uint8_t* frame = (uint8_t*)malloc(FRAME_BYTES);
    if (!frame) {
        Serial.println("Not enough memory for the frame buffer.");
        goToSleep();
    }
 
    FetchResult result = FetchResult::Failed;
    String newETag;
    if (connectWiFi()) {
        result = fetchFrame(frame, newETag);
    }
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);   // WiFi off before the panel refresh
 
    if (result == FetchResult::NewImage) {
        showFrame(frame);
        // Remember the ETag only after the panel was drawn successfully.
        strlcpy(lastETag, newETag.c_str(), sizeof(lastETag));
    } else if (result == FetchResult::Unchanged) {
        Serial.println("Image unchanged: the panel keeps showing it.");
    } else {
        Serial.println("No new image this time; will try again after sleeping.");
    }
 
    free(frame);
    goToSleep();
}
 
void loop() {}
 