"""
File the World Cup B PDFs of weltcup-b.org like the FIS downloads (step 2 of
fis_nk_wcb_scraper.py).

The site names its files by venue and number: 'Karpacz1.pdf' (result),
'Karpacz1_SP.pdf' / '_Sprung' (jump list), '_Lauf' (cross-country), '_Training'.
All files of one number belong to one competition.  Its codex is the one of the
competition in the FIS database (category WCB) whose ranking (fis_nk_fisdb.py,
step 3, run it first) has its first five surnames in this order in the result
list; failing that, the n-th competition of the event, provided the date printed
in the PDF is within three days of it.

The ranking also corrects the FIS attachments: for some events they are filed
under the wrong competition (Chaux-Neuve 2007: 2007NK4122ROF is the Gundersen,
4122 is the sprint in the database and in its ranking).  Such PDFs are renamed
to the right codex, and .renamed.json remembers it for fis_nk_pdf_scraper.py.

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
# the first so many of a FIS ranking must stand in this order in a result list
TOP = 5


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


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    for a, b in (("oe", "o"), ("ae", "a"), ("ue", "u"), ("aa", "a")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z]+", " ", s)


def _rankings(root: Path, season: int) -> dict:
    """codex → the surnames of the first three of its FIS ranking (folded)."""
    top = {}
    for f in (root / str(season)).rglob("*FDB.json") if (root / str(season)).exists() else []:
        d = json.loads(f.read_text(encoding="utf-8"))
        names = []
        for r in d.get("combined_results", [])[:TOP]:
            surname = " ".join(w for w in r["name"].split() if w.isupper() and len(w) > 1) or r["name"].split()[0]
            names.append(_fold(surname).strip())
        if len(names) >= 3:
            top[d["codex"]] = names
    return top


def _ranked_in_order(text: str, names: list):
    """Where the last of the names stands if they stand in this order in the text, else None."""
    at = 0
    for n in names:
        i = text.find(" " + n + " ", at)
        if i < 0:
            return None
        at = i + len(n)
    return at


def _codex_by_ranking(path: Path, codices, rankings: dict):
    """The codex whose FIS ranking stands in this result list, if exactly one does."""
    try:
        with pdfplumber.open(path) as pdf:
            text = " " + _fold(" ".join((pg.extract_text() or "") for pg in pdf.pages[:2])) + " "
    except Exception:
        return None
    # a ranking can also stand further down in another list (the best of the sprint in the
    # Gundersen): of several, the one whose names come first
    hits = sorted((at, c) for c in codices if c in rankings
                  for at in [_ranked_in_order(text, rankings[c])] if at is not None)
    if not hits or (len(hits) > 1 and hits[1][0] - hits[0][0] < 200):
        return None
    return hits[0][1]


def _fix_fis_attachments(root: Path, season: int, events: list, rankings: dict, fis_names: set, dry_run: bool) -> dict:
    """Rename FIS PDFs filed under the wrong competition; returns {old name: new name}."""
    renamed = {}
    for folder, races in events:
        by_codex = {r["codex"]: r for r in races}
        base = root / str(season) / folder
        moves = {}
        for rof in base.rglob("*ROF.pdf") if base.exists() else []:
            own = re.search(r"NK(\d{4})ROF\.pdf$", rof.name)
            if not own or rof.name.rsplit("_", 1)[-1].lower() not in fis_names:
                continue
            right = _codex_by_ranking(rof, by_codex, rankings)
            if right and right != own.group(1):
                moves[own.group(1)] = right
        # only a consistent exchange: no two to one codex, and the target is free or moves away itself
        held = {re.search(r"NK(\d{4})ROF\.pdf$", p.name).group(1) for p in base.rglob("*ROF.pdf")
                if re.search(r"NK(\d{4})ROF\.pdf$", p.name) and p.name.rsplit("_", 1)[-1].lower() in fis_names} \
            if base.exists() else set()
        targets = list(moves.values())
        moves = {old: new for old, new in moves.items()
                 if targets.count(new) == 1 and (new not in held or new in moves)}
        for old, new in moves.items():
            race = by_codex[new]
            for p in base.rglob(f"*NK{old}*.pdf"):
                if p.name.rsplit("_", 1)[-1].lower() not in fis_names:
                    continue
                doc_type = re.search(rf"NK{old}([A-Z0-9]+)\.pdf$", p.name).group(1)
                g = race["gender"] if race["gender"] in ("M", "W") else "X"
                new_name = f"{new}_{race['date']}_{race['name']}_{g}_{season}NK{new}{doc_type}.pdf"
                renamed[p] = p.with_name(new_name)
    if not dry_run:
        # two steps, as two competitions may swap
        temp = {p: p.with_name(p.name + ".moving") for p in renamed}
        for p, t in temp.items():
            p.rename(t)
        for p, t in temp.items():
            t.rename(renamed[p])
    for p, q in renamed.items():
        print(f"  FIS attachment renamed: {p.relative_to(root)}  →  {q.name}")
    return {p.name.rsplit("_", 1)[-1].lower(): q.name.rsplit("_", 1)[-1].lower() for p, q in renamed.items()}


def file_all(root: Path, dry_run: bool = False) -> None:
    session = requests.Session()
    fis_names = _fis_files(root)
    renamed_path = root / ".renamed.json"
    try:
        renamed = json.loads(renamed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        renamed = {}
    # a renamed attachment is there under its new name only
    fis_names = (fis_names - set(renamed)) | set(renamed.values())
    filed, skipped, unmatched = 0, 0, []

    # copies of an earlier run are made again; the FIS downloads stay
    if not dry_run:
        for p in root.glob("20*/*/*/*.pdf"):
            if p.name.rsplit("_", 1)[-1].lower() not in fis_names:
                p.unlink()

    for raw_season in sorted((root / "_raw").iterdir()):
        season = int(raw_season.name[:4]) + 1                       # '2004_05' → 2005
        events = season_events(season, session)
        rankings = _rankings(root, season)
        moved = _fix_fis_attachments(root, season, events, rankings, fis_names, dry_run)
        renamed.update(moved)
        fis_names = (fis_names - set(moved)) | set(moved.values())

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
            # 1. the competition whose FIS ranking stands in the result list
            if any(t == "ROF" for _, t in files):
                for f, races in candidates:
                    codex = _codex_by_ranking(main, [r["codex"] for r in races], rankings)
                    if codex:
                        race, folder = next(r for r in races if r["codex"] == codex), f
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
    if renamed and not dry_run:
        renamed_path.write_text(json.dumps(renamed, indent=0, sort_keys=True), encoding="utf-8")
    print(f"filed {filed}, skipped {skipped} (FIS has that list), unmatched {len(unmatched)}")
    for path, why in unmatched:
        print(f"  unmatched: {path.relative_to(root)}: {why}")
