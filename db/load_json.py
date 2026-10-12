#!/usr/bin/env python3
"""
db/load_json.py — Load parsed JSON output files into PostgreSQL.

Usage:
    python db/load_json.py --db "postgresql://user:pass@localhost/noco" [options]

Options:
    --output-dir DIR    Directory with JSON files (default: output)
    --reset             Drop & recreate schema before loading
    --batch-size N      Commit every N files (default: 200)
    --verbose           Debug logging
"""

import argparse
import glob
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger("loader")


# ─────────────────────────────────────────────────────────────────────────────
# Thin DB adapter — normalises %s→? and RETURNING id→lastrowid for SQLite
# ─────────────────────────────────────────────────────────────────────────────

class _Cursor:
    """Wraps a raw DB cursor; transparently handles SQLite vs PostgreSQL."""

    def __init__(self, raw, is_sqlite: bool):
        self._raw = raw
        self.is_sqlite = is_sqlite

    def _adapt(self, sql: str):
        if self.is_sqlite:
            sql = sql.replace("%s", "?")
            sql = re.sub(r"\s+RETURNING\s+id\s*$", "", sql.strip(), flags=re.IGNORECASE)
            # PostgreSQL NULL-safe equality → SQLite equivalent
            sql = re.sub(r"IS\s+NOT\s+DISTINCT\s+FROM", "IS", sql, flags=re.IGNORECASE)
            sql = re.sub(r"IS\s+DISTINCT\s+FROM", "IS NOT", sql, flags=re.IGNORECASE)
            # PostgreSQL timestamp function → SQLite equivalent
            sql = re.sub(r"\bNOW\(\)", "datetime('now')", sql, flags=re.IGNORECASE)
        return sql

    def execute(self, sql: str, params=()):
        self._raw.execute(self._adapt(sql), params)
        return self

    def fetchone(self):
        return self._raw.fetchone()

    def insert_id(self) -> int:
        """Return the id of the last INSERT — works for both backends."""
        if self.is_sqlite:
            return self._raw.lastrowid
        row = self._raw.fetchone()
        return row[0]


def connect(dsn: str = None, sqlite_path: str = None):
    """Return (conn, cursor_factory, is_sqlite)."""
    if sqlite_path:
        conn = sqlite3.connect(sqlite_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn, True
    else:
        import psycopg2
        conn = psycopg2.connect(dsn)
        return conn, False


def make_cursor(conn, is_sqlite: bool) -> _Cursor:
    return _Cursor(conn.cursor(), is_sqlite)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            pass
    return None


def parse_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def parse_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def status_from_row(r: dict) -> Optional[str]:
    # JSON from ROF parser uses a string 'status' field
    s = (r.get("status") or "").strip().upper()
    if s in ("DNS", "DNF", "DSQ", "DNQ"):
        return s
    # Fallback: boolean flags (used by jump result rows)
    if r.get("dns"):
        return "DNS"
    if r.get("dnf"):
        return "DNF"
    if r.get("dsq"):
        return "DSQ"
    if r.get("dnq"):
        return "DNQ"
    return None


def filename_meta(path: str) -> Dict[str, Any]:
    """Extract codex, gender, circuit, season, doc_type from path."""
    norm = path.replace("\\", "/")
    fname = os.path.basename(norm).replace(".json", "")

    circuit = "WC" if "fis_nk_pdfs/" in norm and "fis_nk_coc_pdfs/" not in norm else "COC"

    m = re.match(r"(\d+)_", fname)
    codex = m.group(1) if m else None

    m = re.search(r"_(M|W)_(M|W)_", fname)
    gender = m.group(1) if m else None

    m = re.search(r"_(\d{4})NK", fname)
    if m:
        end_year = int(m.group(1))
        season_label = f"{end_year - 1}/{end_year}"
        season_start = end_year - 1
    else:
        season_label = None
        season_start = None

    # Match longest doc type first to avoid RL matching RLT/RLLL/RLTR
    m = re.search(r"(RLLL|RLTR|RLT|RL1|ROF|PCR|RL)\.json$", os.path.basename(norm))
    doc_type = m.group(1) if m else None

    return {
        "circuit": circuit,
        "codex": codex,
        "gender": gender,
        "season_label": season_label,
        "season_start": season_start,
        "doc_type": doc_type,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DB get-or-create helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_season(cur: _Cursor, start_year: int, label: str) -> int:
    cur.execute("SELECT id FROM seasons WHERE start_year = %s", (start_year,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO seasons (start_year, label) VALUES (%s, %s) RETURNING id",
        (start_year, label),
    )
    return cur.insert_id()


def get_or_create_venue(cur: _Cursor, location: Optional[str], country: Optional[str], source_file: str) -> Optional[int]:
    loc = (location or "").strip()
    cty = (country or "").strip().upper() or None
    if not loc:
        return None

    # Already seen this raw variant?
    cur.execute(
        "SELECT venue_id FROM venue_name_variants "
        "WHERE name_variant = %s AND country IS NOT DISTINCT FROM %s",
        (loc, cty),
    )
    row = cur.fetchone()
    if row:
        return row[0]

    # Exact canonical match?
    safe_cty = cty or "???"
    cur.execute("SELECT id FROM venues WHERE name = %s AND country = %s", (loc, safe_cty))
    row = cur.fetchone()
    if row:
        venue_id = row[0]
    else:
        cur.execute(
            "INSERT INTO venues (name, country) VALUES (%s, %s) RETURNING id",
            (loc, safe_cty),
        )
        venue_id = cur.insert_id()

    cur.execute(
        "INSERT INTO venue_name_variants (venue_id, name_variant, country, first_seen_file) "
        "VALUES (%s, %s, %s, %s)",
        (venue_id, loc, cty, os.path.basename(source_file)),
    )
    return venue_id


def get_or_create_competition(cur: _Cursor, meta: dict, doc: dict) -> int:
    codex = meta["codex"]
    season_id = get_or_create_season(cur, meta["season_start"], meta["season_label"])

    # Codex is reused across seasons — must include season in lookup key
    cur.execute(
        "SELECT id FROM competitions WHERE fis_codex = %s AND season_id = %s",
        (codex, season_id),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    location = (doc.get("location") or "").strip() or None
    country = (doc.get("country") or "").strip().upper() or None
    venue_id = get_or_create_venue(cur, location, country, doc.get("source_file", ""))

    hill_data = doc.get("hill_data") or {}

    # Try to extract xc_distance from filename: e.g. "10.0_Km" → 10.0
    xc_km = None
    m = re.search(r"_([\d.]+)_Km_", os.path.basename(doc.get("source_file", "") or ""))
    if m:
        xc_km = parse_float(m.group(1))

    cur.execute(
        """
        INSERT INTO competitions
            (season_id, venue_id, fis_codex, circuit, gender, competition_date,
             raw_location, raw_country, format, hill_size_m, xc_distance_km, event_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            season_id,
            venue_id,
            codex,
            meta["circuit"],
            meta["gender"],
            parse_date(doc.get("competition_date")),
            location,
            country,
            (doc.get("discipline") or "")[:30] or None,
            parse_float(hill_data.get("hill_size_m")),
            xc_km,
            (doc.get("event_name") or "")[:300] or None,
        ),
    )
    return cur.insert_id()


def insert_document(cur: _Cursor, competition_id: int, meta: dict, doc: dict) -> int:
    doc_type = meta["doc_type"] or doc.get("doc_type")
    source_file = doc.get("source_file")
    # Normalise path separators so Windows backslash paths match Unix forward-slash
    # paths (happens when re-parsing on a different OS than the initial load).
    source_file_norm = source_file.replace("\\", "/") if source_file else source_file
    warnings = doc.get("warnings") or []

    # Check if this (competition, doc_type, source_file) was already loaded.
    # If so, delete its results and reuse the existing document id to prevent
    # duplicate rows accumulating across multiple load_json runs.
    # Check both normalised and original path to handle mixed-separator history.
    cur.execute(
        "SELECT id FROM competition_documents "
        "WHERE competition_id = %s AND doc_type = %s "
        "AND (source_file = %s OR source_file = %s OR source_file = %s)",
        (competition_id, doc_type, source_file, source_file_norm,
         source_file.replace("/", "\\") if source_file else source_file),
    )
    existing = cur.fetchone()
    if existing:
        existing_id = existing[0]
        cur.execute("DELETE FROM combined_results WHERE document_id = %s", (existing_id,))
        cur.execute("DELETE FROM jump_round_results WHERE document_id = %s", (existing_id,))
        cur.execute("DELETE FROM training_jump_results WHERE document_id = %s", (existing_id,))
        cur.execute("DELETE FROM trial_round_results WHERE document_id = %s", (existing_id,))
        cur.execute("DELETE FROM xc_results WHERE document_id = %s", (existing_id,))
        cur.execute(
            "UPDATE competition_documents SET format_era=%s, fis_report_code=%s, "
            "report_created=%s, start_time=%s, end_time=%s, parse_warnings=%s, "
            "source_file=%s, parsed_at=NOW() WHERE id=%s",
            (
                doc.get("format_era"), doc.get("fis_report_code"),
                doc.get("report_created"), doc.get("start_time"), doc.get("end_time"),
                json.dumps(warnings) if warnings else None,
                source_file_norm,
                existing_id,
            ),
        )
        return existing_id

    cur.execute(
        """
        INSERT INTO competition_documents
            (competition_id, doc_type, format_era, source_file, fis_report_code,
             report_created, start_time, end_time, parse_warnings)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            competition_id,
            doc_type,
            doc.get("format_era"),
            source_file_norm,
            doc.get("fis_report_code"),
            doc.get("report_created"),
            doc.get("start_time"),
            doc.get("end_time"),
            json.dumps(warnings) if warnings else None,
        ),
    )
    return cur.insert_id()


def get_or_create_athlete(
    cur: _Cursor, name: str, nation: Optional[str], dob: Optional[str],
    club: Optional[str], gender: Optional[str], source_file: str
) -> int:
    name = name.strip()
    nat = (nation or "").strip().upper() or None

    # Check name variants table first (fastest path — already seen)
    cur.execute(
        "SELECT athlete_id FROM athlete_name_variants "
        "WHERE name_variant = %s AND nationality IS NOT DISTINCT FROM %s",
        (name, nat),
    )
    row = cur.fetchone()
    if row:
        athlete_id = row[0]
        # Update dob/club if we now have values that were missing
        bd = parse_date(dob)
        if bd or club:
            cur.execute(
                "UPDATE athletes SET "
                "  birth_date  = COALESCE(birth_date, %s), "
                "  active_club = COALESCE(%s, active_club), "
                "  updated_at  = NOW() "
                "WHERE id = %s",
                (bd, club, athlete_id),
            )
        return athlete_id

    # Try canonical name match
    safe_nat = nat or "???"
    cur.execute(
        "SELECT id FROM athletes WHERE full_name = %s AND nationality = %s",
        (name, safe_nat),
    )
    row = cur.fetchone()
    if row:
        athlete_id = row[0]
    else:
        parts = name.split(" ", 1)
        last = parts[0]
        first = parts[1] if len(parts) > 1 else None

        cur.execute(
            """
            INSERT INTO athletes
                (last_name, first_name, full_name, nationality, gender, birth_date, active_club)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (full_name, nationality) DO UPDATE SET
                birth_date  = COALESCE(athletes.birth_date,  EXCLUDED.birth_date),
                active_club = COALESCE(EXCLUDED.active_club, athletes.active_club),
                updated_at  = NOW()
            RETURNING id
            """,
            (last, first, name, safe_nat, gender, parse_date(dob), club),
        )
        athlete_id = cur.insert_id()

    # Record this spelling as a known variant
    cur.execute(
        "INSERT INTO athlete_name_variants (athlete_id, name_variant, nationality, first_seen_file) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (athlete_id, name, nat, os.path.basename(source_file)),
    )
    return athlete_id


# ─────────────────────────────────────────────────────────────────────────────
# Detail row inserters
# ─────────────────────────────────────────────────────────────────────────────

def insert_hill_data(cur, competition_id: int, doc_id: int, hd: dict):
    cur.execute(
        """
        INSERT INTO hill_data
            (competition_id, document_id, hill_size_m, k_point_m, meter_value,
             gate_factor, wind_factor_head, wind_factor_tail, height_difference_m)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            competition_id, doc_id,
            parse_float(hd.get("hill_size_m")),
            parse_float(hd.get("k_point_m")),
            parse_float(hd.get("meter_value")),
            parse_float(hd.get("gate_factor")),
            parse_float(hd.get("wind_factor_head")),
            parse_float(hd.get("wind_factor_tail")),
            parse_float(hd.get("height_difference_m")),
        ),
    )


def insert_course_info(cur, competition_id: int, doc_id: int, ci: dict):
    cur.execute(
        """
        INSERT INTO course_info
            (competition_id, document_id, height_m, max_climb_m,
             total_climb_m, length_km, number_of_laps)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            competition_id, doc_id,
            parse_float(ci.get("height_m")),
            parse_float(ci.get("max_climb_m")),
            parse_float(ci.get("total_climb_m")),
            parse_float(ci.get("length_km")),
            parse_int(ci.get("number_of_laps")),
        ),
    )


def insert_weather(cur, competition_id: int, doc_id: int, w: dict):
    cur.execute(
        """
        INSERT INTO weather_records
            (competition_id, document_id, weather_description, snow_conditions,
             temp_air_c, temp_snow_c, temp_air_start_c, temp_air_finish_c,
             temp_snow_start_c, temp_snow_finish_c,
             humidity_start_pct, humidity_finish_pct,
             wind_min_ms, wind_max_ms, wind_avg_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            competition_id, doc_id,
            w.get("weather_description"),
            w.get("snow_conditions"),
            parse_float(w.get("temp_air_c")),
            parse_float(w.get("temp_snow_c")),
            parse_float(w.get("temp_air_start_c")),
            parse_float(w.get("temp_air_finish_c")),
            parse_float(w.get("temp_snow_start_c")),
            parse_float(w.get("temp_snow_finish_c")),
            parse_float(w.get("humidity_start_pct")),
            parse_float(w.get("humidity_finish_pct")),
            parse_float(w.get("wind_min_ms")),
            parse_float(w.get("wind_max_ms")),
            parse_float(w.get("wind_avg_ms")),
        ),
    )


def insert_jury(cur, doc_id: int, jury: list):
    for j in jury:
        cur.execute(
            "INSERT INTO jury_officials (document_id, role, last_name, first_name, nation) "
            "VALUES (%s, %s, %s, %s, %s)",
            (doc_id, j.get("role"), j.get("last_name"), j.get("first_name"), j.get("nation")),
        )


def insert_judges(cur, doc_id: int, judges: list):
    for j in judges:
        cur.execute(
            "INSERT INTO jumping_judges (document_id, position, last_name, first_name, nation) "
            "VALUES (%s, %s, %s, %s, %s)",
            (doc_id, j.get("position"), j.get("last_name"), j.get("first_name"), j.get("nation")),
        )


def insert_jump_row(cur, table: str, competition_id: int, doc_id: int, athlete_id: int, r: dict):
    """Insert one row into jump_round_results / training_jump_results / trial_round_results."""
    extra_cols = ", pursuit_time_diff" if table == "jump_round_results" else ""
    extra_vals = ", %s" if table == "jump_round_results" else ""
    extra_data = (r.get("pursuit_time_diff"),) if table == "jump_round_results" else ()

    cur.execute(
        f"""
        INSERT INTO {table}
            (competition_id, document_id, athlete_id, raw_name, raw_nation,
             rank, bib, club, date_of_birth, round_number,
             speed_kmh, distance_m, dist_points,
             judge_a, judge_b, judge_c, judge_d, judge_e, style_points,
             gate, gate_comp_pts, wind_ms, wind_comp_pts, total_points,
             dns, dsq, dsq_reason, fall{extra_cols})
        VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s, %s,%s,%s, %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s, %s,%s,%s,%s{extra_vals})
        """,
        (
            competition_id, doc_id, athlete_id,
            r.get("name"), r.get("nation"),
            parse_int(r.get("rank")), parse_int(r.get("bib")),
            r.get("club"), parse_date(r.get("date_of_birth")),
            parse_int(r.get("round_number")),
            parse_float(r.get("speed_kmh")),
            parse_float(r.get("distance_m")),
            parse_float(r.get("dist_points")),
            parse_float(r.get("judge_a")), parse_float(r.get("judge_b")),
            parse_float(r.get("judge_c")), parse_float(r.get("judge_d")),
            parse_float(r.get("judge_e")),
            parse_float(r.get("style_points")),
            parse_int(r.get("gate")),
            parse_float(r.get("gate_comp_pts")),
            parse_float(r.get("wind_ms")),
            parse_float(r.get("wind_comp_pts")),
            parse_float(r.get("total_points")),
            bool(r.get("dns")), bool(r.get("dsq")), r.get("dsq_reason"),
            bool(r.get("fall")),
        ) + extra_data,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Single-file loader
# ─────────────────────────────────────────────────────────────────────────────

def load_file(cur, path: str):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)

    meta = filename_meta(path)
    if not meta["season_start"]:
        log.warning("Cannot determine season from %s — skipping", os.path.basename(path))
        return

    competition_id = get_or_create_competition(cur, meta, doc)
    doc_id = insert_document(cur, competition_id, meta, doc)

    # ── Competition detail ──────────────────────────────────────────────────
    if doc.get("hill_data"):
        insert_hill_data(cur, competition_id, doc_id, doc["hill_data"])
    if doc.get("course_info"):
        insert_course_info(cur, competition_id, doc_id, doc["course_info"])
    if doc.get("weather"):
        insert_weather(cur, competition_id, doc_id, doc["weather"])
    insert_jury(cur, doc_id, doc.get("jury") or [])
    insert_judges(cur, doc_id, doc.get("judges") or [])

    gender = meta.get("gender")
    source = doc.get("source_file", path)
    doc_type = (meta["doc_type"] or doc.get("doc_type") or "").upper()

    # ── Route results by doc type ───────────────────────────────────────────

    # ROF — final combined results
    for r in doc.get("combined_results") or []:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        athlete_id = get_or_create_athlete(
            cur, name, r.get("nation"), r.get("date_of_birth"), r.get("club"), gender, source
        )
        cur.execute(
            """
            INSERT INTO combined_results
                (competition_id, document_id, athlete_id, raw_name, raw_nation,
                 rank, bib, club, date_of_birth,
                 jump_points, jump_rank, time_difference,
                 xc_time, xc_rank, time_behind, wave_start, status)
            VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s, %s,%s,%s,%s,%s)
            """,
            (
                competition_id, doc_id, athlete_id, name, r.get("nation"),
                parse_int(r.get("rank")), parse_int(r.get("bib")),
                r.get("club"), parse_date(r.get("date_of_birth")),
                parse_float(r.get("jump_points")), parse_int(r.get("jump_rank")),
                r.get("time_difference"), r.get("xc_time"),
                parse_int(r.get("xc_rank")), r.get("time_behind"),
                parse_int(r.get("wave_start")), status_from_row(r),
            ),
        )

    # RL / RL1 / PCR — official jump round results
    if doc_type in ("RL", "RL1", "PCR"):
        for r in doc.get("jump_rounds") or []:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            athlete_id = get_or_create_athlete(
                cur, name, r.get("nation"), r.get("date_of_birth"), r.get("club"), gender, source
            )
            insert_jump_row(cur, "jump_round_results", competition_id, doc_id, athlete_id, r)

    # RLT — training jumps (no pursuit_time_diff column)
    elif doc_type == "RLT":
        for r in doc.get("jump_rounds") or []:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            athlete_id = get_or_create_athlete(
                cur, name, r.get("nation"), r.get("date_of_birth"), r.get("club"), gender, source
            )
            insert_jump_row(cur, "training_jump_results", competition_id, doc_id, athlete_id, r)

    # RLTR — trial round results
    elif doc_type == "RLTR":
        for r in doc.get("jump_rounds") or []:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            athlete_id = get_or_create_athlete(
                cur, name, r.get("nation"), r.get("date_of_birth"), r.get("club"), gender, source
            )
            insert_jump_row(cur, "trial_round_results", competition_id, doc_id, athlete_id, r)

    # RLLL — mass start XC leg
    elif doc_type == "RLLL":
        for r in doc.get("xc_results") or []:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            athlete_id = get_or_create_athlete(
                cur, name, r.get("nation"), r.get("date_of_birth"), r.get("club"), gender, source
            )
            cur.execute(
                """
                INSERT INTO xc_results
                    (competition_id, document_id, athlete_id, raw_name, raw_nation,
                     rank, bib, club, date_of_birth, total_time, time_behind, points, status)
                VALUES (%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    competition_id, doc_id, athlete_id, name, r.get("nation"),
                    parse_int(r.get("rank")), parse_int(r.get("bib")),
                    r.get("club"), parse_date(r.get("date_of_birth")),
                    r.get("total_time"), r.get("time_behind"),
                    parse_float(r.get("points")), r.get("status"),
                ),
            )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Load FIS Nordic Combined JSON into PostgreSQL or SQLite"
    )
    ap.add_argument("--db",
                    help="PostgreSQL DSN e.g. postgresql://user:pass@localhost/noco")
    ap.add_argument("--sqlite", metavar="PATH",
                    help="SQLite database file path e.g. db/noco.db")
    ap.add_argument("--output-dir", default="output",
                    help="Directory containing JSON output files (default: output)")
    ap.add_argument("--reset", action="store_true",
                    help="Drop and recreate all tables before loading")
    ap.add_argument("--batch-size", type=int, default=200,
                    help="Commit every N files (default: 200)")
    ap.add_argument("--doc-type", metavar="TYPE",
                    help="Only load files of this doc type (e.g. ROF, RL, PCR)")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    if not args.db and not args.sqlite:
        ap.error("Provide either --db (PostgreSQL) or --sqlite (SQLite)")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    conn, is_sqlite = connect(dsn=args.db, sqlite_path=args.sqlite)
    cur = make_cursor(conn, is_sqlite)

    db_dir = os.path.dirname(os.path.abspath(__file__))

    if args.reset:
        log.info("Recreating schema...")
        if is_sqlite:
            schema_file = os.path.join(db_dir, "schema_sqlite.sql")
            # Drop all tables by recreating the file
            conn.close()
            if os.path.exists(args.sqlite):
                os.remove(args.sqlite)
            conn, is_sqlite = connect(sqlite_path=args.sqlite)
            cur = make_cursor(conn, is_sqlite)
        else:
            schema_file = os.path.join(db_dir, "schema.sql")
            cur.execute("""
                DROP SCHEMA public CASCADE;
                CREATE SCHEMA public;
                GRANT ALL ON SCHEMA public TO PUBLIC;
            """)

        with open(schema_file, encoding="utf-8") as f:
            schema_sql = f.read()

        if is_sqlite:
            # sqlite3 executescript for multi-statement SQL
            conn.executescript(schema_sql)
        else:
            cur.execute(schema_sql)

        conn.commit()
        log.info("Schema ready.")

    files = sorted(glob.glob(os.path.join(args.output_dir, "**/*.json"), recursive=True))
    if args.doc_type:
        dt = args.doc_type.upper()
        files = [f for f in files if re.search(rf'{dt}\.json$', os.path.basename(f), re.IGNORECASE)]
    log.info("Found %d JSON files in %s", len(files), args.output_dir)

    ok = errors = 0
    for i, path in enumerate(files, 1):
        try:
            cur = make_cursor(conn, is_sqlite)
            load_file(cur, path)
            ok += 1
        except Exception as e:
            log.error("Error in %s: %s", os.path.basename(path), e)
            if not is_sqlite:
                conn.rollback()
            errors += 1
            continue

        if i % args.batch_size == 0:
            conn.commit()
            log.info("  %d / %d loaded  (%d errors)", i, len(files), errors)

    conn.commit()
    log.info("Done: %d OK, %d errors", ok, errors)
    conn.close()


if __name__ == "__main__":
    main()
