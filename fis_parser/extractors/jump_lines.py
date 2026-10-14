"""
Line parser for jump lists with judges' marks (RL, RL1, RLQ, PCR).

The lists come in some sixty column layouts, but a jump always prints as

    [speed] distance dist-points  A B C D E  style-points  [gate [gate-pts] wind wind-pts]  [round total] ...

and the style points are the sum of the three middle marks.  That makes the
five marks an anchor that can be verified: the values left and right of it
are assigned from there, independent of the layout.  What surrounds the jump
(rank, bib, name, nation, club, date of birth, total, time difference) is
spread over one to three lines per athlete and collected per block:

    RIIBER Jarl Magnus NOR 119.5                      name line (optional)
    1. 28 84.3 98.5 77.0 16.5 ... 52.5 24 1.56 -10.0  rank line — starts every block
    Il Heming 15 OCT 1997 00:00                       club line

Lists with two jumps per athlete (World Cup until 2008/09, later the last
day of the Seefeld Triple) print the first jump on the name line and the
second on the club line.
"""
import re
from collections import Counter
from typing import List, Optional, Tuple

from fis_parser.models import JumpRound
from fis_parser.utils import clean_name, normalise_date

_MARK = r'(?:20\.0|1?\d\.[05])'
# five marks and the style points; the marks may be printed without a gap
_JUDGES_RE = re.compile(r'(?<![\d.:])(?=((?:' + _MARK + r'\s*){5})\s*(\d{1,2}\.[05])(?![\d.]))')
# 2020/21: three judges, all marks count
_JUDGES3_RE = re.compile(r'(?<![\d.:])(?=((?:' + _MARK + r'\s+){3})(\d{1,2}\.[05])(?![\d.]))')
_MARK_RE = re.compile(_MARK)
_LEFT_NUMS_RE = re.compile(r'(?<![\d.:])((?:-?\d{1,3}\.\d{1,2}\s+){1,4})$')
_RANK_RE = re.compile(r'^=?(\d{1,3})\.(?=\s|$)')
_RANK_NO_DOT_RE = re.compile(r'^(\d{1,3})(?=\s+\d{1,3}\s+(?:\D.*?\s)?\d{2,3}\.\d\s)')   # K-Jump lists
_DOB_RE = re.compile(r'\b(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|\d{2}\.\d{2}\.\d{4}|\d{2}/\d{2}/\d{4})\b')
_TIME_RE = re.compile(r'^\+?\d{1,2}:\d{2}$')
# '21', '08.5', '(cr)20', '©15/16', and a gate changed on the coach's request: '17→©16'
_GATE_RE = re.compile(r'^(?:\(cr\)|\*|©)?(\d{1,2}(?:\.\d)?)(?:/\d{1,2}|[→➔]©?(\d{1,2}))?$')
_GATE_LIKE_RE = re.compile(r'^(?:(?:\(cr\)|\*|©)?\d{1,2}(?:/\d{1,2}|[→➔]©?\d{1,2})?|(?:\(cr\)|\*|©)?0\d\.\d)$')
_WIND_RE = re.compile(r'^-?\d\.\d\d$')
_DEC_RE = re.compile(r'^-?\d{1,3}\.\d$')
_TOTAL_RE = re.compile(r'^-?\d{1,3}\.\d{1,2}$')
_ROUND_RANK_RE = re.compile(r'^=?\d{1,3}\.$')
_NSA_RE = re.compile(r'^[A-Z]{3}$')
_VALUE_TOKEN_RE = re.compile(r'^(?:[-+]?\d[\d.:]*|\d+\.-?[\d.]+|Q|q|nq|NQ|\(cr\)\d+(?:/\d+)?|\*\d+)$')

_UNMARKED_JUMP_RE = re.compile(
    r'(?<![\d.:])(\d{2,3}\.\d)\s+(\d{2,3}\.\d)\s+(-?\d{1,3}\.\d)\s+(?:(-\d{1,2}\.\d)\s+)?(-?\d{1,3}\.\d)\s+=?\d{1,3}\.(?!\d)')
# mixed teams: 'KORHONEN Minja (F)'
_GENDER_RE = re.compile(r'\s*\([FMW]\)(?=\s|$)')
# 'bib-leg' starts the row of a team member: '9-2 88.9 99.0 ...'
_MEMBER_RE = re.compile(r'^(\d{1,3})-(\d)(?=\s|$)')

_HEADER_RE = re.compile(r'\bA\s+B\s+C\s+D\s+E\b|\[km/h\]\s*\[m\]\s*Points\s+Points\s+R(?:an)?k\b')
_HEADER_WORDS = {
    'rank', 'bib', 'name', 'nat', 'nsa', 'noc', 'club', 'code', 'time', 'diff.', 'diff', 'difference',
    'points', 'qual', 'total', 'round', 'behind', 'date', 'of', 'birth', 'birthdate', 'pts', 'rk',
}
_FOOTER_RE = re.compile(
    r'^(?:printed\b|print\s+date|legend\b|weather\b|statistics\b|competitors\b|data\s+(?:service|processing)|'
    r'www\.|page\s+\d|report\s+created|timing\b|fis\s+data|official\s+results|jump\s+statistics|'
    r'remarks?\b|notes?\b|\(cr\)|©|nc\d{2}|sj[mw]\d|_\w+\s|jury\b|competition\s*/|weather\s+information|'
    r'base\s+values|visit\s+fis|number\s+of\s+athletes|competition\s+management|race\s+director)',
    re.IGNORECASE)
# headings of the lists that follow the ranking
_SECTIONS = (
    ('dns', re.compile(r'^(?:did\s+not\s+start|not\s+started|not\s+permitted\s+to\s+start)\b', re.IGNORECASE)),
    ('dsq', re.compile(r'^disqualified\b', re.IGNORECASE)),
    ('dnf', re.compile(r'^did\s+not\s+finish\b', re.IGNORECASE)),
    ('skip', re.compile(r'^reason\s+for\b', re.IGNORECASE)),
)
_SUBHEADING_RE = re.compile(r'^not\s+qualified\b', re.IGNORECASE)      # the ranking goes on below it
_UNRANKED_ROW_RE = re.compile(r'^(?:DNS|DSQ|DNF|NPS)?\s*(\d{1,3})\s*([^\W\d_].*)$')
# K-Jump lists the athletes without a result among the ranked: 'DNS 12 DNS'
_STATUS_ROW_RE = re.compile(r'^(DNS|DSQ)\s+(\d{1,3})\b(.*?)(?:\s+(?:DNS|DSQ))?$')


def has_judges_layout(pages: List[List[str]]) -> bool:
    return any(_HEADER_RE.search(line) for lines in pages for line in lines[:40])


def _section_of(line: str) -> Optional[str]:
    return next((kind for kind, pattern in _SECTIONS if pattern.match(line)), None)


def _data_lines(lines: List[str]) -> Tuple[List[str], bool]:
    """The lines of a page between the column header and the footer; whether wind is a column."""
    start = next((i for i, line in enumerate(lines) if _HEADER_RE.search(line)), None)
    if start is None:
        # a page that only continues the lists after the ranking
        start = next((i for i, line in enumerate(lines) if _section_of(line.strip())), None)
        if start is None:
            return [], False
        start -= 1
    has_wind = any('m/s' in line for line in lines[max(0, start - 3):start + 3])
    start += 1
    while start < len(lines) and lines[start].strip() \
            and all(w.lower() in _HEADER_WORDS for w in lines[start].split()):
        start += 1
    out = []
    for line in lines[start:]:
        line = line.strip()
        if _FOOTER_RE.match(line):
            break
        if line:
            out.append(line)
    return out, has_wind


def _find_jump(line: str, hill: Optional[Tuple[float, float]] = None) -> Optional[Tuple[dict, str, List[str]]]:
    """(jump values, text left of the jump, tokens right of it) or None."""
    found = None
    for m in _JUDGES_RE.finditer(line):
        marks = [float(x) for x in _MARK_RE.findall(m.group(1))][:5]
        if abs(sum(marks) - min(marks) - max(marks) - float(m.group(2))) < 0.01:
            found = (m, marks)
            break
    if found is None:
        m = _JUDGES_RE.search(line)
        if m:
            # marks that do not add up as printed: take them as they are
            found = (m, [float(x) for x in _MARK_RE.findall(m.group(1))][:5])
    if found is None:
        for m in _JUDGES3_RE.finditer(line):
            marks = [float(x) for x in _MARK_RE.findall(m.group(1))][:3]
            if abs(sum(marks) - float(m.group(2))) < 0.01:
                found = (m, marks)
                break
    if found is None:
        return _find_unmarked_jump(line)

    m, marks = found
    left, right = line[:m.start()], line[m.end(2):]
    jump = dict(zip(('judge_a', 'judge_b', 'judge_c', 'judge_d', 'judge_e'), marks))
    jump['style_points'] = float(m.group(2))
    nums = _LEFT_NUMS_RE.search(left)
    if nums:
        values = [float(x) for x in nums.group(1).split()]
        left = left[:nums.start()]
        if len(values) == 2 and hill and not _fits_hill(values[0], values[1], hill) and values[0] > values[1]:
            # the distance points are blank: speed and distance
            jump['speed_kmh'], jump['distance_m'] = values
        else:
            jump['dist_points'] = values[-1]
            if len(values) >= 2:
                jump['distance_m'] = values[-2]
            # tours print the points taken along from the day before in front of the speed
            if len(values) == 4:
                jump['carry'] = values[0]
            if len(values) >= 3:
                if values[-3] >= 60:
                    jump['speed_kmh'] = values[-3]
                elif len(values) == 3:
                    jump['carry'] = values[0]
    return jump, left.strip(), right.split()


def _find_unmarked_jump(line: str) -> Optional[Tuple[dict, str, List[str]]]:
    """Mass start until 2008/09: no marks, 'speed distance dist-points [faults] round-points rank.'"""
    for m in _UNMARKED_JUMP_RE.finditer(line):
        speed, distance, points, faults, total = (float(x) if x else None for x in m.groups())
        if abs(points + (faults or 0) - total) < 0.11:
            jump = {'speed_kmh': speed, 'distance_m': distance, 'dist_points': points, 'total_points': total}
            return jump, line[:m.start()].strip(), line[m.end():].split()
    return None


def _fits_hill(distance: float, points: float, hill: Tuple[float, float]) -> bool:
    k_point, meter_value = hill
    base = 120 if k_point >= 170 else 60
    return abs(base + (distance - k_point) * meter_value - points) < 0.11


def _gate(token: str):
    m = _GATE_RE.match(token)
    value = float(m.group(2) or m.group(1))
    return int(value) if value == int(value) else value


def _read_tail(tokens: List[str], jump: dict, has_wind: bool) -> List[float]:
    """Assign gate, wind and time from the value tokens around a jump; return the remaining totals."""
    values: List[str] = []
    for tok in tokens:
        if _TIME_RE.match(tok):
            jump.setdefault('time', tok)
        elif _ROUND_RANK_RE.match(tok):
            continue
        elif _TOTAL_RE.match(tok) or _GATE_RE.match(tok):
            values.append(tok)

    if has_wind:
        wind_at = next((i for i, v in enumerate(values) if _WIND_RE.match(v)), None)
        if wind_at is not None:
            before, after = values[:wind_at], values[wind_at + 1:]
            jump['wind_ms'] = float(values[wind_at])
            if after and _DEC_RE.match(after[0]):
                jump['wind_comp_pts'] = float(after.pop(0))
            if before:
                if _GATE_LIKE_RE.match(before[-1]) \
                        or (len(before) == 1 and _GATE_RE.match(before[0]) and float(_GATE_RE.match(before[0]).group(1)) < 60):
                    jump['gate'] = _gate(before.pop())
                elif len(before) >= 2 and _GATE_LIKE_RE.match(before[-2]) and _DEC_RE.match(before[-1]):
                    jump['gate_comp_pts'] = float(before.pop())
                    jump['gate'] = _gate(before.pop())
            values = before + after
        elif values and _GATE_LIKE_RE.match(values[0]):
            jump['gate'] = _gate(values.pop(0))
    return [float(v) for v in values if _TOTAL_RE.match(v)]


def _set_total(jump: dict, candidates: List[float]) -> None:
    """The points of the jump among the totals printed (tours also print running totals)."""
    if not candidates or 'style_points' not in jump:
        return
    jump['total_points'] = candidates[0]
    if jump.get('dist_points') is None:
        return
    expected = jump['dist_points'] + jump['style_points'] \
        + jump.get('gate_comp_pts', 0) + jump.get('wind_comp_pts', 0)
    for c in candidates:
        if abs(c - expected) < 0.11:
            jump['total_points'] = c
            return
    carry = jump.get('carry')
    if carry is not None:
        for c in candidates:
            if abs(c - carry - expected) < 0.11:
                jump['total_points'] = round(c - carry, 1)
                return


def _split_name(text: str) -> Tuple[str, Optional[str]]:
    """'RIIBER Jarl Magnus NOR' → ('RIIBER Jarl Magnus', 'NOR'); 'KORHONEN Minja (F)' → ('KORHONEN Minja', None)."""
    words = [w for w in _GENDER_RE.sub('', text).split() if re.search(r'[^\W\d_]', w)]
    if len(words) >= 3 and _NSA_RE.match(words[-1]):
        return ' '.join(words[:-1]), words[-1]
    if len(words) == 1 and _NSA_RE.match(words[0]):
        return '', words[0]
    return ' '.join(words), None


def _strip_values(text: str) -> Tuple[str, List[str]]:
    """Split trailing value tokens (totals, times, ranks) off a text."""
    words = text.split()
    tail: List[str] = []
    while words and _VALUE_TOKEN_RE.match(words[-1]):
        tail.insert(0, words.pop())
    return ' '.join(words), tail


def _date(text: str) -> Optional[str]:
    us = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', text)           # K-Jump prints month/day/year
    if us:
        return f'{us.group(3)}-{us.group(1)}-{us.group(2)}'
    return normalise_date(text)


class _Block:
    def __init__(self, rank: Optional[int], rest: str, status: Optional[str] = None):
        self.pre: Optional[str] = None
        self.rank = rank
        self.rest = rest            # the rank line without the rank
        self.status = status
        self.nation: Optional[str] = None       # team lists: the nation of the team
        self.reason: Optional[str] = None       # disqualified team member
        self.post: List[str] = []


def _blocks(lines: List[str], unread: Optional[List[str]] = None) -> List[_Block]:
    """
    One block per athlete.  In a team list the blocks are the members
    ('9-2 ...'); the line of the team ('1. 9 GER - GERMANY 473.9') gives
    them rank and nation.
    """
    dotted = any(_RANK_RE.match(line) for line in lines)
    rank_re = _RANK_RE if dotted else _RANK_NO_DOT_RE
    team_list = any(_MEMBER_RE.match(line) for line in lines)
    team_rank = team_nation = team_state = None
    after_team_line = False
    blocks: List[_Block] = []
    pending: List[str] = []
    for line in lines:
        m = rank_re.match(line)
        if team_list:
            member = _MEMBER_RE.match(line)
            team_status = None if m or member else re.match(r'^(DSQ|DNS|DNF)\s+\d{1,3}\s', line)
            if m or team_status:
                # the team: the lines before it end the last member of the team above
                team_rank = int(m.group(1)) if m else None
                team_state = team_status.group(1) if team_status else None
                # 'GER - GERMANY', 'Germany III (GER)'; a mixed team 'FIS - FIN/SUI' has none
                nation = re.search(r'\(([A-Z]{3})\)', line) \
                    or re.search(r'\b(?!III\b)([A-Z]{3})\b', line[(m or team_status).end():])
                team_nation = nation.group(1) if nation and nation.group(1) != 'FIS' else None
                if blocks and not after_team_line:
                    blocks[-1].post = pending
                pending, after_team_line = [], True
                continue
            if not member:
                pending.append(line)
                continue
            rest = re.sub(r'^[FMW]\s+(?=[\d-]|DSQ|DNS)', '', line[member.end():].strip())     # '6-1 F 91.6 ...'
            status = re.match(r'^(DSQ|DNS)\b\s*(.*)$', rest)          # '16-2 DSQ ICR 4.2.2.2 0.0'
            if status:
                block = _Block(team_rank, member.group(1), status.group(1))
                block.reason = re.sub(r'\s+0\.0$', '', status.group(2)) or None
            else:
                block = _Block(team_rank, f'{member.group(1)} {rest}')
            block.nation = team_nation
            if team_state and not block.status:
                block.status = team_state if team_state != 'DNF' else None
        else:
            status = None if m or dotted else _STATUS_ROW_RE.match(line)
            if m:
                block = _Block(int(m.group(1)), line[m.end():].strip())
            elif status:
                block = _Block(None, f'{status.group(2)} {status.group(3).strip()}', status.group(1))
            else:
                pending.append(line)
                continue
        found = _find_jump(block.rest)
        text = re.sub(r'^\d{1,3}\b\s*', '', found[1] if found else block.rest)
        name, nation = _split_name(_strip_values(text)[0])
        if _DOB_RE.search(text):
            name = ''               # the club line, printed so close that it reads as part of the rank line
        # The line above belongs to this athlete if it is the name line, the nation alone
        # (K-Jump, if the name is on the rank line) or the first of two jumps.
        # Mixed teams print the club on the member's line, the name above it.
        if pending and (not name or (nation is None and _NSA_RE.match(pending[-1]))
                        or (not found and _find_jump(pending[-1]))
                        or (block.nation and _GENDER_RE.search(pending[-1]))):
            block.pre = pending.pop()
        if blocks and not after_team_line:
            blocks[-1].post = pending
        elif unread is not None and not after_team_line:
            unread.extend(pending)
        pending, after_team_line = [], False
        blocks.append(block)
    if blocks:
        # the last block: as many lines as the others have
        usual = Counter(len(b.post) for b in blocks[:-1]).most_common(1)
        n = usual[0][0] if usual else 1
        blocks[-1].post = pending[:n]
        pending = pending[n:]
    if unread is not None:
        unread.extend(pending)
    return blocks


def _rows_of(block: _Block, has_wind: bool, hill: Optional[Tuple[float, float]]) -> List[JumpRound]:
    jumps: List[Tuple[dict, List[float]]] = []
    leftovers: List[str] = []      # value tokens outside the jump lines
    texts = {'post': []}
    for key, line in [('pre', block.pre), ('anchor', block.rest)] + [('post', p) for p in block.post]:
        if line is None:
            continue
        found = _find_jump(line, hill)
        if found:
            jump, text, tail = found
            jumps.append((jump, _read_tail(tail, jump, has_wind)))
        else:
            text = line
        if key == 'post':
            texts['post'].append(text)
        else:
            texts[key] = text

    anchor_text = texts['anchor']
    bib = None
    bib_m = re.match(r'^(\d{1,3})\b\s*', anchor_text)
    if bib_m:
        bib = int(bib_m.group(1))
        anchor_text = anchor_text[bib_m.end():]
    if _DOB_RE.search(anchor_text):
        texts['post'].insert(0, anchor_text)        # club and date of birth, see _blocks
        anchor_text = ''
    anchor_text, tail = _strip_values(anchor_text)
    leftovers += tail

    name, nation = _split_name(anchor_text)
    if block.pre is not None:
        pre_text, tail = _strip_values(texts['pre'])
        leftovers += tail
        pre_name, pre_nation = _split_name(pre_text)
        if pre_name and name and block.nation:
            texts['post'].insert(0, name)               # team member: the club on the member's line
        name = pre_name or name
        nation = pre_nation or nation

    club = dob = None
    for text in texts['post']:
        dob_m = _DOB_RE.search(text)
        after = ''
        if dob_m:
            dob = _date(dob_m.group(1))
            text, after = text[:dob_m.start()], text[dob_m.end():]
        text, tail = _strip_values(text)
        leftovers += tail + after.split()
        if bib is None:
            bib_m = re.match(r'^(\d{1,3})\s+(?=\D)', text)
            if bib_m:
                bib = int(bib_m.group(1))
                text = text[bib_m.end():]
        nation_m = re.match(r'^([A-Z]{3})(?:,\s*|$)', text)        # 'AUT, SC St. Johann'
        if nation_m and nation is None:
            nation = nation_m.group(1)
            text = text[nation_m.end():]
        if text and club is None and re.search(r'[^\W\d_]', text):
            club = clean_name(text)

    # values printed apart from the jump line (total on the name line, time on the club line)
    extra: dict = {}
    extra_totals = _read_tail(leftovers, extra, has_wind)
    time = next((j['time'] for j, _ in jumps if 'time' in j), None) or extra.get('time')

    def new_row(number: int) -> JumpRound:
        return JumpRound(round_number=number, rank=block.rank, bib=bib, name=clean_name(name) or None,
                         nation=nation or block.nation, club=club, date_of_birth=dob,
                         dns=block.status == 'DNS', dsq=block.status == 'DSQ', dsq_reason=block.reason)

    rows = []
    for number, (jump, totals) in enumerate(jumps, start=1):
        if len(jumps) == 1:
            for key, value in extra.items():
                jump.setdefault(key, value)
            totals = totals + extra_totals
        _set_total(jump, totals)
        if 'speed_kmh' not in jump and totals and jump.get('distance_m', 0) > jump.get('dist_points', 0) \
                and abs(jump.get('style_points', 0) - jump['total_points']) < 0.01:
            # no distance points printed (they would be 0): the two values are speed and distance
            jump['speed_kmh'], jump['distance_m'] = jump['distance_m'], jump.pop('dist_points')
        row = new_row(number)
        row.pursuit_time_diff = time
        for key, value in jump.items():
            if key not in ('time', 'carry'):
                setattr(row, key, value)
        rows.append(row)
    return rows or [new_row(1)]


def parse_jump_lines(pages: List[List[str]], hill: Optional[Tuple[float, float]] = None,
                     unread: Optional[List[str]] = None) -> List[JumpRound]:
    """Rows of a jump list with judges' marks.

    ``pages`` holds the text lines of each page, ``hill`` the K-point and the
    meter value if known; lines that belong to no row are appended to ``unread``.
    """
    lines: List[str] = []
    unranked: List[JumpRound] = []
    has_wind = False
    section = 'ranked'
    previous = ''
    for page in pages:
        data, wind = _data_lines(page)
        has_wind = has_wind or wind
        for line in data:
            if _SUBHEADING_RE.match(line):
                continue
            heading = _section_of(line)
            section = heading or section
            if section == 'ranked':
                lines.append(line)
                continue
            row = None if heading else _unranked_row(line, section)
            if row:
                # 'Did not finish': the one jump made is printed on the line above
                found = _find_jump(previous, hill) if section == 'dnf' else None
                if found:
                    jump, _, tail = found
                    _set_total(jump, _read_tail(tail, jump, has_wind))
                    for key, value in jump.items():
                        if key not in ('time', 'carry'):
                            setattr(row, key, value)
                unranked.append(row)
            elif unread is not None and not heading and not _find_jump(line):
                unread.append(line)
            previous = line
    rows: List[JumpRound] = []
    for block in _blocks(lines, unread):
        rows.extend(_rows_of(block, has_wind, hill))
    return rows + unranked


def _unranked_row(line: str, section: str) -> Optional[JumpRound]:
    """'16 PITTIN Alessandro ITA SCE 4' below 'Disqualified' or 'Did not start'."""
    m = _UNRANKED_ROW_RE.match(line)
    if not m or section == 'skip':
        return None
    words = re.sub(r'^[A-Z]{3} - ', '', m.group(2)).split()       # '27 JPN - NAGAI Hideaki JPN SCE 4'
    name: List[str] = []
    nation = None
    while words:
        word = words[0].rstrip(',')
        glued = re.match(r'^([A-Z]{3})(SCE|ICR)$', word)          # 'FINSCE 4 (Suit)'
        if glued:
            word, words[0] = glued.group(1), glued.group(2)
        elif re.search(r'\d', word) or word in ('SCE', 'ICR'):
            break
        else:
            words.pop(0)
        if word in ('NPS', 'DNS', 'DSQ'):
            break                                       # '8 GARBAJS Matic NPS - SCE4 Suit'
        if len(name) >= 2 and _NSA_RE.match(word):
            nation = word
            break
        name.append(word)
    if len(name) < 2:
        return None
    row = JumpRound(round_number=1, bib=int(m.group(1)), name=clean_name(' '.join(name)), nation=nation)
    if section == 'dsq':
        row.dsq = True
        row.dsq_reason = ' '.join(words) or None
    elif section == 'dns':
        row.dns = True
    return row
