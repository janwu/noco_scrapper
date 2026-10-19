#!/usr/bin/env python3
"""
db/load_json.py — build the database from the parsed JSON files.

The database is derived data: every run builds it from scratch out of
`output/` plus the alias lists in `db/aliases/`.  Nothing is patched in place,
so corrections belong either in the parser or in an alias file — never in
the database.

Usage:
    python db/load_json.py --sqlite db/noco.db
    python db/load_json.py --db "postgresql://user:pass@localhost/noco"

Options:
    --output-dir DIR    Directory with JSON files (default: output)
    --aliases-dir DIR   Directory with athletes.csv / venues.csv (default: db/aliases)
    --verbose           List every skipped document and rejected row

What is loaded
    ROF            → combined_results   (individual competitions)
                   → team_results + team_members   (team competitions)
    RL, PCR        → jump_round_results
    RLT            → training_jump_results
    RLTR           → trial_round_results
    RLLL           → xc_results
A list the parser flagged as broken (parse_errors) is recorded as a document,
but its rows are not loaded.
"""

import argparse
import csv
import difflib
import glob
import json
import logging
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fis_parser.detector import (                      # noqa: E402
    parse_filename_metadata, team_discipline_from_filename, venue_from_path,
)
from fis_parser.validate import is_team_discipline, row_identity_problem   # noqa: E402
from fis_parser.utils import team_name as fis_team_name                    # noqa: E402

log = logging.getLogger("loader")

DB_DIR = os.path.dirname(os.path.abspath(__file__))

# The World Cup B (until 2007/08) is the Continental Cup under its old name: one circuit
# full result lists of other sources than FIS, taken where no FIS result list was read:
# Olympedia (OLY, fis_nk_olympedia.py) and weltcup-b.org (WBL, fis_nk_wcb_1990s.py)
FULL_LISTS = ("OLY", "WBL")
CIRCUIT_BY_DIR = {"fis_nk_pdfs": "WC", "fis_nk_coc_pdfs": "COC", "fis_nk_wcb_pdfs": "COC",
                  "fis_nk_wsc_pdfs": "WSC", "fis_nk_owg_pdfs": "OWG"}
JUMP_TABLE_BY_DOC_TYPE = {
    "RL": "jump_round_results",
    "RL1": "jump_round_results",
    "RLQ": "jump_round_results",
    "PCR": "jump_round_results",
    "RLT": "training_jump_results",
    "RLTR": "trial_round_results",
}
TRAINING_DOC_TYPES = ("RLT", "RLTR")
KNOWN_STATUS = ("DNS", "DNF", "DSQ", "DNQ", "LAP", "NPS", "DQB")


# ─────────────────────────────────────────────────────────────────────────────
# Small converters
# ─────────────────────────────────────────────────────────────────────────────

def iso_date(s: Optional[str]) -> Optional[str]:
    """Any date spelling the parser may emit → 'YYYY-MM-DD' (or None)."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d.%m.%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def to_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def to_int(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def clean(s: Optional[str]) -> Optional[str]:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s or None


def status_of(row: dict) -> Optional[str]:
    s = (row.get("status") or "").strip().upper()
    if s in KNOWN_STATUS:
        return s
    for flag, status in (("dns", "DNS"), ("dnf", "DNF"), ("dsq", "DSQ"), ("dnq", "DNQ")):
        if row.get(flag):
            return status
    return None


_FIS_TRANSLITERATION = str.maketrans({
    "ø": "oe", "Ø": "Oe", "å": "aa", "Å": "Aa", "æ": "ae", "Æ": "Ae",
    "ö": "oe", "Ö": "Oe", "ä": "ae", "Ä": "Ae", "ü": "ue", "Ü": "Ue", "ß": "ss",
})


def to_ascii(name: str) -> str:
    """'Jørgen' → 'Joergen' — the way FIS lists spell names; other accents are dropped."""
    name = unicodedata.normalize("NFKD", name.translate(_FIS_TRANSLITERATION))
    return "".join(ch for ch in name if not unicodedata.combining(ch))


def name_words(name: str) -> List[str]:
    """The words of a name, independent of order, case, hyphens and transliteration."""
    return re.findall(r"[a-z]+", to_ascii(name).lower())


def split_name(full_name: str) -> Tuple[str, Optional[str]]:
    """'WESTVOLD HANSEN Gyda' → ('WESTVOLD HANSEN', 'Gyda')."""
    tokens = full_name.split()
    n = 0
    while n < len(tokens) and tokens[n].upper() == tokens[n] and any(ch.isalpha() for ch in tokens[n]):
        n += 1
    if n == 0 or n == len(tokens):          # no clear split — fall back to first token
        n = 1
    return " ".join(tokens[:n]), " ".join(tokens[n:]) or None


# ─────────────────────────────────────────────────────────────────────────────
# What the path says about a file
# ─────────────────────────────────────────────────────────────────────────────

def file_meta(path: str, output_dir: str) -> Optional[dict]:
    """
    output/<fis_nk_pdfs|fis_nk_coc_pdfs>/<season>/<event>/<M|W>/<codex>_<date>_….json

    The season is the folder (the year the season ends in); older file names
    carry no season at all.  Returns None for files outside that layout.
    """
    rel = os.path.relpath(path, output_dir).replace("\\", "/").split("/")
    if len(rel) < 3 or rel[0] not in CIRCUIT_BY_DIR or not re.fullmatch(r"(19|20)\d{2}", rel[1]):
        return None
    name = rel[-1]
    m = re.match(r"(\d{3,5})_", name)
    if not m:
        return None

    gender = rel[-2] if rel[-2] in ("M", "W") else None
    mixed = re.search(r"_(?:WC|COC|WSC|OWG)_A_X_|_X_(?:\d{4}NK)?\d{4}[A-Z0-9]+\.json$|Mixed", name)
    if mixed:
        gender = "X"

    hs = re.search(r"_HS(\d{2,3})(?:_|\b)", name)
    hill_class = re.search(r"(Normal|Large|Flying|Medium)_Hill|_(NH|LH|FH|MH)_", name, re.IGNORECASE)
    km = re.search(r"_(\d{1,2}(?:\.\d)?)_?K(?:m)?(?:_|\b)", name, re.IGNORECASE)
    relay = re.search(r"_\dx(\d{1,2}(?:\.\d)?)", name)
    fn = parse_filename_metadata(path)
    season_end = int(rel[1])
    return {
        "circuit": CIRCUIT_BY_DIR[rel[0]],
        "season_start": season_end - 1,
        "season_label": f"{season_end - 1}/{season_end}",
        "codex": m.group(1),
        "gender": gender,
        "file_date": fn.get("date"),
        "hill_size_m": float(hs.group(1)) if hs else None,
        "hill_class": ((hill_class.group(1) or hill_class.group(2))[0].upper() + "H") if hill_class else None,
        "xc_distance_km": float(relay.group(1)) if relay else float(km.group(1)) if km else None,
        "team": team_discipline_from_filename(name),
        "provisional": bool(re.search(r"_PR_[MWA]_[MWX]_|PCR\.json$", name)),
        "discipline_hint": fn.get("discipline_hint"),
        "basename": name,
        "source_dir": rel[0],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Alias lists
# ─────────────────────────────────────────────────────────────────────────────

def load_display_names(path: str) -> Dict[Tuple[str, str], str]:
    """CSV with 3 columns: name and nation/country as stored, the name to show in the web app."""
    names: Dict[Tuple[str, str], str] = {}
    if not os.path.exists(path):
        return names
    with open(path, encoding="utf-8", newline="") as fh:
        for line in csv.reader(fh):
            if len(line) < 3 or not line[0].strip() or line[0].lstrip().startswith("#") or line[0] == "name":
                continue
            names[(line[0].strip(), line[1].strip().upper())] = line[2].strip()
    return names


def load_aliases(path: str) -> Dict[Tuple[str, str], Tuple[str, str]]:
    """CSV with 4 columns: name, nation/country, canonical name, canonical nation/country."""
    aliases: Dict[Tuple[str, str], Tuple[str, str]] = {}
    if not os.path.exists(path):
        log.warning("Alias file not found: %s", path)
        return aliases
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)                                   # header
        for line in reader:
            if len(line) < 4 or not line[0].strip() or line[0].lstrip().startswith("#"):
                continue
            name, nat, cname, cnat = (c.strip() for c in line[:4])
            aliases[(name, nat)] = (cname, cnat)
    # Follow chains (A → B, B → C) so the order of lines does not matter
    for key in list(aliases):
        seen = {key}
        target = aliases[key]
        while target in aliases and aliases[target] not in seen:
            seen.add(target)
            target = aliases[target]
        aliases[key] = target
    return aliases


# ─────────────────────────────────────────────────────────────────────────────
# The in-memory database being built
# ─────────────────────────────────────────────────────────────────────────────

class Build:
    """Collects all rows; ids are assigned here so tables can be bulk-inserted."""

    def __init__(self, athlete_aliases, venue_aliases):
        self.athlete_aliases = athlete_aliases
        self.venue_aliases = venue_aliases
        self.rows: Dict[str, List[tuple]] = defaultdict(list)
        self.next_id: Counter = Counter()

        self.seasons: Dict[int, int] = {}
        self.venues: Dict[Tuple[str, str], int] = {}
        self.venue_variants: Dict[Tuple[str, str], Tuple[int, str]] = {}
        self.athletes: Dict[Tuple[str, str], dict] = {}
        self.athlete_variants: Dict[Tuple[str, str], Tuple[int, str]] = {}

        self.nations_by_name: Dict[str, set] = defaultdict(set)   # every name → nations seen with it
        self.result_nations: set = set()                          # nations in validated ROFs
        # athletes of the validated result and competition jump lists: training and
        # trial rounds link to these, they do not add athletes of their own
        self.official_athletes: set = set()                       # (name, nation) after aliases
        self.fdb_used = 0                                         # competitions ranked from the FIS database
        self.oly_used = 0                                         # Olympic results from Olympedia
        self.wbl_used = 0                                         # World Cup B lists of weltcup-b.org (1990s)
        self.olympedia_names = 0                                  # 'HAUG Th' rows given 'HAUG Thorleif'
        self.fdb_disagree: list = []                              # (file, top 3 of the PDF, top 3 of FIS)
        # names with native letters for the web app; the stored name stays as FIS writes it
        self.athlete_display: Dict[Tuple[str, str], str] = {}
        self.venue_display: Dict[Tuple[str, str], str] = {}
        self.recovered_nations: Counter = Counter()               # doc_type → rows
        self.recovered_names: Counter = Counter()                 # doc_type → rows
        self.names_by_words: Dict[Tuple[str, frozenset], set] = defaultdict(set)   # (nation, words) → names
        self.reordered_names: Counter = Counter()                 # 'matched' / 'surname guessed' → rows
        self.guessed_names: set = set()
        self.standings_rows: Counter = Counter()                  # matched to an athlete? → rows
        self.standings_unmatched: set = set()

        self.skipped_docs: List[Tuple[str, str]] = []        # (reason, file)
        self.hill_class: Dict[int, Optional[str]] = {}          # competition id → NH, LH, ...
        self.rejected_rows: Counter = Counter()              # (doc_type, reason) → n
        self.rejected_examples: Dict[Tuple[str, str], List[str]] = defaultdict(list)

    def new_id(self, table: str) -> int:
        self.next_id[table] += 1
        return self.next_id[table]

    def add(self, table: str, *values) -> int:
        row_id = self.new_id(table)
        self.rows[table].append((row_id,) + values)
        return row_id

    # ── dimensions ──────────────────────────────────────────────────────────

    def season(self, start_year: int, label: str) -> int:
        if start_year not in self.seasons:
            self.seasons[start_year] = self.add("seasons", start_year, label)
        return self.seasons[start_year]

    def venue(self, location: Optional[str], country: Optional[str], source: str) -> Optional[int]:
        location, country = clean(location), (clean(country) or "").upper()
        if not location or not country:
            return None
        raw = (location, country)
        name, ctry = self.venue_aliases.get(raw, raw)
        if (name, ctry) not in self.venues:
            self.venues[(name, ctry)] = self.new_id("venues")
        venue_id = self.venues[(name, ctry)]
        self.venue_variants.setdefault(raw, (venue_id, source))
        return venue_id

    def athlete(self, row: dict, comp: dict, source: str) -> int:
        raw = (clean(row.get("name")), (row.get("nation") or "").upper())
        key = self.athlete_aliases.get(raw, raw)
        a = self.athletes.get(key)
        if a is None:
            a = self.athletes[key] = {
                "id": self.new_id("athletes"), "name": key[0], "nation": key[1],
                "genders": Counter(), "dobs": Counter(), "club": None, "club_date": "",
            }
        if comp["gender"] in ("M", "W"):
            a["genders"][comp["gender"]] += 1
        dob = iso_date(row.get("date_of_birth"))
        if dob:
            a["dobs"][dob] += 1
        club, when = clean(row.get("club")), comp["date"] or ""
        if club and when >= a["club_date"]:
            a["club"], a["club_date"] = club, when
        self.athlete_variants.setdefault(raw, (a["id"], source))
        return a["id"]

    def nation_for(self, name: Optional[str], competition_nations: Dict[str, set]) -> Optional[str]:
        for known in (competition_nations, self.nations_by_name):
            nations = known.get(name) or ()
            if len(nations) == 1:
                return next(iter(nations))
        return None

    def find_athlete(self, name: str, nation: str) -> Optional[dict]:
        """
        An athlete already built from the result lists, looked up by a name
        from another source (the FIS database).  Tried in turn: the exact
        name, the same words in another order or spelling ('Jørgen' /
        'Joergen'), and the name alone if only one nation ever carried it
        (athletes who changed nation).
        """
        key = self.athlete_aliases.get((name, nation), (name, nation))
        if key in self.athletes:
            return self.athletes[key]
        candidates = {self.athlete_aliases.get((n, nation), (n, nation))
                      for n in self.names_by_words.get((nation, frozenset(name_words(name))), ())}
        nations = self.nations_by_name.get(name) or ()
        if not candidates and len(nations) == 1:
            other = next(iter(nations))
            candidates = {self.athlete_aliases.get((name, other), (name, other))}
        found = [self.athletes[c] for c in candidates if c in self.athletes]
        return found[0] if len(found) == 1 else None

    def surname_first(self, name: str, nation: str) -> Tuple[str, bool]:
        """
        Turn a 'Firstname Surname' name into the 'SURNAME Firstname' spelling.
        If an athlete of that nation with the same words is already known, his
        spelling is used (which also settles double surnames); otherwise the
        last word is taken as the surname.  Returns (name, was it a known athlete).
        """
        words = frozenset(name_words(name))
        candidates = {self.athlete_aliases.get((n, nation), (n, nation))
                      for n in self.names_by_words.get((nation, words), ())}
        if len(candidates) == 1:
            return next(iter(candidates))[0], True
        parts = to_ascii(name).split()
        return f"{parts[-1].upper()} {' '.join(parts[:-1])}", False

    def known_spelling(self, name: Optional[str], nation: str) -> Optional[str]:
        """'Van Loan Carl' → 'VAN LOAN Carl' if that athlete exists with this nation."""
        tokens = (name or "").split()
        for n in range(1, len(tokens)):
            candidate = " ".join([t.upper() for t in tokens[:n]] + tokens[n:])
            if nation in self.nations_by_name.get(candidate, ()):
                return candidate
        return None

    def reject(self, doc_type: str, reason: str, example: str) -> None:
        self.rejected_rows[(doc_type, reason)] += 1
        if len(self.rejected_examples[(doc_type, reason)]) < 5:
            self.rejected_examples[(doc_type, reason)].append(example)


# ─────────────────────────────────────────────────────────────────────────────
# Reading
# ─────────────────────────────────────────────────────────────────────────────

def read_documents(output_dir: str, build: Build) -> Dict[Tuple[str, str, int], List[Tuple[dict, dict]]]:
    """All JSON files grouped by competition (codex, season); one entry per PDF."""
    by_comp: Dict[Tuple[str, str, int], List[Tuple[dict, dict]]] = defaultdict(list)
    seen = set()
    for path in sorted(glob.glob(os.path.join(output_dir, "**", "*.json"), recursive=True)):
        meta = file_meta(path, output_dir)
        if meta is None:
            build.skipped_docs.append(("not in <circuit>/<season>/… layout", path))
            continue
        key = (meta["circuit"], meta["season_start"], meta["basename"])
        if key in seen:
            build.skipped_docs.append(("duplicate of an already loaded file", path))
            continue
        seen.add(key)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        meta["doc_type"] = (doc.get("doc_type") or "").upper() or None
        # The parser reads them as RL; kept apart: RL1 is the first round of a
        # two-round RL, RLQ a qualification round before the competition round
        suffix = re.search(r"(RL1|RLQ)\.json$", meta["basename"], re.IGNORECASE)
        if meta["doc_type"] == "RL" and suffix:
            meta["doc_type"] = suffix.group(1).upper()
        if not meta["doc_type"]:
            build.skipped_docs.append(("no doc_type", path))
            continue
        by_comp[(meta["circuit"], meta["codex"], meta["season_start"])].append((meta, doc))
    return by_comp


def describe_competition(docs: List[Tuple[dict, dict]]) -> dict:
    """
    One competition, described by all its documents.  The official result
    list (ROF) is the authority for date, venue and format; the other
    documents and the file name fill what it leaves open.
    """
    ordered = sorted(docs, key=lambda md: (md[0]["doc_type"] != "ROF", md[0]["basename"]))
    metas = [m for m, _ in ordered]
    rof = next((d for m, d in ordered if m["doc_type"] == "ROF"), None)
    primary_meta, primary = ordered[0]

    def first(getter):
        for m, d in ordered:
            value = getter(m, d)
            if value:
                return value
        return None

    team = first(lambda m, d: m["team"])
    # the FIS database has individual rankings only: a list it ranks, not read, says nothing
    rof_discipline = None if rof is not None and rof.get("parse_errors") \
        and any(m["doc_type"] == "FDB" for m in metas) else (rof or {}).get("discipline")
    if is_team_discipline(rof_discipline):
        team = rof_discipline
    fmt = team or rof_discipline or first(lambda m, d: m["discipline_hint"]) \
        or first(lambda m, d: d.get("discipline"))
    if not fmt and any(re.match(r"\d+_\d{8}_(Individual|Nordic_Combined)_", m["basename"]) for m in metas):
        # before the Gundersen method (1985): jump and cross-country in points, no pursuit start
        fmt = "Individual"
    if rof is None and any(m["provisional"] for m in metas):
        # The provisional competition round has a codex of its own; it is a
        # jumping round, not a competition with a result list.
        fmt = "Provisional Round"

    # venue from a list that was read (the ROF first): a list that failed validation may
    # have taken a line of the header for the place ('Technical Delegate: Jarkko Laine')
    readable = [d for _, d in ordered if not d.get("parse_errors")] + \
        [d for _, d in ordered if d.get("parse_errors")]
    place_doc = next((d for d in readable if clean(d.get("location"))), {})
    location = clean(place_doc.get("location"))
    country = clean(place_doc.get("country")) or next(
        (clean(d.get("country")) for d in readable if clean(d.get("country"))), None)
    if not location or not country:
        place, ctry = venue_from_path(primary.get("source_file") or "")
        location, country = location or place, country or ctry

    hill = first(lambda m, d: (d.get("hill_data") or {}).get("hill_size_m")) \
        if any(m["doc_type"] in JUMP_TABLE_BY_DOC_TYPE for m in metas) else None
    return {
        "circuit": primary_meta["circuit"],
        "season_start": primary_meta["season_start"],
        "season_label": primary_meta["season_label"],
        "codex": primary_meta["codex"],
        "gender": first(lambda m, d: m["gender"]),
        "date": iso_date((rof or {}).get("competition_date")) or first(lambda m, d: m["file_date"]),
        "location": location,
        "country": (country or "").upper() or None,
        "format": fmt,
        "team": bool(team),
        "hill_size_m": to_float(hill) or first(lambda m, d: m["hill_size_m"]),
        "hill_class": first(lambda m, d: m["hill_class"]),
        "xc_distance_km": first(lambda m, d: m["xc_distance_km"]),
        "event_name": clean((rof or {}).get("event_name")) or first(lambda m, d: clean(d.get("event_name"))),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Building
# ─────────────────────────────────────────────────────────────────────────────

def has_values(d: Optional[dict], ignore=()) -> bool:
    return bool(d) and any(v not in (None, "") for k, v in d.items() if k not in ignore)


def add_details(build: Build, comp_id: int, doc_id: int, doc: dict) -> None:
    hd = doc.get("hill_data")
    if has_values(hd, ignore=("name",)):
        build.add("hill_data", comp_id, doc_id, to_float(hd.get("hill_size_m")), to_float(hd.get("k_point_m")),
                  to_float(hd.get("meter_value")), to_float(hd.get("gate_factor")),
                  to_float(hd.get("wind_factor_head")), to_float(hd.get("wind_factor_tail")))
    ci = doc.get("course_info")
    if has_values(ci):
        lap = to_float(ci.get("lap_length_m"))
        build.add("course_info", comp_id, doc_id, to_float(ci.get("height_difference_m")),
                  to_float(ci.get("maximum_climb_m")), to_float(ci.get("total_climb_m")),
                  round(lap / 1000, 3) if lap else None, to_int(ci.get("number_of_laps")))
    w = doc.get("weather")
    if has_values(w):
        build.add("weather_records", comp_id, doc_id, w.get("weather_description"), w.get("snow_conditions"),
                  *(to_float(w.get(k)) for k in (
                      "temp_air_c", "temp_snow_c", "temp_air_start_c", "temp_air_finish_c",
                      "temp_snow_start_c", "temp_snow_finish_c", "humidity_start_pct",
                      "humidity_finish_pct", "wind_min_ms", "wind_max_ms", "wind_avg_ms")))
    for j in doc.get("jury") or []:
        name = clean(j.get("name"))
        if name:
            last, first = split_name(name.rstrip(","))
            build.add("jury_officials", doc_id, j.get("role"), last, first, j.get("nation"))
    for j in doc.get("judges") or []:
        name = clean(j.get("name"))
        if name:
            last, first = split_name(name.rstrip(","))
            build.add("jumping_judges", doc_id, j.get("position"), last, first, j.get("nation"))


def add_results(build: Build, comp: dict, comp_id: int, doc_id: int, meta: dict, doc: dict) -> None:
    doc_type, source = meta["doc_type"], meta["basename"]

    given_first = doc.get("name_order") == "given-first"

    def athlete_rows(key):
        for r in doc.get(key) or []:
            if given_first and not row_identity_problem(r, given_first=True):
                # 'Jørgen Berget Storsveen' → 'BERGET STORSVEEN Joergen'
                name, known = build.surname_first(clean(r["name"]), r["nation"].upper())
                r = dict(r, name=name)
                build.reordered_names["matched" if known else "surname guessed"] += 1
                if not known:
                    build.guessed_names.add(f"{name} [{r['nation']}]")
            problem = row_identity_problem(r)
            if problem and problem.startswith("name does not start"):
                # Early lists print 'Jezersek Andrej'.  Accept the row if
                # upper-casing the surname gives an athlete already known
                # with this nation.
                known = build.known_spelling(clean(r.get("name")), (r.get("nation") or "").upper())
                if known:
                    r = dict(r, name=known)
                    build.recovered_names[doc_type] += 1
                    problem = None
            if problem and problem.startswith("invalid nation"):
                # Some jump lists print no nation (or the FIS code in its
                # place).  The athlete is still identifiable if the name
                # occurs with exactly one nation in this competition or,
                # failing that, anywhere in the data.
                nation = build.nation_for(clean(r.get("name")), comp["nations"])
                if nation:
                    r = dict(r, nation=nation)
                    build.recovered_nations[doc_type] += 1
                    problem = None
            if not problem and doc_type in TRAINING_DOC_TYPES:
                key = (clean(r["name"]), r["nation"].upper())
                if build.athlete_aliases.get(key, key) not in build.official_athletes:
                    # someone who only trained, or a spelling the result lists do not use
                    problem = "athlete in no result or competition jump list"
            if not problem and doc_type != "ROF" and r["nation"].upper() not in build.result_nations:
                # Jump and training lists are not validated; a three-letter
                # word there ('CUP', 'WED', 'ICR') is only a nation if some
                # official result list knows it.
                problem = "nation not in any official result list"
            if problem:
                build.reject(doc_type, problem.split(":")[0].split(" for ")[0].split(" '")[0],
                             f"{r.get('name')!r} [{r.get('nation')}] in {source}")
                continue
            yield r, build.athlete(r, comp, source)

    if doc.get("parse_errors"):
        build.skipped_docs.append((f"{doc_type} failed validation: {doc['parse_errors'][0]}", source))
        return
    if doc_type in ("ROF", "FDB", *FULL_LISTS):
        if comp["team"]:
            add_team_results(build, comp, comp_id, doc_id, doc, source)
            return
        for r, athlete_id in athlete_rows("combined_results"):
            build.add("combined_results", comp_id, doc_id, athlete_id, clean(r.get("name")), r.get("nation"),
                      to_int(r.get("rank")), to_int(r.get("bib")), clean(r.get("club")),
                      iso_date(r.get("date_of_birth")), to_float(r.get("jump_points")),
                      to_int(r.get("jump_rank")), r.get("time_difference"), r.get("xc_time"),
                      to_int(r.get("xc_rank")), r.get("time_behind"),
                      1 if r.get("wave_start") else 0, status_of(r))

    elif doc_type in JUMP_TABLE_BY_DOC_TYPE:
        table = JUMP_TABLE_BY_DOC_TYPE[doc_type]
        for r, athlete_id in athlete_rows("jump_rounds"):
            values = (comp_id, doc_id, athlete_id, clean(r.get("name")), r.get("nation"),
                      to_int(r.get("rank")), to_int(r.get("bib")), clean(r.get("club")),
                      iso_date(r.get("date_of_birth")), to_int(r.get("round_number")),
                      to_float(r.get("speed_kmh")), to_float(r.get("distance_m")), to_float(r.get("dist_points")),
                      to_float(r.get("judge_a")), to_float(r.get("judge_b")), to_float(r.get("judge_c")),
                      to_float(r.get("judge_d")), to_float(r.get("judge_e")), to_float(r.get("style_points")),
                      to_int(r.get("gate")), to_float(r.get("gate_comp_pts")), to_float(r.get("wind_ms")),
                      to_float(r.get("wind_comp_pts")), to_float(r.get("total_points")),
                      1 if r.get("dns") else 0, 1 if r.get("dsq") else 0, r.get("dsq_reason"),
                      1 if r.get("fall") else 0)
            if table == "jump_round_results":
                values += (r.get("pursuit_time_diff"),)
            build.add(table, *values)

    elif doc_type == "RLLL":
        for r, athlete_id in athlete_rows("xc_results"):
            build.add("xc_results", comp_id, doc_id, athlete_id, clean(r.get("name")), r.get("nation"),
                      to_int(r.get("rank")), to_int(r.get("bib")), clean(r.get("club")),
                      iso_date(r.get("date_of_birth")), r.get("total_time"), r.get("time_behind"),
                      to_float(r.get("points")), status_of(r))


def add_team_results(build: Build, comp: dict, comp_id: int, doc_id: int, doc: dict, source: str) -> None:
    for t in doc.get("team_results") or []:
        team_nation = (t.get("nation") or "").upper()
        team_id = build.add(
            "team_results", comp_id, doc_id, to_int(t.get("rank")), to_int(t.get("bib")), team_nation,
            clean(t.get("team_name")), to_int(t.get("jump_rank")), t.get("time_difference"),
            to_int(t.get("xc_rank")), t.get("xc_time"), t.get("time_behind"),
            to_float(t.get("jump_points")), status_of(t))
        for m in t.get("members") or []:
            name = clean(m.get("name"))
            # Mixed-nation teams run as 'FIS'; the athlete keeps his own nation
            nation = team_nation if team_nation in build.result_nations and team_nation != "FIS" \
                else build.nation_for(name, comp["nations"])
            # a team of two nations runs under one of them ('AUT/JPN'): the athlete keeps his own
            own = build.nations_by_name.get(name) or set()
            if own and team_nation not in own and len(own) == 1:
                nation = next(iter(own))
            athlete_id = None
            row = {"name": name, "nation": nation}
            if nation and not row_identity_problem(row):
                athlete_id = build.athlete(row, comp, source)
            else:
                build.reject("ROF", "team athlete not linked (nation unknown)", f"{name!r} in {source}")
            build.add("team_members", team_id, athlete_id, name, nation or team_nation,
                      to_int(m.get("leg")), m.get("xc_time"), to_float(m.get("jump_points")))


def names_with_nation(docs: List[Tuple[dict, dict]]) -> Dict[str, set]:
    """name → nations, from every row of these documents that is a complete athlete."""
    found: Dict[str, set] = defaultdict(set)
    for _, doc in docs:
        for key in ("combined_results", "jump_rounds", "xc_results"):
            for r in doc.get(key) or []:
                if not row_identity_problem(r):
                    found[clean(r["name"])].add(r["nation"].upper())
    return found


def add_standings(build: Build, standings_dir: Optional[str]) -> None:
    """
    Official cup standings downloaded by fis_nk_standings_scraper.py.
    Athletes are matched to those of the result lists; the FIS competitor id
    comes along and is stored with the athlete.
    """
    if not standings_dir or not os.path.isdir(standings_dir):
        log.warning("No cup standings directory (%s) — cup_standings stays empty", standings_dir)
        return
    for path in sorted(glob.glob(os.path.join(standings_dir, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        season_end = int(data["season"])
        season_id = build.season(season_end - 1, f"{season_end - 1}/{season_end}")
        for row in data["rows"]:
            name, nation = clean(row["name"]), (row.get("nation") or "").upper()
            athlete = build.find_athlete(name, nation)
            if athlete is None:
                build.standings_unmatched.add(f"{name} [{nation}]")
            else:
                athlete.setdefault("fis_id", row.get("competitor_id"))
            for code, standing in row["standings"].items():
                build.add("cup_standings", season_id, data["cup"], data["gender"], code,
                          data["disciplines"].get(code), standing["rank"], standing.get("points"),
                          athlete["id"] if athlete else None, name, nation, row.get("competitor_id"))
                build.standings_rows[athlete is not None] += 1


def fill_hill_sizes(build: Build) -> None:
    """
    A competition with neither a jump list nor 'HS142' in its file name (the FIS
    event pages stopped printing the hill size in 2026) gets the hill size of
    the other competitions on the same hill at the same event: same venue,
    at most four days apart, same hill class (NH, LH) where it is known.
    """
    # competitions: (id, season, venue, codex, circuit, gender, date, location, country,
    #                format, hill_size_m, xc_distance_km, event_name)
    rows = build.rows["competitions"]
    known = [r for r in rows if r[10] and r[6]]
    filled = 0
    for i, r in enumerate(rows):
        if r[10] or not r[6]:
            continue
        day = date.fromisoformat(r[6])
        cls = build.hill_class.get(r[0])
        sizes = {k[10] for k in known if k[2] == r[2]
                 and abs((date.fromisoformat(k[6]) - day).days) <= 4
                 and (cls is None or build.hill_class.get(k[0]) in (None, cls))}
        if len(sizes) == 1:
            rows[i] = r[:10] + (sizes.pop(),) + r[11:]
            filled += 1
    if filled:
        log.info("Hill size taken from the same hill at the same event: %d competitions", filled)


def _fold(text: str) -> str:
    """'MÜNCHMEYER' / 'MUENCHMEYER' / 'Munchmeyer' → 'munchmeyer'; 'ØSTVIK' / 'OESTVIK' / 'OSTVIK' → 'ostvik'."""
    s = to_ascii(text or "").lower()
    for a, b in (("oe", "o"), ("ae", "a"), ("ue", "u"), ("aa", "a")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z]", "", s)


def _surname(name: str) -> str:
    """The surname of 'SURNAME Firstname' (or of 'Surname Firstname', the first word)."""
    words = (name or "").replace(",", " ").split()
    caps = [w for w in words if w.isupper() and len(w) > 1]
    return " ".join(caps) if caps else (words[0] if words else "")


def _given(name: str) -> str:
    words = (name or "").replace(",", " ").split()
    return " ".join(w for w in words if not (w.isupper() and len(w) > 1))


def fis_spelling(by_comp: Dict, build: Build) -> None:
    """
    World Cup B: the lists of weltcup-b.org and of the organisers spell names their
    way ('MÜNCHMEYER Stephan', 'FADEJEV Aleksej', 'Braaten, Kenneth', 'MENZ Matthias,');
    the ranking of the FIS database (doc type FDB) has the FIS spelling.  A row of
    another list of the competition takes the FIS name of the one athlete of that
    ranking with the same surname and nation (letters folded: ü = ue = u).  Team lists,
    which have no ranking, look in all rankings and also compare the given name.

    The FIS database gives Russians and Belarusians of those years as 'AIN' (neutral
    athletes, as of today); they get the nation the lists of the competition print.
    """
    def words(name: str) -> frozenset:
        return frozenset(w for w in (_fold(x) for x in re.split(r"[\s\-,]+", name or "")) if len(w) > 1)

    fdb_rows = [r for docs in by_comp.values() for meta, doc in docs if meta["doc_type"] == "FDB"
                for r in doc.get("combined_results") or []]
    def resolve_ain() -> None:
        """'AIN' in one ranking, the real nation in another or in any readable list."""
        nations_of = defaultdict(set)
        for docs in by_comp.values():
            for meta, doc in docs:
                if doc.get("parse_errors"):
                    continue
                rows = [(r, r.get("nation")) for key in ("combined_results", "jump_rounds", "xc_results")
                        for r in doc.get(key) or []]
                rows += [(m, t.get("nation")) for t in doc.get("team_results") or [] for m in t.get("members") or []]
                for r, nation in rows:
                    if r.get("name") and nation and nation.upper() not in ("AIN", "OAR", "RPF", "RSF", "ROC", "FIS"):
                        nations_of[words(r["name"])].add(nation.upper())
        for r in fdb_rows:
            if r["nation"] == "AIN":
                nations = nations_of.get(words(r["name"]), set())
                if len(nations) == 1:
                    r["nation"] = next(iter(nations))

    # the early FIS database writes native letters small in a surname: 'STRöMSTAD Th.' → 'STRÖMSTAD Th.'
    def surname_case(name: str) -> str:
        return " ".join(w.upper() if any(c.isupper() for c in w) and all(c.isupper() for c in w if c.isascii()
                                                                          and c.isalpha()) else w
                        for w in (name or "").split(" "))

    for r in fdb_rows:
        r["name"] = surname_case(r.get("name"))
    for docs in by_comp.values():
        for meta, doc in docs:
            if meta["doc_type"] == "FDB":
                for t in doc.get("team_results") or []:
                    t["team_name"] = fis_team_name(t.get("team_name") or "")
                    for m in t.get("members") or []:
                        m["name"] = surname_case(m.get("name"))

    # a team of the FIS database given as 'AIN' has its nation in its name ('Russia', 'Belarus II')
    for docs in by_comp.values():
        for meta, doc in docs:
            if meta["doc_type"] == "FDB":
                for t in doc.get("team_results") or []:
                    if t.get("nation") == "AIN":
                        name = (t.get("team_name") or "").lower()
                        t["nation"] = "RUS" if name.startswith("russia") else \
                            "BLR" if name.startswith("belarus") else "AIN"
    resolve_ain()
    # FIS names of all rankings, by nation and the words of the name, and by nation,
    # surname and the start of the given name (looked up for every row: an index)
    by_words, by_surname = defaultdict(set), defaultdict(set)
    for r in fdb_rows:
        by_words[(r["nation"], words(r["name"]))].add(r["name"])
        by_surname[(r["nation"], _fold(_surname(r["name"])), _fold(_given(r["name"]))[:2])].add(r["name"])
    fixed = 0
    for docs in by_comp.values():
        if not any(meta.get("source_dir") == "fis_nk_wcb_pdfs" for meta, _ in docs):
            continue
        ranking = [r for meta, doc in docs if meta["doc_type"] == "FDB" for r in doc.get("combined_results") or []]
        here = defaultdict(set)
        for r in ranking:
            here[_fold(_surname(r["name"]))].add((r["name"], r["nation"]))
        printed = defaultdict(set)            # surname → nations printed in the PDFs of the competition
        for meta, doc in docs:
            if meta["doc_type"] == "FDB":
                continue
            for key in ("combined_results", "jump_rounds", "xc_results"):
                for r in doc.get(key) or []:
                    if r.get("name") and r.get("nation"):
                        printed[_fold(_surname(r["name"]))].add(r["nation"].upper())
            for t in doc.get("team_results") or []:
                for m in t.get("members") or []:
                    if m.get("name") and t.get("nation"):
                        printed[_fold(_surname(m["name"]))].add(t["nation"].upper())
        for r in ranking:
            if r["nation"] == "AIN":
                nations = (printed.get(_fold(_surname(r["name"]))) or set()) - {"AIN"}
                if len(nations) == 1:
                    r["nation"] = next(iter(nations))
        for meta, doc in docs:
            if meta["doc_type"] == "FDB":
                continue
            rows = [r for key in ("combined_results", "jump_rounds", "xc_results") for r in doc.get(key) or []]
            members = [(m, t) for t in doc.get("team_results") or [] for m in t.get("members") or []]
            for r, team in [(r, None) for r in rows] + members:
                name = (r.get("name") or "").strip().rstrip(",.").strip()
                if not name:
                    continue
                nation = (r.get("nation") or (team or {}).get("nation") or "").upper()
                surname = _fold(_surname(name))
                hits = {n for n, nat in here.get(surname, ()) if not nation or nat in (nation, "AIN")}
                if not hits:
                    # not in the ranking of the competition (a team, or no ranking): any World Cup B
                    # ranking, the same words in any order ('AAM Torkild Rasmussen' / 'RASMUSSEN
                    # Torkild Aam') or, with the same surname, the same start of the given name
                    w = words(name)
                    given = _fold(_given(name))[:2]
                    hits = by_words.get((nation, w), set())
                    if not hits:
                        hits = by_surname.get((nation, surname, given), set())
                if len(hits) == 1:
                    fis_name = next(iter(hits))
                    if fis_name != r.get("name"):
                        r["name"] = fis_name
                        fixed += 1
                elif name != r.get("name"):
                    r["name"] = name
    # once more: the lists of other competitions now carry the FIS names too
    resolve_ain()
    if fixed:
        log.info("World Cup B: %d rows take the FIS spelling of the name", fixed)


def _split_initials(name: str):
    """'NILSSON A.H.' → ('NILSSON', ['A', 'H']); 'HAUG Th' → ('HAUG', ['Th']); a full name → None."""
    words = (name or "").split()
    surname = []
    while words and words[0].isupper() and "." not in words[0] and len(words[0]) > 1:
        surname.append(words.pop(0))
    given = " ".join(words)
    tokens = [t for t in re.split(r"[\s.\-]+", given) if t]
    if not surname or not tokens or any(len(t) > 2 for t in tokens):
        return None
    return " ".join(surname), tokens


def olympedia_names(by_comp: Dict, build: Build) -> None:
    """
    The early FIS database gives many athletes with initials only ('HAUG Th',
    'GRÖTTUMSBRAATEN J.', 'NILSSON A.H.'); Olympedia (doc type OLY) has the full name
    of every Olympian ('HAUG Thorleif', 'NILSSON Axel-Herman').  A name with initials
    takes the full name of the one Olympian of the same nation (lineage) and surname
    whose given names start with these initials — in every list, also of World
    Championships without Olympians.
    """
    # Olympedia writes names its way ('BREDESEN Trond Arne', 'ŠMEJC Petr'): the one FIS
    # spelling of the same letters and nation (lineage) is taken where there is one
    def lineage(nation: str) -> str:
        return NATION_LINEAGE.get(nation.upper(), nation.upper())

    fis_names = defaultdict(set)                      # (folded name, lineage) → FIS spellings
    for docs in by_comp.values():
        for meta, doc in docs:
            if meta["doc_type"] == "OLY":
                continue
            rows = [(r, r.get("nation")) for key in ("combined_results", "jump_rounds", "xc_results")
                    for r in doc.get(key) or []]
            rows += [(m, t.get("nation")) for t in doc.get("team_results") or [] for m in t.get("members") or []]
            for r, nation in rows:
                name = clean(r.get("name"))
                if name and nation and name.split()[0].isupper() and _split_initials(name) is None:
                    fis_names[(_fold(name), lineage(nation))].add(name)
    for docs in by_comp.values():
        for meta, doc in docs:
            if meta["doc_type"] != "OLY":
                continue
            rows = [(r, r.get("nation")) for r in doc.get("combined_results") or []]
            rows += [(m, t.get("nation")) for t in doc.get("team_results") or [] for m in t.get("members") or []]
            for r, nation in rows:
                if r.get("name") and nation:
                    known = fis_names.get((_fold(r["name"]), lineage(nation)), set())
                    plain = {n for n in known if n == to_ascii(n)}
                    if len(plain) == 1 and r["name"] not in plain:
                        r["name"] = next(iter(plain))

    olympians = defaultdict(set)                      # (folded surname, lineage) → full names
    for docs in by_comp.values():
        for meta, doc in docs:
            if meta["doc_type"] != "OLY":
                continue
            rows = [(r, r.get("nation")) for r in doc.get("combined_results") or []]
            rows += [(m, t.get("nation")) for t in doc.get("team_results") or [] for m in t.get("members") or []]
            for r, nation in rows:
                split = (r.get("name") or "").split()
                surname = " ".join(w for w in split if w.isupper() and len(w) > 1)
                if surname and nation:
                    nation = nation.upper()
                    olympians[(_fold(surname), NATION_LINEAGE.get(nation, nation))].add(r["name"])

    def given_words(name: str) -> list:
        return [_fold(w) for w in re.split(r"[\s\-]+", " ".join(w for w in name.split()
                                                               if not (w.isupper() and len(w) > 1))) if w]

    for docs in by_comp.values():
        for meta, doc in docs:
            # initials are a thing of the early FIS database ('LI Ji' of today is a full name)
            if meta["doc_type"] != "FDB" or meta["season_start"] >= 1999:
                continue
            rows = [(r, r.get("nation")) for key in ("combined_results", "jump_rounds", "xc_results")
                    for r in doc.get(key) or []]
            rows += [(m, t.get("nation")) for t in doc.get("team_results") or [] for m in t.get("members") or []]
            for r, nation in rows:
                split = _split_initials(r.get("name"))
                if not split or not nation:
                    continue
                surname, tokens = split
                nation = nation.upper()
                hits = {full for full in olympians.get((_fold(surname), NATION_LINEAGE.get(nation, nation)), ())
                        if len(given_words(full)) >= len(tokens)
                        and all(word.startswith(_fold(t)) for word, t in zip(given_words(full), tokens))}
                if len(hits) == 1:
                    r["name"] = next(iter(hits))
                    build.olympedia_names += 1


# Nations that became others: West and East Germany, Czechoslovakia, the Soviet
# Union (CIS / GUS in 1992), Yugoslavia; 'AIN' are Russians and Belarusians today.
NATION_LINEAGE = {code: group for group, codes in {
    "GER": ("FRG", "BRD", "GDR", "DDR", "GER"),
    "TCH": ("TCH", "CZE", "SVK"),
    "SOV": ("SOV", "URS", "CIS", "GUS", "EUN", "RUS", "EST", "LAT", "LTU", "UKR", "BLR", "KAZ", "AIN", "RSF", "RPF", "OAR", "ROC"),
    "YUG": ("YUG", "JUG", "SLO", "CRO", "SRB", "SCG", "BIH", "MKD"),
}.items() for code in codes}


def nation_changes(by_comp: Dict, build: Build) -> None:
    """
    One athlete under the nations of a country that split or united ('ABRATIS Thomas'
    GDR, FRG, GER; 'LEVANDI Allar' SOV, CIS, EST): the same name in one lineage of
    NATION_LINEAGE is one athlete, of the last nation, like a nation change in
    db/aliases/athletes.csv; every result keeps the nation it was printed with.
    A name with native letters ('MüLLER Thomas', from the early FIS database) is the
    athlete of the one plain spelling of the lineage ('MUELLER Thomas').  Lines of
    the alias file come first.
    """
    last = {}                                         # (name, nation) → last date printed
    born = defaultdict(set)                           # (name, nation) → years of birth printed
    for docs in by_comp.values():
        for meta, doc in docs:
            if doc.get("parse_errors"):
                continue
            day = meta.get("file_date") or ""
            rows = [(r, r.get("nation")) for key in ("combined_results", "jump_rounds", "xc_results")
                    for r in doc.get(key) or []]
            rows += [(m, t.get("nation")) for t in doc.get("team_results") or [] for m in t.get("members") or []]
            for r, nation in rows:
                name = clean(r.get("name"))
                if name and nation and nation.upper() != "FIS":
                    key = (name, nation.upper())
                    last[key] = max(last.get(key, ""), day)
                    year = r.get("birth_year") or (re.match(r"(1[89]|20)\d\d", str(r.get("date_of_birth") or ""))
                                                   or [None])[0]
                    if year:
                        born[key].add(int(year))

    def plain(name: str) -> bool:
        return name == to_ascii(name)

    groups = defaultdict(list)                        # (folded name, lineage) → keys
    for key in last:
        groups[(_fold(key[0]), NATION_LINEAGE.get(key[1], key[1]))].append(key)
    added = 0
    for keys in groups.values():
        if len(keys) < 2:
            continue
        years = set().union(*(born[k] for k in keys))
        if max(years, default=0) - min(years, default=0) > 1:
            continue                                  # father and son: 'RYGL Ladislav' 1947 and 1976
        # the last nation; 'AIN' only if there is no other (the FIS database of today)
        nation = max(keys, key=lambda k: (k[1] not in ("AIN", "RSF", "RPF", "OAR", "ROC"), last[k]))[1]
        spellings = {k[0] for k in keys}
        # one plain spelling, 'Rygl Ladislav' (a mixed-case list) being 'RYGL Ladislav'
        plain_ones = sorted({n for n in spellings if plain(n)}, key=lambda n: not n.split()[0].isupper())
        if len(spellings) > 1 and len({n.upper() for n in plain_ones}) != 1:
            continue                                  # two plain spellings: may be two people
        target_name = plain_ones[0] if plain_ones else next(iter(spellings))
        target = build.athlete_aliases.get((target_name, nation), (target_name, nation))
        for key in keys:
            if key != (target_name, nation) and key not in build.athlete_aliases:
                build.athlete_aliases[key] = target
                added += 1
    if added:
        log.info("Nations that split or united: %d names given the athlete's last nation", added)


def external_nations(by_comp: Dict, build: Build) -> None:
    """
    The organisers' lists of weltcup-b.org (WBL) print a wrong nation now and then
    ('CECON, Andrea JPN'): a row takes the nation the athlete has in every FIS list,
    if that is one and another.
    """
    nations = defaultdict(set)
    for docs in by_comp.values():
        for meta, doc in docs:
            if meta["doc_type"] in FULL_LISTS or doc.get("parse_errors"):
                continue
            for key in ("combined_results", "jump_rounds", "xc_results"):
                for r in doc.get(key) or []:
                    if r.get("name") and r.get("nation"):
                        nations[clean(r["name"])].add(r["nation"].upper())
    fixed = 0
    for docs in by_comp.values():
        for meta, doc in docs:
            if meta["doc_type"] != "WBL":
                continue
            for r in doc.get("combined_results") or []:
                known = nations.get(clean(r.get("name")), set())
                if len(known) == 1 and r.get("nation") not in known:
                    r["nation"] = next(iter(known))
                    fixed += 1
    if fixed:
        log.info("weltcup-b.org: %d rows take the nation of the FIS lists", fixed)


def build_database(output_dir: str, build: Build, standings_dir: Optional[str] = None) -> None:
    by_comp = read_documents(output_dir, build)
    log.info("Read %d documents for %d competitions", sum(map(len, by_comp.values())), len(by_comp))
    fis_spelling(by_comp, build)
    external_nations(by_comp, build)
    olympedia_names(by_comp, build)
    nation_changes(by_comp, build)

    for docs in by_comp.values():
        for name, nations in names_with_nation(docs).items():
            build.nations_by_name[name] |= nations
        for meta, doc in docs:
            if not doc.get("parse_errors") and meta["doc_type"] in ("ROF", "FDB", *FULL_LISTS, "RL", "RL1", "RLQ", "PCR"):
                rows = [dict(m, nation=m.get("nation") or t.get("nation"))
                        for t in doc.get("team_results") or [] for m in t.get("members") or []] \
                    + (doc.get("combined_results") or []) + (doc.get("jump_rounds") or [])
                for r in rows:
                    if r.get("name") and r.get("nation") and not row_identity_problem(r):
                        key = (clean(r["name"]), r["nation"].upper())
                        build.official_athletes.add(build.athlete_aliases.get(key, key))
            if meta["doc_type"] in ("ROF", "FDB", *FULL_LISTS) and not doc.get("parse_errors") \
                    and not meta["team"] and not is_team_discipline(doc.get("discipline")):
                build.result_nations.update(
                    r["nation"].upper() for r in doc.get("combined_results") or []
                    if not row_identity_problem(r))

    # A name may also be looked up in its canonical spelling
    for name, nations in list(build.nations_by_name.items()):
        for nation in list(nations):
            cname, cnation = build.athlete_aliases.get((name, nation), (name, nation))
            build.nations_by_name[cname].add(cnation)

    for name, nations in build.nations_by_name.items():
        for nation in nations:
            build.names_by_words[(nation, frozenset(name_words(name)))].add(name)

    for (_, codex, season_start), docs in sorted(by_comp.items(), key=lambda kv: (kv[0][2], kv[0][1], kv[0][0])):
        comp = describe_competition(docs)
        comp["nations"] = names_with_nation(docs)
        circuits = {m["circuit"] for m, _ in docs}
        if len(circuits) > 1:
            log.warning("Codex %s in %s appears in several circuits %s", codex, comp["season_label"], circuits)
        season_id = build.season(comp["season_start"], comp["season_label"])
        venue_id = build.venue(comp["location"], comp["country"], docs[0][0]["basename"])
        comp_id = build.add(
            "competitions", season_id, venue_id, codex, comp["circuit"], comp["gender"], comp["date"],
            comp["location"], comp["country"], (comp["format"] or "")[:30] or None,
            comp["hill_size_m"], comp["xc_distance_km"], (comp["event_name"] or "")[:300] or None)
        build.hill_class[comp_id] = comp["hill_class"]

        # The same result list is sometimes stored twice under two dates
        # (the 2017 ROFs were re-downloaded separately).  One per competition.
        rofs = [m for m, d in docs if m["doc_type"] == "ROF"]
        official = next((m for m in rofs if m["file_date"] == comp["date"]), rofs[0] if rofs else None)

        for meta, doc in sorted(docs, key=lambda md: md[0]["basename"]):
            if meta["doc_type"] == "ROF" and meta is not official:
                build.skipped_docs.append(("second ROF for the same competition", meta["basename"]))
                continue
            if meta["doc_type"] == "FDB":
                # the ranking of the FIS database (World Cup B): only where the result
                # list could not be read, which has the jump and cross-country too
                read = next((d for m, d in docs if m["doc_type"] == "ROF" and not d.get("parse_errors")), None)
                if read is not None:
                    pdf_top = [clean(r.get("name")) for r in sorted(
                        (r for r in read.get("combined_results") or [] if r.get("rank")), key=lambda r: r["rank"])[:3]]
                    fdb_top = [clean(r.get("name")) for r in (doc.get("combined_results") or [])[:3]]
                    if pdf_top and pdf_top != fdb_top:
                        build.fdb_disagree.append((meta["basename"], pdf_top, fdb_top))
                    build.skipped_docs.append(("FIS ranking: the result list was read", meta["basename"]))
                    continue
                if any(m["doc_type"] in FULL_LISTS and not d.get("parse_errors") for m, d in docs):
                    build.skipped_docs.append(("FIS ranking: a full list of another source", meta["basename"]))
                    continue
                build.fdb_used += 1
            if meta["doc_type"] in FULL_LISTS:
                # Olympedia (Olympic Games 1924-1998), weltcup-b.org (World Cup B of the 1990s):
                # the full result, where no result list of FIS was read
                if any(m["doc_type"] == "ROF" and not d.get("parse_errors") for m, d in docs):
                    build.skipped_docs.append((f"{meta['doc_type']}: the result list was read", meta["basename"]))
                    continue
                if meta["doc_type"] == "OLY":
                    build.oly_used += 1
                else:
                    build.wbl_used += 1
            if meta["doc_type"] == "RL1" and any(m["doc_type"] == "RL" for m, _ in docs):
                build.skipped_docs.append(("first round only, the RL holds both", meta["basename"]))
                continue
            notes =[f"ERROR: {e}" for e in doc.get("parse_errors") or []] + list(doc.get("warnings") or [])
            source = (doc.get("source_file") or meta["basename"]).replace("\\", "/")
            doc_id = build.add(
                "competition_documents", comp_id, meta["doc_type"], doc.get("format_era"), source,
                doc.get("fis_report_code"), doc.get("report_created"), doc.get("start_time"),
                doc.get("end_time"), json.dumps(notes, ensure_ascii=False) if notes else None)
            add_details(build, comp_id, doc_id, doc)
            add_results(build, comp, comp_id, doc_id, meta, doc)

    fill_hill_sizes(build)
    add_standings(build, standings_dir)

    # Dimension tables are complete only now
    for (name, country), venue_id in build.venues.items():
        build.rows["venues"].append((venue_id, name, country, build.venue_display.get((name, country))))
    for (raw_name, raw_country), (venue_id, source) in build.venue_variants.items():
        build.add("venue_name_variants", venue_id, raw_name, raw_country, source)
    for a in build.athletes.values():
        last, first = split_name(a["name"])
        gender = a["genders"].most_common(1)[0][0] if a["genders"] else None
        dob = a["dobs"].most_common(1)[0][0] if a["dobs"] else None
        build.rows["athletes"].append((a["id"], last, first, a["name"], a["nation"], gender, dob, a["club"],
                                       a.get("fis_id"), build.athlete_display.get((a["name"], a["nation"]))))
    for (raw_name, raw_nation), (athlete_id, source) in build.athlete_variants.items():
        build.add("athlete_name_variants", athlete_id, raw_name, raw_nation, source)


# ─────────────────────────────────────────────────────────────────────────────
# Writing
# ─────────────────────────────────────────────────────────────────────────────

_JUMP_COLUMNS = (
    "id, competition_id, document_id, athlete_id, raw_name, raw_nation, rank, bib, club, date_of_birth, "
    "round_number, speed_kmh, distance_m, dist_points, judge_a, judge_b, judge_c, judge_d, judge_e, "
    "style_points, gate, gate_comp_pts, wind_ms, wind_comp_pts, total_points, dns, dsq, dsq_reason, fall")

COLUMNS = {
    "seasons": "id, start_year, label",
    "venues": "id, name, country, display_name",
    "venue_name_variants": "id, venue_id, name_variant, country, first_seen_file",
    "athletes": "id, last_name, first_name, full_name, nationality, gender, birth_date, active_club, fis_id, display_name",
    "athlete_name_variants": "id, athlete_id, name_variant, nationality, first_seen_file",
    "competitions": "id, season_id, venue_id, fis_codex, circuit, gender, competition_date, raw_location, "
                    "raw_country, format, hill_size_m, xc_distance_km, event_name",
    "competition_documents": "id, competition_id, doc_type, format_era, source_file, fis_report_code, "
                             "report_created, start_time, end_time, parse_warnings",
    "hill_data": "id, competition_id, document_id, hill_size_m, k_point_m, meter_value, gate_factor, "
                 "wind_factor_head, wind_factor_tail",
    "course_info": "id, competition_id, document_id, height_m, max_climb_m, total_climb_m, length_km, "
                   "number_of_laps",
    "weather_records": "id, competition_id, document_id, weather_description, snow_conditions, temp_air_c, "
                       "temp_snow_c, temp_air_start_c, temp_air_finish_c, temp_snow_start_c, "
                       "temp_snow_finish_c, humidity_start_pct, humidity_finish_pct, wind_min_ms, "
                       "wind_max_ms, wind_avg_ms",
    "jury_officials": "id, document_id, role, last_name, first_name, nation",
    "jumping_judges": "id, document_id, position, last_name, first_name, nation",
    "combined_results": "id, competition_id, document_id, athlete_id, raw_name, raw_nation, rank, bib, club, "
                        "date_of_birth, jump_points, jump_rank, time_difference, xc_time, xc_rank, "
                        "time_behind, wave_start, status",
    "jump_round_results": _JUMP_COLUMNS + ", pursuit_time_diff",
    "training_jump_results": _JUMP_COLUMNS,
    "trial_round_results": _JUMP_COLUMNS,
    "xc_results": "id, competition_id, document_id, athlete_id, raw_name, raw_nation, rank, bib, club, "
                  "date_of_birth, total_time, time_behind, points, status",
    "team_results": "id, competition_id, document_id, rank, bib, nation, team_name, jump_rank, "
                    "time_difference, xc_rank, total_time, time_behind, jump_points, status",
    "team_members": "id, team_result_id, athlete_id, raw_name, raw_nation, leg, xc_time, jump_points",
    "cup_standings": "id, season_id, circuit, gender, discipline_code, discipline_name, rank, points, "
                     "athlete_id, raw_name, raw_nation, fis_competitor_id",
}
# Insert order respects foreign keys
TABLE_ORDER = list(COLUMNS)
BOOLEAN_COLUMNS = ("dns", "dsq", "fall")


def write_sqlite(build: Build, db_path: str) -> None:
    """Build into a new file and swap it in, so a failed run leaves the old database intact."""
    tmp = db_path + ".building"
    for leftover in (tmp, tmp + "-wal", tmp + "-shm"):
        if os.path.exists(leftover):
            os.remove(leftover)
    conn = sqlite3.connect(tmp)
    with open(os.path.join(DB_DIR, "schema_sqlite.sql"), encoding="utf-8") as fh:
        conn.executescript(fh.read())
    conn.execute("PRAGMA journal_mode = DELETE")            # single file, nothing left to clean up
    conn.execute("PRAGMA foreign_keys = ON")
    with conn:
        for table in TABLE_ORDER:
            cols = COLUMNS[table]
            marks = ", ".join("?" * (cols.count(",") + 1))
            conn.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", build.rows[table])
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()
    if violations:
        raise RuntimeError(f"{len(violations)} foreign key violations, e.g. {violations[:3]}")
    for stale in (db_path + "-wal", db_path + "-shm"):
        if os.path.exists(stale):
            os.remove(stale)
    try:
        os.replace(tmp, db_path)
    except PermissionError:
        raise SystemExit(f"Cannot replace {db_path} — is the web app still running? "
                         f"The new database is at {tmp}")


def write_postgres(build: Build, dsn: str) -> None:
    import psycopg2
    from psycopg2.extras import execute_values

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO PUBLIC;")
    with open(os.path.join(DB_DIR, "schema.sql"), encoding="utf-8") as fh:
        cur.execute(fh.read())
    for table in TABLE_ORDER:
        cols = [c.strip() for c in COLUMNS[table].split(",")]
        bool_at = [i for i, c in enumerate(cols) if c in BOOLEAN_COLUMNS]
        rows = build.rows[table]
        if bool_at:
            rows = [tuple(bool(v) if i in bool_at else v for i, v in enumerate(r)) for r in rows]
        if rows:
            execute_values(cur, f"INSERT INTO {table} ({COLUMNS[table]}) VALUES %s", rows, page_size=1000)
            cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}))")
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

def possible_duplicates(build: Build) -> List[Tuple[str, str, str]]:
    """
    Athletes who may be one person: the same name words (in any order, 'oe' = 'o')
    in the same nation, the words of one name inside the other's, or the same name
    in two nations (a nation change).  Settle them in db/aliases/athletes.csv.
    """
    def words(name: str) -> frozenset:
        s = " ".join(name_words(name))
        for a, b in (("ae", "a"), ("oe", "o"), ("ue", "u"), ("aa", "a")):
            s = s.replace(a, b)
        return frozenset(w for w in s.split() if len(w) > 1)

    def split(name: str):
        return (_fold(" ".join(x for x in name.split() if x.isupper() and len(x) > 1)),
                _fold(" ".join(x for x in name.split() if not (x.isupper() and len(x) > 1))))

    def born(a) -> Optional[int]:
        dob = a["dobs"].most_common(1)[0][0] if a.get("dobs") else None
        return int(dob[:4]) if dob and dob[:4].isdigit() else None

    athletes = [(a["name"], a["nation"], words(a["name"]), split(a["name"]), born(a))
                for a in build.athletes.values()]
    found = []
    for i, (name, nation, w, (sur, given), year) in enumerate(athletes):
        for other, other_nation, ow, (osur, ogiven), oyear in athletes[i + 1:]:
            if nation == other_nation and (w == ow or (len(w) >= 2 and len(ow) >= 2 and (w < ow or ow < w))):
                found.append((name, other, nation))
            elif nation != other_nation and w == ow and len(w) >= 2:
                found.append((name, other, f"{nation} / {other_nation}"))
            # the same surname and nation, the given name spelled another way
            # ('SPILLANE John' / 'Johnny', 'DUNDUKOV Andrej' / 'Andrey') — unless born years apart
            elif sur and sur == osur and given and ogiven \
                    and NATION_LINEAGE.get(nation, nation) == NATION_LINEAGE.get(other_nation, other_nation) \
                    and difflib.SequenceMatcher(None, given, ogiven).ratio() >= 0.75 \
                    and not (year and oyear and abs(year - oyear) > 1):
                found.append((name, other, nation if nation == other_nation else f"{nation} / {other_nation}"))
    return found


def report(build: Build, verbose: bool) -> None:
    log.info("Rows written:")
    for table in TABLE_ORDER:
        log.info("  %-24s %7d", table, len(build.rows[table]))

    if build.fdb_used:
        log.info("Competitions ranked from the FIS database (result list not readable): %d", build.fdb_used)
    if build.oly_used:
        log.info("Olympic competitions from Olympedia (no result list read): %d", build.oly_used)
    if build.wbl_used:
        log.info("World Cup B competitions of the 1990s from weltcup-b.org: %d", build.wbl_used)
    if build.olympedia_names:
        log.info("Names with initials completed from Olympedia: %d", build.olympedia_names)
    for name, pdf_top, fdb_top in build.fdb_disagree:
        log.warning("  top 3 of %s differ from the FIS database: %s / %s", name, pdf_top, fdb_top)

    duplicates = possible_duplicates(build)
    if duplicates:
        log.warning("Athletes that may be the same person (settle in db/aliases/athletes.csv):")
        for name, other, nation in duplicates:
            log.warning("  %-35s %-35s %s", name, other, nation)

    reasons = Counter(re.sub(r"\d+", "N", re.sub(r"'[^']*'", "…", reason))[:80] for reason, _ in build.skipped_docs)
    if reasons:
        log.info("Documents whose result rows were not loaded:")
        for reason, n in reasons.most_common():
            log.info("  %5d  %s", n, reason)
        if verbose:
            for reason, path in build.skipped_docs:
                log.info("         %s  ←  %s", os.path.basename(path), reason)

    if build.recovered_nations:
        log.info("Rows without nation, completed from the athlete's other results: %s",
                 ", ".join(f"{t} {n}" for t, n in sorted(build.recovered_nations.items())))

    if build.recovered_names:
        log.info("Rows with mixed-case name, matched to a known athlete: %s",
                 ", ".join(f"{t} {n}" for t, n in sorted(build.recovered_names.items())))

    if build.reordered_names:
        log.info("Rows printed 'Firstname Surname': %s",
                 ", ".join(f"{n} {kind}" for kind, n in sorted(build.reordered_names.items())))
        for name in sorted(build.guessed_names)[: None if verbose else 8]:
            log.info("         surname guessed: %s", name)

    if build.standings_rows:
        log.info("Cup standings: %d rows linked to an athlete, %d not (%d athletes without a result here)",
                 build.standings_rows[True], build.standings_rows[False], len(build.standings_unmatched))
        for name in sorted(build.standings_unmatched)[: None if verbose else 8]:
            log.info("         not found: %s", name)

    if build.rejected_rows:
        log.info("Rows rejected (not an athlete):")
        for (doc_type, reason), n in sorted(build.rejected_rows.items(), key=lambda kv: -kv[1]):
            log.info("  %5d  %-5s %s", n, doc_type, reason)
            for example in build.rejected_examples[(doc_type, reason)][: 5 if verbose else 2]:
                log.info("         e.g. %s", example)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the Nordic Combined database from parsed JSON")
    ap.add_argument("--db", help="PostgreSQL DSN, e.g. postgresql://user:pass@localhost/noco")
    ap.add_argument("--sqlite", metavar="PATH", help="SQLite database file, e.g. db/noco.db")
    ap.add_argument("--output-dir", default="output", help="Directory with JSON files (default: output)")
    ap.add_argument("--aliases-dir", default=os.path.join(DB_DIR, "aliases"),
                    help="Directory with athletes.csv and venues.csv (default: db/aliases)")
    ap.add_argument("--standings-dir", default="fis_nk_standings",
                    help="Directory with cup standings JSON (default: fis_nk_standings)")
    ap.add_argument("--reset", action="store_true", help=argparse.SUPPRESS)   # always a full rebuild now
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    if not args.db and not args.sqlite:
        ap.error("Provide either --db (PostgreSQL) or --sqlite (SQLite)")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
    if not os.path.isdir(args.output_dir):
        log.error("Output directory not found: %s", args.output_dir)
        return 1

    build = Build(load_aliases(os.path.join(args.aliases_dir, "athletes.csv")),
                  load_aliases(os.path.join(args.aliases_dir, "venues.csv")))
    build.athlete_display = load_display_names(os.path.join(args.aliases_dir, "athlete_display_names.csv"))
    build.venue_display = load_display_names(os.path.join(args.aliases_dir, "venue_display_names.csv"))
    log.info("Aliases: %d athletes, %d venues; display names: %d athletes, %d venues",
             len(build.athlete_aliases), len(build.venue_aliases),
             len(build.athlete_display), len(build.venue_display))
    build_database(args.output_dir, build, args.standings_dir)
    if args.sqlite:
        write_sqlite(build, args.sqlite)
    else:
        write_postgres(build, args.db)
    report(build, args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
