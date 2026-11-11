
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "secrets.h"

const char* IMAGE_URL =
  "https://raw.githubusercontent.com/alvaropicazo/app-epaper/main/output/display.png";

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("\nConnecting to WiFi...");

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println("\nWiFi connected!");

    WiFiClientSecure client;

    // Temporary testing only.
    // We will configure certificate verification in production.
    client.setInsecure();

    HTTPClient http;

    Serial.println("Downloading image from GitHub...");

    if (http.begin(client, IMAGE_URL)) {
        int httpCode = http.GET();

        Serial.printf("HTTP response: %d\n", httpCode);

        if (httpCode == HTTP_CODE_OK) {
            int imageSize = http.getSize();

            Serial.printf("Image size: %d bytes\n", imageSize);

            WiFiClient* stream = http.getStreamPtr();

            uint8_t buffer[1024];
            int totalBytes = 0;

            while (http.connected() &&
                   (imageSize < 0 || totalBytes < imageSize)) {

                size_t available = stream->available();

                if (available) {
                    int bytesRead = stream->readBytes(
                        buffer,
                        min((size_t)sizeof(buffer), available)
                    );

                    totalBytes += bytesRead;
                }

                delay(1);
            }

            Serial.printf("Downloaded: %d bytes\n", totalBytes);
        } else {
            Serial.printf("Download failed: %s\n",
                          http.errorToString(httpCode).c_str());
        }

        http.end();
    } else {
        Serial.println("Unable to connect to GitHub.");
    }
}

void loop() {
    delay(10000);
}
