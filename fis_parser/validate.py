"""
Plausibility checks for parsed documents.

The extractors never fail loudly on a layout they do not understand — they
just return fewer rows.  These checks compare the parsed rows against facts
the PDF states about itself (competitor statistics on the last page, rank
numbering) and record every violation, so a broken parse is visible in
`parse_errors` instead of silently ending up in the database.

    parse_errors  — the result list is incomplete or wrong; do not trust it
    warnings      — rows are there, but individual fields are missing
"""
import re
from typing import List, Optional, Tuple

from fis_parser.utils import is_valid_athlete_name

_MONTHS = {'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
           'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'}

# Share of ranked rows that may lack a field before a warning is raised
_FIELD_GAP_TOLERANCE = 0.05


def is_team_discipline(discipline: Optional[str]) -> bool:
    return bool(discipline) and discipline.startswith('Team')


def _check_rank_sequence(ranks: List[int]) -> Optional[str]:
    """Ranks must run 1..N; ties repeat a rank and skip the following ones."""
    ordered = sorted(ranks)
    for i, rank in enumerate(ordered):
        if rank != i + 1 and not (i > 0 and rank == ordered[i - 1]):
            return (f"rank sequence broken at position {i + 1}: "
                    f"found rank {rank} ({len(ordered)} ranked rows, max rank {ordered[-1]})")
    return None


def row_identity_problem(row: dict) -> Optional[str]:
    """Why this row cannot be an athlete (name + nation), or None if it can."""
    name = row.get('name') or ''
    nation = row.get('nation')
    if not is_valid_athlete_name(name):
        return f"invalid athlete name {name!r}"
    if not _SURNAME_FIRST_RE.match(name):
        # Names are printed 'SURNAME Firstname'; anything else is a club,
        # header or jury line that slipped into the result list.
        return f"name does not start with an upper-case surname: {name!r}"
    if _TWO_NAMES_RE.search(name):
        # 'MUENCHMEYER StephanGER KIRCHEISEN Bjoern': two table cells in one
        return f"name holds more than one person: {name!r}"
    if not nation or not re.match(r'^[A-Z]{3}$', nation) or nation in _MONTHS:
        return f"invalid nation {nation!r} for {name!r}"
    return None


# 'MOAN Magnus', 'LI Ji', "O'BRIEN Tom", 'O CONNELL Kathleen', 'McKINNON Joe' —
# but not 'E Loeng Geir' (judge letter + name) or 'Lisa EDER'
_SURNAME_FIRST_RE = re.compile(
    r"^(?:Mc)?[^\W\d_a-z](?:[^\Wa-z_]+[\s\-']|'[^\W\d_a-z]|\s[^\W\d_a-z]{2})")
# first name (has lower case) followed by another all-caps word of 3+ letters
_TWO_NAMES_RE = re.compile(r"[^\W\d_]*[a-zà-ÿ][^\W\d_]*\s+[^\W\d_a-zà-ÿ]{3,}(?:\s|$)")


def validate_rof(doc: dict) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings) for a parsed ROF document given as a dict."""
    errors: List[str] = []
    warnings: List[str] = []
    rows = doc.get('combined_results') or []
    stats = doc.get('competitor_stats') or {}

    for field in ('location', 'country', 'competition_date', 'discipline'):
        if not doc.get(field):
            warnings.append(f"header: {field} missing")
    location = doc.get('location') or ''
    if re.search(r'Director|Delegate|Coordinator|Chief\s+of|^in\s', location):
        errors.append(f"header: location is not a place: {location!r}")

    if is_team_discipline(doc.get('discipline')):
        # Team result lists have no parser of their own yet; whatever rows
        # the individual parser picked up are neither complete nor checked.
        warnings.append("team competition: result rows not parsed")
        return errors, warnings

    if not rows:
        errors.append("no result rows")
        return errors, warnings

    ranked = [r for r in rows if r.get('rank') is not None]
    unranked = [r for r in rows if r.get('rank') is None]

    # ── completeness ────────────────────────────────────────────────────────
    if not ranked:
        errors.append(f"no ranked rows ({len(rows)} rows, all without rank)")
    else:
        if not any(r['rank'] == 1 for r in ranked):
            errors.append("no winner (rank 1 missing)")
        seq = _check_rank_sequence([r['rank'] for r in ranked])
        if seq:
            errors.append(seq)

    # Lapped athletes are printed with a rank; depending on the season the
    # statistics count them as ranked or only under LAP.
    lapped = sum(1 for r in ranked if r.get('status') == 'LAP')
    expected = stats.get('ranked_athletes')
    if expected is not None and expected not in (len(ranked), len(ranked) - lapped):
        errors.append(f"ranked rows: parsed {len(ranked)} ({lapped} lapped), PDF statistics say {expected}")

    for r in unranked:
        if not r.get('status'):
            errors.append(f"row without rank and without status: {r.get('name')!r}")

    for status, key in (('DNS', 'dns'), ('DNF', 'dnf'), ('DSQ', 'dsq')):
        want = stats.get(key)
        got = sum(1 for r in unranked if r.get('status') == status)
        if want is not None and want != got:
            warnings.append(f"{status} rows: parsed {got}, PDF statistics say {want}")

    # ── identity ────────────────────────────────────────────────────────────
    for r in rows:
        problem = row_identity_problem(r)
        if problem:
            errors.append(problem)

    seen = {}
    for r in ranked:
        key = (r.get('name'), r.get('nation'))
        if key in seen:
            errors.append(f"athlete ranked twice: {r.get('name')!r} (ranks {seen[key]} and {r['rank']})")
        seen[key] = r['rank']

    # ── field coverage ──────────────────────────────────────────────────────
    finished = [r for r in ranked if r.get('status') != 'LAP']
    if finished:
        for field in ('bib', 'jump_points', 'xc_time', 'time_behind'):
            missing = sum(1 for r in finished if r.get(field) in (None, ''))
            if missing / len(finished) > _FIELD_GAP_TOLERANCE:
                warnings.append(f"{field} missing in {missing} of {len(finished)} finishers")

    return errors, warnings


def validate(doc: dict) -> Tuple[List[str], List[str]]:
    """Validate a parsed document (as dict). Only ROF is checked so far."""
    if doc.get('doc_type') == 'ROF':
        return validate_rof(doc)
    return [], []
