"""
Parser for result lists produced by K-Jump, the Norwegian timing service
(Continental Cup Lillehammer 2022/23 and 2025/26).

Each athlete occupies a block around one line of numbers:

    Kasper Moen Flatla                     NOR
    2   5              Kollenhopp          122.0   5   0:12   23:56.9  14      0.5
    IL Jardar                              1999

Name and club share the first column and are centred vertically on the
number line, so the name sits above it when there is a club, *on* it when
there is none, and two lines above when the club wraps.  Text order is
therefore useless here; the block is rebuilt from word positions:

    x: rank | bib | name / club | team | nation / birth | jumping … cross-country
    y: every word belongs to the nearest number line

Names are printed 'Firstname Surname' in mixed case.  They are returned as
printed (ParsedDocument.name_order = 'given-first'); matching them to the
'SURNAME Firstname' spelling of all other lists is the loader's job.
"""
import re
from typing import Dict, List, Optional, Tuple

from fis_parser.models import CombinedResult, CompetitorStats
from fis_parser.utils import parse_float, parse_int

_STATUS = ('DNS', 'DNF', 'DSQ', 'NPS', 'LAP')
_TIME_RE = re.compile(r'^\d{1,2}:\d{2}(?:\.\d)?$')


def is_kjump_layout(full_text: str) -> bool:
    return bool(re.search(r'K-Jump\s+Page\s+\d', full_text)
                and re.search(r'Rank\s+Bib\s+Name\s+Team\s+Nation\s+Jumping', full_text))


def _lines(words: List[dict], tol: float = 2.0) -> List[List[dict]]:
    """Words grouped into lines by their vertical position."""
    lines: List[List[dict]] = []
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if lines and abs(w['top'] - lines[-1][0]['top']) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w['x0']) for line in lines]


def _columns(lines: List[List[dict]]) -> Optional[Tuple[float, Dict[str, float]]]:
    """(y of the table header, x where each column starts) or None if the page has no table."""
    for line in lines:
        text = [w['text'] for w in line]
        if text[:5] == ['Rank', 'Bib', 'Name', 'Team', 'Nation']:
            x = {w['text']: w['x0'] for w in line[:6]}
            return line[0]['top'], {
                'bib': x['Bib'] - 6, 'name': x['Name'] - 3, 'team': x['Team'] - 3,
                # nation codes and birth dates are right-aligned under 'Nation'
                'nation': x['Nation'] - 22, 'numbers': x.get('Jumping', x['Nation'] + 63) - 32,
            }
    return None


def _iso_date(token: str) -> Optional[str]:
    m = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', token)        # US order: 04/20/2002
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None


def parse_kjump_rof(pdf) -> Tuple[List[CombinedResult], Optional[CompetitorStats], List[str]]:
    """Returns (results, statistics if printed, notes about blocks that could not be read)."""
    results: List[CombinedResult] = []
    problems: List[str] = []
    stats: Optional[CompetitorStats] = None

    for page in pdf.pages:
        lines = _lines(page.extract_words())
        found = _columns(lines)
        if not found:
            continue
        header_y, col = found

        # The table ends at 'Number of athletes: 57'; the statistics follow
        end_y = page.height
        for i, line in enumerate(lines):
            text = ' '.join(w['text'] for w in line)
            if text.startswith('Number of athletes') or re.search(r'K-Jump\s+Page', text):
                end_y = min(end_y, line[0]['top'])
            if re.search(r'Total\s+Started\s+Results', text) and i + 1 < len(lines):
                fr = re.findall(r'(\d+)\s*/\s*(\d+)', ' '.join(w['text'] for w in lines[i + 1]))
                if len(fr) >= 3:
                    stats = CompetitorStats(
                        entries_athletes=int(fr[0][0]), entries_nations=int(fr[0][1]),
                        ranked_athletes=int(fr[2][0]), ranked_nations=int(fr[2][1]))

        body = [w for line in lines for w in line if header_y + 15 < w['top'] < end_y - 1]
        # A number line starts with the rank (or DNS / DNF / DSQ) in the first column
        anchors = [w for w in body if w['x0'] < col['bib'] and
                   (w['text'].isdigit() or w['text'] in _STATUS)]
        if not anchors:
            continue
        blocks: Dict[int, List[dict]] = {i: [] for i in range(len(anchors))}
        for w in body:
            nearest = min(range(len(anchors)), key=lambda i: abs(anchors[i]['top'] - w['top']))
            blocks[nearest].append(w)

        for i, anchor in enumerate(anchors):
            row = _read_block(anchor, blocks[i], col)
            if row is None:
                problems.append("block not understood: " +
                                ' '.join(w['text'] for w in sorted(blocks[i], key=lambda w: (w['top'], w['x0']))))
            else:
                results.append(row)
    return results, stats, problems


def _read_block(anchor: dict, words: List[dict], col: Dict[str, float]) -> Optional[CombinedResult]:
    y0 = anchor['top']
    on_line = lambda w: abs(w['top'] - y0) <= 2.0

    cr = CombinedResult()
    if anchor['text'] in _STATUS:
        cr.status = anchor['text']
    else:
        cr.rank = int(anchor['text'])

    bib = [w for w in words if on_line(w) and col['bib'] <= w['x0'] < col['name'] and w['text'].isdigit()]
    cr.bib = int(bib[0]['text']) if bib else None

    # First column: name first, then the club (one or two lines)
    first_col = _lines([w for w in words if col['name'] <= w['x0'] < col['team']])
    if not first_col:
        return None
    cr.name = ' '.join(w['text'] for w in first_col[0])
    club = ' '.join(w['text'] for line in first_col[1:] for w in line)
    cr.club = club or None

    for w in words:
        if not (col['nation'] <= w['x0'] < col['numbers']):
            continue
        if re.fullmatch(r'[A-Z]{3}', w['text']):
            cr.nation = w['text']
        elif _iso_date(w['text']):
            cr.date_of_birth = _iso_date(w['text'])
        # a bare year ('2000') is not a date of birth — dropped

    nums = [w['text'] for w in sorted(words, key=lambda w: w['x0'])
            if on_line(w) and w['x0'] >= col['numbers'] and w['text'] not in _STATUS]
    if '**' in nums:
        cr.wave_start = True
        nums = [n for n in nums if n != '**']
    if len(nums) >= 3:
        cr.jump_points = parse_float(nums[0])
        cr.jump_rank = parse_int(nums[1])
        cr.time_difference = nums[2]
    if len(nums) >= 6 and _TIME_RE.match(nums[3]):
        cr.xc_time = nums[3]
        cr.xc_rank = parse_int(nums[4])
        # the winner's gap is printed as '0.0'; everyone else's as m:ss.t or s.t
        cr.time_behind = nums[5] if cr.rank == 1 else '+' + nums[5]
    return cr
