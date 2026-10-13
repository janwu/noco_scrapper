"""
Line-based parser for result lists of the formats that end with the jump:
Mass Start and Super Sprint.  The race comes first, its gaps are converted
into points, the jumping round is added, and the list is ranked by total
points — so the columns are those of a jump list with the race in front.

Three families of layouts:

Modern (Swiss Timing and ewoxx since 2018/19)
    RIIBER Jarl Magnus NOR 23:46.6 156.0 154.3        name, nation, race time, [round points, [total]]
    2. 51 88.5 134.5 86.1 17.5 … 53.0 17 21.6 0.40 -4.7     rank, bib, jump details
    Il Heming 15 OCT 1997 10.-1.7 2. -1.1             club, birth date, race rank, race points gap, jump rank, [behind]
  In 2025/26 club and birth date moved onto the second line and there is no third.
  The points behind the race time are the jumping round and, if there are
  two, the total.  With one or none, the last number of the jump details is
  the total (and with none the round is the total without the race gap).

Two jumping rounds (World Cup 2006/07 – 2008/09)
    KOIVURANTA Anssi FIN 88.6 96.0 72.0 72.0 1.       first round: speed, distance, points, round, rank
    2. 31 21:56.9 18. 117.7 146.0 263.7               rank, bib, race time, race rank, race points, jump points, total
    Kuusamon Erae-Veikot 3 JUL 1988 88.4 97.0 74.0 74.0 2.   club, birth date, second round

One round, race given in points only (Klingenthal 2008)
    ACKERMANN Ronny GER
    2. 30 112.0 94.9 134.5 71.4 71.4 3. 183.4         rank, bib, race points, speed, distance, points, round, rank, total

Stored the same way for all three (as the other parsers do for mass starts):
    xc_time / xc_rank   the race
    time_difference     race points gap to the best race ('0.0', '-1.7')
    jump_points / jump_rank   the jumping part (both rounds together)
    time_behind         total points gap to the winner ('0.0', '-1.1')
"""
import re
from typing import List, Optional, Tuple

from fis_parser.models import CombinedResult
from fis_parser.utils import parse_float, normalise_date, clean_name

_NAME = r"(?P<name>[^\W\d_a-z][^\d]*?)"
_CLOCK = r'\d{1,2}:\d{2}\.\d'
_NUM = r'[+-]?\d+(?:\.\d+)?'
_DOB_RE = re.compile(r'\b(\d{1,2}\s+[A-Z]{3}\s+\d{4})\b')

_NAME_LINE_RE = re.compile(r'^' + _NAME + r'\s+(?P<nat>[A-Z]{3})(?P<rest>(?:\s+\S+)*)$')
_RANK_LINE_RE = re.compile(r'^(?:(?:PF|FF)\s+)?(?P<rank>=?\d+)\.\s+(?P<bib>\d+)(?:\s+(?P<rest>.*))?$')
_SECTION_RE = re.compile(
    r'^(?:(?P<dns>Did\s+not\s+start|Not\s+permitted\s+to\s+start)'
    r'|(?P<dnf>Did\s+not\s+finish)|(?P<dsq>Disqualified))\b', re.IGNORECASE)
_SECTION_ROW_RE = re.compile(r'^(?:(?P<bib>\d+)\s+)?' + _NAME + r'\s+(?P<nat>[A-Z]{3})\b')
_HEADER_RE = re.compile(r'^(?:RANK|NAME)\b.*\b(?:NSA|NAT|BIB)', re.IGNORECASE)
# second and third line of the column header
_SUBHEADER_RE = re.compile(
    r'^(?:CLUB\s+(?:DATE\s+OF\s+BIRTH|Birthdate)|TOTAL$|Time\s+Rk\b|Points\s+Faults\b|Rank\s+Bib\b'
    r'|Points\s+per\s+minute)', re.IGNORECASE)
_END_RE = re.compile(
    r'^(?:Weather\b|Temperatures?\b|Statistics\b|Legend\b|Jury\b|Competition\s+(?:Management|/)'
    r'|Gate\s+Athletes|Technical\s+Delegate\b.*Chief)', re.IGNORECASE)
_FURNITURE_RE = re.compile(
    r'Timing\s+and\s+Data|Data\s+(?:Service|Provider|processing)|Report\s+Created|www\.|fis-ski'
    r'|\bPage\s*\d+\s*(?:/|of|from)\s*\d+|^printed\b|^\d{1,2}\s+[A-Z]{3}\s+\d{4}\s*/', re.IGNORECASE)


def is_jump_last_layout(text: str) -> bool:
    """True for the column headers of the three families described above."""
    head = text[:3000]
    return bool(
        re.search(r'RACE\s+TIME\s+SPEED\s+DISTANCE', head, re.IGNORECASE)                    # modern
        or re.search(r'Name\s+NSA\s+Time\s+Gate/Wind\s+Comp', head)                           # ewoxx 2021/22-
        or re.search(r'Speed\s+Distance\s+Distance\s+Round\s+Round', head))                   # 2006/07-2008/09


def _numbers(text: str) -> List[str]:
    """Number tokens of a line; 'N.' ranks keep their dot, '18.-2.4' is taken apart."""
    text = re.sub(r'(\d\.)(-)', r'\1 \2', text or '')
    return [t for t in text.split() if re.fullmatch(_NUM + r'\.?|' + _CLOCK, t)]


def _is_rank(token: str) -> bool:
    return bool(re.fullmatch(r'\d+\.', token))


def _points(tokens: List[str]) -> List[float]:
    return [float(t) for t in tokens if re.fullmatch(_NUM, t) and '.' in t]


def parse_jump_last_rof(pages: List[List[str]]) -> Tuple[List[CombinedResult], List[str]]:
    """Returns (results, lines of the result list that could not be read)."""
    blocks: List[dict] = []            # one per ranked athlete: name line, rank line, third line
    unranked: List[CombinedResult] = []
    unparsed: List[str] = []
    section: Optional[str] = None
    finished = False

    for lines in pages:
        if finished:
            break
        in_table = False
        pending_name = None
        for raw in lines:
            line = raw.strip()
            if not line or _FURNITURE_RE.search(line):
                continue
            if _HEADER_RE.match(line):
                in_table = True
                continue
            sec = _SECTION_RE.match(line)
            if sec and (in_table or blocks):
                section = 'DNS' if sec.group('dns') else 'DNF' if sec.group('dnf') else 'DSQ'
                in_table, pending_name = True, None
                continue
            if not in_table or _SUBHEADER_RE.match(line):
                continue
            if _END_RE.match(line):
                finished = bool(blocks)
                break

            if section:
                m = _SECTION_ROW_RE.match(line)
                if m:
                    unranked.append(CombinedResult(
                        bib=int(m.group('bib')) if m.group('bib') else None,
                        name=clean_name(m.group('name')), nation=m.group('nat'), status=section))
                # anything else under these headings is a club line or the reason
                continue

            m = _RANK_LINE_RE.match(line)
            if m and pending_name:
                blocks.append({'name': pending_name, 'rank': m, 'third': None})
                pending_name = None
                continue
            m = _NAME_LINE_RE.match(line)
            # a name line has no birth date; a club line with one belongs to the athlete above
            if m and not _DOB_RE.search(line) and m.group('name').split()[0].isupper():
                pending_name = m
                continue
            if blocks and blocks[-1]['third'] is None and pending_name is None:
                blocks[-1]['third'] = line
                continue
            unparsed.append(line)

    results = [_read_block(b) for b in blocks]
    _fill_gaps(results)
    return [r for r, _ in results] + unranked, unparsed


def _read_block(block: dict) -> Tuple[CombinedResult, dict]:
    """One athlete.  Returns the row and the raw points (race, total) for the gaps."""
    name, rank = block['name'], block['rank']
    cr = CombinedResult(
        rank=int(rank.group('rank').lstrip('=')), bib=int(rank.group('bib')),
        name=clean_name(name.group('name')), nation=name.group('nat'))
    raw = {'race_points': None, 'race_gap': None, 'total': None}

    head = _numbers(name.group('rest'))
    second = rank.group('rest') or ''
    third = block['third'] or ''

    # club and birth date: on the third line, or (2025/26) on the second
    carrier = third if _DOB_RE.search(third) or not _DOB_RE.search(second) else second
    dob = _DOB_RE.search(carrier)
    if dob:
        cr.date_of_birth = normalise_date(dob.group(1))
        cr.club = clean_name(carrier[:dob.start()]) or None
        after_dob = _numbers(carrier[dob.end():])
    else:
        cr.club = clean_name(re.sub(r'[\d.+:-]+\s*', ' ', carrier)) or None if carrier is third else None
        after_dob = _numbers(carrier)

    if head and re.fullmatch(_CLOCK, head[0]):
        # ── modern: race time on the name line ───────────────────────────────
        cr.xc_time = head[0]
        on_name = _points(head[1:])
        details = _numbers(second if carrier is third else carrier[dob.end():] if dob else '')
        if carrier is not third:
            # 2025/26: '7. -1.0 <jump details> 1. [behind]' all behind the birth date
            details = after_dob
        ranks = [t for t in after_dob if _is_rank(t)]
        if ranks:
            cr.xc_rank = int(ranks[0].rstrip('.'))
            if len(ranks) > 1:
                cr.jump_rank = int(ranks[-1].rstrip('.'))
        first_rank = next((i for i, t in enumerate(after_dob) if _is_rank(t)), None)
        if first_rank is not None and first_rank + 1 < len(after_dob) and not _is_rank(after_dob[first_rank + 1]):
            raw['race_gap'] = float(after_dob[first_rank + 1])
        jump_details = _points([t for t in details if not _is_rank(t)])
        if len(on_name) >= 2:
            cr.jump_points, raw['total'] = on_name[0], on_name[1]
        elif len(on_name) == 1:
            cr.jump_points = on_name[0]
            raw['total'] = jump_details[-1] if carrier is third and jump_details else None
        elif jump_details and carrier is third:
            # 2018/19: only the total is printed; the round is the total without the race gap
            raw['total'] = jump_details[-1]
            if raw['race_gap'] is not None:
                cr.jump_points = round(raw['total'] - raw['race_gap'], 1)
        if raw['total'] is None and cr.jump_points is not None and raw['race_gap'] is not None:
            raw['total'] = round(cr.jump_points + raw['race_gap'], 1)
    else:
        nums = _numbers(second)
        if nums and re.fullmatch(_CLOCK, nums[0]):
            # ── two rounds: 'time rank. race points, jump points, total' ────
            cr.xc_time = nums[0]
            if len(nums) > 1 and _is_rank(nums[1]):
                cr.xc_rank = int(nums[1].rstrip('.'))
            pts = _points(nums[1:])
            if len(pts) >= 3:
                raw['race_points'], cr.jump_points, raw['total'] = pts[-3], pts[-2], pts[-1]
        else:
            # ── race in points only: 'race points … round rank. total' ──────
            pts = _points(nums)
            ranks = [t for t in nums if _is_rank(t)]
            if len(pts) >= 3:
                raw['race_points'], cr.jump_points, raw['total'] = pts[0], pts[-2], pts[-1]
            if ranks:
                cr.jump_rank = int(ranks[-1].rstrip('.'))
    return cr, raw


def _fill_gaps(results: List[Tuple[CombinedResult, dict]]) -> None:
    """Race points gap and total gap, relative to the best race / the winner."""
    best_race = max((raw['race_points'] for _, raw in results if raw['race_points'] is not None), default=None)
    winner_total = next((raw['total'] for cr, raw in results if cr.rank == 1 and raw['total'] is not None), None)
    for cr, raw in results:
        gap = raw['race_gap']
        if gap is None and raw['race_points'] is not None and best_race is not None:
            gap = raw['race_points'] - best_race
        if gap is not None:
            cr.time_difference = f"{gap:.1f}" if gap else "0.0"
        if raw['total'] is not None and winner_total is not None:
            diff = round(raw['total'] - winner_total, 1)
            cr.time_behind = f"{diff:.1f}" if diff else "0.0"

    # The old layouts print no rank for the jumping part as a whole
    if results and all(cr.jump_rank is None for cr, _ in results):
        scored = sorted((cr for cr, _ in results if cr.jump_points is not None),
                        key=lambda cr: -cr.jump_points)
        for i, cr in enumerate(scored):
            same = i > 0 and scored[i - 1].jump_points == cr.jump_points
            cr.jump_rank = scored[i - 1].jump_rank if same else i + 1
