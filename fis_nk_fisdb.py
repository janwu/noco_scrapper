"""
The final ranking of competitions from the FIS database, where there is no result
PDF to read (doc type FDB):

  World Cup B 2000/01 - 2007/08   step 3 of fis_nk_wcb_scraper.py (--fis-results)
  World Cup 1983/84 - 2000/01     python fis_nk_fisdb.py --circuit WC

Not every World Cup B competition has a result PDF that can be read: FIS has PDFs
of half of them, and the lists of weltcup-b.org come from the organisers in many
layouts.  The World Cup has PDFs only from 2001/02.  The FIS database has the
ranking of each race, uniform, with the names spelled as everywhere else in FIS:
rank, FIS code, name, year of birth, nation and, depending on the years, the gap
to the winner or the World Cup points of the race (no jump or cross-country
details, and no DNF / DNS).  The early World Cup has the first 15 only, the ones
that scored points.

It is stored next to the PDFs, named like them with the type FDB:

    fis_nk_wcb_pdfs/2005/20050205_20050206_KARPACZ_POL/M/4170_20050205_..._M_2005NK4170FDB.json
    fis_nk_pdfs/1990/19900106_19900106_REIT_IM_WINKL_BRD/M/0111_19900106_..._M_1990NK0111FDB.json

Races before 2000/01 have no codex; their race id in the FIS database stands in
for it (four digits, unique within the season like a codex).

run_parser.py copies these files to output/; load_json.py takes the ranking from
there for a competition whose result PDF could not be read (see db/load_json.py).
World Cup points are kept in the JSON only: the database has the official cup
standings (fis_nk_standings_scraper.py), as the points rules changed over the years.
"""
import argparse
import io
import json
import re
import sys
import time
from pathlib import Path

import requests

import fis_nk_pdf_scraper as fis

RESULTS_URL = "https://www.fis-ski.com/DB/general/results.html?sectorcode=NK&raceid={raceid}"
CIRCUITS = {
    "WCB": {"seasons": range(2001, 2009), "root": Path(__file__).parent / "fis_nk_wcb_pdfs"},
    # the World Cup has result PDFs from 2001/02 (fis_nk_scraper.py)
    "WC": {"seasons": range(1984, 2002), "root": Path(__file__).parent / "fis_nk_pdfs"},
}
SEASONS = CIRCUITS["WCB"]["seasons"]


def _gap(text: str):
    """'.4' → '+0.4', '8:29.2' → '+8:29.2', '.0' or '' → None (the winner)."""
    t = text.strip()
    if not t or re.fullmatch(r"\.?0*\.?0", t):
        return None
    if t.startswith("."):
        t = "0" + t
    return "+" + t


def race_ranking(raceid: str, session: requests.Session) -> list:
    """
    The rows of a FIS result page: [{rank, fis_code, name, birth_year, nation,
    time_behind, wc_points}].

    After the nation the page has the gap to the winner (blue) and a second
    column, or, before 2000/01, one column only: the World Cup points of the race.
    """
    soup = fis.get_soup(RESULTS_URL.format(raceid=raceid), session)
    box = soup.select_one("#events-info-results")
    rows = []
    for row in box.select("a.table-row") if box else []:
        leaves = [d for d in row.select("div") if not d.select("div")]
        cells = [d.get_text(" ", strip=True) for d in leaves]
        if not cells or not cells[0].isdigit():
            continue
        # by content, not position: some pages leave out a column (no FIS code)
        nation_at = next((i for i, d in enumerate(leaves) if "country" in (d.get("class") or [])), None)
        name_at = next((i for i, c in enumerate(cells) if re.search(r"[^\W\d_]{2}", c)
                        and i != nation_at), None)
        if nation_at is None or name_at is None:
            continue
        year = next((c for c in cells[name_at + 1:nation_at] if re.fullmatch(r"(19|20)\d{2}", c)), None)
        code = next((c for c in cells[1:name_at] if c.isdigit()), None)
        after = [(d, c) for d, c in zip(leaves[nation_at + 1:], cells[nation_at + 1:]) if c]
        gap = points = None
        if len(after) == 1 and "blue" not in (after[0][0].get("class") or []) and after[0][1].isdigit():
            points = int(after[0][1])
        elif after:
            gap = _gap(after[0][1])
        rows.append({
            "rank": int(cells[0]),
            "fis_code": code,
            "name": re.sub(r"\s+", " ", cells[name_at]),
            "birth_year": int(year) if year else None,
            "nation": cells[nation_at],
            "time_behind": gap,
            "wc_points": points,
        })
    return rows


def fetch_all(root: Path = None, seasons=None, circuit: str = "WCB", overwrite: bool = False) -> None:
    root = root or CIRCUITS[circuit]["root"]
    seasons = seasons or CIRCUITS[circuit]["seasons"]
    session = requests.Session()
    written = empty = 0
    for season in seasons:
        events = []
        for _ in range(3):
            events = fis.get_events_for_season(circuit, season, session)
            if events:
                break
            time.sleep(10)
        for event in events:
            read = None
            for _ in range(3):
                read = fis.read_event(event, session)
                if read is not None:
                    break
                time.sleep(10)
            if read is None:
                print(f"  FAIL event {event['url']}")
                continue
            _, folder, races, _ = read
            for raceid, race in races.items():
                if not race["date"]:
                    continue
                if re.search(r"\bteam\b", race["name"].replace("_", " "), re.IGNORECASE):
                    continue                      # the database lists teams; the team PDFs are read instead
                codex = race["codex"] or str(raceid).zfill(4)
                g = race["gender"] if race["gender"] in ("M", "W") else "X"
                name = f"{codex}_{race['date']}_{race['name']}_{g}_{season}NK{codex}FDB.json"
                dest = root / str(season) / folder / (g if g != "X" else "unknown") / name
                if dest.exists() and not overwrite:
                    continue
                rows = race_ranking(raceid, session)
                if not rows:
                    empty += 1
                    print(f"  no ranking: {season} {folder} {race['name']}")
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                d = race["date"]
                dest.write_text(json.dumps({
                    "doc_type": "FDB",
                    "source_file": RESULTS_URL.format(raceid=raceid),
                    "codex": codex,
                    "competition_date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                    "location": folder.split("_", 2)[-1].rsplit("_", 1)[0].replace("_", " ").title(),
                    "country": folder.rsplit("_", 1)[-1],
                    "event_name": race["name"].replace("_", " "),
                    "combined_results": rows,
                    "parse_errors": [],
                    "warnings": [],
                }, ensure_ascii=False, indent=1), encoding="utf-8")
                written += 1
        print(f"  season {season}: done")
    print(f"{written} rankings written, {empty} races without a ranking")


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--circuit", choices=sorted(CIRCUITS), default="WC")
    parser.add_argument("--seasons", type=int, nargs="+", help="seasons (year the season ends in)")
    parser.add_argument("--overwrite", action="store_true", help="fetch rankings already on disk again")
    args = parser.parse_args()
    fetch_all(seasons=args.seasons, circuit=args.circuit, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
