"""
Word-position parser for training and trial round lists (RLT, RLTR).

These lists print up to three rounds side by side (training) or two athletes
per line (trial round), and a round an athlete left out is just blank.  Read
line by line, values slide into the wrong round; so this parser works on the
position of every word:

- The column header gives the x position of every column: the unit line
  '[km/h] [m] GATE [m/s]' (one group per round, or per half of the page), or
  the titles 'Speed Dist Gate m/s'.  A trial list has two 'BIB' headers: the
  page is split between them.
- An athlete is anchored on the line with his speed and distance; name, nation
  and bib are looked for in a narrow band around it, since depending on the
  layout they are on the same line or 3-5 pt above or below.
- Every number goes to the nearest column, and only if it is close to it.
  Ranks ('46.') end in a dot and are never taken for a value.
"""
import re
from typing import Dict, List, Optional, Tuple

from fis_parser.models import JumpRound
from fis_parser.utils import clean_name

_DECIMAL_RE = re.compile(r'^\d{2,3}\.\d$')
_GATE_RE = re.compile(r'^\d{1,2}$')
_WIND_RE = re.compile(r'^[-+]?\d\.\d\d$')
_NSA_RE = re.compile(r'^[A-Z]{3}$')
_MONTHS = {'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'}
_BIB_RE = re.compile(r'^\d{1,3}$')
_ALPHA_RE = re.compile(r"[^\W\d_]")
# titles that stand where a name could ('Trial Round', '2nd Training')
_TITLE_WORDS = {'trial', 'round', 'training', 'official', 'results', 'result', 'list', 'jury', 'page',
                'weather', 'statistics', 'did', 'not', 'start', 'disqualified'}

_SPEED_HEADERS = ('[km/h]', 'speed', 'km/h')
_DIST_HEADERS = ('[m]', 'dist', 'dist.', 'distance', 'm')
_GATE_HEADERS = ('gate',)
_WIND_HEADERS = ('[m/s]', 'm/s')

_COLUMN_TOLERANCE = 13      # pt between a value and the centre of its column
_BAND_ABOVE = 6             # pt above the data line still holding name / nation / bib
_BAND_BELOW = 8


def _lines(words: List[dict], tol: float = 2.0) -> List[List[dict]]:
    lines: List[List[dict]] = []
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if lines and abs(w['top'] - lines[-1][0]['top']) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    for line in lines:
        line.sort(key=lambda w: w['x0'])
    return lines


def _cx(w: dict) -> float:
    return (w['x0'] + w['x1']) / 2


class _Side:
    """One half of a page (trial rounds) or the whole page: its columns."""

    def __init__(self, x0: float, x1: float):
        self.x0, self.x1 = x0, x1
        self.columns: List[Tuple[float, str, int]] = []      # (x, kind, round)
        self.name_x: Optional[float] = None
        self.bib_x: Optional[float] = None

    def contains(self, x: float) -> bool:
        return self.x0 <= x < self.x1

    @property
    def first_value_x(self) -> float:
        return min(x for x, _, _ in self.columns) if self.columns else self.x1


def _header(lines: List[List[dict]], page_width: float) -> Tuple[Optional[int], List[_Side]]:
    """Index of the last header line and the sides with their columns, or (None, [])."""
    for i, line in enumerate(lines):
        texts = [w['text'].lower() for w in line]
        speeds = [w for w in line if w['text'].lower() in _SPEED_HEADERS]
        dists = [w for w in line if w['text'].lower() in _DIST_HEADERS[:-1]]       # not a lone 'm'
        if not speeds or not dists or len(dists) != len(speeds):
            continue
        # the header block: this line and the lines up to 4 below / above it
        block = [w for l in lines[max(0, i - 4):i + 5] for w in l]
        bibs = sorted((w for w in block if w['text'].lower() == 'bib'), key=_cx)
        if len(bibs) >= 2 and _cx(bibs[1]) > page_width * 0.35:
            split = bibs[1]['x0'] - 4
            sides = [_Side(0, split), _Side(split, page_width + 1)]
        else:
            sides = [_Side(0, page_width + 1)]
        for side in sides:
            unit_line = [w for w in line if side.contains(_cx(w))]
            # gate / wind: on this line, or on a header line close above
            nearby = [w for w in block if side.contains(_cx(w)) and abs(w['top'] - line[0]['top']) <= 12]
            rnd = 0
            for w in sorted(unit_line, key=_cx):
                t = w['text'].lower()
                if t in _SPEED_HEADERS:
                    rnd += 1
                    side.columns.append((_cx(w), 'speed', rnd))
                elif t in _DIST_HEADERS[:-1]:
                    side.columns.append((_cx(w), 'distance', max(rnd, 1)))
            speed_xs = sorted(x for x, k, _ in side.columns if k == 'speed')
            for w in nearby:
                t = w['text'].lower()
                kind = 'gate' if t in _GATE_HEADERS else 'wind' if t in _WIND_HEADERS else None
                if kind and not any(abs(x - _cx(w)) < 4 for x, _, _ in side.columns):
                    r = sum(1 for x in speed_xs if x <= _cx(w)) or 1
                    side.columns.append((_cx(w), kind, r))
            names = [w for w in block if side.contains(_cx(w)) and w['text'].lower() == 'name']
            side.name_x = names[0]['x0'] if names else None
            sb = [w for w in bibs if side.contains(_cx(w))]
            side.bib_x = _cx(sb[0]) if sb else None
        last = max((j for j in range(max(0, i - 4), min(len(lines), i + 5))
                    if any(w['text'].lower() in ('rank', 'rank*', 'club', 'bib', '[m]', '[km/h]', 'birthdate')
                           for w in lines[j])), default=i)
        return last, [s for s in sides if any(k == 'distance' for _, k, _ in s.columns)]
    return None, []


def _column_of(side: _Side, x: float) -> Optional[Tuple[float, str, int]]:
    best = min(side.columns, key=lambda c: abs(c[0] - x), default=None)
    if best is None or abs(best[0] - x) > _COLUMN_TOLERANCE:
        return None
    return best


def parse_training_page(words: List[dict], page_width: float) -> List[JumpRound]:
    """The jumps on one page of a training or trial list (empty if it has no column header)."""
    lines = _lines(words)
    last_header, sides = _header(lines, page_width)
    if last_header is None:
        return []
    body = [w for line in lines[last_header + 1:] for w in line]
    rows: List[JumpRound] = []
    for side in sides:
        side_words = [w for w in body if side.contains(_cx(w))]
        data_lines = _lines([w for w in side_words if _cx(w) >= side.first_value_x - _COLUMN_TOLERANCE])
        for line in data_lines:
            values: Dict[Tuple[str, int], str] = {}
            for w in line:
                col = _column_of(side, _cx(w))
                if col is None:
                    continue
                _, kind, rnd = col
                t = w['text']
                ok = (_DECIMAL_RE.match(t) and (kind != 'speed' or 50 <= float(t) <= 120)) if kind in ('speed', 'distance') \
                    else _GATE_RE.match(t) if kind == 'gate' else _WIND_RE.match(t)
                if ok:
                    values.setdefault((kind, rnd), t)
            if not any(k == 'distance' for k, _ in values):
                continue
            top = line[0]['top']
            band = [w for w in side_words if top - _BAND_ABOVE <= w['top'] <= top + _BAND_BELOW
                    and _cx(w) < side.first_value_x - 8]
            row = _identity(band, side)
            if row is None:
                continue
            rounds = sorted({r for _, r in values})
            for rnd in rounds:
                if ('distance', rnd) not in values:
                    continue
                jr = JumpRound(round_number=rnd, bib=row.bib, name=row.name, nation=row.nation)
                jr.distance_m = float(values[('distance', rnd)])
                if ('speed', rnd) in values:
                    jr.speed_kmh = float(values[('speed', rnd)])
                if ('gate', rnd) in values:
                    jr.gate = int(values[('gate', rnd)])
                if ('wind', rnd) in values:
                    jr.wind_ms = float(values[('wind', rnd)])
                rows.append(jr)
    return rows


def _identity(band: List[dict], side: _Side) -> Optional[JumpRound]:
    """Name, nation and bib from the words around a data line."""
    # the line holding the name: the one with the most letters, nearest to the data line first
    by_line = _lines(band, tol=1.5)
    named = None
    for line in by_line:
        alpha = [w for w in line if _ALPHA_RE.search(w['text']) and not _NSA_RE.match(w['text'])]
        if any(w['text'].lower() in _TITLE_WORDS for w in alpha):
            continue
        if len(alpha) >= 2 and (side.name_x is None or _cx(alpha[0]) >= side.name_x - 25):
            named = line
            break
    if named is None:
        return None
    name_words = []
    for w in named:
        if _NSA_RE.match(w['text']) and name_words:
            break
        if _ALPHA_RE.search(w['text']) and not re.search(r'\d', w['text']):
            name_words.append(w['text'])
    # the nation: on the name line if it is there, else the nearest ('APR' of a birth date is none)
    nsa = [w for w in band if _NSA_RE.match(w['text']) and w['text'] not in _MONTHS
           and (not name_words or w not in named[:len(name_words)])]
    nsa.sort(key=lambda w: (w not in named, abs(w['top'] - named[0]['top'])))
    nsa = [w['text'] for w in nsa][::-1]
    bibs = [w for w in band if _BIB_RE.match(w['text'])
            and (side.bib_x is None or abs(_cx(w) - side.bib_x) <= 15)]
    name = clean_name(' '.join(name_words))
    if len(name.split()) < 2:
        return None
    return JumpRound(name=name, nation=nsa[-1] if nsa else None,
                     bib=int(bibs[0]['text']) if bibs else None)


def parse_training_pdf(pdf) -> List[JumpRound]:
    rows: List[JumpRound] = []
    for page in pdf.pages:
        words = page.extract_words(x_tolerance=1.5)
        rows.extend(parse_training_page(words, page.width))
    return rows
