
# Installation and Setup

This document describes how to set up the current ePaper project on a Mac and deploy it to an ESP32.

## 1. Clone the repository

```bash
git clone https://github.com/alvaropicazo/app-epaper.git
cd app-epaper
```

## 2. Set up Python

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Test the local renderer

Generate a local preview:

```bash
python render.py --open
```

This uses simulated sunny weather by default and does not require an internet connection.

Try other weather conditions:

```bash
python render.py --weather rain --open
python render.py --weather snow --open
```

Preview a particular date:

```bash
python render.py --date 2026-12-25 --open
```

See [RENDERING.md](RENDERING.md) for all local preview options.

## 4. Configure Wi-Fi credentials

The firmware needs your Wi-Fi credentials to download the daily display images.

Create:

```text
firmware/src/secrets.h
```

Add:

```cpp
#pragma once

#define WIFI_SSID "your-wifi-name"
#define WIFI_PASSWORD "your-wifi-password"
```

Do not commit this file or share your credentials.

## 5. Build the firmware

Install PlatformIO if it is not already installed.

From the repository root:

```bash
cd firmware
pio run
```

This compiles the firmware without requiring the ESP32 to be connected.

## 6. Upload to the ESP32

Connect the ESP32 to your computer over USB.

Upload the firmware:

```bash
pio run -t upload
```

If PlatformIO does not detect the correct serial port automatically, specify it:

```bash
pio run -t upload --upload-port /dev/cu.usbmodem5ABA0263181
```

The serial monitor can be opened with:

```bash
pio device monitor -b 115200
```

The firmware uses LittleFS to store the downloaded display frames. It downloads the four production `.bin` files itself.

A filesystem upload is not normally required. Avoid running `pio run -t uploadfs` unless you intentionally need to replace the local filesystem contents.

## 7. Enable GitHub Actions

The repository workflow is located at:

```text
.github/workflows/render.yml
```

The workflow needs permission to write repository contents so it can commit generated display frames.

Check the repository's GitHub settings:

1. Open the repository on GitHub.
2. Go to **Settings → Actions → General**.
3. Find **Workflow permissions**.
4. Enable **Read and write permissions**.
5. Save the setting.

The workflow runs automatically at approximately 3:17 AM Chicago time. You can also start it manually from **Actions → Generate ePaper Display → Run workflow**.

## 8. Verify generated files

After a successful workflow run, the `output/` directory should contain:

```text
output/
├── morning.png
├── morning.bin
├── afternoon.png
├── afternoon.bin
├── evening.png
├── evening.bin
├── night.png
└── night.bin
```

Each `.bin` file should be 77,760 bytes.

The ESP32 downloads these files from the repository and stores them in LittleFS.

## Daily operation

Once the firmware is uploaded and the ESP32 has Wi-Fi access, it runs independently.

| Chicago time | Activity |
|---|---|
| 3:17 AM | GitHub Actions generates and publishes the daily images |
| 5:45 AM | ESP32 starts checking for and downloading the new images |
| 6:00 AM | Morning display |
| 11:00 AM | Afternoon display |
| 4:00 PM | Evening display |
| 9:00 PM | Night display |

GitHub scheduled jobs can start later than their configured time. The delay between generation and the ESP32's download attempt gives the workflow time to finish.

The computer does not need to remain on. The ESP32 only needs power and Wi-Fi.
