# epaper-morning

Daily Spanish word + weather + a little dachshund, rendered for a 648x480 e-paper panel.
Black & white by default; add `--color` for the panel's 4 colors (black/white/red/yellow).
Preview it on your Mac, no hardware needed.

## Setup (macOS)
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

## Preview
    python render.py --weather rain --open     # fake weather: sunny | cloudy | rain | cold | snow
    python render.py                           # live Chicago weather in °F (Open-Meteo, no API key)
    python render.py --all --open              # weather versions + personal celebrations in one image
    python render.py --holidays --open         # every special day, on its date this year
    python render.py --date 2026-11-26 --open  # pretend it is another day

Output goes to `out/preview.png`. To change the city, edit `CITY`, `LAT` and `LON` at the top of `render.py`.

## Layout
Everything on screen is in English except the word card, which is the one place Spanish is taught.
- **Header:** weekday, city, date
- **Left:** the weather card: big temperature, feels-like and wind, a four-slot forecast (morning, noon,
  afternoon, evening) and sunrise/sunset. Real data comes from Open-Meteo; if the fetch fails it falls back to sample weather.
- **Right:** the dog in its scene, standing on a bit of grass. The weather shows in the sky (rain, snow, sun...).
  The dog's size is `DOG_SCALE` at the top of the layout section in `render.py`.
- **Banner:** a one-line banner appears under them only on celebration days (birthdays, monthlyversary, special days).
- **Bottom:** the word card with the word, pronunciation, meaning, a Spanish example and its translation.
- **Anniversary:** on April 3 the big anniversary card replaces the weather card.

## Your data (lives in the repo)
- `data/words.csv`: `word,type,meaning,pronunciation,example,translation`. One word per day in the
  "Palabra del día" card. It goes through the whole list in a shuffled order before repeating, and the
  word stays the same all day. Phrases work too (set type to `phrase`). `pronunciation` is a respelling
  for a Spain accent (stressed syllable in CAPS, "th" as in "think"). Only `word`, `type` and `meaning`
  are required; the card simply skips what's empty.
- `data/dates.csv`: **every date lives here**: `name,month,day,year,rule`
  - **People:** `Alex,11,1,1990,`. Year is optional (leave it empty to hide the age).
  - **Special days** (US bank holidays and more, see below): the row's *name* decides what it is.
  - **Floating dates:** leave `day` empty and fill `rule`: `4th thu` (Thanksgiving), `last mon`
    (Memorial Day), `3rd mon`, `2nd sun`... or `easter`, which is calculated for you every year.
  - Special-day names must be one of the names listed in `HOLIDAY_NAMES` in `render.py`
    (case, accents and punctuation don't matter). Matching is exact on purpose, so a friend called
    "Pascual" or "Valentine" is never mistaken for Easter or Valentine's Day.

## Celebrations
The dog jumps, wears a costume and there is confetti whenever there is something to celebrate:
- **Birthdays**: banner "Happy birthday Alex (36)!"
- **Monthlyversary** on the 3rd of every month: banner "Happy monthlyversary! Month N"
- **Anniversary** on April 3: a big "Happy Anniversary! N years together" card takes over the display
  (weather shrinks to one line, the word of the day stays). The start date is `ANNIVERSARY` in `render.py`.
- **Special days**: each has its own costume, banner and Spanish word of the day.

| Day | Dog | Word of the day |
|---|---|---|
| New Year's Day | party hat, clock at midnight | Año Nuevo |
| Martin Luther King Jr. Day | calm, with a heart | sueño |
| Valentine's Day | hearts everywhere | San Valentín |
| Presidents' Day | Uncle Sam hat + flag | presidente |
| Easter (calculated) | bunny ears, eggs | Semana Santa |
| Mother's Day (2nd Sun May) | hearts | madre |
| Memorial Day (last Mon May) | calm, with a small flag | recuerdo |
| Father's Day (3rd Sun Jun) | hearts | padre |
| Juneteenth | party hat | libertad |
| July 4th (`America`) | Uncle Sam hat + waving flag, stars. Banner shows America's age | fuegos artificiales |
| Labor Day (1st Mon Sep) | hard hat | trabajo |
| Columbus Day (2nd Mon Oct) | calm | festivo |
| Halloween | witch hat, pumpkin, bats | calabaza |
| Veterans Day | calm, with a small flag | agradecer |
| Thanksgiving (4th Thu Nov) | pilgrim hat, pumpkin, leaves | Acción de Gracias |
| Christmas | Santa hat, a present, snowflakes | Feliz Navidad |
| New Year's Eve | party hat, clock at 11:58, stars | Nochevieja |

On cold and snowy days the dog also wears a knitted sweater, plus a beanie when it isn't already wearing a hat.

On solemn days (MLK Day, Memorial Day, Veterans Day, Columbus Day) the dog keeps its calm everyday pose.
Costumes, banners and words are set in the `HOLIDAYS` table in `render.py`.
To remove a special day, delete its row from `dates.csv`.

**Privacy:** `dates.csv` has your friends' birthdays, so keep the repo private, and think twice
before publishing the rendered image anywhere public (use first names only, or serve it
from your home network).

## Roadmap
- [x] Spanish words + dates from CSV files in the repo
- [x] US bank holidays and more, including floating dates (Thanksgiving, Easter...)
- [ ] More dachshund poses
- [ ] Export panel-ready data for the ESP32 firmware
- [ ] Scheduled rendering (GitHub Action or home server)
- [ ] ESP32 firmware (Arduino/C++): wake, download image, refresh, sleep
