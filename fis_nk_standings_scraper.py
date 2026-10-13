#!/usr/bin/env python3
"""
FIS Nordic Combined — cup standings scraper
============================================
Downloads the official final standings of every season from the FIS
database (World Cup and Continental Cup, men and women) and stores them
as JSON, one file per cup / season / gender.

Why not compute the standings from the results?  The points rules changed
over the years (100-80-60, later 100-90-80), and events like the Ruka Tour
or the Seefeld Triple score differently again.  FIS publishes the result of
all that; this script fetches it.

    python fis_nk_standings_scraper.py                       # all seasons 2002-2026
    python fis_nk_standings_scraper.py --seasons 2025 2026   # refresh the current ones
    python fis_nk_standings_scraper.py --dry-run

Output (fis_nk_standings/WC_2024_M.json):
    {
      "cup": "WC", "season": 2024, "gender": "M",
      "disciplines": {"ALL": "Overall", "IC": "Individual Compact", "BJT": "Best Jumper Trophy", ...},
      "rows": [
        {"competitor_id": "157270", "name": "RIIBER Jarl Magnus", "nation": "NOR",
         "standings": {"ALL": {"rank": 1, "points": 1870}, "BJT": {"rank": 1, "points": 1830}, ...}},
        ...
      ]
    }

The season is the year it ends in (2024 = 2023/24), as on the FIS site.
A cup / season / gender without standings (women before 2018, say) gets no file.
"""
import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing dependencies. Please run:\n  pip install requests beautifulsoup4")
    sys.exit(1)

URL = ("https://www.fis-ski.com/DB/nordic-combined/cup-standings.html"
       "?sectorcode=NK&seasoncode={season}&cupcode={cup}&disciplinecode=ALL&gendercode={gender}&nationcode=")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
CUPS = ("WC", "COC")
GENDERS = ("M", "W")
FIRST_SEASON, LAST_SEASON = 2002, datetime.date.today().year + (datetime.date.today().month >= 7)
REQUEST_DELAY_S = 1.0


def parse_standings(html: str) -> dict:
    """{'selected': {...}, 'disciplines': {code: label}, 'rows': [...]} from a cup-standings page."""
    soup = BeautifulSoup(html, "html.parser")

    selected, disciplines = {}, {}
    for select in soup.find_all("select"):
        name = select.get("name")
        chosen = [o.get("value") for o in select.find_all("option") if o.has_attr("selected")]
        selected[name] = chosen[0] if chosen else None
        if name == "disciplinecode":
            disciplines = {o.get("value"): o.get_text(strip=True) for o in select.find_all("option")}

    rows = []
    for a in soup.select("a.table-row"):
        m = re.search(r"competitorid=(\d+)", a.get("href", ""))
        cells = [c for c in a.get_text("|", strip=True).split("|") if c]
        if not m or len(cells) < 2:
            continue
        row = {"competitor_id": m.group(1), "name": cells[0], "nation": cells[1], "standings": {}}
        # After name and nation: per discipline its label, its code, then rank and points
        # ('---' or nothing if the athlete is not ranked in it).
        i = 2
        while i < len(cells):
            if cells[i] in disciplines and i > 2 and cells[i - 1] == disciplines[cells[i]]:
                code = cells[i]
                values = []
                j = i + 1
                while j < len(cells) and cells[j] not in disciplines.values():
                    values.append(cells[j])
                    j += 1
                numbers = [int(v.replace("'", "")) for v in values if re.fullmatch(r"[\d']+", v)]
                if numbers:
                    row["standings"][code] = {
                        "rank": numbers[0],
                        "points": numbers[1] if len(numbers) > 1 else None,
                    }
                i = j
            else:
                i += 1
        rows.append(row)
    return {"selected": selected, "disciplines": disciplines, "rows": rows}


def fetch(session: requests.Session, cup: str, season: int, gender: str) -> dict:
    url = URL.format(season=season, cup=cup, gender=gender)
    response = session.get(url, timeout=30)
    response.raise_for_status()
    page = parse_standings(response.text)
    # The site answers an unknown combination with some other one; trust only an exact echo
    echoed = (page["selected"].get("seasoncode"), page["selected"].get("cupcode"),
              page["selected"].get("gendercode"))
    if echoed != (str(season), cup, gender):
        page["rows"] = []
    page["url"] = url
    return page


def main() -> int:
    ap = argparse.ArgumentParser(description="Download FIS Nordic Combined cup standings")
    ap.add_argument("--seasons", nargs="+", type=int, help="Seasons (year the season ends in)")
    ap.add_argument("--from-season", type=int, default=FIRST_SEASON)
    ap.add_argument("--to-season", type=int, default=LAST_SEASON)
    ap.add_argument("--output-dir", default="fis_nk_standings")
    ap.add_argument("--dry-run", action="store_true", help="Fetch and report, write nothing")
    args = ap.parse_args()

    seasons = args.seasons or list(range(args.from_season, args.to_season + 1))
    out_dir = Path(args.output_dir)
    session = requests.Session()
    session.headers.update(HEADERS)

    written = empty = 0
    for season in seasons:
        for cup in CUPS:
            for gender in GENDERS:
                try:
                    page = fetch(session, cup, season, gender)
                except requests.RequestException as exc:
                    print(f"  {cup} {season} {gender}: FAILED {exc}")
                    continue
                finally:
                    time.sleep(REQUEST_DELAY_S)
                ranked = [r for r in page["rows"] if "ALL" in r["standings"]]
                if not ranked:
                    empty += 1
                    continue
                leader = min(ranked, key=lambda r: r["standings"]["ALL"]["rank"])
                print(f"  {cup} {season} {gender}: {len(page['rows']):3d} athletes, "
                      f"{', '.join(page['disciplines'])} — 1. {leader['name']} "
                      f"{leader['standings']['ALL']['points']}")
                if args.dry_run:
                    continue
                out_dir.mkdir(parents=True, exist_ok=True)
                data = {
                    "cup": cup, "season": season, "gender": gender,
                    "source_url": page["url"],
                    "fetched": datetime.date.today().isoformat(),
                    "disciplines": page["disciplines"],
                    "rows": page["rows"],
                }
                with open(out_dir / f"{cup}_{season}_{gender}.json", "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=1)
                written += 1
    print(f"Done: {written} standings written, {empty} combinations without standings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
