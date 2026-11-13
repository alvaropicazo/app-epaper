
#!/usr/bin/env python3
"""
Generate four panel-ready ePaper frames from one Open-Meteo forecast:
morning (09:00), afternoon (13:00), evening (18:00), and night (22:00).

The existing render.py owns the complete design, daily Spanish word,
dates, celebrations, and dachshund illustration. This script reuses
that renderer and changes only the hourly weather conditions featured
in the weather card.
"""

import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path

import render
from panel_export import save_panel_bin

PERIOD_HOURS = {
    "morning": 9,
    "afternoon": 13,
    "evening": 18,
    "night": 22,
}

LABELS = {
    "sunny": "Sunny",
    "cloudy": "Cloudy",
    "rain": "Rain",
    "snow": "Snow",
    "cold": "Cold",
}


def fetch_forecast(lat, lon):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,apparent_temperature,precipitation_probability,"
        "weather_code,wind_speed_10m"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
        "sunrise,sunset"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph"
        "&timezone=auto&forecast_days=2"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "app-epaper/1.0"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def find_hour(hourly_times, date, hour):
    wanted = f"{date.isoformat()}T{hour:02d}:00"
    try:
        return hourly_times.index(wanted)
    except ValueError as exc:
        raise RuntimeError(
            f"Forecast is missing the requested local hour: {wanted}"
        ) from exc


def make_weather(data, today, period):
    hourly = data["hourly"]
    daily = data["daily"]

    day_index = daily["time"].index(today.isoformat())
    hour = PERIOD_HOURS[period]
    i = find_hour(hourly["time"], today, hour)

    temp = round(hourly["temperature_2m"][i])
    apparent = round(hourly["apparent_temperature"][i])
    rain = hourly["precipitation_probability"][i] or 0

    kind = render.kind_from_code(
        hourly["weather_code"][i],
        rain
    )

    if kind not in ("rain", "snow") and temp <= 41:
        kind = "cold"

    # Keep the existing four forecast rows.
    slots = []

    for label, slot_hour in zip(
        render.SLOT_LABELS,
        render.SLOT_HOURS
    ):
        j = find_hour(hourly["time"], today, slot_hour)
        probability = hourly["precipitation_probability"][j] or 0

        slot_kind = render.kind_from_code(
            hourly["weather_code"][j],
            probability
        )

        slot_temp = round(hourly["temperature_2m"][j])

        slots.append((
            label,
            slot_kind,
            slot_temp,
            round(probability)
        ))

    sunrise = render._clock(daily["sunrise"][day_index])
    sunset = render._clock(daily["sunset"][day_index])

    return {
        "kind": kind,
        "label": LABELS[kind],
        "high": temp,
        "low": round(daily["temperature_2m_min"][day_index]),
        "rain": round(rain),
        "feels": apparent,
        "wind": round(hourly["wind_speed_10m"][i]),
        "slots": slots,
        "sunrise": sunrise,
        "sunset": sunset,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--out-dir",
        default="output",
        help="Directory for generated frames"
    )

    parser.add_argument(
        "--date",
        help="Override today's date (YYYY-MM-DD), useful for testing"
    )

    args = parser.parse_args()

    today = (
        dt.date.fromisoformat(args.date)
        if args.date
        else dt.datetime.now().date()
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    forecast = fetch_forecast(render.LAT, render.LON)

    # Force all four forecast frames to black and white only.
    render.RED = render.BLACK
    render.YELLOW = render.WHITE
    render.PALETTE = [render.BLACK, render.WHITE]

    codes = {
        render.BLACK: 0,
        render.WHITE: 1,
    }

    for period in PERIOD_HOURS:
        weather = make_weather(forecast, today, period)

        holiday = render.todays_holiday(today)
        word = render.word_for(today, holiday)
        birthdays = render.todays_birthdays(today)
        monthly, years = render.relationship_celebration(today)

        image = render.to_panel_colors(
            render.render(
                weather,
                word,
                today,
                birthdays,
                monthly,
                years,
                holiday
            )
        )

        png_path = out_dir / f"{period}.png"
        bin_path = out_dir / f"{period}.bin"

        image.save(png_path)
        save_panel_bin(image, bin_path, codes)

        print(
            f"Generated {period}: "
            f"{PERIOD_HOURS[period]:02d}:00 forecast "
            f"({weather['kind']}, {weather['high']}°F)"
        )


if __name__ == "__main__":
    main()
