"""
Line-based parser for the ewoxx "Official Results" layout used in the
Continental Cup 2008/09 – 2021/22.

Every ranked athlete takes three text lines:

    1. GEIGER Vinzenz GER 126.5 22:14.7          rank, name, nation, jump points, XC time
    00:24 22:38.7                                start difference, total time / time behind
    4 SC 1906 Oberstdorf 24 JUL 1997 4. 6.       bib, club, birthdate, jump rank, XC rank

The 2008/09 variant prints the FIS code where the nation is and moves the
nation in front of the club ("9 USA, Steamboat Springs ... 21.11.1976 9. 2.").

Athletes without a result follow under "Did not start" / "Did not finish" /
"Disqualified", either on one line ("9 BORISOV Timofey RUS 118.5 8. 00:56")
or, in the older files, spread over three lines like the ranked athletes.
"""
import re
from typing import List, Optional, Tuple

from fis_parser.models import CombinedResult, CompetitorStats
from fis_parser.utils import parse_float, parse_int, normalise_date, clean_name

_HEADER_RE = re.compile(r'^Rank\s+Name\s+(Nation|FIS-Code)\b')
_HEADER2_RE = re.compile(r'^Bib\s+(Nation,\s+)?Club\s+Birthdate\b')

_NAME = r"(?P<name>[^\W\d_a-z][^\d]*?)"
_DOB = r'(?P<dob>\d{1,2}\s+[A-Z]{3}\s+\d{4}|\d{1,2}\.\d{2}\.\d{4})'
_TIME = r'\d{1,2}:\d{2}(?::\d{2})?(?:\.\d)?'

_RANKED1_RE = re.compile(
    r'^(?:(?:FF|PF)\s+)?(?P<rank>\d+)\.\s+' + _NAME + r'\s+(?P<nat>[A-Z]{3}|\d+)'
    r'\s+(?P<pts>-?\d+\.\d)(?:\s+(?P<xc>' + _TIME + r'))?$')
_RANKED2_RE = re.compile(
    r'^(?:(?P<diff>' + _TIME + r')\s+)?(?P<behind>\+?\s?' + _TIME + r')$')
_ROW3_RE = re.compile(
    r'^(?P<bib>\d+)(?:\s+(?P<club>.*?))??(?:\s+' + _DOB + r')?'
    r'(?:\s+(?P<jrank>\d+)\.)?(?:\s+(?P<xcrank>\d+)\.)?$')

_SECTION_RE = re.compile(
    r'^(?:(?P<dns>Did\s+not\s+start|Not\s+permitted\s+to\s+start)'
    r'|(?P<dnf>Did\s+not\s+finish|Lapped)'
    r'|(?P<dsq>Disqualified))\b', re.IGNORECASE)
# Disqualifications carry the rule reference, e.g. 'ICR531.3.1 Violated start procedure'
_REASON = r'(?:\s+ICR\s?\d.*)?'
# One-line section row: bib, name, nation, optional jump points / rank / start difference
_SECTION_ROW_RE = re.compile(
    r'^(?P<bib>\d+)\s+' + _NAME + r'\s+(?P<nat>[A-Z]{3})'
    r'(?:\s+(?P<pts>-?\d+\.\d))?(?:\s+(?P<jrank>\d+)\.)?(?:\s+(?P<diff>' + _TIME + r'))?'
    + _REASON + r'$')
# Three-line section row (older files)
_SECTION_NAME_RE = re.compile(
    r'^' + _NAME + r'\s+(?P<nat>[A-Z]{3}|\d+)(?:\s+(?P<pts>-?\d+[.,]\d))?$')
_SECTION_BIB_RE = re.compile(r'^(?P<bib>\d+)(?:\s+(?P<diff>' + _TIME + r'))?' + _REASON + r'$')
_SECTION_CLUB_RE = re.compile(
    r'^(?P<club>.*?)\s*' + _DOB + r'(?:\s+(?P<jrank>\d+)\.)?$')

# Everything from here on is weather / signatures / footer
_END_RE = re.compile(r'^(?:Weather\b|Air\s+Snow\b|Snow\s+Air\b|TD\s+Chief|Chief\s+of\s+Competition\s+TD)',
                     re.IGNORECASE)
_STATS_RE = re.compile(r'Entries\s+Started\s+Results', re.IGNORECASE)


def is_ewoxx_layout(lines: List[str]) -> bool:
    for i, line in enumerate(lines[:-1]):
        if _HEADER_RE.match(line.strip()) and _HEADER2_RE.match(lines[i + 1].strip()):
            return True
    return False


def _split_nation_club(club: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """'USA, Steamboat Springs WSC' → ('USA', 'Steamboat Springs WSC'); 'JPN' → ('JPN', None)."""
    m = re.match(r'^([A-Z]{3})(?:,\s*(.*))?$', club or '')
    if m:
        return m.group(1), m.group(2) or None
    return None, club or None


def parse_ewoxx_rof(pages: List[List[str]]) -> Tuple[List[CombinedResult], Optional[CompetitorStats], List[str]]:
    """
    Parse all pages (each a list of text lines).
    Returns (results, competitor statistics if printed, lines in the result
    table that could not be interpreted).
    """
    results: List[CombinedResult] = []
    unparsed: List[str] = []
    stats: Optional[CompetitorStats] = None
    section: Optional[str] = None          # None = ranked list; else DNS / DNF / DSQ
    current: Optional[CombinedResult] = None
    expect = 0                             # which line of `current` comes next (2 or 3)

    def close():
        nonlocal current, expect
        if current is not None:
            results.append(current)
        current, expect = None, 0

    for lines in pages:
        # 'Entries Started Results' / '53/12 51/11 50/11' below the table
        for i, raw in enumerate(lines[:-1]):
            if _STATS_RE.search(raw):
                fr = re.findall(r'(\d+)\s*/\s*(\d+)', lines[i + 1])
                if len(fr) >= 3:
                    stats = CompetitorStats(
                        entries_athletes=int(fr[-3][0]), entries_nations=int(fr[-3][1]),
                        ranked_athletes=int(fr[-1][0]), ranked_nations=int(fr[-1][1]))

        in_table = False
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if _HEADER_RE.match(line) or _HEADER2_RE.match(line):
                in_table = True
                continue
            if not in_table:
                continue
            if _END_RE.match(line):
                break
            if re.match(r'^(?:data\s+processing|visit\s+fis-ski|printed\b|Bib\s+Name\b|Club$)',
                        line, re.IGNORECASE):
                continue

            sec = _SECTION_RE.match(line)
            if sec:
                close()
                section = 'DNS' if sec.group('dns') else 'DNF' if sec.group('dnf') else 'DSQ'
                continue

            m = _RANKED1_RE.match(line)
            if m:
                close()
                section = None
                current = CombinedResult(
                    rank=int(m.group('rank')),
                    name=clean_name(m.group('name')),
                    nation=m.group('nat') if m.group('nat').isalpha() else None,
                    jump_points=parse_float(m.group('pts')),
                    xc_time=m.group('xc'),
                )
                expect = 2
                continue

            if section is None:
                if current is not None and expect == 2:
                    m = _RANKED2_RE.match(line)
                    if m:
                        current.time_difference = m.group('diff')
                        current.time_behind = m.group('behind').replace(' ', '')
                        if current.rank == 1:
                            # the winner's total time, sometimes printed '+28:36.0'
                            current.time_behind = current.time_behind.lstrip('+')
                        expect = 3
                        continue
                if current is not None and expect in (2, 3):
                    m = _ROW3_RE.match(line)
                    if m:
                        _fill_row3(current, m)
                        close()
                        continue
                unparsed.append(line)
                continue

            # ── DNS / DNF / DSQ section ─────────────────────────────────────
            m = _SECTION_ROW_RE.match(line)
            if m:
                close()
                results.append(CombinedResult(
                    bib=int(m.group('bib')), name=clean_name(m.group('name')),
                    nation=m.group('nat'), status=section,
                    jump_points=parse_float(m.group('pts')) if m.group('pts') else None,
                    jump_rank=parse_int(m.group('jrank')) if m.group('jrank') else None,
                    time_difference=m.group('diff'),
                ))
                continue
            if current is not None and expect == 2:
                m = _SECTION_BIB_RE.match(line)
                if m:
                    current.bib = int(m.group('bib'))
                    current.time_difference = m.group('diff')
                    expect = 3
                    continue
            if current is not None and expect in (2, 3):
                m = _SECTION_CLUB_RE.match(line)
                if m:
                    _set_club(current, m.group('club'))
                    current.date_of_birth = normalise_date(m.group('dob'))
                    current.jump_rank = parse_int(m.group('jrank')) if m.group('jrank') else None
                    close()
                    continue
            m = _SECTION_NAME_RE.match(line)
            if m:
                close()
                current = CombinedResult(
                    name=clean_name(m.group('name')),
                    nation=m.group('nat') if m.group('nat').isalpha() else None,
                    status=section,
                    jump_points=parse_float(m.group('pts')) if m.group('pts') else None)
                expect = 2
                continue
            unparsed.append(line)
        # A page break never splits an athlete block
        close()

    # A photo finish for first place prints the total time on both lines
    # instead of a gap for the second athlete.
    winner_total = next((r.time_behind for r in results if r.rank == 1), None)
    for r in results:
        if r.rank and r.rank > 1 and winner_total and r.time_behind == winner_total:
            r.time_behind = '+0.0'
    return results, stats, unparsed


def _fill_row3(cr: CombinedResult, m: 're.Match') -> None:
    cr.bib = int(m.group('bib'))
    _set_club(cr, m.group('club'))
    if m.group('dob'):
        cr.date_of_birth = normalise_date(m.group('dob'))
    cr.jump_rank = parse_int(m.group('jrank')) if m.group('jrank') else None
    cr.xc_rank = parse_int(m.group('xcrank')) if m.group('xcrank') else None


def _set_club(cr: CombinedResult, club: Optional[str]) -> None:
    club = (club or '').strip()
    if cr.nation is None:
        # FIS-code variant: the nation is printed in front of the club
        cr.nation, club = _split_nation_club(club)
    cr.club = clean_name(club) if club else None
