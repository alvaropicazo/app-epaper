#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <vector>
#include "secrets.h"

// Public image hosted in your GitHub repository
const char* IMAGE_URL =
    "https://raw.githubusercontent.com/alvaropicazo/app-epaper/main/output/display.png";

// Check GitHub every 15 minutes
const unsigned long CHECK_INTERVAL = 15UL * 60UL * 1000UL;

// Wi-Fi connection timeout
const unsigned long WIFI_TIMEOUT = 30000;

// Last successful check
unsigned long lastCheck = 0;

// ETag returned by GitHub
String lastETag = "";

// Latest downloaded image (held in RAM)
std::vector<uint8_t> imageBuffer;

// Temporary HTTPS configuration.
// We will replace this with certificate verification before deployment.
void configureTLS(WiFiClientSecure& client) {
    client.setInsecure();
}

bool connectWiFi() {
    if (WiFi.status() == WL_CONNECTED) {
        return true;
    }

    Serial.println("Connecting to WiFi...");

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long start = millis();

    while (WiFi.status() != WL_CONNECTED &&
           millis() - start < WIFI_TIMEOUT) {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected!");
        Serial.print("IP address: ");
        Serial.println(WiFi.localIP());
        return true;
    }

    Serial.println("\nWiFi connection failed.");
    return false;
}

bool validPNG(const std::vector<uint8_t>& data) {
    const uint8_t signature[] = {
        0x89, 0x50, 0x4E, 0x47,
        0x0D, 0x0A, 0x1A, 0x0A
    };

    if (data.size() < 24) {
        return false;
    }

    for (int i = 0; i < 8; i++) {
        if (data[i] != signature[i]) {
            return false;
        }
    }

    // PNG IHDR dimensions
    uint32_t width =
        ((uint32_t)data[16] << 24) |
        ((uint32_t)data[17] << 16) |
        ((uint32_t)data[18] << 8) |
        data[19];

    uint32_t height =
        ((uint32_t)data[20] << 24) |
        ((uint32_t)data[21] << 16) |
        ((uint32_t)data[22] << 8) |
        data[23];

    Serial.printf("PNG dimensions: %lu x %lu\n",
                  (unsigned long)width,
                  (unsigned long)height);

    return width == 648 && height == 480;
}

bool downloadImage() {
    if (!connectWiFi()) {
        return false;
    }

    WiFiClientSecure client;
    configureTLS(client);

    HTTPClient http;

    const char* headerKeys[] = {"ETag"};
    http.collectHeaders(headerKeys, 1);

    Serial.println("\nChecking GitHub for image updates...");

    if (!http.begin(client, IMAGE_URL)) {
        Serial.println("Unable to initialize HTTPS.");
        return false;
    }

    http.setTimeout(20000);

    // Ask GitHub to send the image only if it has changed.
    if (lastETag.length() > 0) {
        http.addHeader("If-None-Match", lastETag);
    }

    int httpCode = http.GET();

    Serial.printf("HTTP response: %d\n", httpCode);

    if (httpCode == HTTP_CODE_NOT_MODIFIED) {
        Serial.println("Image unchanged. No download needed.");
        http.end();
        return true;
    }

    if (httpCode != HTTP_CODE_OK) {
        Serial.printf("Download failed: %s\n",
                      http.errorToString(httpCode).c_str());
        http.end();
        return false;
    }

    int imageSize = http.getSize();

    Serial.printf("Image size: %d bytes\n", imageSize);

    if (imageSize <= 0 || imageSize > 500000) {
        Serial.println("Invalid or unexpected image size.");
        http.end();
        return false;
    }

    std::vector<uint8_t> newImage;
    newImage.reserve(imageSize);

    WiFiClient* stream = http.getStreamPtr();

    unsigned long start = millis();

    while (newImage.size() < (size_t)imageSize &&
           millis() - start < 30000) {

        if (stream->available()) {
            uint8_t buffer[1024];

            size_t remaining = imageSize - newImage.size();
            size_t toRead = min(sizeof(buffer), remaining);

            int bytesRead = stream->readBytes(buffer, toRead);

            if (bytesRead > 0) {
                newImage.insert(
                    newImage.end(),
                    buffer,
                    buffer + bytesRead
                );
            }
        } else if (!http.connected()) {
            break;
        }

        delay(1);
    }

    String newETag = http.header("ETag");

    http.end();

    Serial.printf("Downloaded: %u bytes\n",
                  (unsigned int)newImage.size());

    if (newImage.size() != (size_t)imageSize) {
        Serial.println("Incomplete download.");
        return false;
    }

    if (!validPNG(newImage)) {
        Serial.println("Invalid PNG or incorrect dimensions.");
        return false;
    }

    imageBuffer = std::move(newImage);

    // Note: capture the ETag before http.end() in production.
    // This is handled below in the corrected implementation.

    if (newETag.length() > 0) {
        lastETag = newETag;
    } else {
        lastETag = "";
    }

    Serial.println("New image downloaded and validated!");
    Serial.printf("Image stored in RAM: %u bytes\n",
                  (unsigned int)imageBuffer.size());

    return true;
}

void setup() {
    Serial.begin(115200);
    delay(1500);

    Serial.println("\n================================");
    Serial.println("Waveshare ESP32 ePaper Controller");
    Serial.println("Automatic GitHub image updater");
    Serial.println("================================");

    connectWiFi();

    // Download the latest image immediately at startup.
    downloadImage();

    lastCheck = millis();
}

void loop() {
    if (millis() - lastCheck >= CHECK_INTERVAL) {
        Serial.println("\nScheduled image check");

        if (WiFi.status() != WL_CONNECTED) {
            connectWiFi();
        }

        downloadImage();

        lastCheck = millis();
    }

    delay(1000);
}
