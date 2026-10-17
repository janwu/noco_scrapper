"""
File the World Cup B PDFs of weltcup-b.org like the FIS downloads (step 2 of
fis_nk_wcb_scraper.py).

The site names its files by venue and number: 'Karpacz1.pdf' (result),
'Karpacz1_SP.pdf' / '_Sprung' (jump list), '_Lauf' (cross-country), '_Training'.
All files of one number belong to one competition, which gets its codex like this:

- if FIS has result PDFs of the event, the one with the same date and kind of
  competition (team, mass start, sprint, individual) in its heading;  the FIS
  database and its attachments disagree for some events (Chaux-Neuve 2007:
  the database has 4122 as the sprint, the PDF 2007NK4122ROF is the Gundersen),
  and the PDFs are what gets parsed;
- else the n-th competition of the event in the FIS database (category WCB),
  provided the date printed in the PDF is within three days of it.

A file is then copied to the layout of the FIS downloads

    fis_nk_wcb_pdfs/<season>/<from>_<to>_<VENUE>_<NAT>/M/<codex>_<date>_<race>_M_<season>NK<codex><type>.pdf

unless FIS has the same kind of list for that competition.  Files that match
no competition are listed (coaches' race, team slalom, triathlon).
"""
import datetime
import json
import re
import shutil
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import pdfplumber
import requests

import fis_nk_pdf_scraper as fis

KINDS = {"": "ROF", "sp": "RL", "sprung": "RL", "ssprung": "RL", "lauf": "RLLL", "training": "RLT"}
FILE_RE = re.compile(r"^(?P<place>[A-Za-z][A-Za-z_ \-]*?)(?P<n>\d?)(?:_(?P<kind>SP|Sprung|Ssprung|Lauf|Training))?\.pdf$",
                     re.IGNORECASE)
# venues the site names differently from the FIS database
PLACE_ALIASES = {"hoydalsmo": "hoeydalsmo", "kthal": "klingenthal", "othal": "oberwiesenthal", "kuusamo": "ruka"}
# dates in the PDF this far from the date in the FIS database still belong to the competition
# (a training the days before; a few competitions were moved by a day or two)
DAYS = 3


def _key(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def _head(path: Path, lines: int = 14) -> str:
    try:
        with pdfplumber.open(path) as pdf:
            return "\n".join((pdf.pages[0].extract_text() or "").split("\n")[:lines])
    except Exception:
        return ""


def kind_of(text: str) -> str:
    """team / mass / sprint / ind / ? from the heading of a list or a race name."""
    t = text.lower()
    if re.search(r"\bteam\b|staffel|relay|mannschaft|3\s*x\s*5|4\s*x\s*5|druzstv|joukkue", t):
        return "team"
    if re.search(r"mass\s*start|massenstart|hromadn", t):
        return "mass"
    if re.search(r"sprint", t):
        return "sprint"
    if re.search(r"gundersen|individual|einzel|15\s*km", t):
        return "ind"
    return "?"


def _dates(text: str, season: int) -> list:
    """The dates of the season in a text, in order ('21.01.2001', '15.1.2003', 'SUN 18 MAR 2007', '12/17/2005')."""
    found = []
    for m in re.finditer(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{2,4})\b|\b(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})\b"
                         r"|\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text):
        try:
            if m.group(1):
                y = int(m.group(3))
                y = y + 2000 if y < 100 else y
                d = datetime.date(y, int(m.group(2)), int(m.group(1)))
            elif m.group(4):
                month = fis.MONTH_MAP.get(m.group(5).lower()[:3])
                if not month:
                    continue
                d = datetime.date(int(m.group(6)), month, int(m.group(4)))
            else:
                d = datetime.date(int(m.group(9)), int(m.group(7)), int(m.group(8)))
        except ValueError:
            continue
        s = d.strftime("%Y%m%d")
        if f"{season - 1}0801" <= s <= f"{season}0531":
            found.append(s)
    return found


def _near(date: str, dates) -> bool:
    day = datetime.date(int(date[:4]), int(date[4:6]), int(date[6:]))
    return any(abs((datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])) - day).days) <= DAYS for d in dates)


def season_events(season: int, session: requests.Session) -> list:
    """[(folder_name, [race, ...])] of the World Cup B events of a season, races in date order."""
    for attempt in range(3):                       # the FIS site does not always answer at once
        events = fis.get_events_for_season("WCB", season, session)
        if events:
            break
        time.sleep(10)
    out = []
    for event in events:
        read = None
        for attempt in range(3):
            read = fis.read_event(event, session)
            if read is not None:
                break
            time.sleep(10)
        if read is None:
            raise RuntimeError(f"event page of {event['url']} could not be read")
        _, folder, races, _ = read
        ordered = sorted((r for r in races.values() if r["codex"] and r["date"]),
                         key=lambda r: (r["date"], r["codex"]))
        out.append((folder, ordered))
    return out


def _fis_files(root: Path) -> set:
    """FIS names ('2005nk4170rof.pdf') of the PDFs downloaded from FIS (fis_nk_pdf_scraper)."""
    try:
        return {n.lower() for n in json.loads((root / ".attachments.json").read_text(encoding="utf-8")).values()}
    except (OSError, ValueError):
        return set()


def _fis_results(folder: Path, season: int, fis_names: set) -> list:
    """(codex, date, kind) of the FIS result PDFs of an event, read from their heading."""
    found = []
    for p in folder.rglob("*ROF.pdf") if folder.exists() else []:
        m = re.search(r"NK(\d{4})ROF\.pdf$", p.name)
        if not m or p.name.rsplit("_", 1)[-1].lower() not in fis_names:
            continue
        head = _head(p)
        dates = _dates(head, season)
        found.append((m.group(1), dates[0] if dates else None, kind_of(head)))
    return found


def file_all(root: Path, dry_run: bool = False) -> None:
    session = requests.Session()
    fis_names = _fis_files(root)
    filed, skipped, unmatched = 0, 0, []

    # copies of an earlier run are made again; the FIS downloads stay
    if not dry_run:
        for p in root.glob("20*/*/*/*.pdf"):
            if p.name.rsplit("_", 1)[-1].lower() not in fis_names:
                p.unlink()

    for raw_season in sorted((root / "_raw").iterdir()):
        season = int(raw_season.name[:4]) + 1                       # '2004_05' → 2005
        events = season_events(season, session)

        groups = defaultdict(list)                                  # (place, n) → [(path, doc type)]
        for path in sorted((raw_season / "Ergebnisse").glob("*.pdf")):
            m = FILE_RE.match(path.name)
            if not m:
                unmatched.append((path, "not a result file name"))
                continue
            place = _key(m.group("place"))
            place = next((v for k, v in PLACE_ALIASES.items() if place.startswith(k)), place)
            groups[(place, int(m.group("n") or 1))].append((path, KINDS[(m.group("kind") or "").lower()]))

        for (place, n), files in sorted(groups.items()):
            candidates = [(folder, races) for folder, races in events if place[:5] and place[:5] in _key(folder)]
            if not candidates:
                unmatched += [(p, f"no World Cup B event at '{place}' in {season}") for p, _ in files]
                continue
            main = next((p for p, t in files if t == "ROF"), files[0][0])
            head = _head(main)
            dates, kind = _dates(head, season), kind_of(head)

            race, folder = None, None
            # 1. FIS result PDFs of the event: same date and kind in their heading
            for f, races in candidates:
                hits = [c for c, d, k in _fis_results(root / str(season) / f, season, fis_names)
                        if d and d in dates[:2] and (k == kind or "?" in (k, kind))]
                if len(hits) == 1:
                    race = next((r for r in races if r["codex"] == hits[0]), None)
                    folder = f
                    if race:
                        break
            # 2. the n-th competition of the event, the date printed nearby
            if race is None:
                for f, races in candidates:
                    if len(races) >= n and (not dates or _near(races[n - 1]["date"], dates)):
                        race, folder = races[n - 1], f
                        break
            # 3. the competition of the event on the printed date
            if race is None:
                for f, races in candidates:
                    on_day = [r for r in races if r["date"] in dates]
                    if len(on_day) == 1:
                        race, folder = on_day[0], f
                        break
            if race is None:
                unmatched += [(p, f"no competition #{n} near the dates {dates[:3]}") for p, _ in files]
                continue

            for path, doc_type in files:
                if f"{season}nk{race['codex']}{doc_type}.pdf".lower() in fis_names:
                    skipped += 1
                    continue
                g = race["gender"] if race["gender"] in ("M", "W") else "X"
                name = f"{race['codex']}_{race['date']}_{race['name']}_{g}_{season}NK{race['codex']}{doc_type}.pdf"
                dest = root / str(season) / folder / (g if g != "X" else "unknown") / name
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
                print(f"  {path.relative_to(root)}  →  {dest.relative_to(root)}")
                filed += 1
    print(f"filed {filed}, skipped {skipped} (FIS has that list), unmatched {len(unmatched)}")
    for path, why in unmatched:
        print(f"  unmatched: {path.relative_to(root)}: {why}")
