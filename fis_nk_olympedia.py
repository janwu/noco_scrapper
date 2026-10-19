"""
Olympic Nordic combined results from Olympedia (www.olympedia.org), for the Games
FIS has no result PDF of (1924 - 1998): the full ranking with jump and cross-country,
DNS / DNF, the teams with their athletes, and the full names of the athletes — the
FIS database has the first 6 to 15 of the early Games only, often with initials
('HAUG Th').

    python fis_nk_olympedia.py                  # 1924-1998
    python fis_nk_olympedia.py --years 1992 1994

Each competition is stored next to the ranking of the FIS database it belongs to,
as doc type OLY (same file name, OLY instead of FDB):

    fis_nk_owg_pdfs/1992/19920212_19920218_ALBERTVILLE_FRA/M/..._1992NK0xxxOLY.json

Until 1980 the Olympic competition was the World Championships too: its OLY file
goes to fis_nk_wsc_pdfs/ as well.  Run fis_nk_fisdb.py --circuit OWG / WSC first.
The names: Olympedia's 'used name' (given•surname) of the athlete page, written
'SURNAME Given' like FIS; the pages are kept in fis_nk_owg_pdfs/_olympedia_athletes.json.

run_parser.py copies the files to output/; load_json.py prefers them to the FIS
ranking where no result PDF was read, and takes the full names for the initials.
"""
import argparse
import io
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.olympedia.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (noco_scrapper; personal research on Nordic combined results)"}
ROOT = Path(__file__).parent
OWG_ROOT, WSC_ROOT = ROOT / "fis_nk_owg_pdfs", ROOT / "fis_nk_wsc_pdfs"
ATHLETE_CACHE = OWG_ROOT / "_olympedia_athletes.json"
# the Olympic competitions that were the World Championships as well
CHAMPIONSHIPS_UNTIL = 1980
DELAY_S = 3.0


def get(session: requests.Session, path: str) -> BeautifulSoup:
    """A page, slowly: Olympedia answers 429 (too many requests) to a fast client."""
    for attempt in range(6):
        try:
            r = session.get(BASE + path, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "60")) if r.headers.get("Retry-After", "").isdigit() else 60
                print(f"    (Olympedia asks to wait {wait} s)")
                time.sleep(wait)
                continue
            r.raise_for_status()
            time.sleep(DELAY_S)
            return BeautifulSoup(r.text, "html.parser")
        except requests.RequestException:
            if attempt == 5:
                raise
            time.sleep(20)
    raise RuntimeError(f"Olympedia keeps refusing {path}")


def winter_editions(session) -> dict:
    """year → edition path ('/editions/44'), the Winter Games that were held."""
    soup = get(session, "/editions")
    table = next(t for t in soup.select("table")
                 if (h := t.find_previous(["h2", "h3"])) and "Winter" in h.get_text())
    editions = {}
    for tr in table.select("tr"):
        a = tr.find("a", href=re.compile(r"^/editions/\d+$"))
        year = re.search(r"\b(19|20)\d{2}\b", tr.get_text(" "))
        if a and year and tr.find("a", href=re.compile(r"/results/|/sports/")) is None:
            editions[int(year.group(0))] = a["href"]
    return editions


def edition_events(session, edition: str) -> list:
    """[(event name, result path, first day 'YYYY-MM-DD')] of the Nordic combined of a Games."""
    soup = get(session, f"{edition}/sports/NCB")
    events = []
    for tr in soup.select("table tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        a = tr.find("a", href=re.compile(r"^/results/\d+$"))
        if a and len(cells) >= 3 and cells[1] == "Olympic":
            events.append((cells[0], a["href"], first_day(cells[2])))
    return events


def first_day(text: str):
    """'11 – 12 February 1992' → '1992-02-11'; '27 January –  4 February 1956' → '1956-01-27'."""
    m = re.match(r"\s*(\d{1,2})\s*(?:([A-Za-z]+)\s*)?[–-]?.*?([A-Za-z]+)\s+(\d{4})", text)
    if not m:
        return None
    day, month, last_month, year = m.groups()
    try:
        return datetime.strptime(f"{day} {month or last_month} {year}", "%d %B %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def athlete(session, cache: dict, path: str) -> dict:
    """{'name': 'GUY Fabrice', 'born': '1968-12-30'} from the athlete page (cached)."""
    aid = path.rsplit("/", 1)[-1]
    if aid in cache:
        return cache[aid]
    soup = get(session, path)
    info = {}
    for tr in soup.select("table.biodata tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            info[th.get_text(strip=True)] = td.get_text(" ", strip=True)
    used = info.get("Used name") or (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
    if "•" in used:
        given, surname = (p.strip() for p in used.split("•", 1))
    else:
        parts = used.split()
        given, surname = " ".join(parts[:-1]), parts[-1] if parts else ""
    born = None
    m = re.match(r"(\d{1,2} [A-Za-z]+ \d{4})", info.get("Born", ""))
    if m:
        try:
            born = datetime.strptime(m.group(1), "%d %B %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    cache[aid] = {"name": f"{surname.upper()} {given}".strip(), "born": born}
    return cache[aid]


def value_and_rank(text: str):
    """'222.1 (3)' → ('222.1', 3); '43:45.4 (6)' → ('43:45.4', 6); '– ( DNS )' → (None, None)."""
    m = re.match(r"\s*([\d.:,-]+)\s*(?:\(\s*=?(\d+)\s*\))?", text or "")
    if not m or not re.search(r"\d", m.group(1)):
        return None, None
    return m.group(1), int(m.group(2)) if m.group(2) else None


def xc_time(text):
    """'1-14:31' (1 h 14 min 31 s) → '1:14:31'."""
    return re.sub(r"^(\d)-", r"\1:", text) if text else None


def to_float(text):
    try:
        return float(text) if text is not None else None
    except ValueError:
        return None


def result_table(session, cache: dict, path: str) -> dict:
    """The competition: {'individual': [...]} or {'teams': [...]}, in the FIS JSON layout."""
    soup = get(session, path)
    table = soup.select_one("table.table")
    rows = table.select("tr") if table else []
    head = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])] if rows else []
    jump_at = next((i for i, h in enumerate(head) if h.startswith("Ski Jumping")), None)
    xc_at = next((i for i, h in enumerate(head) if h.startswith("Cross Country")), None)
    margin_at = next((i for i, h in enumerate(head) if h == "Time Margin"), None)
    points_at = next((i for i, h in enumerate(head) if h == "Points"), None)
    team = head[1:2] == ["Competitors"]
    individual, teams = [], []
    for tr in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if len(cells) < 3:
            continue
        pos = cells[0].lstrip("=")
        rank = int(pos) if pos.isdigit() else None
        status = None if rank or not pos else pos.upper()
        jump, jump_rank = value_and_rank(cells[jump_at]) if jump_at is not None else (None, None)
        xc, xc_rank = value_and_rank(cells[xc_at]) if xc_at is not None else (None, None)
        if status is None and rank is None and jump_at is not None and "DNS" in cells[xc_at or jump_at]:
            status = "DNS"
        margin = cells[margin_at] if margin_at is not None else ""
        link = tr.find("a", href=re.compile(r"^/athletes/\d+"))
        if team and cells[2]:                                  # a team line
            teams.append({"rank": rank, "nation": cells[2], "team_name": cells[1], "status": status,
                          "jump_points": to_float(jump), "jump_rank": jump_rank,
                          "xc_time": xc_time(xc), "xc_rank": xc_rank,
                          "time_behind": margin if margin.startswith("+") else None, "members": []})
        elif team and link and teams:                         # an athlete of the team above
            a = athlete(session, cache, link["href"])
            teams[-1]["members"].append({"leg": len(teams[-1]["members"]) + 1, "name": a["name"],
                                         "date_of_birth": a["born"], "jump_points": to_float(jump),
                                         "xc_time": xc_time(xc), "olympedia_id": link["href"].rsplit("/", 1)[-1]})
        elif link:
            a = athlete(session, cache, link["href"])
            individual.append({"rank": rank, "name": a["name"], "nation": cells[2], "date_of_birth": a["born"],
                               "jump_points": to_float(jump), "jump_rank": jump_rank,
                               "xc_time": xc_time(xc), "xc_rank": xc_rank,
                               "time_behind": margin if margin.startswith("+") else None,
                               "total_points": to_float(cells[points_at]) if points_at is not None else None,
                               "status": status, "olympedia_id": link["href"].rsplit("/", 1)[-1]})
    return {"teams": teams} if team else {"individual": individual}


def fis_rankings(root: Path, year: int) -> list:
    """The FDB files of a year: [(path, is_team, date)], in date order."""
    found = []
    for f in sorted((root / str(year)).glob("*/*/*FDB.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        found.append((f, bool(d.get("team_results")) or "_Team_" in f.name, d.get("competition_date")))
    return sorted(found, key=lambda x: x[2] or "")


def store(fdb: Path, event: str, path: str, result: dict) -> Path:
    d = json.loads(fdb.read_text(encoding="utf-8"))
    dest = fdb.with_name(fdb.name.replace("FDB.json", "OLY.json"))
    dest.write_text(json.dumps({
        "doc_type": "OLY",
        "source_file": BASE + path,
        "codex": d.get("codex"),
        "competition_date": d.get("competition_date"),
        "location": d.get("location"),
        "country": d.get("country"),
        "event_name": event,
        "discipline": "Team" if "teams" in result else d.get("discipline"),
        "combined_results": result.get("individual", []),
        "team_results": result.get("teams", []),
        "parse_errors": [],
        "warnings": [],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return dest


def fetch(years) -> None:
    session = requests.Session()
    cache = json.loads(ATHLETE_CACHE.read_text(encoding="utf-8")) if ATHLETE_CACHE.exists() else {}
    editions = winter_editions(session)
    written = 0
    results = {}
    try:
        for year in years:
            if year not in editions:
                print(f"  {year}: no Winter Games on Olympedia")
                continue
            events = edition_events(session, editions[year])
            for circuit_root in (OWG_ROOT, WSC_ROOT) if year <= CHAMPIONSHIPS_UNTIL else (OWG_ROOT,):
                rankings = fis_rankings(circuit_root, year)
                for kind in (False, True):
                    fis = [r for r in rankings if r[1] == kind]
                    oly = sorted((e for e in events if e[0].startswith("Team") == kind), key=lambda e: e[2] or "")
                    if len(fis) != len(oly):
                        print(f"  {year} {circuit_root.name}: {len(oly)} Olympedia / {len(fis)} FIS "
                              f"{'team' if kind else 'individual'} competitions, not matched")
                        continue
                    for (fdb, _, _), (event, path, _) in zip(fis, oly):
                        if path not in results:            # until 1980 for both circuits
                            results[path] = result_table(session, cache, path)
                        result = results[path]
                        dest = store(fdb, event, path, result)
                        n = len(result.get("individual") or result.get("teams"))
                        print(f"  {year} {event}: {n} {'teams' if kind else 'athletes'} → {dest.relative_to(ROOT)}")
                        written += 1
    finally:
        ATHLETE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{written} Olympedia results written")


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--years", type=int, nargs="+",
                        default=[1924, 1928, 1932, 1936, *range(1948, 1993, 4), 1994, 1998])
    args = parser.parse_args()
    fetch(args.years)


if __name__ == "__main__":
    main()
