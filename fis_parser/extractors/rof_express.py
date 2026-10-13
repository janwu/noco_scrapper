"""
Line-based parser for the Express Race (Continental Cup 2025/26, ewoxx).

After the jump the field races short knock-out heats; only the best of a
heat go on to the next.  The list prints, per athlete, the race time and
the total of every heat he took part in:

    DOLEZAL Lukas CZE 122.5 3:06.1 +5.2 2:59.7. +2.0 3:03.1 3:06.1 3:02.4 +0.5
    2. 3 00:06
    Dukla Liberec 21 FEB 2006 3. 33. 2. 8. 2. 10. 1. 5. 2.

    name, nation, jump points, then per heat: race time, total (the heat
        leader's total time, or the gap to him)
    rank, bib, start gap after the jump
    club, birth date, jump rank, per heat: race rank and position, final rank

What is stored of the heats is the last one the athlete raced:
    xc_time       his race time in that heat
    time_behind   his gap to the leader of that heat — the winner's total time
                  for the winner.  Only athletes who reached the final have a
                  gap to the winner; for the others it is the gap in the heat
                  that eliminated them.
    xc_rank       not stored: the ranks are per heat and do not compare
"""
import re
from typing import List, Optional, Tuple

from fis_parser.models import CombinedResult
from fis_parser.utils import parse_float, normalise_date, clean_name

_NAME = r"(?P<name>[^\W\d_a-z][^\d]*?)"
_TIME = r'\d{1,2}:\d{2}\.\d'
_DOB_RE = re.compile(r'\b(\d{1,2}\s+[A-Z]{3}\s+\d{4})\b')

_NAME_LINE_RE = re.compile(
    r'^' + _NAME + r'\s+(?P<nat>[A-Z]{3})\s+(?P<pts>-?\d+\.\d)(?P<heats>(?:\s+\+?[\d:]+\.\d\.?)+)'
    r'(?:\s+(?:DNS|DNF|DSQ))?$')        # did not start in the next heat — still ranked
_RANK_LINE_RE = re.compile(r'^(?P<rank>\d+)\.\s+(?P<bib>\d+)(?:\s+(?P<diff>\d{1,2}:\d{2}))?$')
_SECTION_RE = re.compile(
    r'^(?:(?P<dns>Did\s+not\s+start|Not\s+permitted\s+to\s+start)'
    r'|(?P<dnf>Did\s+not\s+finish)|(?P<dsq>Disqualified))\b', re.IGNORECASE)
_SECTION_ROW_RE = re.compile(r'^(?:(?P<bib>\d+)\s+)?' + _NAME + r'\s+(?P<nat>[A-Z]{3})\b')
_END_RE = re.compile(r'^(?:Jury\b|Weather\b|Temperatures?\b|Competition\s+Management)', re.IGNORECASE)
_SKIP_RE = re.compile(
    r'^(?:Heat\s+\d|Ski\s+Jumping\s+Heat|Name\s+NSA|Rank\s+Bib|Club\s+Date\s+of\s+Birth)'
    r'|Timing\s+and\s+Data|Report\s+Created|^\d{1,2}\s+[A-Z]{3}\s+\d{4}\s*/', re.IGNORECASE)


def is_express_layout(text: str) -> bool:
    return bool(re.search(r'Ski\s+Jumping\s+Heat\s+1\s+Heat\s+2', text[:3000]))


def parse_express_rof(pages: List[List[str]]) -> Tuple[List[CombinedResult], List[str]]:
    """Returns (results, lines of the result list that could not be read)."""
    results: List[CombinedResult] = []
    unparsed: List[str] = []
    section: Optional[str] = None
    current: Optional[CombinedResult] = None       # athlete whose block is being read
    expect = 0                                     # 2 = rank line, 3 = club line
    finished = False

    for lines in pages:
        if finished:
            break
        in_table = False
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if line.startswith('Ski Jumping Heat'):
                in_table = True
            if not in_table or _SKIP_RE.search(line):
                continue
            if _END_RE.match(line):
                finished = bool(results)
                break
            sec = _SECTION_RE.match(line)
            if sec:
                section = 'DNS' if sec.group('dns') else 'DNF' if sec.group('dnf') else 'DSQ'
                current, expect = None, 0
                continue
            if section:
                m = _SECTION_ROW_RE.match(line)
                if m:
                    results.append(CombinedResult(
                        bib=int(m.group('bib')) if m.group('bib') else None,
                        name=clean_name(m.group('name')), nation=m.group('nat'), status=section))
                continue

            m = _NAME_LINE_RE.match(line)
            if m:
                current = _from_name_line(m)
                results.append(current)
                expect = 2
                continue
            m = _RANK_LINE_RE.match(line)
            if m and current is not None and expect == 2:
                current.rank, current.bib = int(m.group('rank')), int(m.group('bib'))
                current.time_difference = m.group('diff')
                expect = 3
                continue
            if current is not None and expect == 3:
                dob = _DOB_RE.search(line)
                ranks = re.findall(r'(\d+)\.(?=\s|$)', line[dob.end():] if dob else line)
                if dob:
                    current.date_of_birth = normalise_date(dob.group(1))
                    current.club = clean_name(line[:dob.start()]) or None
                if ranks:
                    current.jump_rank = int(ranks[0])
                    expect = 0
                    continue
            unparsed.append(line)
    return results, unparsed


def _from_name_line(m: 're.Match') -> CombinedResult:
    cr = CombinedResult(name=clean_name(m.group('name')), nation=m.group('nat'),
                        jump_points=parse_float(m.group('pts')))
    values = [v.rstrip('.') if v.count('.') > 1 else v for v in m.group('heats').split()]
    # pairs of (race time, total); the last pair is the athlete's last heat
    if len(values) >= 2 and len(values) % 2 == 0:
        cr.xc_time, cr.time_behind = values[-2], values[-1]
    return cr
