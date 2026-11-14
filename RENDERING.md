
# Local Display Preview and Rendering (`render.py`)

`render.py` is the local development and preview tool for the e-paper display.

It lets you render the display for a selected date, simulate different weather conditions, and preview special occasions without connecting to the internet or uploading anything to the ESP32.

It is intended for visual development and testing.

## What it can do

- Preview the display for today or a selected date.
- Simulate sunny, cloudy, rainy, cold, and snowy weather.
- Preview birthdays and relationship celebrations.
- Preview holidays and other special days defined in `data/dates.csv`.
- Preview the Spanish word of the day from `data/words.csv`.
- Generate comparison sheets containing multiple weather and celebration examples.
- Preview in black and white or with all four e-paper colors.
- Save rendered images locally as PNG files.

## Requirements

Run the script from the project root directory.

Install the Python dependencies if needed:

```bash
python3 -m pip install -r requirements.txt
```

The renderer uses Pillow to draw and save the display image.

## Basic usage

From the project directory:

```bash
python render.py
```

This renders today's display using simulated sunny weather and saves the result to:

```text
out/preview.png
```

To open the image automatically in macOS Preview:

```bash
python render.py --open
```

## Simulating weather

Weather is simulated by default. No API request is made.

Choose one of the available conditions:

```bash
python render.py --weather sunny --open
python render.py --weather cloudy --open
python render.py --weather rain --open
python render.py --weather cold --open
python render.py --weather snow --open
```

This makes it possible to check how the display looks under different weather conditions without depending on the weather service.

## Previewing a specific date

Use `--date` to make the renderer behave as if today were another date.

The format is `YYYY-MM-DD`.

For example:

```bash
python render.py --date 2026-11-26 --open
python render.py --date 2026-12-25 --open
python render.py --date 2027-01-01 --open
```

The selected date is used to determine date-dependent content, including:

- The calendar date.
- The Spanish word of the day.
- Holidays and special days.
- Birthdays configured in `data/dates.csv`.
- Monthly and yearly relationship celebrations.

You can combine a date with simulated weather:

```bash
python render.py --date 2026-11-26 --weather snow --open
```

This is particularly useful for testing how a holiday or celebration looks with different weather conditions.

**Note:** `--date` changes the date used by the local renderer. It does not request historical weather. The default simulated weather is independent of the selected date.

## Previewing all weather and celebration examples

To generate a collection of example images:

```bash
python render.py --all --open
```

This generates examples for:

- Sunny weather.
- Cloudy weather.
- Rain.
- Cold weather.
- Snow.
- A birthday.
- A monthlyversary.
- An anniversary.

The images are saved in `out/`, together with a combined contact sheet:

```text
out/
├── sunny.png
├── cloudy.png
├── rain.png
├── cold.png
├── snow.png
├── birthday.png
├── monthlyversary.png
├── anniversary.png
└── all.png
```

## Previewing all holidays and special days

To render every special day configured in `data/dates.csv`:

```bash
python render.py --holidays --open
```

The script generates individual previews for recognized special days and a combined contact sheet:

```text
out/
├── holiday_*.png
└── holidays.png
```

This is useful when developing or adjusting holiday-specific illustrations, banners, costumes, and Spanish words.

## Using all four e-paper colors

By default, the renderer uses black and white.

To preview the full four-color palette (black, white, red, and yellow):

```bash
python render.py --color --open
```

You can combine this option with a date and simulated weather:

```bash
python render.py --date 2026-12-25 --weather snow --color --open
```

## Using actual weather

Simulated weather is the default to keep local development fast and independent of network availability.

If you explicitly want to fetch the actual forecast for the configured location, use:

```bash
python render.py --live-weather --open
```

The location is configured near the top of `render.py` using `CITY`, `LAT`, and `LON`.

Live weather requires an internet connection and a working SSL certificate configuration for Python.

## Choosing an output path

Use `--out` to choose where a single preview image is saved:

```bash
python render.py --date 2026-12-25 --out out/christmas.png
```

The output directory is created automatically if it does not exist.

For `--all` and `--holidays`, the script writes its collection of images into the directory containing the specified output path.

## Relationship with the production renderer

There are two separate rendering scripts in this project:

| Script | Purpose |
|---|---|
| `render.py` | Local development, visual previews, simulated weather, and date testing |
| `render_periods.py` | Production generation of the four daily display periods |

`render.py` is intended for experimentation on your Mac. It produces PNG previews and does not replace the production rendering process.

`render_periods.py` remains responsible for generating the four images and binary files consumed by the ESP32:

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

The ESP32 firmware downloads and uses those production `.bin` files. The local preview script is not required by the firmware or the scheduled GitHub Actions workflow.

## Typical development workflow

When changing the layout, illustrations, typography, or date-dependent content:

1. Edit the relevant drawing or rendering functions in `render.py`.
2. Generate a preview for today's date or a date you want to test.
3. Try different weather conditions.
4. Test special dates using `--date`.
5. Use `--all` or `--holidays` to compare multiple designs.
6. Once the design is ready, make the corresponding change in `render_periods.py` if you want it to appear on the physical display.

For example:

```bash
python render.py --open
python render.py --weather rain --open
python render.py --date 2026-12-25 --weather snow --open
python render.py --all --open
python render.py --holidays --open
```

**Important:** `render.py` and `render_periods.py` are separate renderers. Changes made to the local preview renderer do not automatically change the production output.
