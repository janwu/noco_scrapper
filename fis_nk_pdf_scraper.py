#!/usr/bin/env python3
"""
FIS Nordic Combined - result PDF scraper (World Cup and Continental Cup)
=======================================================================
Downloads the result PDFs attached to the competitions in the FIS calendar.

    python fis_nk_pdf_scraper.py --circuit WC --seasons 2027
    python fis_nk_pdf_scraper.py --circuit COC --seasons 2027 --dry-run

fis_nk_scraper.py (WC) and fis_nk_coc_scraper.py (COC) call this module with
the circuit set and take the same options.

Requirements: pip install requests beautifulsoup4 (tqdm optional)

Output, one folder per event and gender (unknown = mixed):

    fis_nk_pdfs/2026/20251128_20251130_RUKA_FIN/M/
        4117_20251128_Individual_Compact_Large_Hill_7.5_km_WC_M_M_2026NK4117ROF.pdf

The part after the last '_' is the name FIS gives the file (Content-Disposition),
'<season>NK<codex><type>.pdf'; the parser takes the document type (ROF, RL,
PCR, ...) from it.  The prefix — codex, date, race, gender — comes from the
race row on the event page.

How the FIS pages work (checked October 2026)
---------------------------------------------
- The calendar lists the events (event-details.html?eventid=...).
- An event page lists its races; each race row has several links to
  results.html?raceid=... (date, codex, name, category, gender) and a drop-down
  with the attachments.
- Since 2026 every attachment is /DB/v2/download/competition-attachment/<uuid>.pdf
  (before: /DB/pdf/<name>.pdf).  The link carries the codex, the gender and the
  document label: data-ga-codex="4117" data-ga-gender="M"
  data-ga-download="Official Results".  The file name is only known from the
  download response; it is remembered in <output>/.attachments.json so a
  re-run does not ask again.
- A file counts as downloaded if a PDF with the same FIS name exists anywhere
  in the season folder — the race descriptions on the event pages change over
  the years, so the prefix of older downloads may differ.

Notes: 1 second between requests; Women's World Cup from 2018, Continental Cup
from 2009, PDFs from 2001.
"""

import argparse
import datetime
import io
import json
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

CALENDAR_URL = (
    "https://www.fis-ski.com/DB/nordic-combined/calendar-results.html"
    "?sectorcode=NK&categorycode={circuit}&saveselection=-1&seasonselection={season}"
)

CIRCUITS = {
    "WC":  {"first_season": 2001, "output_dir": "fis_nk_pdfs",     "name": "World Cup"},
    "COC": {"first_season": 2009, "output_dir": "fis_nk_coc_pdfs", "name": "Continental Cup"},
    # the World Cup B, renamed Continental Cup in 2008/09; FIS has PDFs of a few of its competitions
    "WCB": {"first_season": 2001, "last_season": 2008, "output_dir": "fis_nk_wcb_pdfs", "name": "World Cup B"},
}


def current_season(today: datetime.date = None) -> int:
    """FIS names a season after the year it ends in; it starts in the autumn."""
    today = today or datetime.date.today()
    return today.year + 1 if today.month >= 7 else today.year


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
    "nations cup standings",
    "continental cup standings",
    "prize money",
    "trophy",
    "standings",
    "ranking",
    "program",
    "programme",
    "start list",
    "equipment control",
]

# Document type by label, used for the file name only if the server sends none
LABEL_DOC_TYPES = [
    ("official results", "ROF"),
    ("provisional competition round", "PCR"),
    ("results list ski jumping", "RL"),
    ("1st round", "RL1"),
    ("qualification", "RLQ"),
    ("cross country", "RLLL"),
    ("trial round", "RLTR"),
    ("official training", "RLT"),
]

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FIS-NK-Scraper/3.0)"}
REQUEST_DELAY = 1.0

ATTACHMENT_RE = re.compile(r"/DB/v2/download/competition-attachment/([0-9a-f-]+)\.pdf", re.I)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def get_soup(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return BeautifulSoup(resp.text, "html.parser")


def filename_from_response(resp) -> str:
    """'inline; filename=2026NK4117ROF.pdf' → '2026NK4117ROF.pdf' ('' if none)."""
    disposition = resp.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", disposition, re.I)
    return Path(m.group(1).strip()).name if m else ""


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

class SimpleProgress:
    """Minimal progress display when tqdm is not installed."""
    def __init__(self, total: int, desc: str = ""):
        self.total = total
        self.n = 0
        self._print()

    def _print(self):
        pct = int(100 * self.n / self.total) if self.total else 100
        filled = int(30 * self.n / self.total) if self.total else 30
        bar = "#" * filled + "-" * (30 - filled)
        sys.stdout.write(f"\r  [{bar}] {self.n}/{self.total} ({pct}%)")
        sys.stdout.flush()

    def update(self, n: int = 1):
        self.n += n
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
# Calendar
# ---------------------------------------------------------------------------

def get_events_for_season(circuit: str, season: int, session: requests.Session) -> list:
    url = CALENDAR_URL.format(circuit=circuit, season=season)
    print(f"  Fetching {circuit} calendar for season {season} ...")
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
        if not m or m.group(1) in seen_ids:
            continue
        seen_ids.add(m.group(1))

        raw_text = a.get_text(" ", strip=True)
        nation_m = re.search(r"\b([A-Z]{3})\b", raw_text)
        place = re.sub(r"\s+", "_", re.sub(r"[^\w\s]", "", raw_text.split("\n")[0].strip()))[:30]
        full_url = urljoin(BASE_URL, href)
        if "seasoncode" not in full_url:
            full_url += f"&seasoncode={season}"
        events.append({
            "eventid": m.group(1),
            "place": place,
            "nation": nation_m.group(1) if nation_m else "UNK",
            "url": full_url,
            "season": season,
        })

    print(f"  Found {len(events)} events")
    return events


# ---------------------------------------------------------------------------
# Event page
# ---------------------------------------------------------------------------

def parse_location(soup: BeautifulSoup) -> str:
    """H1 location, e.g. "Ruka (FIN)" -> "RUKA_FIN"."""
    h1 = soup.find("h1")
    if not h1:
        return ""
    raw = h1.get_text(strip=True).upper()
    raw = re.sub(r"[()]+", "_", raw)
    raw = re.sub(r"[^A-Z0-9_]+", "_", raw)
    return re.sub(r"_+", "_", raw).strip("_")


def date_from_text(text: str, season: int) -> str:
    """YYYYMMDD for the first 'DD Mon' in text, or ''."""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})", text)
    if not m or m.group(2).lower()[:3] not in MONTH_MAP:
        return ""
    month = MONTH_MAP[m.group(2).lower()[:3]]
    year = season - 1 if month >= 10 else season
    try:
        return datetime.date(year, month, int(m.group(1))).strftime("%Y%m%d")
    except ValueError:
        return ""


def event_name_from_text(text: str) -> str:
    """
    The race description from the merged texts of a race row: the longest line
    that looks like one ('Individual Compact Large Hill/7.5 km WC M'), made
    file-name safe.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    junk = re.compile(r"^([DPMC]+|[MWA]|WC|COC|PR|review|\d{1,2}(st|nd|rd|th)?|\d{1,2}:\d{2})$", re.I)
    date_re = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", re.I)
    status_re = re.compile(r"official results|cancelled|start list|postponed", re.I)
    event_re = re.compile(
        r"\b(Hill|Sprint|Gundersen|Mass.?Start|Compact|Provisional|Team|Individual|Km|HS\d|NH|LH)\b", re.I)

    best = ""
    for line in lines:
        if junk.match(line) or date_re.search(line) or status_re.search(line):
            continue
        if event_re.search(line) and len(line) > len(best):
            best = line
        elif not best and len(line) > len(best):
            best = line
    if not best:
        return "unknown"
    s = best.replace("/", "_").replace(",", ".").replace(" ", "_")
    s = re.sub(r"[^\w.]", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


def parse_all_dates(soup: BeautifulSoup, season: int) -> tuple:
    """(first, last) YYYYMMDD over all race rows of the page."""
    dates = []
    for a in soup.find_all("a", href=True):
        if "results.html" not in a["href"] or "raceid" not in a["href"]:
            continue
        for m in re.finditer(r"(\d{1,2})\s+([A-Za-z]{3})", a.get_text(" ", strip=True)):
            mon = m.group(2).lower()[:3]
            if mon not in MONTH_MAP:
                continue
            month = MONTH_MAP[mon]
            try:
                dates.append(datetime.date(season - 1 if month >= 10 else season, month, int(m.group(1))))
            except ValueError:
                pass
    if not dates:
        return "", ""
    dates.sort()
    return dates[0].strftime("%Y%m%d"), dates[-1].strftime("%Y%m%d")


def attachment_label(a) -> str:
    """'Official Results' — from data-ga-download, else from the text next to the link."""
    label = (a.get("data-ga-download") or "").strip()
    if not label:
        prev = a.find_previous_sibling(string=True)
        label = prev.strip() if prev else ""
        if not label:
            span = a.find_previous_sibling("span")
            label = span.get_text(" ", strip=True) if span else ""
        if not label and a.parent:
            label = a.parent.get_text(" ", strip=True).replace("download", "").strip()
    return re.sub(r"\(\s*[\d.,]+\s*kb\s*\)", "", label, flags=re.I).strip()


def read_event(event: dict, session: requests.Session):
    """
    (soup, folder_name, races, rid_by_codex) of an event page, or None if it cannot be read.
    races: raceid -> {codex, date, name, gender, category}, in page order.

    A race row has several links to the same raceid (date, codex, name,
    category, gender); their texts are merged to describe the race.
    """
    try:
        soup = get_soup(event["url"], session)
    except Exception as e:
        print(f"  FAIL Could not fetch event page: {e}")
        return None

    location = parse_location(soup) or f"{event['place']}_{event['nation']}"
    date_from, date_to = parse_all_dates(soup, event["season"])
    if date_from and date_to:
        folder_name = f"{date_from}_{date_to}_{location}"
    elif date_from:
        folder_name = f"{date_from}_{location}"
    else:
        folder_name = f"{location}_{event['eventid']}"

    raceid_texts = defaultdict(list)
    raceid_order = []
    raceid_codex = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "results.html" in href and "raceid" in href:
            m = re.search(r"raceid=(\d+)", href)
            if m:
                if m.group(1) not in raceid_texts:
                    raceid_order.append(m.group(1))
                raceid_texts[m.group(1)].append(a.get_text(" ", strip=True))
        if "live.fis-ski.com" in href and raceid_order:
            codex_m = re.search(r"/nk-(\d{4})/", href)
            if codex_m:
                raceid_codex[raceid_order[-1]] = codex_m.group(1)

    race_meta = {}
    for rid in raceid_order:
        merged = "\n".join(raceid_texts[rid])
        codex = raceid_codex.get(rid, "")
        if not codex:
            # the codex is a link text of its own: '4117'
            codex = next((t for t in raceid_texts[rid] if re.fullmatch(r"\d{4}", t)
                          and not 1980 <= int(t) <= 2100), "")
        if not codex:
            codex = next((m.group(1) for m in re.finditer(r"\b(\d{4})\b", merged)
                          if not 1980 <= int(m.group(1)) <= 2100), "")
        gender_m = re.search(r"\b(?:WC|WCB|COC|PR)\b\s*\n?\s*\b([MWA])\b", merged)
        if gender_m:
            gender = gender_m.group(1)
        else:
            tokens = re.findall(r"\b([MWA])\b", merged)
            gender = tokens[-1] if tokens else "unknown"
        cat_m = re.search(r"\b(WC|WCB|COC|PR)\b", merged)
        race_meta[rid] = {
            "codex": codex,
            "date": date_from_text(merged, event["season"]),
            "name": event_name_from_text(merged),
            "gender": gender,
            "category": cat_m.group(1) if cat_m else "unknown",
        }
    rid_by_codex = {meta["codex"]: rid for rid, meta in race_meta.items() if meta["codex"]}
    return soup, folder_name, race_meta, rid_by_codex


def parse_event_page(event: dict, session: requests.Session) -> tuple:
    """
    (pdfs, folder_name) of an event page.  An attachment belongs to the race of
    its data-ga-codex, else to the race row above it.
    """
    read = read_event(event, session)
    if read is None:
        return [], event["eventid"]
    soup, folder_name, race_meta, rid_by_codex = read

    pdfs = []
    current_rid = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "results.html" in href and "raceid" in href:
            m = re.search(r"raceid=(\d+)", href)
            if m:
                current_rid = m.group(1)
            continue

        attachment = ATTACHMENT_RE.search(href)
        legacy = href.lower().endswith(".pdf") and "/DB/pdf/" in href
        if not (attachment or legacy):
            continue

        rid = rid_by_codex.get(a.get("data-ga-codex", ""), current_rid)
        meta = race_meta.get(rid, {})
        codex = a.get("data-ga-codex") or meta.get("codex") or "0000"
        gender = a.get("data-ga-gender") or meta.get("gender") or "unknown"
        pdfs.append({
            "label": attachment_label(a),
            "url": urljoin(BASE_URL, href),
            "attachment_id": attachment.group(1) if attachment else None,
            # known for the old links only; the new ones are named by the download
            "original_filename": None if attachment else href.split("/")[-1],
            "gender": gender,
            "category": meta.get("category", "unknown"),
            "codex": codex,
            "race_date": meta.get("date") or "00000000",
            "race_name": meta.get("name") or "unknown",
        })
    return pdfs, folder_name


def is_result_pdf(pdf: dict) -> bool:
    label = pdf["label"].lower()
    if any(kw in label for kw in EXCLUDE_KEYWORDS):
        return False
    return any(kw in label for kw in RESULT_KEYWORDS)


def fallback_filename(pdf: dict, season: int) -> str:
    """'2026NK4117ROF.pdf' from the label, for a download without a file name."""
    label = pdf["label"].lower()
    doc_type = next((t for kw, t in LABEL_DOC_TYPES if kw in label), "DOC")
    return f"{season}NK{pdf['codex']}{doc_type}.pdf"


def prefixed_filename(pdf: dict, original: str) -> str:
    g = pdf["gender"] if pdf["gender"] in ("M", "W") else "X"
    return f"{pdf['codex']}_{pdf['race_date']}_{pdf['race_name']}_{g}_{original}"


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------

class Downloads:
    """What is on disk for a season, and the names of attachments seen before."""

    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.cache_path = output_root / ".attachments.json"
        try:
            self.names = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.names = {}
        self.on_disk = {}

    def existing(self, season: int) -> set:
        """FIS file names (the part after the last '_') of the season's PDFs."""
        if season not in self.on_disk:
            folder = self.output_root / str(season)
            self.on_disk[season] = {p.name.rsplit("_", 1)[-1].lower() for p in folder.rglob("*.pdf")} \
                if folder.exists() else set()
            # attachments FIS filed under the wrong competition, renamed by fis_nk_wcb_files.py
            try:
                renamed = json.loads((self.output_root / ".renamed.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                renamed = {}
            self.on_disk[season] |= {old for old, new in renamed.items() if new in self.on_disk[season]}
        return self.on_disk[season]

    def remember(self, attachment_id: str, name: str) -> None:
        self.names[attachment_id] = name

    def save(self) -> None:
        if self.names:
            self.output_root.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.names, indent=0, sort_keys=True), encoding="utf-8")


def download_pdf(pdf: dict, season: int, dest_dir: Path, downloads: Downloads,
                 session: requests.Session, dry_run: bool, counters: dict) -> None:
    original = pdf["original_filename"] or downloads.names.get(pdf["attachment_id"])
    if original and original.lower() in downloads.existing(season):
        counters["skipped"] += 1
        return
    if original and dry_run:
        counters["would_download"] += 1
        print(f"\n    would download {prefixed_filename(pdf, original)}")
        return

    try:
        resp = session.get(pdf["url"], headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        if not original:
            original = filename_from_response(resp) or fallback_filename(pdf, season)
            if pdf["attachment_id"]:
                downloads.remember(pdf["attachment_id"], original)
        if original.lower() in downloads.existing(season) or dry_run:
            resp.close()
            if dry_run and original.lower() not in downloads.existing(season):
                counters["would_download"] += 1
                print(f"\n    would download {prefixed_filename(pdf, original)}")
            else:
                counters["skipped"] += 1
            time.sleep(REQUEST_DELAY)
            return
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / prefixed_filename(pdf, original)
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=16384):
                f.write(chunk)
        downloads.existing(season).add(original.lower())
        counters["downloaded"] += 1
        time.sleep(REQUEST_DELAY)
    except Exception as e:
        print(f"\n  FAIL {pdf['url']}: {e}")
        counters["failed"] += 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(circuit: str = None, argv: list = None) -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Download FIS Nordic Combined result PDFs.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    if circuit is None:
        parser.add_argument("--circuit", choices=sorted(CIRCUITS), required=True,
                            help="WC = World Cup, COC = Continental Cup.")
    parser.add_argument("--from-season", type=int, default=None, metavar="YEAR",
                        help="Earliest season (default: the first with PDFs).")
    parser.add_argument("--to-season", type=int, default=current_season(), metavar="YEAR",
                        help="Latest season (default: the current one, %(default)s).")
    parser.add_argument("--seasons", nargs="+", type=int, default=None, metavar="YEAR",
                        help="Explicit season list; overrides --from-season/--to-season.")
    parser.add_argument("--output-dir", default=None,
                        help="Root folder (default: fis_nk_pdfs or fis_nk_coc_pdfs).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be downloaded without downloading anything.")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between HTTP requests (default: 1.0).")
    args = parser.parse_args(argv)
    circuit = circuit or args.circuit
    config = CIRCUITS[circuit]

    global REQUEST_DELAY
    REQUEST_DELAY = args.delay

    first = args.from_season or config["first_season"]
    seasons = (sorted(args.seasons, reverse=True) if args.seasons
               else list(range(args.to_season, first - 1, -1)))
    output_root = Path(args.output_dir or config["output_dir"])

    print("=" * 65)
    print(f"  FIS Nordic Combined {config['name']} - Result PDF Scraper")
    print("=" * 65)
    print(f"  Seasons  : {min(seasons)}-{max(seasons)}  ({len(seasons)} seasons)")
    print(f"  Output   : {output_root.resolve()}")
    print(f"  Dry run  : {args.dry_run}")
    print("=" * 65)

    session = requests.Session()
    downloads = Downloads(output_root)
    counters = {"downloaded": 0, "skipped": 0, "failed": 0, "would_download": 0}
    try:
        for season in seasons:
            print(f"\n{'-' * 65}\n  SEASON {season}\n{'-' * 65}")
            events = get_events_for_season(circuit, season, session)
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
                    download_pdf(pdf, season, dest_dir, downloads, session, args.dry_run, counters)
                    progress.update(1)
                progress.close()
    finally:
        downloads.save()

    print(f"\n{'=' * 65}\n  Done.")
    if args.dry_run:
        print(f"  Would download  : {counters['would_download']}")
        print(f"  Already existed : {counters['skipped']}")
    else:
        print(f"  Downloaded      : {counters['downloaded']}")
        print(f"  Already existed : {counters['skipped']}")
        print(f"  Failed          : {counters['failed']}")
    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    main()
