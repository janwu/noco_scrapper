#!/usr/bin/env python3
"""
FIS Nordic Combined 2017 - Missing ROF PDF Downloader
======================================================
The main scraper (fis_nk_scraper.py) collects PDFs by following <a href> links
on FIS event pages.  In the 2017 season, the "Official Results" (ROF) PDFs are
NOT linked in the page HTML, even though FIS shows "Official results" in the
race status column and the files exist on the server at a predictable URL.

This script:
  1. Scrapes every 2017 WC event page to collect race metadata
     (codex, date, event name, folder path).
  2. Constructs the ROF URL directly:
       https://www.fis-ski.com/DB/pdf/2017/NK/{codex}/2017NK{codex}ROF.pdf
  3. Sends a HEAD request to verify the file exists (HTTP 200).
  4. Downloads it and saves with the SAME naming schema used by the main
     scraper:
       {codex}_{date}_{event_name}_M_{season}NK{codex}ROF.pdf
     inside the matching season / event-folder / gender subfolder.

Usage
-----
    # Dry-run: show what would be downloaded
    python fis_nk_2017_rof_fixer.py --dry-run

    # Download into the same root folder used by the main scraper
    python fis_nk_2017_rof_fixer.py --output-dir fis_nk_pdfs

    # Adjust request delay (default 1 s)
    python fis_nk_2017_rof_fixer.py --delay 1.5

Requirements
------------
    pip install requests beautifulsoup4 tqdm
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
# Constants (must match main scraper)
# ---------------------------------------------------------------------------

BASE_URL   = "https://www.fis-ski.com"
SEASON     = 2017
PDF_BASE   = "https://www.fis-ski.com/DB/pdf"
HEADERS    = {"User-Agent": "Mozilla/5.0 (compatible; FIS-NK-Scraper/2.0)"}

CALENDAR_URL = (
    "https://www.fis-ski.com/DB/nordic-combined/calendar-results.html"
    "?sectorcode=NK&categorycode=WC&saveselection=-1&seasonselection={season}"
)

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

REQUEST_DELAY = 1.0   # overridden by --delay


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return BeautifulSoup(resp.text, "html.parser")


def head_ok(url: str, session: requests.Session) -> bool:
    """Return True if a HEAD request gets HTTP 200."""
    try:
        resp = session.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        time.sleep(REQUEST_DELAY)
        return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Parsing helpers (copied from main scraper for compatibility)
# ---------------------------------------------------------------------------

def parse_location(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if not h1:
        return ""
    raw = h1.get_text(strip=True).upper()
    raw = re.sub(r"[()]+", "_", raw)
    raw = re.sub(r"[^A-Z0-9_]+", "_", raw)
    return re.sub(r"_+", "_", raw).strip("_")


def date_from_text(text: str, season: int) -> str:
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


def parse_all_dates(soup: BeautifulSoup, season: int) -> tuple:
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


def event_name_from_text(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    JUNK = re.compile(
        r"^([DPMC]+|[MW]|WC|PR|review|\d{1,2}(st|nd|rd|th)?|\d{1,2}:\d{2})$", re.I
    )
    DATE_RE  = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", re.I)
    STATUS_RE = re.compile(r"official results|cancelled|start list|postponed", re.I)
    best = ""
    for line in lines:
        if JUNK.match(line):
            continue
        if DATE_RE.search(line):
            continue
        if STATUS_RE.search(line):
            continue
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
    s = best.replace("/", "_").replace(",", ".").replace(" ", "_")
    s = re.sub(r"[^\w.]", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


# ---------------------------------------------------------------------------
# Calendar: get all 2017 event IDs
# ---------------------------------------------------------------------------

def get_event_ids(season: int, session: requests.Session) -> list:
    url = CALENDAR_URL.format(season=season)
    print(f"  Fetching 2017 calendar ...")
    soup = get_soup(url, session)
    seen, events = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "event-details" not in href:
            continue
        m = re.search(r"eventid=(\d+)", href)
        if not m:
            continue
        eid = m.group(1)
        if eid in seen:
            continue
        seen.add(eid)
        raw  = a.get_text(" ", strip=True)
        nat  = re.search(r"\b([A-Z]{3})\b", raw)
        nation = nat.group(1) if nat else "UNK"
        place  = re.sub(r"\s+", "_", re.sub(r"[^\w\s]", "", raw.split("\n")[0].strip()))[:30]
        full_url = urljoin(BASE_URL, href)
        if "seasoncode" not in full_url:
            full_url += f"&seasoncode={season}"
        events.append({"eventid": eid, "place": place, "nation": nation, "url": full_url})
    print(f"  Found {len(events)} events")
    return events


# ---------------------------------------------------------------------------
# Event page: extract per-race metadata and folder name
# ---------------------------------------------------------------------------

def parse_event(event: dict, session: requests.Session) -> tuple:
    """
    Returns (races, folder_name).
    races is a list of dicts: {codex, date, name, gender, folder_name}
    """
    try:
        soup = get_soup(event["url"], session)
    except Exception as e:
        print(f"  FAIL fetching event {event['eventid']}: {e}")
        return [], event["eventid"]

    # Build folder name (identical logic to main scraper)
    location  = parse_location(soup) or f"{event['place']}_{event['nation']}"
    date_from, date_to = parse_all_dates(soup, SEASON)
    if date_from and date_to:
        folder_name = f"{date_from}_{date_to}_{location}"
    elif date_from:
        folder_name = f"{date_from}_{location}"
    else:
        folder_name = f"{location}_{event['eventid']}"

    # Group anchor texts by raceid
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

        if "live.fis-ski.com" in href:
            cm = re.search(r"/nk-(\d{4})/", href)
            if cm and raceid_order:
                raceid_codex[raceid_order[-1]] = cm.group(1)

    # Also extract codexes from result-page links like /pdf/2017/NK/4125/
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/DB/pdf/" in href:
            cm = re.search(r"/pdf/\d+/NK/(\d{4})/", href)
            if cm:
                codex_val = cm.group(1)
                # Try to associate with an un-codexed raceid via proximity
                # The PDF section appears right after the race row; walk backwards
                # through raceid_order to find the most recent one without a codex
                for rid in reversed(raceid_order):
                    if rid not in raceid_codex:
                        raceid_codex[rid] = codex_val
                        break
                    elif raceid_codex[rid] == codex_val:
                        break  # already assigned

    races = []
    for rid in raceid_order:
        merged = "\n".join(raceid_texts[rid])

        # Codex: from live link or from PDF path
        codex = raceid_codex.get(rid, "")
        if not codex:
            # Fallback: look for a 4-digit number in merged text
            for m in re.finditer(r"\b(\d{4})\b", merged):
                val = int(m.group(1))
                if val < 1980 or val > 2100:
                    codex = m.group(1)
                    break
        if not codex:
            continue   # can't build ROF URL without codex

        race_date = date_from_text(merged, SEASON)
        race_name = event_name_from_text(merged)

        gm = re.search(r"\b(?:WC|PR)\b\s*\n?\s*\b([MW])\b", merged)
        if gm:
            gender = gm.group(1)
        else:
            tokens = re.findall(r"\b([MW])\b", merged)
            gender = tokens[-1] if tokens else "M"   # 2017 is Men-only

        races.append({
            "codex":       codex,
            "date":        race_date or "00000000",
            "name":        race_name or "unknown",
            "gender":      gender if gender in ("M", "W") else "M",
            "folder_name": folder_name,
        })

    return races, folder_name


# ---------------------------------------------------------------------------
# ROF URL + filename helpers
# ---------------------------------------------------------------------------

def rof_url(codex: str) -> str:
    return f"{PDF_BASE}/{SEASON}/NK/{codex}/{SEASON}NK{codex}ROF.pdf"


def rof_filename(race: dict) -> str:
    """
    Matches the main scraper naming schema:
      {codex}_{date}_{name}_{gender}_{season}NK{codex}ROF.pdf
    """
    original = f"{SEASON}NK{race['codex']}ROF.pdf"
    prefix   = f"{race['codex']}_{race['date']}_{race['name']}_{race['gender']}_"
    return prefix + original


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_rof(race: dict, output_root: Path, session: requests.Session,
                 dry_run: bool, counters: dict) -> None:
    url      = rof_url(race["codex"])
    fname    = rof_filename(race)
    dest_dir = output_root / str(SEASON) / race["folder_name"] / race["gender"]
    dest     = dest_dir / fname

    if dest.exists():
        print(f"    SKIP (exists)  {fname}")
        counters["skipped"] += 1
        return

    # Probe the server
    print(f"    Checking ...   {url}")
    if not head_ok(url, session):
        print(f"    NOT FOUND      {race['codex']}ROF — skipping")
        counters["not_found"] += 1
        return

    if dry_run:
        print(f"    WOULD DOWNLOAD {fname}")
        counters["would_download"] += 1
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        resp = session.get(url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=16384):
                f.write(chunk)
        print(f"    DOWNLOADED     {fname}")
        counters["downloaded"] += 1
        time.sleep(REQUEST_DELAY)
    except Exception as e:
        print(f"    FAIL           {url}: {e}")
        counters["failed"] += 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Download missing ROF (Official Results) PDFs for FIS NK WC 2017.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir", default="fis_nk_pdfs",
        help="Root folder — must match what you used with fis_nk_scraper.py (default: ./fis_nk_pdfs).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be downloaded without actually downloading.",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between HTTP requests (default: 1.0).",
    )
    args = parser.parse_args()

    global REQUEST_DELAY
    REQUEST_DELAY = args.delay

    output_root = Path(args.output_dir)

    print("=" * 65)
    print("  FIS NK 2017 — Missing ROF PDF Downloader")
    print("=" * 65)
    print(f"  Season   : {SEASON}")
    print(f"  Suffix   : ROF  (Official Results)")
    print(f"  Output   : {output_root.resolve()}")
    print(f"  Dry run  : {args.dry_run}")
    print("=" * 65)

    session  = requests.Session()
    counters = {"downloaded": 0, "skipped": 0, "not_found": 0,
                "failed": 0, "would_download": 0}

    events = get_event_ids(SEASON, session)
    if not events:
        print("  No events found — aborting.")
        sys.exit(1)

    all_races = []
    seen_codexes = set()

    for i, event in enumerate(events, 1):
        print(f"\n  [{i}/{len(events)}] event {event['eventid']} ...")
        races, folder = parse_event(event, session)
        print(f"    → {folder}")
        for race in races:
            if race["codex"] not in seen_codexes:
                seen_codexes.add(race["codex"])
                all_races.append(race)
                print(f"    codex {race['codex']}  {race['date']}  {race['name']}  [{race['gender']}]")

    print(f"\n{'=' * 65}")
    print(f"  Total unique races found : {len(all_races)}")
    print(f"  Probing for ROF PDFs ...")
    print(f"{'=' * 65}\n")

    for race in all_races:
        print(f"  Codex {race['codex']} — {race['name']}")
        download_rof(race, output_root, session, args.dry_run, counters)

    print(f"\n{'=' * 65}")
    print("  Done.")
    if args.dry_run:
        print(f"  Would download  : {counters['would_download']}")
    else:
        print(f"  Downloaded      : {counters['downloaded']}")
        print(f"  Already existed : {counters['skipped']}")
        print(f"  Not on server   : {counters['not_found']}")
        print(f"  Failed          : {counters['failed']}")
    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    main()
