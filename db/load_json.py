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
A ROF the parser flagged as broken (parse_errors) is recorded as a document,
but its rows are not loaded.
"""

import argparse
import csv
import glob
import json
import logging
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fis_parser.detector import (                      # noqa: E402
    parse_filename_metadata, team_discipline_from_filename, venue_from_path,
)
from fis_parser.validate import is_team_discipline, row_identity_problem   # noqa: E402

log = logging.getLogger("loader")

DB_DIR = os.path.dirname(os.path.abspath(__file__))

CIRCUIT_BY_DIR = {"fis_nk_pdfs": "WC", "fis_nk_coc_pdfs": "COC"}
JUMP_TABLE_BY_DOC_TYPE = {
    "RL": "jump_round_results",
    "RL1": "jump_round_results",
    "PCR": "jump_round_results",
    "RLT": "training_jump_results",
    "RLTR": "trial_round_results",
}
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
    mixed = re.search(r"_(?:WC|COC)_A_X_|_X_(?:\d{4}NK)?\d{4}[A-Z0-9]+\.json$|Mixed", name)
    if mixed:
        gender = "X"

    hs = re.search(r"_HS(\d{2,3})(?:_|\b)", name)
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
        "xc_distance_km": float(relay.group(1)) if relay else float(km.group(1)) if km else None,
        "team": team_discipline_from_filename(name),
        "provisional": bool(re.search(r"_PR_[MWA]_[MWX]_|PCR\.json$", name)),
        "discipline_hint": fn.get("discipline_hint"),
        "basename": name,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Alias lists
# ─────────────────────────────────────────────────────────────────────────────

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
        self.recovered_nations: Counter = Counter()               # doc_type → rows
        self.recovered_names: Counter = Counter()                 # doc_type → rows

        self.skipped_docs: List[Tuple[str, str]] = []        # (reason, file)
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

def read_documents(output_dir: str, build: Build) -> Dict[Tuple[str, int], List[Tuple[dict, dict]]]:
    """All JSON files grouped by competition (codex, season); one entry per PDF."""
    by_comp: Dict[Tuple[str, int], List[Tuple[dict, dict]]] = defaultdict(list)
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
        if not meta["doc_type"]:
            build.skipped_docs.append(("no doc_type", path))
            continue
        by_comp[(meta["codex"], meta["season_start"])].append((meta, doc))
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
    if rof is not None and is_team_discipline(rof.get("discipline")):
        team = rof["discipline"]
    fmt = team or (rof or {}).get("discipline") or first(lambda m, d: m["discipline_hint"]) \
        or first(lambda m, d: d.get("discipline"))
    if rof is None and any(m["provisional"] for m in metas):
        # The provisional competition round has a codex of its own; it is a
        # jumping round, not a competition with a result list.
        fmt = "Provisional Round"

    location = clean((rof or {}).get("location")) or first(lambda m, d: clean(d.get("location")))
    country = clean((rof or {}).get("country")) or first(lambda m, d: clean(d.get("country")))
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

    def athlete_rows(key):
        for r in doc.get(key) or []:
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

    if doc_type == "ROF":
        if doc.get("parse_errors"):
            build.skipped_docs.append((f"ROF failed validation: {doc['parse_errors'][0]}", source))
            return
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
            nation = team_nation if team_nation in build.result_nations \
                else build.nation_for(name, comp["nations"])
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


def build_database(output_dir: str, build: Build) -> None:
    by_comp = read_documents(output_dir, build)
    log.info("Read %d documents for %d competitions", sum(map(len, by_comp.values())), len(by_comp))

    for docs in by_comp.values():
        for name, nations in names_with_nation(docs).items():
            build.nations_by_name[name] |= nations
        for meta, doc in docs:
            if meta["doc_type"] == "ROF" and not doc.get("parse_errors") \
                    and not meta["team"] and not is_team_discipline(doc.get("discipline")):
                build.result_nations.update(
                    r["nation"].upper() for r in doc.get("combined_results") or []
                    if not row_identity_problem(r))

    # A name may also be looked up in its canonical spelling
    for name, nations in list(build.nations_by_name.items()):
        for nation in nations:
            cname, cnation = build.athlete_aliases.get((name, nation), (name, nation))
            build.nations_by_name[cname].add(cnation)

    for (codex, season_start), docs in sorted(by_comp.items(), key=lambda kv: (kv[0][1], kv[0][0])):
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

        # The same result list is sometimes stored twice under two dates
        # (the 2017 ROFs were re-downloaded separately).  One per competition.
        rofs = [m for m, d in docs if m["doc_type"] == "ROF"]
        official = next((m for m in rofs if m["file_date"] == comp["date"]), rofs[0] if rofs else None)

        for meta, doc in sorted(docs, key=lambda md: md[0]["basename"]):
            if meta["doc_type"] == "ROF" and meta is not official:
                build.skipped_docs.append(("second ROF for the same competition", meta["basename"]))
                continue
            notes =[f"ERROR: {e}" for e in doc.get("parse_errors") or []] + list(doc.get("warnings") or [])
            source = (doc.get("source_file") or meta["basename"]).replace("\\", "/")
            doc_id = build.add(
                "competition_documents", comp_id, meta["doc_type"], doc.get("format_era"), source,
                doc.get("fis_report_code"), doc.get("report_created"), doc.get("start_time"),
                doc.get("end_time"), json.dumps(notes, ensure_ascii=False) if notes else None)
            add_details(build, comp_id, doc_id, doc)
            add_results(build, comp, comp_id, doc_id, meta, doc)

    # Dimension tables are complete only now
    for (name, country), venue_id in build.venues.items():
        build.rows["venues"].append((venue_id, name, country))
    for (raw_name, raw_country), (venue_id, source) in build.venue_variants.items():
        build.add("venue_name_variants", venue_id, raw_name, raw_country, source)
    for a in build.athletes.values():
        last, first = split_name(a["name"])
        gender = a["genders"].most_common(1)[0][0] if a["genders"] else None
        dob = a["dobs"].most_common(1)[0][0] if a["dobs"] else None
        build.rows["athletes"].append((a["id"], last, first, a["name"], a["nation"], gender, dob, a["club"]))
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
    "venues": "id, name, country",
    "venue_name_variants": "id, venue_id, name_variant, country, first_seen_file",
    "athletes": "id, last_name, first_name, full_name, nationality, gender, birth_date, active_club",
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

def report(build: Build, verbose: bool) -> None:
    log.info("Rows written:")
    for table in TABLE_ORDER:
        log.info("  %-24s %7d", table, len(build.rows[table]))

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
    log.info("Aliases: %d athletes, %d venues", len(build.athlete_aliases), len(build.venue_aliases))
    build_database(args.output_dir, build)
    if args.sqlite:
        write_sqlite(build, args.sqlite)
    else:
        write_postgres(build, args.db)
    report(build, args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
