#!/usr/bin/env python3
"""
Morning e-paper renderer: Spanish word of the day + weather + a little dachshund.

Produces a 648x480 image restricted to black & white by default
(use --color for the panel's 4 colors: black, white, red, yellow), so the preview on your Mac looks like
what the real display will show.

Celebrations (the dog jumps, wears a party hat and there is confetti):
  - birthdays from data/birthdays.csv
  - July 4th: America's birthday (patriotic dog with an Uncle Sam hat and a flag)
  - monthlyversary on the 3rd of every month (see ANNIVERSARY below)
  - anniversary on April 3: a big "Happy Anniversary!" card takes over the display

Usage:
    python render.py                        # live weather for CITY (see top of file), Fahrenheit
    python render.py --weather rain         # fake weather: sunny | cloudy | rain | cold | snow
    python render.py --all --open           # every version as one overview image
    python render.py --date 2026-04-03      # pretend it is another day (test celebrations)
    python render.py --color                # use all 4 panel colors instead of black & white
"""
import argparse
import csv
import datetime as dt
import json
import math
import random
import re
import subprocess
import urllib.request
from pathlib import Path

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


def is_july_4th(today):
    return today.month == 7 and today.day == 4


def is_america(name):
    """July 4th is built in, so skip a birthdays.csv row that is just 'America' (avoids a double banner)."""
    n = re.sub(r"[^a-z]", "", name.lower())
    return n.startswith("america") or n in ("usa", "us", "unitedstates", "theusa")


def todays_birthdays(today):
    """List of (name, age_or_None) for people whose birthday is today."""
    path = DATA_DIR / "birthdays.csv"
    if not path.exists():
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if is_america(row["name"]):
                continue
            if int(row["month"]) == today.month and int(row["day"]) == today.day:
                year = (row.get("year") or "").strip()
                out.append((row["name"].strip(), today.year - int(year) if year else None))
    return out

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

def mock_weather(kind):
    presets = {
        "sunny": dict(kind="sunny", label="Sunny", high=75, low=57, rain=5),
        "rain": dict(kind="rain", label="Rain", high=59, low=50, rain=80),
        "cold": dict(kind="cold", label="Cold", high=36, low=25, rain=10),
        "snow": dict(kind="snow", label="Snow", high=30, low=21, rain=70),
        "cloudy": dict(kind="cloudy", label="Cloudy", high=64, low=54, rain=20),
    }
    return presets[kind]


def live_weather(lat, lon):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max&temperature_unit=fahrenheit"
        "&timezone=auto&forecast_days=1"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        d = json.load(r)["daily"]
    code = d["weather_code"][0]
    high, low = round(d["temperature_2m_max"][0]), round(d["temperature_2m_min"][0])
    rain = d["precipitation_probability_max"][0] or 0
    if code in (71, 73, 75, 77, 85, 86):
        kind, label = "snow", "Snow"
    elif code >= 51 or rain >= 50:
        kind, label = "rain", "Rain"
    elif high <= 41:
        kind, label = "cold", "Cold"
    elif code <= 1:
        kind, label = "sunny", "Sunny"
    else:
        kind, label = "cloudy", "Cloudy"
    return dict(kind=kind, label=label, high=high, low=low, rain=rain)


# ---------------------------------------------------------------- drawing

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
            d.ellipse([px - 2, py - 2, px + 2, py + 2], fill=BLACK)


def draw_sam_hat(d, hx, hoy):
    """Uncle Sam style top hat: striped crown, band with a star."""
    top, base = hoy + 46, hoy + 90
    d.rectangle([hx - 16, top, hx + 14, base], fill=WHITE, outline=BLACK, width=3)
    for x in range(hx - 12, hx + 12, 8):
        d.rectangle([x, top + 3, x + 3, base - 14], fill=RED)
    d.rectangle([hx - 16, base - 14, hx + 14, base], fill=BLACK)
    draw_star(d, hx - 1, base - 7, 5, WHITE)
    d.rounded_rectangle([hx - 28, base - 2, hx + 26, base + 6], radius=3, fill=BLACK)


def draw_dachshund(d, ox, oy, kind, celebrate=False, patriotic=False):
    """A long, low dachshund facing left. (ox, oy) = top-left of a ~250x230 area.
    Idle pose: head up, tail curled, one front paw lifted.
    Celebrating pose: mid-jump with a party hat, tongue out, wagging tail, confetti."""
    ground = oy + 206
    orig_oy = oy
    if celebrate:
        oy -= 24                      # jump!
    hoy = oy - 8                      # head sits a little high
    hx = ox + 48

    # tail (curled up) and wag lines
    tip = (ox + 236, oy + 80) if celebrate else (ox + 230, oy + 92)
    d.line([(ox + 206, oy + 142), (ox + 226, oy + 130), (ox + 236, oy + 108), tip],
           fill=BLACK, width=9, joint="curve")
    if celebrate:
        for (x1, y1), (x2, y2) in [((248, 96), (262, 88)), ((250, 108), (264, 108)), ((248, 120), (262, 128))]:
            d.line([(ox + x1, oy + y1), (ox + x2, oy + y2)], fill=BLACK, width=3)

    # legs (drawn before the body so it overlaps them)
    if celebrate:
        limb(d, (ox + 72, oy + 170), (ox + 38, oy + 178))     # front legs reaching forward
        limb(d, (ox + 98, oy + 174), (ox + 66, oy + 194))
        limb(d, (ox + 176, oy + 176), (ox + 194, oy + 202))   # back legs kicked out
        limb(d, (ox + 204, oy + 174), (ox + 224, oy + 196))
        d.ellipse([ox + 40, ground - 5, ox + 222, ground + 7], outline=BLACK, width=2)  # shadow
    else:
        for lx in (ox + 92, ox + 170, ox + 200):
            d.rounded_rectangle([lx, oy + 168, lx + 20, ground], radius=8,
                                fill=YELLOW, outline=BLACK, width=4)
        limb(d, (ox + 72, oy + 172), (ox + 46, oy + 190))     # lifted front paw
        d.line([ox + 30, ground + 1, ox + 226, ground + 1], fill=BLACK, width=3)

    # body
    d.rounded_rectangle([ox + 50, oy + 128, ox + 214, oy + 186], radius=29,
                        fill=YELLOW, outline=BLACK, width=4)

    # snout, head, nose, mouth, ear
    d.rounded_rectangle([ox - 14, hoy + 106, ox + 44, hoy + 134], radius=13,
                        fill=YELLOW, outline=BLACK, width=4)
    d.ellipse([ox + 18, hoy + 88, ox + 80, hoy + 142], fill=YELLOW, outline=BLACK, width=4)
    d.ellipse([ox - 18, hoy + 106, ox, hoy + 122], fill=BLACK)
    if celebrate:  # tongue out
        d.ellipse([ox + 8, hoy + 124, ox + 26, hoy + 148], fill=RED, outline=BLACK, width=3)
    d.arc([ox + 6, hoy + 118, ox + 40, hoy + 136], 0, 90, fill=BLACK, width=3)
    d.ellipse([ox + 56, hoy + 98, ox + 92, hoy + 156], fill=BLACK)

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

    # accessories
    if patriotic:
        draw_sam_hat(d, hx, hoy)
    elif celebrate:  # party hat
        d.polygon([(hx - 16, hoy + 92), (hx + 14, hoy + 92), (hx - 1, hoy + 52)],
                  fill=RED, outline=BLACK)
        d.ellipse([hx - 7, hoy + 44, hx + 5, hoy + 56], fill=WHITE, outline=BLACK, width=2)
    if patriotic:  # flag planted on the dog's back
        px = ox + 112
        d.line([(px, oy + 132), (px, oy + 4)], fill=BLACK, width=5)
        d.ellipse([px - 5, oy - 4, px + 5, oy + 6], fill=BLACK)
        draw_flag(d, px + 3, oy + 10, 76, 49)
    if kind == "rain" and not patriotic:  # umbrella tucked into the dog's back
        cx = ox + 135
        d.pieslice([cx - 95, oy + 6, cx + 95, oy + 74], 180, 360, fill=RED, outline=BLACK, width=4)
        d.line([cx, oy + 40, cx, oy + 130], fill=BLACK, width=5)
    if kind in ("cold", "snow"):  # striped scarf, just behind the ear
        d.rectangle([ox + 86, oy + 128, ox + 112, oy + 154], fill=YELLOW, outline=BLACK, width=3)
        d.rectangle([ox + 90, oy + 152, ox + 108, oy + 184], fill=YELLOW, outline=BLACK, width=3)
        for sy in (136, 146):
            d.line([ox + 87, oy + sy, ox + 111, oy + sy], fill=RED, width=4)
        for sy in (162, 172):
            d.line([ox + 91, oy + sy, ox + 107, oy + sy], fill=RED, width=4)

    # confetti
    if celebrate:
        for dx, dy, shape in [(-8, 34, "sq"), (8, 2, "ci"), (78, -10, "sq"), (112, 22, "ci"),
                              (160, -4, "ci"), (198, 14, "sq"), (236, 40, "ci"), (250, 10, "sq"),
                              (-12, 92, "ci"), (238, 150, "sq")]:
            if patriotic and 100 <= dx <= 200 and -20 <= dy <= 42:
                continue  # keep the flag clear
            x, y = ox + dx, orig_oy + dy
            if shape == "sq" and patriotic:
                draw_star(d, x + 5, y + 5, 7, RED)
            elif shape == "sq":
                d.rectangle([x, y, x + 8, y + 8], fill=RED)
            else:
                d.ellipse([x, y, x + 10, y + 10], outline=BLACK, width=3)


def draw_anniversary(d, years, weather):
    """The big anniversary takeover: framed message on the left, short weather line below."""
    d.rounded_rectangle([24, 84, 338, 296], radius=18, outline=BLACK, width=6)
    d.rounded_rectangle([34, 94, 328, 286], radius=12, outline=BLACK, width=2)
    cx = 181
    d.text((cx, 120), "HAPPY", font=font(28, True), fill=BLACK, anchor="mm")
    d.text((cx, 160), "Anniversary!", font=fit_font(d, "Anniversary!", 270, 46), fill=BLACK, anchor="mm")

    num = str(years)
    side1 = "year" if years == 1 else "years"
    nf, sf1, sf2 = font(92, True), font(32, True), font(22, True)
    nw = d.textlength(num, font=nf)
    sw = max(d.textlength(side1, font=sf1), d.textlength("together", font=sf2))
    x0 = cx - (nw + 14 + sw) / 2
    d.text((x0, 214), num, font=nf, fill=BLACK, anchor="lm")
    d.text((x0 + nw + 14, 200), side1, font=sf1, fill=BLACK, anchor="lm")
    d.text((x0 + nw + 14, 230), "together", font=sf2, fill=BLACK, anchor="lm")
    for hx in (cx - 44, cx, cx + 44):
        draw_heart(d, hx - 6, 266, 6, RED)

    line = f"{weather['label']}   {weather['high']}\u00b0 / {weather['low']}\u00b0   \u2022   {weather['rain']}% rain"
    d.text((24, 316), line, font=fit_font(d, line, 310, 24), fill=BLACK, anchor="lm")


def draw_word(d, word):
    """Bottom strip: the Spanish word of the day and what it means."""
    d.line([24, 372, W - 24, 372], fill=BLACK, width=3)
    d.text((W - 24, 384), "PALABRA DEL D\u00cdA", font=font(14, True), fill=RED, anchor="ra")
    d.text((W - 24, 404), word["type"], font=font(18), fill=BLACK, anchor="ra")
    d.text((24, 378), word["word"], font=fit_font(d, word["word"], 430, 42), fill=BLACK, anchor="la")
    mfont = font(20)
    y = 430
    for line in wrap(d, word["meaning"], mfont, W - 48)[:2]:
        d.text((24, y), line, font=mfont, fill=BLACK)
        y += 24


def render(weather, word, today, birthdays=(), monthly=None, years=None):
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    july4 = is_july_4th(today)
    celebrate = bool(birthdays or monthly or years or july4)

    # header bar
    d.rectangle([0, 0, W, 70], fill=BLACK)
    d.text((24, 12), today.strftime("%A"), font=font(34, True), fill=WHITE)
    d.text((W // 2 - 6, 35), CITY, font=font(22), fill=WHITE, anchor="mm")
    d.text((W - 24, 22), today.strftime("%d %B %Y"), font=font(24), fill=YELLOW, anchor="ra")

    if years:
        draw_anniversary(d, years, weather)
    else:
        # weather panel (left)
        draw_weather_icon(d, weather["kind"], 100, 150)
        d.text((24, 210), f"{weather['high']}\u00b0", font=font(64, True), fill=BLACK)
        d.text((140, 245), f"/ {weather['low']}\u00b0", font=font(30), fill=BLACK)
        d.text((24, 295), weather["label"], font=font(26, True), fill=RED)
        d.text((24, 328), f"Rain chance: {weather['rain']}%", font=font(20), fill=BLACK)

    # dachshund (right)
    draw_dachshund(d, 366, 112, weather["kind"], celebrate=celebrate, patriotic=july4)

    # celebration banner (birthday and/or monthlyversary)
    msgs = []
    if monthly:
        msgs.append(f"Happy monthlyversary! Month {monthly}")
    if birthdays:
        names = ", ".join(f"{n} ({a})" if a else n for n, a in birthdays)
        msgs.append(f"Happy birthday {names}!")
    if july4:
        msgs.append(f"Happy birthday, America! ({today.year - 1776})")
    if msgs:
        text = "  \u2022  ".join(msgs)
        bf = fit_font(d, text, 380, 20)
        d.rectangle([224, 340, W - 24, 368], fill=YELLOW, outline=BLACK, width=2)
        d.text(((224 + W - 24) / 2, 354), text, font=bf, fill=RED, anchor="mm")

    draw_word(d, word)
    return img


def to_panel_colors(img):
    """Snap every pixel to the nearest of the 4 panel colors (with dithering)."""
    pal_img = Image.new("P", (1, 1))
    flat = [c for rgb in PALETTE for c in rgb]
    pal_img.putpalette(flat + [0] * (768 - len(flat)))
    return img.quantize(palette=pal_img, dither=Image.Dither.NONE).convert("RGB")


def render_all(args):
    """Render every weather type plus the celebration versions, and a contact sheet."""
    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    out_dir = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    # (file name, weather kind, birthdays, monthly, years)
    cases = [(k, k, [], None, None) for k in ("sunny", "cloudy", "rain", "cold", "snow")]
    cases += [
        ("birthday", "sunny", [("Alex", 36)], None, None),
        ("monthlyversary", "cloudy", [], 7, None),
        ("anniversary", "sunny", [], None, 2),
        ("july4", "sunny", [], None, None),
    ]
    images = []
    for i, (name, kind, bdays, monthly, years) in enumerate(cases):
        w = mock_weather(kind)
        word = pick_word(today + dt.timedelta(days=i))  # a different word per sample
        day = dt.date(today.year, 7, 4) if name == "july4" else today
        img = to_panel_colors(render(w, word, day, bdays, monthly, years))
        img.save(out_dir / f"{name}.png")
        images.append(img)
        print(f"Saved {out_dir / (name + '.png')}")
    cols, rows = 3, 3
    sheet = Image.new("RGB", (W * cols + 10 * (cols + 1), H * rows + 10 * (rows + 1)), (150, 150, 150))
    for i, img in enumerate(images):
        sheet.paste(img, (10 + (i % cols) * (W + 10), 10 + (i // cols) * (H + 10)))
    sheet.save(out_dir / "all.png")
    print(f"Saved {out_dir / 'all.png'}")
    if args.open:
        subprocess.run(["open", str(out_dir / "all.png")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", choices=["sunny", "rain", "cold", "snow", "cloudy"],
                    help="force a fake weather type instead of fetching the real forecast")
    ap.add_argument("--open", action="store_true", help="open result in Preview (macOS)")
    ap.add_argument("--all", action="store_true",
                    help="render every version + a contact sheet (out/all.png)")
    ap.add_argument("--color", action="store_true",
                    help="use all 4 panel colors (default is black & white only)")
    ap.add_argument("--date", help="pretend today is YYYY-MM-DD (to test birthdays)")
    ap.add_argument("--out", default="out/preview.png")
    args = ap.parse_args()

    global RED, YELLOW, PALETTE
    if not args.color:  # black & white mode: accents become black, yellow becomes white
        RED, YELLOW, PALETTE = BLACK, WHITE, [BLACK, WHITE]

    if args.all:
        render_all(args)
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
    word = pick_word(today)
    birthdays = todays_birthdays(today)
    monthly, years = relationship_celebration(today)
    img = to_panel_colors(render(weather, word, today, birthdays, monthly, years))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"Saved {out} ({img.size[0]}x{img.size[1]}, weather={weather['kind']})")
    if args.open:
        subprocess.run(["open", str(out)])


if __name__ == "__main__":
    main()
