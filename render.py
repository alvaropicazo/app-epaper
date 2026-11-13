#!/usr/bin/env python3
"""
Morning e-paper renderer: weather + a little dachshund + a Spanish word of the day.

Produces a 648x480 image restricted to black & white by default
(use --color for the panel's 4 colors: black, white, red, yellow), so the preview on your Mac looks like
what the real display will show.

Celebrations (the dog jumps, wears a costume and there is confetti):
  - birthdays from data/dates.csv
  - monthlyversary on the 3rd of every month (see ANNIVERSARY below)
  - anniversary on April 3: a big "Happy Anniversary!" card takes over the display
  - special days from data/dates.csv (US bank holidays and more, see HOLIDAYS below).
    Each has its own dog costume, banner and Spanish word of the day.

Usage:
    python render.py                        # live weather for CITY (see top of file), Fahrenheit
    python render.py --weather rain         # fake weather: sunny | cloudy | rain | cold | snow
    python render.py --all --open           # weather versions + personal celebrations in one image
    python render.py --holidays --open      # every special day, on its date this year
    python render.py --date 2026-11-26      # pretend it is another day (test celebrations)
    python render.py --color                # use all 4 panel colors instead of black & white
"""
import argparse
import csv
import datetime as dt
import json
import math
import random
import re
import unicodedata
import subprocess
import urllib.request
from pathlib import Path
from panel_export import save_panel_bin

from PIL import Image, ImageDraw, ImageFont

W, H = 648, 480

# The four panel colors. Real e-paper inks are a bit muted; tweak these
# to match your panel once it arrives.
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (200, 30, 30)
YELLOW = (240, 200, 0)
PALETTE = [BLACK, WHITE, RED, YELLOW]

# Where the weather comes from (change these to move the display to another city)
CITY = "Chicago"
LAT, LON = 41.8781, -87.6298

# The day you two started. Monthlyversaries fall on this day of every month;
# the anniversary is on this month + day every year.
ANNIVERSARY = dt.date(2024, 4, 3)

DATA_DIR = Path(__file__).parent / "data"

def load_words():
    with open(DATA_DIR / "words.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pick_word(today):
    """Spanish word of the day. Goes through the whole list in a shuffled order
    before repeating, and is stable for the whole day (same date -> same word)."""
    words = load_words()
    n = len(words)
    cycle, pos = divmod(today.toordinal(), n)
    order = list(range(n))
    random.Random(cycle).shuffle(order)
    return words[order[pos]]


# Special days. The DATES live in data/dates.csv (a row whose name matches one of the
# prefixes in HOLIDAY_PREFIXES). This table says how each day looks:
#   theme  - which costume/props the dog gets (see draw_dachshund)
#   calm   - True for solemn days: the dog stays in its normal pose, no confetti
#   banner - the text in the banner
#   word   - the day's Spanish word (replaces the normal word of the day)
HOLIDAYS = {
    "newyear_day": dict(theme="newyearday", calm=False, banner="Happy New Year!",
        word=dict(word="Año Nuevo", type="noun", pronunciation="A-nyo NWE-bo", example="Brindamos por el Año Nuevo.", translation="We toasted to the New Year.", meaning='New Year. "¡Feliz Año Nuevo!" = Happy New Year!')),
    "mlk": dict(theme="heart", calm=True, banner="Martin Luther King Jr. Day",
        word=dict(word="sueño", type="noun", pronunciation="SWE-nyo", example="Anoche tuve un sueño raro.", translation="Last night I had a strange dream.", meaning='Dream; also "sleep". "Tengo un sueño" = "I have a dream"')),
    "valentines": dict(theme="love", calm=False, banner="Happy Valentine's Day!",
        word=dict(word="San Valentín", type="noun", pronunciation="san ba-len-TEEN", example="Te regalé flores por San Valentín.", translation="I gave you flowers for Valentine's Day.", meaning='Valentine\'s Day; also called "el Día de los Enamorados"')),
    "presidents": dict(theme="patriotic", calm=False, banner="Happy Presidents' Day!",
        word=dict(word="presidente", type="noun", pronunciation="pre-see-DEN-te", example="El presidente habló esta mañana.", translation="The president spoke this morning.", meaning="President; also the head of a club, company or board")),
    "easter": dict(theme="easter", calm=False, banner="Happy Easter!",
        word=dict(word="Semana Santa", type="noun", pronunciation="se-MA-na SAN-ta", example="En Semana Santa hay procesiones.", translation="During Holy Week there are processions.", meaning="Holy Week, the week before Easter. In Spain it means huge processions")),
    "mothers": dict(theme="love", calm=False, banner="Happy Mother's Day!",
        word=dict(word="madre", type="noun", pronunciation="MA-dre", example="Mi madre cocina muy bien.", translation="My mother cooks very well.", meaning="Mother; mamá is the affectionate version. In Spain, Mother's Day is the first Sunday of May")),
    "memorial": dict(theme="flag_small", calm=True, banner="Memorial Day: we remember",
        word=dict(word="recuerdo", type="noun", pronunciation="re-KWER-do", example="Tengo un buen recuerdo de ese viaje.", translation="I have a good memory of that trip.", meaning='A memory or a keepsake. "Recordar" = to remember')),
    "fathers": dict(theme="love", calm=False, banner="Happy Father's Day!",
        word=dict(word="padre", type="noun", pronunciation="PA-dre", example="Mi padre me enseñó a nadar.", translation="My father taught me to swim.", meaning="Father; papá is the affectionate version. In Spain, Father's Day is March 19")),
    "juneteenth": dict(theme="party", calm=False, banner="Happy Juneteenth!",
        word=dict(word="libertad", type="noun", pronunciation="lee-ber-TAD", example="La libertad es muy importante.", translation="Freedom is very important.", meaning="Freedom; liberty")),
    "july4": dict(theme="patriotic", calm=False, banner="Happy birthday, America!",
        word=dict(word="fuegos artificiales", type="noun", pronunciation="FWE-gos ar-tee-fee-THYA-les", example="Los fuegos artificiales empiezan a las diez.", translation="The fireworks start at ten.", meaning='Fireworks; literally "artificial fires"')),
    "labor": dict(theme="labor", calm=False, banner="Happy Labor Day!",
        word=dict(word="trabajo", type="noun", pronunciation="tra-BA-ho", example="Hoy tengo mucho trabajo.", translation="I have a lot of work today.", meaning='Work; also a job or an assignment. In Spain, "Día del Trabajo" is May 1')),
    "columbus": dict(theme="plain", calm=True, banner="Columbus Day / Indigenous Peoples' Day",
        word=dict(word="festivo", type="noun", pronunciation="fes-TEE-bo", example="El lunes es festivo.", translation="Monday is a public holiday.", meaning='A public holiday, a day off for everyone. "Día festivo" works too')),
    "halloween": dict(theme="halloween", calm=False, banner="Happy Halloween!",
        word=dict(word="calabaza", type="noun", pronunciation="ka-la-BA-tha", example="Vamos a tallar una calabaza.", translation="We're going to carve a pumpkin.", meaning='Pumpkin. "Dar calabazas" means to turn someone down')),
    "veterans": dict(theme="flag_small", calm=True, banner="Veterans Day: thank you for your service",
        word=dict(word="agradecer", type="verb", pronunciation="a-gra-de-THER", example="Quiero agradecerte tu ayuda.", translation="I want to thank you for your help.", meaning='To thank, or be grateful for. "Te lo agradezco" = I appreciate it')),
    "thanksgiving": dict(theme="thanksgiving", calm=False, banner="Happy Thanksgiving!",
        word=dict(word="Acción de Gracias", type="noun", pronunciation="ak-THYON de GRA-thyas", example="En Acción de Gracias comemos pavo.", translation="On Thanksgiving we eat turkey.", meaning='Thanksgiving; literally "action of thanks"')),
    "christmas": dict(theme="christmas", calm=False, banner="Merry Christmas!",
        word=dict(word="Feliz Navidad", type="phrase", pronunciation="fe-LEETH na-bee-DAD", example="¡Feliz Navidad a todos!", translation="Merry Christmas, everyone!", meaning="Merry Christmas! On its own, Navidad is the whole Christmas season")),
    "newyear": dict(theme="newyear", calm=False, banner="Happy New Year's Eve!",
        word=dict(word="Nochevieja", type="noun", pronunciation="no-che-BYE-ha", example="En Nochevieja tomamos doce uvas.", translation="On New Year's Eve we eat twelve grapes.", meaning='New Year\'s Eve; literally "old night". In Spain you eat 12 grapes at midnight')),
}

# A dates.csv row is a special day if its name is one of these (ignoring case, accents,
# spaces and punctuation). Exact matches only, so a person called "Pascual" or "Valentine"
# is never mistaken for Easter or Valentine's Day.
HOLIDAY_NAMES = {
    "newyear": ["New Year's Eve", "Nochevieja"],
    "newyear_day": ["New Year's Day", "New Year Day", "Año Nuevo"],
    "mlk": ["Martin Luther King Jr. Day", "Martin Luther King Day", "MLK Day", "MLK"],
    "valentines": ["Valentine's Day", "San Valentín"],
    "presidents": ["Presidents' Day", "President's Day", "Presidents Day"],
    "easter": ["Easter", "Easter Sunday", "Pascua", "Domingo de Pascua"],
    "mothers": ["Mother's Day", "Mothers Day"],
    "memorial": ["Memorial Day"],
    "fathers": ["Father's Day", "Fathers Day"],
    "juneteenth": ["Juneteenth"],
    "july4": ["America", "America's birthday", "USA", "US", "United States", "Independence Day", "4th of July", "July 4th"],
    "labor": ["Labor Day", "Labour Day"],
    "columbus": ["Columbus Day", "Indigenous Peoples' Day", "Indigenous Peoples Day"],
    "halloween": ["Halloween"],
    "veterans": ["Veterans Day"],
    "thanksgiving": ["Thanksgiving", "Thanksgiving Day"],
    "christmas": ["Christmas", "Christmas Day", "Navidad"],
}


def _norm(name):
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", plain.lower())


_HOLIDAY_LOOKUP = {_norm(n): key for key, names in HOLIDAY_NAMES.items() for n in names}


def holiday_key(name):
    """Which special day a dates.csv row is (or None for a normal birthday)."""
    return _HOLIDAY_LOOKUP.get(_norm(name))


WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def easter_date(year):
    """Western (Gregorian) Easter Sunday."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def row_date(row, year):
    """The date a dates.csv row falls on in `year`.
    A fixed date (month + day), or a rule such as "4th thu", "last mon" or "easter"."""
    rule = (row.get("rule") or "").strip().lower()
    if rule == "easter":
        return easter_date(year)
    month = int(row["month"])
    if not rule:
        day = int(row["day"])
        try:
            return dt.date(year, month, day)
        except ValueError:  # Feb 29 in a non-leap year
            return dt.date(year, month, 28)
    nth, weekday = rule.split()
    wanted = WEEKDAYS[weekday[:3]]
    days = [dt.date(year, month, d) for d in range(1, 29 + 3)
            if _valid(year, month, d) and dt.date(year, month, d).weekday() == wanted]
    return days[-1] if nth == "last" else days[int(nth[0]) - 1]


def _valid(year, month, day):
    try:
        dt.date(year, month, day)
        return True
    except ValueError:
        return False


def load_dates():
    path = DATA_DIR / "dates.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _rows_for(today):
    return [r for r in load_dates() if row_date(r, today.year) == today]


def todays_birthdays(today):
    """List of (name, age_or_None) for people whose birthday is today."""
    out = []
    for row in _rows_for(today):
        if holiday_key(row["name"]):
            continue
        year = (row.get("year") or "").strip()
        out.append((row["name"].strip(), today.year - int(year) if year else None))
    return out


def todays_holiday(today):
    """(key, year_or_None) if today is one of the special days in dates.csv, else None."""
    for row in _rows_for(today):
        key = holiday_key(row["name"])
        if key:
            year = (row.get("year") or "").strip()
            return key, int(year) if year else None
    return None


def holiday_banner(holiday, today):
    key, year = holiday
    text = HOLIDAYS[key]["banner"]
    if key == "july4" and year:
        text += f" ({today.year - year})"
    return text


def word_for(today, holiday):
    """Special days get their own themed word; every other day uses the rotation."""
    return HOLIDAYS[holiday[0]]["word"] if holiday else pick_word(today)


def relationship_celebration(today):
    """Returns (monthly, years).
    monthly: month number on the 3rd of a month (None otherwise)
    years:   number of years on the anniversary itself (None otherwise)"""
    if today.day != ANNIVERSARY.day or today <= ANNIVERSARY:
        return None, None
    months = (today.year - ANNIVERSARY.year) * 12 + today.month - ANNIVERSARY.month
    if months % 12 == 0:
        return None, months // 12
    return months, None


FONT_CANDIDATES_BOLD = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",   # macOS
    "/System/Library/Fonts/Helvetica.ttc",                 # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
]
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font(size, bold=False):
    for path in (FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)  # Pillow >= 10.1


# ---------------------------------------------------------------- weather

SLOT_LABELS = ("Morning", "Afternoon", "Evening", "Night")
SLOT_HOURS = (9, 12, 16, 20)


def kind_from_code(code, rain):
    """Icon type for one weather code (Open-Meteo / WMO codes)."""
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code >= 51 or rain >= 50:
        return "rain"
    return "sunny" if code <= 1 else "cloudy"


def mock_weather(kind):
    base = {
        "sunny": dict(label="Sunny", high=75, low=57, rain=5),
        "rain": dict(label="Rain", high=59, low=50, rain=80),
        "cold": dict(label="Cold", high=36, low=25, rain=10),
        "snow": dict(label="Snow", high=30, low=21, rain=70),
        "cloudy": dict(label="Cloudy", high=64, low=54, rain=20),
    }[kind]
    icons = {"sunny": ("sunny", "sunny", "sunny", "cloudy"), "cloudy": ("cloudy", "cloudy", "sunny", "cloudy"),
             "rain": ("cloudy", "rain", "rain", "cloudy"), "cold": ("cloudy", "cloudy", "sunny", "cloudy"),
             "snow": ("snow", "snow", "snow", "cloudy")}[kind]
    wet = kind in ("rain", "snow")
    temp_f = (0.15, 0.8, 1.0, 0.4)
    rain_f = (0.4, 1.0, 0.9, 0.4) if wet else (0.3, 0.6, 0.6, 0.3)
    slots = [(SLOT_LABELS[i], icons[i], round(base["low"] + (base["high"] - base["low"]) * temp_f[i]),
              round(base["rain"] * rain_f[i])) for i in range(4)]
    return dict(kind=kind, slots=slots, feels=base["high"] - (4 if kind in ("cold", "snow") else 2),
                wind={"sunny": 6, "cloudy": 9, "rain": 12, "cold": 14, "snow": 15}[kind],
                sunrise="6:34 AM", sunset="4:50 PM", **base)


def _clock(iso):
    t = dt.datetime.fromisoformat(iso)
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def live_weather(lat, lon):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,precipitation_probability,weather_code"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
        "apparent_temperature_max,wind_speed_10m_max,sunrise,sunset"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto&forecast_days=1"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.load(r)
    d, h = data["daily"], data["hourly"]
    code = d["weather_code"][0]
    high, low = round(d["temperature_2m_max"][0]), round(d["temperature_2m_min"][0])
    rain = d["precipitation_probability_max"][0] or 0
    kind = kind_from_code(code, rain)
    label = {"snow": "Snow", "rain": "Rain", "sunny": "Sunny", "cloudy": "Cloudy"}[kind]
    if kind not in ("snow", "rain") and high <= 41:
        kind, label = "cold", "Cold"
    slots = []
    for name, hour in zip(SLOT_LABELS, SLOT_HOURS):
        pr = h["precipitation_probability"][hour] or 0
        slots.append((name, kind_from_code(h["weather_code"][hour], pr), round(h["temperature_2m"][hour]), round(pr)))
    return dict(kind=kind, label=label, high=high, low=low, rain=rain, slots=slots,
                feels=round(d["apparent_temperature_max"][0]), wind=round(d["wind_speed_10m_max"][0]),
                sunrise=_clock(d["sunrise"][0]), sunset=_clock(d["sunset"][0]))


# ---------------------------------------------------------------- drawing
def sprite(draw_fn, height):
    """Draw something on a scratch canvas, crop it and scale it to `height` px (kept crisp in black & white)."""
    big = Image.new("RGB", (170, 150), WHITE)
    draw_fn(ImageDraw.Draw(big))
    big = big.crop(big.convert("L").point(lambda v: 255 if v < 128 else 0).getbbox())
    small = big.resize((max(1, round(big.width * height / big.height)), height), Image.LANCZOS)
    if PALETTE == [BLACK, WHITE]:
        small = small.convert("L").point(lambda v: 255 if v > 150 else 0).convert("RGB")
    return small


def wrap(draw, text, fnt, max_width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_width:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def draw_sun(d, cx, cy, r):
    for i in range(8):
        import math
        a = i * math.pi / 4
        d.line([cx + math.cos(a) * (r + 6), cy + math.sin(a) * (r + 6),
                cx + math.cos(a) * (r + 20), cy + math.sin(a) * (r + 20)],
               fill=(YELLOW if YELLOW != WHITE else BLACK), width=5)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=YELLOW, outline=BLACK, width=3)


def draw_cloud(d, cx, cy, fill=WHITE):
    for dx, dy, r in [(-24, 6, 20), (0, -8, 26), (26, 6, 20)]:
        d.ellipse([cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r],
                  fill=fill, outline=BLACK, width=3)
    d.rectangle([cx - 24, cy + 2, cx + 26, cy + 26], fill=fill)
    d.line([cx - 44, cy + 26, cx + 46, cy + 26], fill=BLACK, width=3)


def draw_weather_icon(d, kind, cx, cy):
    if kind == "sunny":
        draw_sun(d, cx, cy, 30)
    elif kind == "rain":
        draw_cloud(d, cx, cy - 10)
        for x in (-24, 0, 24):
            d.line([cx + x, cy + 36, cx + x - 8, cy + 56], fill=RED, width=4)
    elif kind == "snow":
        draw_cloud(d, cx, cy - 10)
        for x in (-24, 0, 24):
            d.text((cx + x, cy + 44), "*", font=font(34, True), fill=BLACK, anchor="mm")
    elif kind == "cold":  # thermometer
        d.rounded_rectangle([cx - 9, cy - 44, cx + 9, cy + 20], radius=9, fill=WHITE, outline=BLACK, width=4)
        d.ellipse([cx - 20, cy + 6, cx + 20, cy + 46], fill=WHITE, outline=BLACK, width=4)
        d.rectangle([cx - 4, cy - 10, cx + 4, cy + 24], fill=RED)
        d.ellipse([cx - 13, cy + 13, cx + 13, cy + 39], fill=RED)
    else:
        draw_sun(d, cx - 18, cy - 18, 18)
        draw_cloud(d, cx + 6, cy + 8)


def fit_font(d, text, max_width, start, bold=True):
    """Largest font (<= start) whose rendering of `text` fits in max_width."""
    size = start
    while size > 10 and d.textlength(text, font=font(size, bold)) > max_width:
        size -= 1
    return font(size, bold)


def draw_heart(d, cx, cy, r, fill):
    d.ellipse([cx - 2 * r, cy - r, cx, cy + r], fill=fill)
    d.ellipse([cx, cy - r, cx + 2 * r, cy + r], fill=fill)
    d.polygon([(cx - 2 * r + 1, cy + r * 0.45), (cx + 2 * r - 1, cy + r * 0.45),
               (cx, cy + r * 2.6)], fill=fill)


def limb(d, p1, p2, w=20):
    """A short rounded, outlined leg from p1 to p2."""
    for width, color in ((w + 8, BLACK), (w, YELLOW)):
        d.line([p1, p2], fill=color, width=width)
        for x, y in (p1, p2):
            d.ellipse([x - width // 2, y - width // 2, x + width // 2, y + width // 2], fill=color)


def draw_star(d, cx, cy, r, fill):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    d.polygon(pts, fill=fill)


def draw_flag(d, x, y, w, h):
    """A waving stars-and-stripes flag (7 stripes, white canton with star dots).
    (x, y) = top-left, i.e. the pole side."""
    bh = h / 7
    cw, ch = w * 0.42, bh * 4

    def wave(c):
        return round(3 * math.sin(c / 8))

    for c in range(0, w, 2):
        o = wave(c)
        for b in range(0, 7, 2):  # red stripes (the white ones are just the page)
            d.rectangle([x + c, y + o + b * bh, x + c + 1, y + o + (b + 1) * bh], fill=RED)
        if c < cw:
            d.rectangle([x + c, y + o, x + c + 1, y + o + ch], fill=WHITE)
    cols = list(range(0, w + 1, 2))
    top = [(x + c, y + wave(c)) for c in cols]
    bot = [(x + c, y + wave(c) + h) for c in cols]
    for edge in (top, bot):
        d.line(edge, fill=BLACK, width=3)
    d.line([top[0], bot[0]], fill=BLACK, width=3)
    d.line([top[-1], bot[-1]], fill=BLACK, width=3)
    d.line([(x + c, y + wave(c) + ch) for c in range(0, int(cw) + 1, 2)], fill=BLACK, width=2)
    d.line([(x + cw, y + wave(int(cw))), (x + cw, y + wave(int(cw)) + ch)], fill=BLACK, width=2)
    for r in range(3):  # the stars
        for k in range(4):
            c = 6 + k * (cw - 12) / 3
            px, py = x + c, y + wave(int(c)) + 6 + r * (ch - 12) / 2
            dot = 2 if w >= 60 else 1
            d.ellipse([px - dot, py - dot, px + dot, py + dot], fill=BLACK)


def draw_sam_hat(d, hx, hoy):
    """Uncle Sam style top hat: striped crown, band with a star."""
    top, base = hoy + 46, hoy + 90
    d.rectangle([hx - 16, top, hx + 14, base], fill=WHITE, outline=BLACK, width=3)
    for x in range(hx - 12, hx + 12, 8):
        d.rectangle([x, top + 3, x + 3, base - 14], fill=RED)
    d.rectangle([hx - 16, base - 14, hx + 14, base], fill=BLACK)
    draw_star(d, hx - 1, base - 7, 5, WHITE)
    d.rounded_rectangle([hx - 28, base - 2, hx + 26, base + 6], radius=3, fill=BLACK)


def draw_santa_hat(d, hx, hoy):
    base = hoy + 92
    d.polygon([(hx - 20, base), (hx + 22, base), (hx + 32, hoy + 60), (hx + 6, hoy + 44)],
              fill=RED, outline=BLACK)
    d.line([(hx - 20, base), (hx + 6, hoy + 44), (hx + 32, hoy + 60), (hx + 22, base)], fill=BLACK, width=3)
    d.ellipse([hx + 24, hoy + 54, hx + 42, hoy + 72], fill=WHITE, outline=BLACK, width=3)  # pompom
    d.rounded_rectangle([hx - 26, base - 7, hx + 28, base + 7], radius=7,
                        fill=WHITE, outline=BLACK, width=3)                                # fur brim


def draw_gift(d, x, y, w=38, h=30):
    """A wrapped present; (x, y) = top-left."""
    d.rectangle([x, y, x + w, y + h], fill=WHITE, outline=BLACK, width=3)
    d.rectangle([x + w // 2 - 4, y, x + w // 2 + 4, y + h], fill=BLACK)   # ribbon
    d.rectangle([x, y + h // 2 - 4, x + w, y + h // 2 + 4], fill=BLACK)
    d.ellipse([x + w // 2 - 13, y - 10, x + w // 2 - 1, y + 2], outline=BLACK, width=3)  # bow
    d.ellipse([x + w // 2 + 1, y - 10, x + w // 2 + 13, y + 2], outline=BLACK, width=3)


def draw_clock(d, cx, cy, r, minute=58):
    """A clock: 11:58 (two minutes to midnight) by default, or minute=0 for exactly midnight."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=BLACK, width=4)
    for i in range(12):
        a = i * math.pi / 6
        inner = r - (10 if i % 3 == 0 else 7)
        d.line([(cx + inner * math.sin(a), cy - inner * math.cos(a)),
                (cx + (r - 4) * math.sin(a), cy - (r - 4) * math.cos(a))], fill=BLACK, width=2)
    a = math.radians(minute * 6)  # minute hand
    d.line([(cx, cy), (cx + (r - 9) * math.sin(a), cy - (r - 9) * math.cos(a))], fill=BLACK, width=3)
    d.line([(cx, cy), (cx, cy - (r - 15))], fill=BLACK, width=4)            # hour hand: 12
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=BLACK)


def draw_snowflake(d, cx, cy, r):
    for i in range(3):
        a = i * math.pi / 3
        d.line([(cx - r * math.cos(a), cy - r * math.sin(a)), (cx + r * math.cos(a), cy + r * math.sin(a))],
               fill=BLACK, width=2)


def draw_witch_hat(d, hx, hoy):
    base = hoy + 90
    d.polygon([(hx - 18, base), (hx + 18, base), (hx + 8, hoy + 56), (hx + 26, hoy + 44)],
              fill=RED, outline=BLACK)
    d.line([(hx - 18, base), (hx + 8, hoy + 56), (hx + 26, hoy + 44), (hx + 18, base)], fill=BLACK, width=3)
    d.rectangle([hx - 15, base - 14, hx + 15, base - 5], fill=WHITE, outline=BLACK, width=2)  # band
    d.ellipse([hx - 32, base - 7, hx + 32, base + 7], fill=BLACK)                             # brim


def draw_pilgrim_hat(d, hx, hoy):
    base = hoy + 90
    d.polygon([(hx - 20, base), (hx + 20, base), (hx + 15, hoy + 50), (hx - 15, hoy + 50)],
              fill=RED, outline=BLACK)
    d.rectangle([hx - 20, base - 15, hx + 20, base - 3], fill=WHITE, outline=BLACK, width=2)  # band
    d.rectangle([hx - 5, base - 13, hx + 5, base - 5], outline=BLACK, width=2)                # buckle
    d.rounded_rectangle([hx - 30, base - 3, hx + 30, base + 6], radius=3, fill=BLACK)         # brim


def draw_beanie(d, hx, hoy):
    """A knitted winter beanie: striped dome, ribbed cuff and a pom-pom."""
    d.pieslice([hx - 22, hoy + 60, hx + 22, hoy + 120], 180, 360, fill=YELLOW, outline=BLACK, width=3)
    for y, half in ((70, 15), (80, 19)):  # knitted stripes
        d.line([(hx - half, hoy + y), (hx + half, hoy + y)], fill=RED, width=3)
    d.rounded_rectangle([hx - 25, hoy + 86, hx + 25, hoy + 98], radius=4, fill=BLACK)  # ribbed cuff
    for x in range(hx - 20, hx + 22, 6):
        d.line([(x, hoy + 88), (x, hoy + 96)], fill=WHITE, width=2)
    d.ellipse([hx - 8, hoy + 47, hx + 8, hoy + 63], fill=WHITE, outline=BLACK, width=3)  # pom-pom
    d.ellipse([hx - 2, hoy + 53, hx + 2, hoy + 57], fill=BLACK)


def draw_bunny_ears(d, hx, hoy):
    for x0, x1 in ((hx - 22, hx - 2), (hx + 2, hx + 22)):
        d.ellipse([x0, hoy + 22, x1, hoy + 96], fill=WHITE, outline=BLACK, width=3)
        d.ellipse([x0 + 6, hoy + 34, x1 - 6, hoy + 82], fill=RED)


def draw_hard_hat(d, hx, hoy):
    d.pieslice([hx - 26, hoy + 58, hx + 26, hoy + 118], 180, 360, fill=YELLOW, outline=BLACK, width=3)
    d.rectangle([hx - 5, hoy + 62, hx + 5, hoy + 88], fill=RED)
    d.rounded_rectangle([hx - 32, hoy + 86, hx + 32, hoy + 95], radius=4, fill=BLACK)


def draw_pumpkin(d, x, y, face=False):
    """(x, y) = top-left of a ~46x36 pumpkin."""
    d.ellipse([x, y, x + 46, y + 36], fill=WHITE, outline=BLACK, width=3)
    d.arc([x + 10, y + 1, x + 36, y + 35], 90, 270, fill=BLACK, width=2)
    d.arc([x + 10, y + 1, x + 36, y + 35], 270, 90, fill=BLACK, width=2)
    d.rectangle([x + 20, y - 8, x + 26, y + 3], fill=BLACK)  # stem
    if face:
        d.polygon([(x + 12, y + 13), (x + 19, y + 13), (x + 15, y + 8)], fill=BLACK)
        d.polygon([(x + 27, y + 13), (x + 34, y + 13), (x + 30, y + 8)], fill=BLACK)
        d.line([(x + 12, y + 24), (x + 18, y + 28), (x + 23, y + 24), (x + 28, y + 28), (x + 34, y + 24)],
               fill=BLACK, width=3)


def draw_egg(d, cx, cy, r):
    d.ellipse([cx - r * 0.75, cy - r, cx + r * 0.75, cy + r], fill=WHITE, outline=BLACK, width=2)
    d.line([(cx - r * 0.65, cy + 1), (cx - r * 0.3, cy - 3), (cx, cy + 1), (cx + r * 0.3, cy - 3), (cx + r * 0.65, cy + 1)],
           fill=RED, width=3)


def draw_leaf(d, cx, cy, r):
    d.polygon([(cx, cy - r), (cx + r * 0.65, cy), (cx, cy + r), (cx - r * 0.65, cy)], fill=RED, outline=BLACK)
    d.line([(cx, cy - r * 0.6), (cx, cy + r + 3)], fill=BLACK, width=2)


def draw_bat(d, cx, cy):
    for sgn in (-1, 1):
        d.polygon([(cx, cy - 2), (cx + sgn * 9, cy - 9), (cx + sgn * 16, cy - 3),
                   (cx + sgn * 11, cy - 2), (cx + sgn * 7, cy + 3), (cx + sgn * 3, cy + 1)], fill=BLACK)
    d.ellipse([cx - 3, cy - 4, cx + 3, cy + 5], fill=BLACK)


def confetti_piece(d, theme, x, y):
    """One piece of the 'square' confetti, dressed for the theme."""
    if theme == "christmas":
        draw_snowflake(d, x + 5, y + 5, 8)
    elif theme in ("patriotic", "newyear", "newyearday"):
        draw_star(d, x + 5, y + 5, 7, RED)
    elif theme == "love":
        draw_heart(d, x + 8, y + 3, 4, RED)
    elif theme == "halloween":
        draw_bat(d, x + 8, y + 6)
    elif theme == "easter":
        draw_egg(d, x + 5, y + 6, 8)
    elif theme == "thanksgiving":
        draw_leaf(d, x + 5, y + 6, 8)
    else:
        d.rectangle([x, y, x + 8, y + 8], fill=RED)


HEADGEAR = {"patriotic": draw_sam_hat, "christmas": draw_santa_hat, "halloween": draw_witch_hat,
            "thanksgiving": draw_pilgrim_hat, "easter": draw_bunny_ears, "labor": draw_hard_hat}
NO_PARTY_HAT = ("love", "flag_small", "heart", "plain")


class ScaledDraw:
    """Wraps an ImageDraw so that everything is drawn `k` times bigger around the point (ax, ay).
    Lets the dog (with all its costumes and props) be resized without touching any coordinates."""

    def __init__(self, d, k, ax, ay):
        self.d, self.k, self.ax, self.ay = d, k, ax, ay

    def _xy(self, xy):
        xy = list(xy)
        if xy and isinstance(xy[0], (tuple, list)):
            return [(self.ax + (x - self.ax) * self.k, self.ay + (y - self.ay) * self.k) for x, y in xy]
        return [self.ax + (v - self.ax) * self.k if i % 2 == 0 else self.ay + (v - self.ay) * self.k
                for i, v in enumerate(xy)]

    def __getattr__(self, name):  # line, ellipse, rectangle, rounded_rectangle, polygon, arc, pieslice
        fn = getattr(self.d, name)

        def draw(xy, *args, **kw):
            for key in ("width", "radius"):
                if kw.get(key):
                    kw[key] = max(1, round(kw[key] * self.k))
            return fn(self._xy(xy), *args, **kw)
        return draw


def draw_dachshund(d, ox, oy, kind, celebrate=False, theme=None, scale=1.0):
    """A long, low dachshund facing left. (ox, oy) = top-left of a ~250x230 area (before scaling).
    Idle pose: head up, tail curled, one front paw lifted.
    Celebrating pose: mid-jump with a party hat, tongue out, wagging tail, confetti.
    scale > 1 draws it bigger, growing from the middle of its feet."""
    ground = oy + 206
    if scale != 1.0:
        d = ScaledDraw(d, scale, ox + 109, ground)
    orig_oy = oy
    if celebrate:
        oy -= 24                      # jump!
    hoy = oy - 8                      # head sits a little high
    hx = ox + 48

    # tail (curled up) and wag lines
    tip = (ox + 236, oy + 80) if celebrate else (ox + 230, oy + 92)
    p0, ctrl = (ox + 206, oy + 142), (ox + 248, oy + 128)
    prev = p0
    for i in range(1, 13):  # a smooth curl, thick at the base and thin at the tip
        t = i / 12
        q = tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * b + t * t * c for a, b, c in zip(p0, ctrl, tip))
        w = round(11 - 5 * t)
        d.line([prev, q], fill=BLACK, width=w)
        d.ellipse([q[0] - w / 2, q[1] - w / 2, q[0] + w / 2, q[1] + w / 2], fill=BLACK)
        prev = q
    if celebrate:
        for (x1, y1), (x2, y2) in [((242, 96), (253, 89)), ((244, 108), (256, 108)), ((242, 120), (253, 127))]:
            d.line([(ox + x1, oy + y1), (ox + x2, oy + y2)], fill=BLACK, width=3)

    # legs (drawn before the body so it overlaps them)
    if celebrate:
        limb(d, (ox + 72, oy + 170), (ox + 38, oy + 178))     # front legs reaching forward
        limb(d, (ox + 98, oy + 174), (ox + 66, oy + 194))
        limb(d, (ox + 176, oy + 176), (ox + 194, oy + 202))   # back legs kicked out
        limb(d, (ox + 204, oy + 174), (ox + 224, oy + 196))
        d.ellipse([ox + 50, ground - 2, ox + 210, ground + 6], fill=BLACK)  # shadow on the ground
    else:
        for lx in (ox + 92, ox + 170, ox + 200):
            d.rounded_rectangle([lx, oy + 168, lx + 20, ground], radius=8,
                                fill=YELLOW, outline=BLACK, width=4)
            d.ellipse([lx - 2, ground - 8, lx + 22, ground + 2], fill=YELLOW, outline=BLACK, width=3)  # paw
        limb(d, (ox + 72, oy + 172), (ox + 46, oy + 190))     # lifted front paw

    # body
    d.rounded_rectangle([ox + 50, oy + 128, ox + 214, oy + 186], radius=29,
                        fill=YELLOW, outline=BLACK, width=4)
    if kind in ("cold", "snow"):  # knitted sweater: a band, a zigzag and a ribbed hem
        sx0, sx1 = ox + 84, ox + 186
        d.rectangle([sx0, oy + 132, sx1, oy + 182], fill=YELLOW)
        d.rectangle([sx0, oy + 138, sx1, oy + 150], fill=RED)
        zig = [(x, oy + 160 + (7 if ((x - sx0) // 8) % 2 else 0)) for x in range(sx0, sx1 + 1, 8)]
        d.line(zig, fill=BLACK, width=2)
        for x in range(sx0 + 5, sx1, 7):
            d.line([(x, oy + 173), (x, oy + 182)], fill=BLACK, width=2)
        d.line([(sx0, oy + 130), (sx0, oy + 184)], fill=BLACK, width=3)
        d.line([(sx1, oy + 130), (sx1, oy + 184)], fill=BLACK, width=3)

    # snout, head, nose, mouth, ear
    d.rounded_rectangle([ox - 14, hoy + 106, ox + 44, hoy + 134], radius=13,
                        fill=YELLOW, outline=BLACK, width=4)
    d.ellipse([ox + 18, hoy + 88, ox + 80, hoy + 142], fill=YELLOW, outline=BLACK, width=4)
    d.ellipse([ox - 18, hoy + 106, ox, hoy + 122], fill=BLACK)
    d.ellipse([ox - 14, hoy + 109, ox - 9, hoy + 113], fill=WHITE)  # shiny nose
    for wx, wy in ((ox + 10, hoy + 112), (ox + 17, hoy + 114), (ox + 12, hoy + 119)):  # whisker dots
        d.ellipse([wx - 1.5, wy - 1.5, wx + 1.5, wy + 1.5], fill=BLACK)
    if celebrate:  # tongue out
        d.ellipse([ox + 8, hoy + 124, ox + 26, hoy + 148], fill=RED, outline=BLACK, width=3)
    d.arc([ox + 6, hoy + 118, ox + 40, hoy + 136], 0, 90, fill=BLACK, width=3)
    d.ellipse([ox + 56, hoy + 98, ox + 92, hoy + 156], fill=BLACK)
    d.arc([ox + 62, hoy + 106, ox + 86, hoy + 148], 290, 70, fill=WHITE, width=2)  # shine on the ear

    # eye / glasses
    if kind == "sunny":
        d.rectangle([ox + 22, hoy + 101, ox + 50, hoy + 117], fill=BLACK)
        d.line([ox + 50, hoy + 108, ox + 58, hoy + 108], fill=BLACK, width=4)
    elif celebrate:  # happy ^ eye
        d.arc([ox + 32, hoy + 102, ox + 52, hoy + 118], 180, 360, fill=BLACK, width=4)
    elif kind == "cloudy":  # sleepy
        d.arc([ox + 32, hoy + 104, ox + 52, hoy + 118], 0, 180, fill=BLACK, width=4)
    else:
        d.ellipse([ox + 36, hoy + 102, ox + 48, hoy + 114], fill=BLACK)
        d.ellipse([ox + 40, hoy + 105, ox + 44, hoy + 109], fill=WHITE)  # sparkle in the eye

    # accessories
    hat_on = theme in HEADGEAR or (celebrate and theme not in NO_PARTY_HAT)
    if kind in ("cold", "snow") and not hat_on:
        draw_beanie(d, hx, hoy)
    if theme in HEADGEAR:
        HEADGEAR[theme](d, hx, hoy)
    elif celebrate and theme not in NO_PARTY_HAT:  # plain party hat
        d.polygon([(hx - 16, hoy + 92), (hx + 14, hoy + 92), (hx - 1, hoy + 52)],
                  fill=RED, outline=BLACK)
        d.ellipse([hx - 7, hoy + 44, hx + 5, hoy + 56], fill=WHITE, outline=BLACK, width=2)
    if theme == "christmas":  # a present waiting on the ground
        draw_gift(d, ox - 4, ground - 30)
    if theme in ("halloween", "thanksgiving"):  # a pumpkin on the ground
        draw_pumpkin(d, ox - 8, ground - 36, face=(theme == "halloween"))
    if theme in ("newyear", "newyearday"):  # the clock: 11:58 on the eve, midnight on the day
        draw_clock(d, ox + 150, oy + 40, 30, minute=58 if theme == "newyear" else 0)
    if theme == "heart":  # a heart floating above the dog
        draw_heart(d, ox + 150, oy + 56, 13, RED)
    if theme == "flag_small":  # a small flag on the dog's back
        px = ox + 112
        d.line([(px, oy + 132), (px, oy + 66)], fill=BLACK, width=4)
        d.ellipse([px - 4, oy + 61, px + 4, oy + 69], fill=BLACK)
        draw_flag(d, px + 2, oy + 70, 52, 34)
    if theme == "patriotic":  # flag planted on the dog's back
        px = ox + 112
        d.line([(px, oy + 132), (px, oy + 20)], fill=BLACK, width=5)
        d.ellipse([px - 5, oy + 14, px + 5, oy + 24], fill=BLACK)
        draw_flag(d, px + 3, oy + 26, 76, 49)
    if kind == "rain" and not theme:  # umbrella tucked into the dog's back
        cx = ox + 135
        d.pieslice([cx - 95, oy + 6, cx + 95, oy + 74], 180, 360, fill=RED, outline=BLACK, width=4)
        d.line([cx, oy + 40, cx, oy + 130], fill=BLACK, width=5)

    # confetti, dressed for the theme (stars, snowflakes, hearts, bats, eggs, leaves...)
    if celebrate:
        for dx, dy, shape in [(-8, 34, "sq"), (8, 2, "ci"), (78, -10, "sq"), (112, 22, "ci"),
                              (160, -4, "ci"), (198, 14, "sq"), (216, 30, "ci"), (240, 8, "sq"),
                              (-12, 92, "ci"), (232, 150, "sq")]:
            if theme == "patriotic" and 100 <= dx <= 200 and -20 <= dy <= 42:
                continue  # keep the flag clear
            if theme in ("newyear", "newyearday") and 112 <= dx <= 192 and -30 <= dy <= 52:
                continue  # keep the clock clear
            x, y = ox + dx, orig_oy + dy
            if shape == "sq":
                confetti_piece(d, theme, x, y)
            else:
                d.ellipse([x, y, x + 10, y + 10], outline=BLACK, width=3)


# Layout (648x480):  header | weather card (left) + dog scene (right) | [banner] | word card
LEFT = (24, 290)             # weather card columns
SCENE = (306, 58, W - 24, 326)
GROUND = 308                 # the dog's ground line inside the scene
DOG_X = 348
DOG_SCALE = 1.1


def drops(d, x, y0, y1, step=34):
    y = y0
    while y < y1:
        d.line([(x, y), (x - 4, y + 13)], fill=BLACK, width=3)
        y += step


def draw_anniversary(d, years, weather):
    """The big anniversary takeover: a framed message replaces the weather card."""
    d.rounded_rectangle([24, 58, 290, 292], radius=18, outline=BLACK, width=6)
    d.rounded_rectangle([34, 68, 280, 282], radius=12, outline=BLACK, width=2)
    cx = 157
    d.text((cx, 94), "HAPPY", font=font(26, True), fill=BLACK, anchor="mm")
    d.text((cx, 132), "Anniversary!", font=fit_font(d, "Anniversary!", 228, 40), fill=BLACK, anchor="mm")
    num = str(years)
    side1 = "year" if years == 1 else "years"
    nf, sf1, sf2 = font(88, True), font(30, True), font(20, True)
    nw = d.textlength(num, font=nf)
    sw = max(d.textlength(side1, font=sf1), d.textlength("together", font=sf2))
    x0 = cx - (nw + 12 + sw) / 2
    d.text((x0, 196), num, font=nf, fill=BLACK, anchor="lm")
    d.text((x0 + nw + 12, 184), side1, font=sf1, fill=BLACK, anchor="lm")
    d.text((x0 + nw + 12, 212), "together", font=sf2, fill=BLACK, anchor="lm")
    for hx in (cx - 42, cx, cx + 42):
        draw_heart(d, hx - 6, 258, 6, RED)
    line = f"{weather['label']}   {weather['high']}\u00b0 / {weather['low']}\u00b0   \u2022   {weather['rain']}% rain"
    d.text((24, 310), line, font=fit_font(d, line, 266, 20), fill=BLACK, anchor="lm")


def draw_weather_card(img, d, weather):
    """Big temperature, a four-slot forecast, and the small details."""
    x0, x1 = LEFT
    tf = font(78, True)
    temp = f"{weather['high']}\u00b0"
    d.text((x0 + 4, 54), temp, font=tf, fill=BLACK, anchor="la")
    d.text((x0 + 4 + d.textlength(temp, font=tf) + 12, 104), f"/ {weather['low']}\u00b0",
           font=font(30), fill=BLACK, anchor="la")
    lf = font(26, True)
    d.text((x0 + 4, 144), weather["label"], font=lf, fill=BLACK, anchor="la")
    detail = f"Feels {weather['feels']}\u00b0  \u00b7  Wind {weather['wind']} mph"
    dx = x0 + 4 + d.textlength(weather["label"], font=lf) + 14
    d.text((dx, 152), detail, font=fit_font(d, detail, x1 - dx, 14, False), fill=BLACK, anchor="la")
    d.line([(x0, 182), (x1, 182)], fill=BLACK, width=2)
    for i, (label, kind, temp_f, rain) in enumerate(weather["slots"]):
        y = 188 + i * 28
        d.text((x0 + 4, y + 13), label, font=font(16, True), fill=BLACK, anchor="lm")
        img.paste(sprite(lambda dd, k=kind: draw_weather_icon(dd, k, 85, 72), 24), (140, y + 2))
        d.text((202, y + 13), f"{temp_f}\u00b0", font=font(18, True), fill=BLACK, anchor="lm")
        d.text((250, y + 13), f"{rain}%", font=font(16), fill=BLACK, anchor="lm")
    d.line([(x0, 302), (x1, 302)], fill=BLACK, width=2)
    d.text((x0 + 4, 309), f"Sunrise {weather['sunrise']}  \u00b7  Sunset {weather['sunset']}",
           font=fit_font(d, f"Sunrise {weather['sunrise']}  \u00b7  Sunset {weather['sunset']}", x1 - x0 - 4, 14, False),
           fill=BLACK, anchor="la")


def draw_scene(img, d, weather, celebrate, theme):
    """The dog in its box, with the weather in the sky and a little grass at its feet."""
    bx0, by0, bx1, by1 = SCENE
    kind = weather["kind"]
    if not celebrate:  # keep the sky calm when the dog is jumping
        if kind == "rain":
            for x in (bx0 + 32, bx0 + 60, bx1 - 36, bx1 - 14):
                drops(d, x, by0 + 12, GROUND - 10)
        elif kind == "snow":
            for fx, fy in ((330, 76), (358, 104), (392, 132), (600, 80), (584, 124), (606, 150), (340, 150)):
                draw_snowflake(d, fx, fy, 8)
        else:
            img.paste(sprite(lambda dd: draw_weather_icon(dd, kind, 85, 72), 36), (bx1 - 74, by0 + 12))
    draw_dachshund(d, DOG_X, GROUND - 206, kind, celebrate=celebrate, theme=theme, scale=DOG_SCALE)
    d.line([(bx0 + 2, GROUND + 2), (bx1 - 2, GROUND + 2)], fill=BLACK, width=3)
    for x in range(bx0 + 16, bx1 - 14, 24):  # little grass tufts
        d.line([(x, GROUND + 15), (x + 4, GROUND + 7), (x + 8, GROUND + 15)], fill=BLACK, width=2)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=14, outline=BLACK, width=4)


def draw_word_card(d, word, y0):
    """The one Spanish part of the screen: the word, how to say it, what it means, an example."""
    y1 = 476
    d.rounded_rectangle([24, y0, W - 24, y1], radius=12, outline=BLACK, width=3)
    roomy = (y1 - y0) >= 120
    pron = (word.get("pronunciation") or "").strip()
    example = (word.get("example") or "").strip()
    translation = (word.get("translation") or "").strip()
    inner = W - 76
    for scale in (1.0, 0.92, 0.84, 0.76):
        s_word, s_mean, s_ex, s_tr = (round(v * scale) for v in ((48, 21, 20, 17) if roomy else (34, 16, 15, 13)))
        wf = fit_font(d, word["word"], 330, s_word)
        mf, ef, tf = font(s_mean), font(s_ex, True), font(s_tr)
        mlines = wrap(d, word["meaning"], mf, inner)[:2]
        total = wf.size * 1.2 + len(mlines) * s_mean * 1.25 + (s_ex * 1.25 if example else 0) + (s_tr * 1.3 if translation else 0)
        if total <= (y1 - y0) - 14:
            break
    y = y0 + 6
    d.text((38, y), word["word"], font=wf, fill=BLACK, anchor="la")
    d.text((W - 38, y + 3), "PALABRA DEL D\u00cdA", font=font(12, True), fill=BLACK, anchor="ra")
    tag = f"{word['type']}  \u00b7  /{pron}/" if pron else word["type"]
    d.text((W - 38, y + 19), tag, font=fit_font(d, tag, 250, 14, False), fill=BLACK, anchor="ra")
    y += wf.size * 1.2
    for line in mlines:
        d.text((38, y), line, font=mf, fill=BLACK, anchor="la")
        y += s_mean * 1.25
    if example:
        d.text((38, y), example, font=fit_font(d, example, inner, s_ex), fill=BLACK, anchor="la")
        y += s_ex * 1.25
    if translation:
        d.text((38, y), translation, font=fit_font(d, translation, inner, s_tr, False), fill=BLACK, anchor="la")
        y += s_tr * 1.3
    return y  # how far down the text reaches (used by the tests)


def render(weather, word, today, birthdays=(), monthly=None, years=None, holiday=None):
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    day_info = HOLIDAYS[holiday[0]] if holiday else None
    theme = day_info["theme"] if day_info else None
    # solemn days (Memorial Day, Veterans Day...) keep the dog calm: no jumping, no confetti
    celebrate = bool(birthdays or monthly or years or (day_info and not day_info["calm"]))

    # header bar
    d.rectangle([0, 0, W, 50], fill=BLACK)
    d.text((24, 25), today.strftime("%A"), font=font(28, True), fill=WHITE, anchor="lm")
    d.text((W // 2 + 40, 25), CITY, font=font(20), fill=WHITE, anchor="mm")
    d.text((W - 24, 25), f"{today.strftime('%b')} {today.day}, {today.year}", font=font(22), fill=WHITE, anchor="rm")

    # left: weather card (or the anniversary card), right: the dog
    if years:
        draw_anniversary(d, years, weather)
    else:
        draw_weather_card(img, d, weather)
    draw_scene(img, d, weather, celebrate, theme)

    # celebration banner: only takes space when there is something to celebrate
    msgs = []
    if monthly:
        msgs.append(f"Happy monthlyversary! Month {monthly}")
    if birthdays:
        names = ", ".join(f"{n} ({a})" if a else n for n, a in birthdays)
        msgs.append(f"Happy birthday {names}!")
    if holiday:
        msgs.append(holiday_banner(holiday, today))
    card_y = 340
    if msgs:
        text = "  \u2022  ".join(msgs)
        d.rounded_rectangle([24, 334, W - 24, 360], radius=8, fill=YELLOW, outline=BLACK, width=3)
        d.text((W // 2, 347), text, font=fit_font(d, text, 580, 18), fill=RED, anchor="mm")
        card_y = 368

    draw_word_card(d, word, card_y)
    return img


def to_panel_colors(img):
    """Snap every pixel to the nearest of the 4 panel colors (with dithering)."""
    pal_img = Image.new("P", (1, 1))
    flat = [c for rgb in PALETTE for c in rgb]
    pal_img.putpalette(flat + [0] * (768 - len(flat)))
    return img.quantize(palette=pal_img, dither=Image.Dither.NONE).convert("RGB")


def contact_sheet(images, out_path, cols=4):
    rows = -(-len(images) // cols)
    sheet = Image.new("RGB", (W * cols + 10 * (cols + 1), H * rows + 10 * (rows + 1)), (150, 150, 150))
    for i, img in enumerate(images):
        sheet.paste(img, (10 + (i % cols) * (W + 10), 10 + (i // cols) * (H + 10)))
    sheet.save(out_path)
    print(f"Saved {out_path}")


def render_all(args):
    """Render every weather type plus the personal celebrations, and a contact sheet."""
    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    out_dir = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    # (file name, weather kind, birthdays, monthly, years)
    cases = [(k, k, [], None, None) for k in ("sunny", "cloudy", "rain", "cold", "snow")]
    cases += [
        ("birthday", "sunny", [("Alex", 36)], None, None),
        ("monthlyversary", "cloudy", [], 7, None),
        ("anniversary", "sunny", [], None, 2),
    ]
    images = []
    for i, (name, kind, bdays, monthly, years) in enumerate(cases):
        word = pick_word(today + dt.timedelta(days=i))  # a different word per sample
        img = to_panel_colors(render(mock_weather(kind), word, today, bdays, monthly, years))
        img.save(out_dir / f"{name}.png")
        images.append(img)
        print(f"Saved {out_dir / (name + '.png')}")
    contact_sheet(images, out_dir / "all.png")
    if args.open:
        subprocess.run(["open", str(out_dir / "all.png")])


def render_holidays(args):
    """Render every special day in dates.csv, on the date it falls on this year."""
    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    out_dir = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    kinds = ("sunny", "cloudy", "rain", "cold", "snow")
    found = []
    for row in load_dates():
        key = holiday_key(row["name"])
        if key:
            year = (row.get("year") or "").strip()
            found.append((row_date(row, today.year), key, int(year) if year else None, row["name"]))
    found.sort()
    images = []
    for i, (day, key, year, name) in enumerate(found):
        holiday = (key, year)
        img = to_panel_colors(render(mock_weather(kinds[i % len(kinds)]), word_for(day, holiday), day,
                                     holiday=holiday))
        img.save(out_dir / f"holiday_{key}.png")
        images.append(img)
        print(f"{day}  {name}")
    contact_sheet(images, out_dir / "holidays.png")
    if args.open:
        subprocess.run(["open", str(out_dir / "holidays.png")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", choices=["sunny", "rain", "cold", "snow", "cloudy"],
                    help="force a fake weather type instead of fetching the real forecast")
    ap.add_argument("--open", action="store_true", help="open result in Preview (macOS)")
    ap.add_argument("--all", action="store_true",
                    help="render every version + a contact sheet (out/all.png)")
    ap.add_argument("--holidays", action="store_true",
                    help="render every special day from dates.csv + a contact sheet (out/holidays.png)")
    ap.add_argument("--color", action="store_true",
                    help="use all 4 panel colors (default is black & white only)")
    ap.add_argument("--date", help="pretend today is YYYY-MM-DD (to test celebrations)")
    ap.add_argument("--out", default="out/preview.png")
    args = ap.parse_args()

    global RED, YELLOW, PALETTE
    if not args.color:  # black & white mode: accents become black, yellow becomes white
        RED, YELLOW, PALETTE = BLACK, WHITE, [BLACK, WHITE]

    if args.all:
        render_all(args)
        return
    if args.holidays:
        render_holidays(args)
        return

    if args.weather:
        weather = mock_weather(args.weather)
    else:
        try:
            weather = live_weather(LAT, LON)
        except Exception as e:  # no internet etc.
            print(f"Could not fetch live weather ({e}); using mock sunny instead.")
            weather = mock_weather("sunny")

    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    holiday = todays_holiday(today)
    word = word_for(today, holiday)
    birthdays = todays_birthdays(today)
    monthly, years = relationship_celebration(today)
    img = to_panel_colors(render(weather, word, today, birthdays, monthly, years, holiday))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"Saved {out} ({img.size[0]}x{img.size[1]}, weather={weather['kind']})")
    codes = {BLACK: 0, WHITE: 1}
    if args.color:
       codes.update({YELLOW: 2, RED: 3})
    save_panel_bin(img, out.with_suffix(".bin"), codes)
    if args.open:
        subprocess.run(["open", str(out)])


if __name__ == "__main__":
    main()
