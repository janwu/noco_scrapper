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
    if re.search(r'[()]', name):
        # 'ARMBRUSTER Nathalie (F)': a second athlete next to 'ARMBRUSTER Nathalie'
        return f"name holds a bracket: {name!r}"
    if given_first:
        if not re.fullmatch(r"[^\W\d_][^\W\d_.'-]*(?:[ -][^\W\d_][^\W\d_.'-]*)+", name):
            return f"not a 'Firstname Surname' name: {name!r}"
    elif not _SURNAME_FIRST_RE.match(name):
        # Names are printed 'SURNAME Firstname'; anything else is a club,
        # header or jury line that slipped into the result list.
        return f"name does not start with an upper-case surname: {name!r}"
    if not given_first and _TWO_NAMES_RE.search(re.sub(r'^(?:van|von|de|di|da|del|der|le|la)\s', '', name)):
        # 'MUENCHMEYER StephanGER KIRCHEISEN Bjoern': two table cells in one
        return f"name holds more than one person: {name!r}"
    if not nation or not re.match(r'^[A-Z]{3}$', nation) or nation in _MONTHS:
        return f"invalid nation {nation!r} for {name!r}"
    return None


# 'MOAN Magnus', 'LI Ji', "O'BRIEN Tom", 'O CONNELL Kathleen', 'McKINNON Joe' —
# but not 'E Loeng Geir' (judge letter + name) or 'Lisa EDER'
_SURNAME_FIRST_RE = re.compile(
    r"^(?:(?:van|von|de|di|da|del|der|le|la)\s)?(?:Mc)?[^\W\d_a-z](?:[^\Wa-z_]+[\s\-']|'[^\W\d_a-z]|\s[^\W\d_a-z]{2})")
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


# ── jump lists ───────────────────────────────────────────────────────────────

# Rows of a list whose printed values may contradict each other before the
# parse (rather than the PDF) is blamed: 5 %, at least 2
def _too_many(count: int, rows: int) -> bool:
    return count > max(2, 0.05 * rows)


def _is_plain_case_list(rows: List[dict]) -> bool:
    """World Cup lists of 2002/03–2004/05 print 'Ackermann Ronny', not 'ACKERMANN Ronny'."""
    named = [r['name'] for r in rows if r.get('name')]
    plain = [n for n in named if re.match(r"^[^\W\d_a-z][^\W\d_A-Z]", n) and not _SURNAME_FIRST_RE.match(n)]
    return bool(named) and len(plain) >= 0.8 * len(named)


def jump_row_identity_problem(row: dict, given_first: bool = False, plain_case: bool = False) -> Optional[str]:
    """row_identity_problem for jump lists; plain_case: see _is_plain_case_list."""
    if not plain_case:
        return row_identity_problem(row, given_first)
    name = row.get('name') or ''
    nation = row.get('nation')
    if not is_valid_athlete_name(name) or len(name.split()) < 2 or re.search(r'\d', name):
        return f"invalid athlete name {name!r}"
    if not nation or not re.match(r'^[A-Z]{3}$', nation) or nation in _MONTHS:
        return f"invalid nation {nation!r} for {name!r}"
    return None


def _marks(row: dict) -> List[float]:
    return [row[k] for k in ('judge_a', 'judge_b', 'judge_c', 'judge_d', 'judge_e') if row.get(k) is not None]


def validate_jump(doc: dict) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings) for a competition jump list (RL, RL1, RLQ, PCR)."""
    errors: List[str] = []
    warnings: List[str] = []
    rows = doc.get('jump_rounds') or []
    if not rows:
        return ["no jump rows"], warnings

    ranked = [r for r in rows if r.get('rank') is not None]
    first_round = [r for r in ranked if r.get('round_number') == 1]
    is_team_list = False
    if not ranked:
        errors.append(f"no ranked rows ({len(rows)} rows, all without rank)")
    else:
        if not any(r['rank'] == 1 for r in ranked):
            errors.append("no winner (rank 1 missing)")
        # team lists: every member carries the rank and the bib of his team
        teams = {(r['rank'], r.get('bib')) for r in first_round}
        is_team_list = len(teams) < len(first_round)
        seq = _check_rank_sequence([rank for rank, _ in teams] if is_team_list
                                   else [r['rank'] for r in first_round])
        if seq:
            errors.append(seq)
    for r in rows:
        if r.get('rank') is None and not (r.get('dns') or r.get('dsq')) and r.get('distance_m') is None:
            errors.append(f"row without rank, status and jump: {r.get('name')!r}")

    # ── identity ────────────────────────────────────────────────────────────
    given_first = doc.get('name_order') == 'given-first'
    plain_case = _is_plain_case_list(rows)
    # lists by ewoxx name the athletes who did not start without their nation
    # (and mixed teams, 'FIS', their members); the loader completes it from their other results
    named_only = lambda r: (r.get('rank') is None or is_team_list) and not r.get('nation')
    for r in rows:
        problem = jump_row_identity_problem(dict(r, nation='XXX') if named_only(r) else r, given_first, plain_case)
        if problem:
            errors.append(problem)
    seen = set()
    for r in first_round:
        key = (r.get('name'), r.get('nation'), r.get('bib'))
        if key in seen:
            errors.append(f"athlete ranked twice: {r.get('name')!r}")
        seen.add(key)

    # ── the values of a jump ────────────────────────────────────────────────
    no_jump = [r for r in ranked if (r.get('distance_m') is None or r.get('total_points') is None)
               and not (r.get('dns') or r.get('dsq'))]
    if _too_many(len(no_jump), len(ranked)):
        errors.append(f"jump values missing in {len(no_jump)} of {len(ranked)} ranked rows")
    elif no_jump:
        warnings.append(f"jump values missing: {', '.join(str(r.get('name')) for r in no_jump)}")

    hill = doc.get('hill_data') or {}
    k_point, meter_value = hill.get('k_point_m'), hill.get('meter_value')
    checks = {'style points are not the sum of the marks': [],
              'distance points do not follow from the distance': [],
              'total is not the sum of its parts': [],
              'distance out of range': [],
              'speed out of range': []}
    for r in ranked:
        name = str(r.get('name'))
        marks = _marks(r)
        style, points, total = r.get('style_points'), r.get('dist_points'), r.get('total_points')
        distance = r.get('distance_m')
        if style is not None and len(marks) in (3, 5):
            counted = sum(marks) - min(marks) - max(marks) if len(marks) == 5 else sum(marks)
            if abs(counted - style) > 0.05:
                checks['style points are not the sum of the marks'].append(name)
        if k_point and meter_value and distance is not None and points is not None and k_point < 170:
            if abs(60 + (distance - k_point) * meter_value - points) > 0.11:
                checks['distance points do not follow from the distance'].append(name)
        if None not in (style, points, total):
            parts = points + style + (r.get('gate_comp_pts') or 0) + (r.get('wind_comp_pts') or 0)
            if abs(parts - total) > 0.11 and not (parts < 0 and total == 0):
                checks['total is not the sum of its parts'].append(name)
        if distance is not None and not 30 <= distance <= 260:
            checks['distance out of range'].append(name)
        if r.get('speed_kmh') is not None and not 60 <= r['speed_kmh'] <= 115:
            checks['speed out of range'].append(name)
    for what, names in checks.items():
        if _too_many(len(names), len(ranked)):
            errors.append(f"{what} in {len(names)} of {len(ranked)} ranked rows")
        elif names:
            warnings.append(f"{what}: {', '.join(names)}")

    return errors, warnings


def validate_training(doc: dict) -> Tuple[List[str], List[str]]:
    """
    Return (errors, warnings) for a training or trial round list (RLT, RLTR).
    They print no marks to check the values against, so only identity and
    plausible ranges are checked.
    """
    errors: List[str] = []
    warnings: List[str] = []
    rows = doc.get('jump_rounds') or []
    if not rows:
        return ["no jump rows"], warnings
    given_first = doc.get('name_order') == 'given-first'
    plain_case = _is_plain_case_list(rows)
    # a row without nation is completed by the loader from the athlete's other results;
    # a few rows that are no athlete (a club name) are dropped by the loader one by one
    bad = [p for p in (jump_row_identity_problem(dict(r, nation=r.get('nation') or 'XXX'), given_first, plain_case)
                       for r in rows) if p]
    if _too_many(len(bad), len(rows)):
        errors.append(f"{len(bad)} of {len(rows)} rows are no athlete, e.g. {bad[0]}")
    elif bad:
        warnings.append(f"rows that are no athlete: {'; '.join(bad)}")
    seen = set()
    twice = []
    for r in rows:
        key = (r.get('name'), r.get('nation'), r.get('round_number'))
        if key in seen:
            twice.append(f"{r.get('name')!r} in round {r.get('round_number')}")
        seen.add(key)
    if _too_many(len(twice), len(rows)):
        errors.append(f"athletes twice in a round: {len(twice)}, e.g. {twice[0]}")
    elif twice:
        warnings.append(f"athletes twice in a round: {', '.join(twice)}")
    jumped = [r for r in rows if r.get('distance_m') is not None]
    if _too_many(len(rows) - len(jumped), len(rows)):
        errors.append(f"distance missing in {len(rows) - len(jumped)} of {len(rows)} rows")
    hill = (doc.get('hill_data') or {}).get('hill_size_m')
    longest = hill * 1.12 if hill else 260          # a jump 12 % beyond the hill size is a misread
    for what, test in (('distance', lambda r: not 30 <= r['distance_m'] <= longest),
                       ('speed', lambda r: r.get('speed_kmh') is not None and not 60 <= r['speed_kmh'] <= 115),
                       ('gate', lambda r: r.get('gate') is not None and not 0 < r['gate'] <= 60)):
        names = [str(r.get('name')) for r in jumped if test(r)]
        if _too_many(len(names), len(jumped)):
            errors.append(f"{what} out of range in {len(names)} of {len(jumped)} rows")
        elif names:
            warnings.append(f"{what} out of range: {', '.join(names)}")
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
    """Validate a parsed document (as dict). Cross-country lists (RLLL) are not checked."""
    if doc.get('doc_type') == 'ROF':
        return validate_rof(doc)
    if doc.get('doc_type') in ('RL', 'RL1', 'PCR'):
        return validate_jump(doc)
    if doc.get('doc_type') in ('RLT', 'RLTR'):
        return validate_training(doc)
    return [], []
