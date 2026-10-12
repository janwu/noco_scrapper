#!/usr/bin/env python3
"""
FIS Nordic Combined Continental Cup - Result PDF Scraper
=========================================================
Downloads all result-related PDFs for both Men and Women across all
available seasons from the FIS website (Continental Cup, categorycode=COC).

Requirements:
    pip install requests beautifulsoup4 tqdm

Quick start (downloads all seasons 2009-2026, both genders, all results):
    python fis_nk_coc_scraper.py

Limit by range:
    python fis_nk_coc_scraper.py --from-season 2018

Limit to specific seasons:
    python fis_nk_coc_scraper.py --seasons 2023 2024 2025 2026

Preview without downloading:
    python fis_nk_coc_scraper.py --dry-run

Change output folder:
    python fis_nk_coc_scraper.py --output-dir /my/folder

Output folder structure:
    fis_nk_coc_pdfs/
    2026/
      20251128_20251130_RUKA_FIN/
        M/
          4117_20251128_Individual_Compact_Large_Hill_HS142_7.5_Km_M_2026NK4117ROF.pdf
          ...
        W/  ...

Notes:
  - Already-downloaded files are skipped automatically (safe to re-run).
  - A 1-second delay is inserted between HTTP requests to be polite.
  - Continental Cup started in season 2008/2009 (FIS code: 2009).
  - PDFs are available from the 2009 season onwards.
  - Output directory defaults to ./fis_nk_coc_pdfs (separate from WC downloads).
  - Install tqdm for a nicer progress bar: pip install tqdm
"""

import argparse
import datetime
import io
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing dependencies. Please run:\n  pip install requests beautifulsoup4 tqdm")
    sys.exit(1)

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.fis-ski.com"

# Continental Cup uses categorycode=COC
CALENDAR_URL = (
    "https://www.fis-ski.com/DB/nordic-combined/calendar-results.html"
    "?sectorcode=NK&categorycode=COC&saveselection=-1&seasonselection={season}"
)

FIRST_SEASON_WITH_PDFS = 2009   # COC started in season 2008/2009
CURRENT_SEASON = 2026

RESULT_KEYWORDS = [
    "official results",
    "results provisional competition round",
    "results list ski jumping",
    "results cross country",
    "results trial round",
    "results list official training",
    "results list",
    "result",
]

EXCLUDE_KEYWORDS = [
    "world cup standings",
    "continental cup standings",
    "nations cup standings",
    "prize money",
    "trophy",
    "standings",
    "program",
    "programme",
    "start list",
]

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FIS-NK-COC-Scraper/1.0)"}
REQUEST_DELAY = 1.0


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return BeautifulSoup(resp.text, "html.parser")


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

class SimpleProgress:
    """Minimal progress display when tqdm is not installed."""
    def __init__(self, total: int, desc: str = ""):
        self.total = total
        self.n = 0
        self.desc = desc
        self._print()

    def _print(self):
        pct = int(100 * self.n / self.total) if self.total else 100
        filled = int(30 * self.n / self.total) if self.total else 30
        bar = "#" * filled + "-" * (30 - filled)
        sys.stdout.write(f"\r  [{bar}] {self.n}/{self.total} ({pct}%)")
        sys.stdout.flush()

    def update(self, desc: str = ""):
        self.n += 1
        self._print()

    def set_postfix_str(self, s, **_):
        pass

    def close(self):
        sys.stdout.write("\n")
        sys.stdout.flush()


def make_progress(total: int, desc: str):
    if HAS_TQDM:
        return tqdm(total=total, desc=desc, unit="file", ncols=80,
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
    return SimpleProgress(total=total, desc=desc)


# ---------------------------------------------------------------------------
# Calendar scraping
# ---------------------------------------------------------------------------

def get_events_for_season(season: int, session: requests.Session) -> list:
    url = CALENDAR_URL.format(season=season)
    print(f"  Fetching COC calendar for season {season} ...")
    try:
        soup = get_soup(url, session)
    except Exception as e:
        print(f"  FAIL Could not fetch calendar: {e}")
        return []

    events = []
    seen_ids = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "event-details" not in href:
            continue
        m = re.search(r"eventid=(\d+)", href)
        if not m:
            continue
        eventid = m.group(1)
        if eventid in seen_ids:
            continue
        seen_ids.add(eventid)

        raw_text = a.get_text(" ", strip=True)
        nation_m = re.search(r"\b([A-Z]{3})\b", raw_text)
        nation = nation_m.group(1) if nation_m else "UNK"
        place = re.sub(r"\s+", "_", re.sub(r"[^\w\s]", "", raw_text.split("\n")[0].strip()))[:30]

        full_url = urljoin(BASE_URL, href)
        if "seasoncode" not in full_url:
            full_url += f"&seasoncode={season}"

        events.append({
            "eventid": eventid,
            "place": place,
            "nation": nation,
            "url": full_url,
            "season": season,
        })

    print(f"  Found {len(events)} events")
    return events


# ---------------------------------------------------------------------------
# Event detail page helpers
# ---------------------------------------------------------------------------

def parse_location(soup: BeautifulSoup) -> str:
    """Extract H1 location, e.g. "Ruka (FIN)" -> "RUKA_FIN"."""
    h1 = soup.find("h1")
    if not h1:
        return ""
    raw = h1.get_text(strip=True).upper()
    raw = re.sub(r"[()]+", "_", raw)
    raw = re.sub(r"[^A-Z0-9_]+", "_", raw)
    return re.sub(r"_+", "_", raw).strip("_")


def date_from_text(text: str, season: int) -> str:
    """Return YYYYMMDD for first 'DD Mon' found in text, or ''."""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})", text)
    if not m:
        return ""
    day = int(m.group(1))
    mon_str = m.group(2).lower()[:3]
    if mon_str not in MONTH_MAP:
        return ""
    month = MONTH_MAP[mon_str]
    year = season - 1 if month >= 10 else season
    try:
        return datetime.date(year, month, day).strftime("%Y%m%d")
    except ValueError:
        return ""


def event_name_from_text(text: str) -> str:
    """
    Extract the race event name from merged anchor text.
    Looks for the longest line that looks like a race description
    (contains discipline keywords or hill/distance info).
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Junk patterns to skip
    JUNK = re.compile(
        r"^([DPMC]+|[MW]|WC|COC|PR|review|\d{1,2}(st|nd|rd|th)?|\d{1,2}:\d{2})$",
        re.I
    )
    DATE_RE = re.compile(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", re.I
    )
    STATUS_RE = re.compile(
        r"official results|cancelled|start list|postponed", re.I
    )

    best = ""
    for line in lines:
        if JUNK.match(line):
            continue
        if DATE_RE.search(line):
            continue
        if STATUS_RE.search(line):
            continue
        # Prefer lines that look like event names
        looks_like_event = bool(re.search(
            r"\b(Hill|Sprint|Gundersen|Mass.?Start|Compact|Provisional|Team|Individual|Km|HS\d|NH|LH)\b",
            line, re.I
        ))
        if looks_like_event and len(line) > len(best):
            best = line
        elif not best and len(line) > len(best):
            best = line

    if not best:
        return "unknown"

    # Sanitise
    s = best.replace("/", "_").replace(",", ".").replace(" ", "_")
    s = re.sub(r"[^\w.]", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


def parse_all_dates(soup: BeautifulSoup, season: int) -> tuple:
    """Return (first_YYYYMMDD, last_YYYYMMDD) across all race anchors on the page."""
    dates = []
    for a in soup.find_all("a", href=True):
        if "results.html" not in a["href"] or "raceid" not in a["href"]:
            continue
        for m in re.finditer(r"(\d{1,2})\s+([A-Za-z]{3})", a.get_text(" ", strip=True)):
            day = int(m.group(1))
            mon_str = m.group(2).lower()[:3]
            if mon_str not in MONTH_MAP:
                continue
            month = MONTH_MAP[mon_str]
            year = season - 1 if month >= 10 else season
            try:
                dates.append(datetime.date(year, month, day))
            except ValueError:
                pass
    if not dates:
        return ("", "")
    dates.sort()
    return (dates[0].strftime("%Y%m%d"), dates[-1].strftime("%Y%m%d"))


# ---------------------------------------------------------------------------
# Event detail page scraping
# ---------------------------------------------------------------------------

def parse_event_page(event: dict, session: requests.Session) -> tuple:
    """
    Returns (pdfs, folder_name).

    Each pdf dict contains:
      label, url, original_filename, prefixed_filename,
      gender, category, codex, race_date, race_name
    """
    try:
        soup = get_soup(event["url"], session)
    except Exception as e:
        print(f"  FAIL Could not fetch event page: {e}")
        return [], event["eventid"]

    # --- Folder name --------------------------------------------------------
    location = parse_location(soup) or f"{event['place']}_{event['nation']}"
    date_from, date_to = parse_all_dates(soup, event["season"])
    if date_from and date_to:
        folder_name = f"{date_from}_{date_to}_{location}"
    elif date_from:
        folder_name = f"{date_from}_{location}"
    else:
        folder_name = f"{location}_{event['eventid']}"

    # --- Group anchor texts by raceid --------------------------------------
    raceid_texts = defaultdict(list)
    raceid_order = []
    raceid_codex = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)

        if "results.html" in href and "raceid" in href:
            m = re.search(r"raceid=(\d+)", href)
            if m:
                rid = m.group(1)
                if rid not in raceid_texts:
                    raceid_order.append(rid)
                raceid_texts[rid].append(text)

        # Codex from live.fis-ski.com (e.g. /nk-4117/)
        if "live.fis-ski.com" in href:
            codex_m = re.search(r"/nk-(\d{4})/", href)
            if codex_m:
                codex_val = codex_m.group(1)
                if raceid_order:
                    raceid_codex[raceid_order[-1]] = codex_val

    # --- Build per-race metadata from merged texts -------------------------
    race_meta = {}
    for rid in raceid_order:
        merged = "\n".join(raceid_texts[rid])

        codex = raceid_codex.get(rid, "")
        if not codex:
            codex_m = re.search(r"\b(\d{4})\b", merged)
            if codex_m:
                val = int(codex_m.group(1))
                if val < 1980 or val > 2100:
                    codex = codex_m.group(1)

        # Fallback: try to find a 4-digit number that isn't a year
        if not codex:
            for m in re.finditer(r"\b(\d{4})\b", merged):
                val = int(m.group(1))
                if val < 1980 or val > 2100:
                    codex = m.group(1)
                    break

        race_date = date_from_text(merged, event["season"])
        race_name = event_name_from_text(merged)

        # COC pages use "COC" as category code instead of "WC"
        gender_m = re.search(r"\b(?:COC|WC|PR)\b\s*\n?\s*\b([MW])\b", merged)
        if gender_m:
            gender = gender_m.group(1)
        else:
            tokens = re.findall(r"\b([MW])\b", merged)
            gender = tokens[-1] if tokens else "unknown"

        cat_m = re.search(r"\b(COC|WC|PR)\b", merged)
        category = cat_m.group(1) if cat_m else "COC"

        race_meta[rid] = {
            "codex":    codex,
            "date":     race_date,
            "name":     race_name,
            "gender":   gender,
            "category": category,
        }

    # --- Walk anchors again to pick up PDF links, associated to race -------
    pdfs = []
    current_rid = None

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "results.html" in href and "raceid" in href:
            m = re.search(r"raceid=(\d+)", href)
            if m:
                current_rid = m.group(1)
            continue

        if href.lower().endswith(".pdf") and "/DB/pdf/" in href:
            label = ""
            prev = a.find_previous_sibling(string=True)
            if prev:
                label = prev.strip()
            if not label and a.parent:
                label = a.parent.get_text(" ", strip=True).replace("download", "").strip()
            label = re.sub(r"\(\s*[\d.,]+\s*kb\s*\)", "", label, flags=re.I).strip()

            original_filename = href.split("/")[-1]

            if current_rid and current_rid in race_meta:
                meta = race_meta[current_rid]
                codex  = meta["codex"]  or "0000"
                date   = meta["date"]   or "00000000"
                name   = meta["name"]   or "unknown"
                gender = meta["gender"]
                g      = gender if gender in ("M", "W") else "X"
            else:
                codex, date, name, gender, g = "0000", "00000000", "unknown", "unknown", "X"

            prefix = f"{codex}_{date}_{name}_{g}_"
            prefixed_filename = prefix + original_filename

            pdfs.append({
                "label":             label,
                "url":               urljoin(BASE_URL, href),
                "original_filename": original_filename,
                "prefixed_filename": prefixed_filename,
                "gender":            gender,
                "category":          race_meta.get(current_rid, {}).get("category", "COC"),
                "codex":             codex,
                "race_date":         date,
                "race_name":         name,
            })

    return pdfs, folder_name


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def is_result_pdf(pdf: dict) -> bool:
    label = pdf["label"].lower()
    if any(kw in label for kw in EXCLUDE_KEYWORDS):
        return False
    return any(kw in label for kw in RESULT_KEYWORDS)


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------

def download_pdf(pdf: dict, dest_dir: Path, session: requests.Session,
                 dry_run: bool, counters: dict, progress) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / pdf["prefixed_filename"]

    if HAS_TQDM:
        progress.set_postfix_str(pdf["prefixed_filename"][:50], refresh=True)

    if dest_path.exists():
        counters["skipped"] += 1
        if HAS_TQDM:
            progress.update(1)
        else:
            progress.update()
        return

    if dry_run:
        counters["would_download"] += 1
        if HAS_TQDM:
            progress.update(1)
        else:
            progress.update()
        return

    try:
        resp = session.get(pdf["url"], headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=16384):
                f.write(chunk)
        counters["downloaded"] += 1
        time.sleep(REQUEST_DELAY)
    except Exception as e:
        print(f"\n  FAIL {pdf['url']}: {e}")
        counters["failed"] += 1

    if HAS_TQDM:
        progress.update(1)
    else:
        progress.update()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Download FIS Nordic Combined Continental Cup (COC) result PDFs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--from-season", type=int, default=FIRST_SEASON_WITH_PDFS, metavar="YEAR",
        help=f"Earliest season to download (default: {FIRST_SEASON_WITH_PDFS}).",
    )
    parser.add_argument(
        "--to-season", type=int, default=CURRENT_SEASON, metavar="YEAR",
        help=f"Latest season to download (default: {CURRENT_SEASON}).",
    )
    parser.add_argument(
        "--seasons", nargs="+", type=int, default=None, metavar="YEAR",
        help="Explicit season list; overrides --from-season/--to-season.",
    )
    parser.add_argument(
        "--output-dir", default="fis_nk_coc_pdfs",   # <-- separate from WC folder
        help="Root folder for downloaded PDFs (default: ./fis_nk_coc_pdfs).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be downloaded without downloading anything.",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between HTTP requests (default: 1.0).",
    )
    args = parser.parse_args()

    global REQUEST_DELAY
    REQUEST_DELAY = args.delay

    seasons = (sorted(args.seasons, reverse=True) if args.seasons
               else list(range(args.to_season, args.from_season - 1, -1)))
    output_root = Path(args.output_dir)

    if not HAS_TQDM:
        print("  Tip: pip install tqdm  for a nicer progress bar")

    season_range = f"{min(seasons)}-{max(seasons)}" if len(seasons) > 1 else str(seasons[0])
    print("=" * 65)
    print("  FIS Nordic Combined Continental Cup (COC) - Result PDF Scraper")
    print("=" * 65)
    print(f"  Seasons  : {season_range}  ({len(seasons)} seasons)")
    print(f"  Genders  : Men + Women")
    print(f"  Output   : {output_root.resolve()}")
    print(f"  Dry run  : {args.dry_run}")
    print("=" * 65)

    session = requests.Session()
    counters = {"downloaded": 0, "skipped": 0, "failed": 0, "would_download": 0}

    for season in seasons:
        print(f"\n{'-' * 65}")
        print(f"  SEASON {season}")
        print(f"{'-' * 65}")

        events = get_events_for_season(season, session)
        if not events:
            print("  (no events found - skipping)")
            continue

        for i, event in enumerate(events, 1):
            all_pdfs, folder_name = parse_event_page(event, session)
            result_pdfs = [p for p in all_pdfs if is_result_pdf(p)]

            print(f"\n  [{i}/{len(events)}] {folder_name}")
            print(f"  {len(all_pdfs)} total PDFs, {len(result_pdfs)} result-related")

            if not result_pdfs:
                continue

            progress = make_progress(len(result_pdfs), desc="  Downloading")

            for pdf in result_pdfs:
                gender_folder = pdf["gender"] if pdf["gender"] in ("M", "W") else "unknown"
                dest_dir = output_root / str(season) / folder_name / gender_folder
                download_pdf(pdf, dest_dir, session, args.dry_run, counters, progress)

            progress.close()

    total = sum(counters.values())
    print(f"\n{'=' * 65}")
    print("  Done.")
    if args.dry_run:
        print(f"  Would download  : {counters['would_download']}")
    else:
        print(f"  Downloaded      : {counters['downloaded']}")
        print(f"  Already existed : {counters['skipped']}")
        print(f"  Failed          : {counters['failed']}")
    print(f"  Total files     : {total}")
    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    main()
