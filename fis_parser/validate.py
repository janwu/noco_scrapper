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


def is_jump_last(discipline: Optional[str]) -> bool:
    """
    Mass Start and Super Sprint: the race comes first and is converted into
    points, the jump decides.  Gaps in these lists are points, not times.
    """
    return discipline in ('Mass Start', 'Super Sprint')


def _check_rank_sequence(ranks: List[int]) -> Optional[str]:
    """Ranks must run 1..N; ties repeat a rank and skip the following ones."""
    ordered = sorted(ranks)
    for i, rank in enumerate(ordered):
        if rank != i + 1 and not (i > 0 and rank == ordered[i - 1]):
            return (f"rank sequence broken at position {i + 1}: "
                    f"found rank {rank} ({len(ordered)} ranked rows, max rank {ordered[-1]})")
    return None


def row_identity_problem(row: dict, given_first: bool = False) -> Optional[str]:
    """
    Why this row cannot be an athlete (name + nation), or None if it can.
    given_first: the list prints 'Firstname Surname' in mixed case (K-Jump).
    """
    name = row.get('name') or ''
    nation = row.get('nation')
    if not is_valid_athlete_name(name):
        return f"invalid athlete name {name!r}"
    if given_first:
        if not re.fullmatch(r"[^\W\d_][^\W\d_.'-]*(?:[ -][^\W\d_][^\W\d_.'-]*)+", name):
            return f"not a 'Firstname Surname' name: {name!r}"
    elif not _SURNAME_FIRST_RE.match(name):
        # Names are printed 'SURNAME Firstname'; anything else is a club,
        # header or jury line that slipped into the result list.
        return f"name does not start with an upper-case surname: {name!r}"
    if not given_first and _TWO_NAMES_RE.search(name):
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


def _validate_teams(doc: dict, errors: List[str], warnings: List[str]) -> None:
    """Checks for a team result list (doc['team_results'])."""
    teams = doc.get('team_results') or []
    stats = doc.get('competitor_stats') or {}
    if not teams:
        errors.append("no team rows")
        return
    ranked = [t for t in teams if t.get('rank') is not None]
    if not ranked:
        errors.append(f"no ranked teams ({len(teams)} teams, all without rank)")
        return
    if not any(t['rank'] == 1 for t in ranked):
        errors.append("no winner (rank 1 missing)")
    seq = _check_rank_sequence([t['rank'] for t in ranked])
    if seq:
        errors.append(seq)

    # Every ranked team has the same number of athletes (2 in a team sprint, else 3 or 4)
    sizes = sorted({len(t.get('members') or []) for t in ranked})
    if len(sizes) != 1 or sizes[0] < 2:
        errors.append(f"teams have {sizes} athletes")

    # The statistics count athletes, not teams
    athletes = sum(len(t.get('members') or []) for t in ranked)
    lapped = sum(len(t.get('members') or []) for t in ranked if t.get('status') == 'LAP')
    expected = stats.get('ranked_athletes')
    if expected is not None and expected not in (athletes, athletes - lapped):
        errors.append(f"athletes in ranked teams: parsed {athletes} ({lapped} lapped), "
                      f"PDF statistics say {expected}")

    for t in teams:
        label = t.get('team_name') or t.get('nation')
        nation = t.get('nation')
        if not nation or not re.match(r'^[A-Z]{3}$', nation) or nation in _MONTHS:
            errors.append(f"invalid nation {nation!r} for team {label!r}")
        if t.get('rank') is None and not t.get('status'):
            errors.append(f"team without rank and without status: {label!r}")
        for m in t.get('members') or []:
            problem = row_identity_problem({'name': m.get('name'), 'nation': nation or 'XXX'})
            if problem:
                errors.append(f"team {label!r}: {problem}")

    finished = [t for t in ranked if t.get('status') != 'LAP']
    for field in ('bib', 'jump_points', 'xc_time', 'time_behind'):
        missing = sum(1 for t in finished if t.get(field) in (None, ''))
        if finished and missing / len(finished) > _FIELD_GAP_TOLERANCE:
            warnings.append(f"{field} missing in {missing} of {len(finished)} ranked teams")
    members = [m for t in ranked for m in t.get('members') or []]
    missing = sum(1 for m in members if m.get('jump_points') is None)
    if members and missing / len(members) > _FIELD_GAP_TOLERANCE:
        warnings.append(f"jump_points missing for {missing} of {len(members)} team athletes")


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
        _validate_teams(doc, errors, warnings)
        return errors, warnings

    if doc.get('discipline') == 'Provisional Round':
        warnings.append("provisional round filed as official result list: not parsed")
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
    given_first = doc.get('name_order') == 'given-first'
    for r in rows:
        problem = row_identity_problem(r, given_first)
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
        _check_time_formats(doc, rows, errors, warnings)
        _check_order(finished, 'jump_rank', 'jump_points', False, errors, warnings)
        _check_order(finished, 'xc_rank', 'xc_time', True, errors, warnings)

    return errors, warnings


CLOCK_RE = re.compile(r'^(?:\d+:)?\d{1,2}:\d{2}\.\d$')             # 23:44.4, 1:02:13.5
START_GAP_RE = re.compile(r'^\+?\d{1,2}:\d{2}$')                    # 0:24, +1:07, 00:38
FINISH_GAP_RE = re.compile(r'^\+(?:(?:\d+:)?\d{1,2}:)?\d{1,2}\.\d$')    # +41.6, +1:24.5, +00:03.9
_POINTS_RE = re.compile(r'^[+-]?\d+\.\d+$')                         # mass start: gaps are points
_COUNT_RE = re.compile(r'^\d+$')                                    # penalty race: penalty laps

_WHAT = {'xc_time': 'a time', 'time_difference': 'a start gap', 'time_behind': 'a gap to the winner'}


def _get(row, field):
    return row.get(field) if isinstance(row, dict) else getattr(row, field)


def time_format_problems(discipline: Optional[str], rows) -> List[tuple]:
    """
    (row, field) for every time value that cannot be what its field says.
    Works on dicts and on CombinedResult objects.

    A filled field is not yet a right one: when a layout has an extra column
    (the TRIPLE points, a sprint's start distance) every value after it
    slides one column to the left and a points value ends up as a time.
    """
    mass_start = is_jump_last(discipline)
    problems = []
    for row in rows:
        ranked = _get(row, 'rank') is not None
        expected = {'xc_time': CLOCK_RE}
        if mass_start:
            # cross-country comes first; the gaps are jump-equivalent points
            expected['time_behind'] = _POINTS_RE
        else:
            expected['time_difference'] = _COUNT_RE if discipline == 'Penalty Race' else START_GAP_RE
            # the winner's line carries his total time instead of a gap
            expected['time_behind'] = CLOCK_RE if _get(row, 'rank') == 1 else FINISH_GAP_RE
        for field, pattern in expected.items():
            value = _get(row, field)
            if value in (None, ''):
                continue
            if field == 'time_behind' and (not ranked or value in ('0.0', '+0.0')):
                continue
            if not pattern.match(value):
                problems.append((row, field))
    return problems


def _check_time_formats(doc: dict, rows: List[dict], errors: List[str], warnings: List[str]) -> None:
    bad: dict = {}
    for row, field in time_format_problems(doc.get('discipline'), rows):
        bad.setdefault(field, []).append(row[field])
    for field, values in bad.items():
        filled = sum(1 for r in rows if r.get(field) not in (None, ''))
        message = f"{field} is not {_WHAT[field]} in {len(values)} of {filled} rows, e.g. {values[0]!r}"
        (errors if len(values) / filled > _FIELD_GAP_TOLERANCE else warnings).append(message)


def _seconds(clock: str) -> Optional[float]:
    try:
        total = 0.0
        for part in clock.split(':'):
            total = total * 60 + float(part)
        return total
    except (ValueError, AttributeError):
        return None


def _check_order(rows: List[dict], rank_field: str, value_field: str, ascending: bool,
                 errors: List[str], warnings: List[str]) -> None:
    """
    A rank and the value it ranks must tell the same story: the better jump
    rank has the higher points, the better cross-country rank the shorter
    time.  If they do not, one of the two columns holds something else
    (a distance instead of points, the points of a single round, ...).
    """
    pairs = []
    for r in rows:
        rank, value = r.get(rank_field), r.get(value_field)
        if value_field == 'xc_time' and value:
            value = _seconds(value)
        if rank is not None and value is not None:
            pairs.append((rank, value))
    if len(pairs) < 5:
        return
    pairs.sort()
    wrong = 0
    for (rank_a, a), (rank_b, b) in zip(pairs, pairs[1:]):
        if rank_a != rank_b and (a > b if ascending else a < b):
            wrong += 1
    if not wrong:
        return
    message = f"{value_field} does not follow {rank_field} for {wrong} of {len(pairs) - 1} neighbours"
    (errors if wrong / (len(pairs) - 1) > _FIELD_GAP_TOLERANCE else warnings).append(message)


def validate(doc: dict) -> Tuple[List[str], List[str]]:
    """Validate a parsed document (as dict). Only ROF is checked so far."""
    if doc.get('doc_type') == 'ROF':
        return validate_rof(doc)
    return [], []
