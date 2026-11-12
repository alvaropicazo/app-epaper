# Manual install notes — four daily ePaper periods

This bundle contains the complete replacement/new source files for the four-period
forecast workflow.

## Files in this bundle

- `render_periods.py` — **new**. Reuses the current `render.py` design and creates
  `morning`, `afternoon`, `evening`, and `night` PNG + 77,760-byte BIN files.
- `.github/workflows/render.yml` — **replace** the existing workflow. Runs at
  approximately 5:17 AM Chicago time and publishes all four binary frames.
- `firmware/src/main.cpp` — **replace** the existing ESP32 sketch. Caches all four
  frames in LittleFS, switches only at 6 AM / 11 AM / 4 PM / 9 PM Chicago time,
  and sleeps until the next cache/display event.

No changes to `render.py`, `panel_export.py`, `requirements.txt`, or the existing
Waveshare driver files are required.

## Install

1. Add `render_periods.py` to the repository root (next to `render.py`).
2. Replace `.github/workflows/render.yml` with the file in this bundle.
3. Replace `firmware/src/main.cpp` with the file in this bundle.
4. Keep `firmware/src/secrets.h` local and untracked. It must define `WIFI_SSID`
   and `WIFI_PASSWORD`, as in the existing sketch.
5. Confirm the GitHub Actions workflow has permission to write repository contents.
6. Run the workflow once with **Actions → Generate ePaper Display → Run workflow**.
   It should create these files in `output/`:
   `morning.bin`, `afternoon.bin`, `evening.bin`, `night.bin`, and matching PNGs.

## Important hardware notes

- Four raw frames occupy about 304 KiB in LittleFS (plus filesystem overhead).
  Confirm the ESP32 PlatformIO partition layout has enough filesystem space.
- The sketch uses the same Waveshare `EPD_5IN83G` driver calls as the existing
  firmware. Compile and test against the exact driver library/board before flashing.
- TLS certificate verification is still disabled in the HTTPS client, matching
  the existing sketch's approach. For a production deployment, pin/verify the
  GitHub certificate.
- The ESP32 wakes at 5:05 AM to cache the day's four frames. It does not refresh
  the panel at that time; it waits until the 6:00 AM morning boundary.
- If the daily download fails, the previous cached files remain available and
  the date marker is not advanced. The next wake retries.
- The existing `output/display.bin` is still generated for backward compatibility.
