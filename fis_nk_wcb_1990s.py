"""
World Cup B of the 1990s: the result lists weltcup-b.org has (1996/97 - 1999/2000,
some competitions in Klingenthal, Lake Placid, Zakopane, Reit im Winkl).

The FIS database has the podium of the World Cup B before 2000/01 only (stored by
fis_nk_fisdb.py --circuit WCB); a list of weltcup-b.org has every athlete with
jump and cross-country.  It is read here and stored next to the FIS ranking of
its competition as doc type WBL (same file name, WBL instead of FDB); load_json.py
takes it in place of the ranking.

    python fis_nk_wcb_1990s.py            # downloads to fis_nk_wcb_pdfs/_raw/1990s/, then reads

The lists come from the organisers in several layouts (a text table, an HTML table
with one cell per line, a PDF); a line is an athlete when it has a rank, a name, a
nation, jump points and rank, a cross-country time and rank.
"""
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import fitz
import requests
from bs4 import BeautifulSoup

BASE = "https://www.weltcup-b.org/Weltcup-B/"
ROOT = Path(__file__).parent / "fis_nk_wcb_pdfs"
RAW = ROOT / "_raw" / "1990s"
# file of weltcup-b.org → season (the year it ends in)
FILES = {
    "WCB9697_Klingenthal.html": 1997, "WCB9697_Zakopane.pdf": 1997,
    "WCB9798_Klingenthal_1.html": 1998, "WCB9798_Klingenthal_2.html": 1998,
    "1998_99/BNK9899_Klingenthal_1.html": 1999, "1998_99/BNK9899_Klingenthal_2.html": 1999,
    "1998_99/BNK9899_Klingenthal_3.html": 1999, "1998_99/BNK9899_LakePlacid_1.html": 1999,
    "1998_99/BNK9899_LakePlacid_2.html": 1999, "1998_99/BNK9899_LakePlacid_3.html": 1999,
    "1998_99/BNK9899_Zakopane_15.html": 1999,
    "1999_00/Klingenthal1.htm": 2000, "1999_00/Klingenthal2.htm": 2000, "1999_00/WCB_Reit.pdf": 2000,
}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"], 1)}

# capitals of a surname, and the ß of LOOß
CAPS = "A-ZÄÖÜÉÈÁČŠŽØÅÆß"
# rank, bib, 'SURNAME, Given' / 'Surname, Given' / 'SURNAME Given', nation, jump points and
# rank, the start gap (some lists), cross-country time and rank
ROW = re.compile(
    r"(?<![\d:,.])(?P<rank>\d{1,3})\.?\s+(?:(?P<bib>\d{1,3})\s+)?"
    # letters only: a name must not reach over the numbers into the next athlete's row
    rf"(?:(?P<sur>[{CAPS}][^\W\d_'\- ]*(?:[ '\-][^\W\d_]+)*?),\s*(?P<giv>[^\W\d_]+(?:[ .'\-]+[^\W\d_]+)*\.?)"
    rf"|(?P<sur2>[{CAPS}'\-]{{2,}}(?:\s[{CAPS}'\-]{{2,}})*)\s+(?P<giv2>[^\W\d_]+(?:[ .'\-]+[^\W\d_]+)*?\.?))\s+"
    # 'USA-D': the second US team of Lake Placid
    r"(?P<nat>[A-Z]{3})(?:-[A-Z])?\s+(?P<jp>\d{2,3}[.,]\d)\s+(?P<jr>\d{1,3})\s+"
    r"(?:\d{1,2}:\d{2}(?![.,\d])\s+)?(?P<xc>\d{1,2}:\d{2}[.,]\d)\s+(?P<xr>\d{1,3})(?![\d:,.])")
# Reit im Winkl 1999: rank, year of birth, SURNAME Given, nation, club, cross-country time,
# points, rank, jump points, rank, total
REIT = re.compile(
    rf"^(?P<rank>\d{{1,3}})\s+(?:\d{{2}}\s+)?(?P<sur2>[{CAPS}'\-]{{2,}}(?:\s+[{CAPS}'\-]{{2,}})*)\s+"
    # a second given name has small letters ('Jan Rune'), the nation not ('Marco GER')
    r"(?P<giv2>[^\W\d_][\w.'\-]*(?:\s+[^\W\d_][a-zà-ÿ][\w.'\-]*)?)\s+(?P<nat>[A-Z]{3})\s+.*?"
    r"(?P<xc>\d{1,2}:\d{2},\d)\s+[\d,]+\s+(?P<xr>\d{1,3})\s+(?P<jp>\d{2,3},\d)\s+(?P<jr>\d{1,3})\s")


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        dest = RAW / f.replace("/", "_")
        if not dest.exists():
            r = requests.get(BASE + f, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            r.raise_for_status()
            dest.write_bytes(r.content)


def lines_of(path: Path) -> list:
    """The text of a list, one table row a line."""
    if path.suffix == ".pdf":
        lines = []
        for page in fitz.open(path):
            rows = {}
            for x0, y0, x1, y1, word, *_ in page.get_text("words"):
                rows.setdefault(round(y0 / 3), []).append((x0, word))
            lines += ["  ".join(w for _, w in sorted(ws)) for _, ws in sorted(rows.items())]
        return lines
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    rows = soup.find_all("tr")
    if len(rows) > 10:
        return ["  ".join(c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])) for tr in rows]
    return soup.get_text("\n").splitlines()


def competition_date(text: str, season: int):
    """'Klingenthal, 06./ 07.03.1999' → '1999-03-06'; 'Thursday, January 21, 1999' → '1999-01-21'."""
    m = re.search(r"(\d{1,2})\.\s*/?\s*(?:\d{1,2}\.)?\s*(\d{2})\.(\d{4})", text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"
    m = re.search(r"\b([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2}),?\s*(\d{4})", text)
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Z][a-z]{2})[a-z]*\s+(\d{4})", text)
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None


def fis_name(raw: str) -> str:
    """'SPILLANE, Johnny' / 'VAN LOAN Carl' → 'SPILLANE Johnny' / 'VAN LOAN Carl'."""
    raw = re.sub(r"\s+", " ", raw.replace(",", " ")).strip()
    return raw


def read(path: Path) -> list:
    lines = [l.replace("\xa0", " ") for l in lines_of(path)]
    if path.suffix == ".pdf":
        found = [m for m in (REIT.match(re.sub(r"\s+", " ", l) + " ") for l in lines) if m]
    else:
        found = [m for m in (ROW.search(re.sub(r"\s+", " ", l)) for l in lines) if m]
        if len(found) < 3:
            # rows broken over lines (the HTML of 1997 and 1998): one text, rows by pattern —
            # only then, as the points after a row ('… 00.0 31') would look like a rank there
            found = list(ROW.finditer(re.sub(r"\s+", " ", " ".join(lines))))
    rows, seen = [], set()
    for m in found:
        rank = int(m.group("rank"))
        g = m.groupdict()
        surname, given = (g.get("sur") or g.get("sur2")), (g.get("giv") or g.get("giv2"))
        if (rank, surname.upper()) in seen:
            continue
        seen.add((rank, surname.upper()))
        rows.append({
            "rank": rank, "bib": int(g["bib"]) if g.get("bib") else None,
            "name": f"{surname.strip().upper()} {given.strip()}", "nation": g["nat"],
            "jump_points": float(g["jp"].replace(",", ".")), "jump_rank": int(g["jr"]),
            "xc_time": g["xc"].replace(",", "."), "xc_rank": int(g["xr"]),
        })
    rows.sort(key=lambda r: r["rank"])
    # a list from the winner on; a tie shares the rank ('15, 15, 17'), a place the list
    # itself leaves out ('33, 35') is no reason to stop, two in a row are
    complete, missing = [], 0
    for i, r in enumerate(rows, 1):
        expected = i + missing
        if complete and r["rank"] == complete[-1]["rank"]:
            pass
        elif r["rank"] == expected + 1 and complete:
            missing += 1
        elif r["rank"] != expected:
            break
        complete.append(r)
    return complete


def fold(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def all_dates(text: str) -> list:
    """Every date in the head of a list: the jump and the race may be on different days."""
    head = text[:900]
    days = [competition_date(head[m.start():], 0) for m in re.finditer(r"\d{1,2}\.\s*/?\s*(?:\d{1,2}\.)?\s*\d{2}\.\d{4}"
                                                                         r"|[A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s*\d{4}"
                                                                         r"|\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]{2,8}\s+\d{4}",
                                                                         head)]
    days += [f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"
             for m in re.finditer(r"(\d{1,2})\.\s*/\s*(\d{2})\.(\d{4})", head)]   # '06./ 07.03.1999': the 06
    days += [f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"
             for m in re.finditer(r"/\s*(\d{1,2})\.(\d{2})\.(\d{4})", head)]       # … and the 07
    return sorted({d for d in days if d})


def match(path: Path, season: int, days: list, sprint: bool):
    """The FIS ranking (FDB) of the competition: same place, on a day of the list or next to it."""
    # '1998_99_BNK9899_Klingenthal_1' → 'klingenthal', '1999_00_WCB_Reit' → 'reit'
    stem = path.stem.split("_", 2)[-1] if path.stem.startswith("1") else path.stem
    place = fold(re.sub(r"(BNK|WCB)(\d{4})?_|_\d+$|\d+$", "", stem))
    best = None
    for fdb in sorted((ROOT / str(season)).glob("*/*/*FDB.json")):
        d = json.loads(fdb.read_text(encoding="utf-8"))
        if place[:6] not in fold(fdb.parent.parent.name) or d.get("team_results"):
            continue
        gap = min(abs((datetime.fromisoformat(d["competition_date"]) - datetime.fromisoformat(day)).days)
                  for day in days)
        # the date first (a list may say 'Einzel' of a sprint), the kind breaks a tie
        key = (gap, ("Sprint" in fdb.name) != sprint)
        if gap <= 1 and (best is None or key < best[0]):
            best = (key, fdb)
    return best[1] if best else None


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    download()
    stored = 0
    for f, season in FILES.items():
        path = RAW / f.replace("/", "_")
        text = "\n".join(lines_of(path))
        rows = read(path)
        days = all_dates(text.replace("\xa0", " "))
        sprint = bool(re.search(r"sprint", text[:600], re.I))
        fdb = match(path, season, days, sprint) if days else None
        print(f"  {f}: {len(rows)} athletes, {days}, {'sprint' if sprint else 'individual'}"
              f" → {fdb.name if fdb else 'no FIS competition'}")
        if not rows or not fdb:
            continue
        d = json.loads(fdb.read_text(encoding="utf-8"))
        top = [r["name"] for r in d["combined_results"][:3]]
        dest = fdb.with_name(fdb.name.replace("FDB.json", "WBL.json"))
        dest.write_text(json.dumps({
            "doc_type": "WBL",
            "source_file": BASE + f,
            "codex": d.get("codex"), "competition_date": d.get("competition_date"),
            "location": d.get("location"), "country": d.get("country"),
            "event_name": d.get("event_name"), "discipline": d.get("discipline"),
            "combined_results": rows, "team_results": [],
            "parse_errors": [], "warnings": [f"FIS podium: {', '.join(top)}"],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        stored += 1
    print(f"{stored} lists stored")


if __name__ == "__main__":
    main()
