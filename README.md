# epaper-morning

Daily Spanish word + weather + a little dachshund, rendered for a 648x480 e-paper panel.
Black & white by default; add `--color` for the panel's 4 colors (black/white/red/yellow). Preview it on your Mac, no hardware needed.

## Setup (macOS)
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

## Preview
    python render.py --weather rain --open     # fake weather: sunny | cloudy | rain | cold | snow
    python render.py --all --open              # every version + birthday, as one overview (out/all.png)
    python render.py                           # live Chicago weather in °F (Open-Meteo, no API key)

Output goes to `out/preview.png`.

## Celebrations
The dog jumps, wears a party hat and there is confetti whenever there is something to celebrate:
- **Birthdays** (`data/birthdays.csv`): banner "Happy birthday Alex (36)!"
- **July 4th**: America's birthday. The dog wears an Uncle Sam hat, waves a flag and stars replace the confetti.
  Banner: "Happy birthday, America! (250)" (the number counts up every year). It's built in, so you don't need a row in
  `birthdays.csv` (if you add one named "America", it's ignored to avoid a double banner).
- **Monthlyversary** on the 3rd of every month: banner "Happy monthlyversary! Month N"
- **Anniversary** on April 3: a big "Happy Anniversary! N years together" card takes over the display
  (weather shrinks to one line, the word of the day stays).

The start date is `ANNIVERSARY = dt.date(2024, 4, 3)` at the top of `render.py`.
Test any day with `--date`, e.g. `python render.py --weather rain --date 2026-04-03 --open`.

## Your data (lives in the repo)
- `data/words.csv`: `word,type,meaning`. One word per day, shown as "Palabra del día" with a short
  English description. It goes through the whole list in a shuffled order before repeating, and the
  word stays the same all day. Phrases work too (set type to `phrase`). Add as many as you like!
- `data/birthdays.csv`: `name,month,day,year`. Year is optional (leave empty to hide age).
  On a birthday the dog wears a party hat and a banner appears.

Test a birthday: `python render.py --date 2026-11-01 --open`

**Privacy:** birthdays are personal data, so keep the repo private, and think twice
before publishing the rendered image anywhere public (use first names only, or serve it
from your home network).

## Roadmap
- [x] Spanish words + birthdays from CSV files in the repo
- [ ] More dachshund poses, seasonal/birthday variants
- [ ] Export panel-ready data for the ESP32 firmware
- [ ] Scheduled rendering (GitHub Action or home server)
- [ ] ESP32 firmware (Arduino/C++): wake, download image, refresh, sleep


To change the city, edit `CITY`, `LAT` and `LON` at the top of `render.py`.
