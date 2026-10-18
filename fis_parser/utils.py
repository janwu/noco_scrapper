"""
Shared text-processing utilities for FIS PDF parsing.
"""
import re
from typing import Optional, List, Dict, Tuple


# ── Time / numeric helpers ────────────────────────────────────────────────────

def parse_float(s: str) -> Optional[float]:
    """Parse a float string, returning None on failure."""
    try:
        return float(s.replace(',', '.'))
    except (ValueError, AttributeError):
        return None


def parse_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except (ValueError, AttributeError):
        return None


def parse_temp(s: str) -> Optional[float]:
    """Parse temperature strings like '-3.0', '-1.0°C', '1.0°C'."""
    if not s:
        return None
    cleaned = s.replace('°C', '').replace('°', '').strip()
    return parse_float(cleaned)


def parse_fraction(s: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse '46/14' → (46, 14).  Returns (None, None) on failure."""
    m = re.match(r'(\d+)\s*/\s*(\d+)', s.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


# ── Nation / name extraction ──────────────────────────────────────────────────

_KNOWN_NATIONS = {
    'AUT', 'GER', 'NOR', 'FIN', 'JPN', 'FRA', 'SUI', 'USA', 'SLO', 'CZE',
    'ITA', 'POL', 'EST', 'NOR', 'RUS', 'BLR', 'KAZ', 'SWE', 'CHN', 'UKR',
    'KOR', 'CAN', 'SVK', 'LAT', 'LTU', 'HUN', 'ROU', 'BUL', 'TUR', 'GBR',
    'ISL', 'LUX', 'BEL', 'NED', 'DEN', 'SRB', 'CRO', 'BIH', 'MKD',
}


def extract_nation(s: str) -> Tuple[Optional[str], str]:
    """
    Try to find a 3-letter nation code in a string.
    Returns (nation, remainder_string).
    """
    m = re.search(r'\b([A-Z]{3})\b', s)
    if m and m.group(1) in _KNOWN_NATIONS:
        nation = m.group(1)
        remainder = (s[:m.start()] + s[m.end():]).strip()
        return nation, remainder
    return None, s


def extract_nation_parens(s: str) -> Tuple[Optional[str], str]:
    """Extract nation from '(AUT)' or '(FIS)' at end of string."""
    m = re.search(r'\(([A-Z]{2,4})\)\s*$', s.strip())
    if m:
        nation = m.group(1)
        remainder = s[:m.start()].strip()
        return nation, remainder
    return None, s


# ── Date helpers ──────────────────────────────────────────────────────────────

_MONTH_MAP = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
}

def normalise_date(s: str) -> Optional[str]:
    """
    Convert various date formats to ISO YYYY-MM-DD.
    Handles: '9 DEC 1991', '9 DEC 1991', '04.03.1989', '03 JAN 2009'
    """
    if not s:
        return None
    s = s.strip()
    # 'D MMM YYYY' or 'DD MMM YYYY'
    m = re.match(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})$', s)
    if m:
        day, mon, year = m.group(1), m.group(2).upper(), m.group(3)
        if mon in _MONTH_MAP:
            return f"{year}-{_MONTH_MAP[mon]}-{int(day):02d}"
    # 'DD.MM.YYYY'
    m = re.match(r'(\d{1,2})\.(\d{2})\.(\d{4})$', s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"
    return s   # return as-is if unrecognised


# ── pdfplumber word-row grouping ──────────────────────────────────────────────

def group_words_into_rows(words: List[dict], y_tol: float = 3.0) -> List[List[dict]]:
    """
    Given a list of pdfplumber word dicts (with 'top' key), group them
    into lines by proximity on the y-axis.
    Returns list of rows, each row sorted by x0.

    Words are first sorted spatially (by y then x) so that stream-order
    PDF encoding artefacts don't create artificially split rows.
    """
    if not words:
        return []
    # Sort spatially so words at similar y-positions are adjacent
    sorted_words = sorted(words, key=lambda w: (w['top'], w['x0']))
    rows: List[List[dict]] = []
    current_row: List[dict] = [sorted_words[0]]
    current_y = sorted_words[0]['top']

    for w in sorted_words[1:]:
        if abs(w['top'] - current_y) <= y_tol:
            current_row.append(w)
        else:
            rows.append(sorted(current_row, key=lambda x: x['x0']))
            current_row = [w]
            current_y = w['top']
    rows.append(sorted(current_row, key=lambda x: x['x0']))
    return rows


def row_text(row: List[dict]) -> str:
    """Concatenate words in a row with single spaces."""
    return ' '.join(w['text'] for w in row)


def words_in_x_range(row: List[dict], x_min: float, x_max: float) -> str:
    """Extract text from words whose centre falls within [x_min, x_max]."""
    return ' '.join(
        w['text'] for w in row
        if x_min <= (w['x0'] + w['x1']) / 2 <= x_max
    ).strip()


# ── Text-block section locating ───────────────────────────────────────────────

def find_line_index(lines: List[str], pattern: str,
                    start: int = 0, flags=re.IGNORECASE) -> int:
    """Return index of first line matching *pattern*, or -1."""
    rx = re.compile(pattern, flags)
    for i in range(start, len(lines)):
        if rx.search(lines[i]):
            return i
    return -1


def extract_value_after(line: str, label: str) -> Optional[str]:
    """
    Given 'Height Difference (HD):   56 m', return '56 m' for label 'Height Difference'.
    Case-insensitive.
    """
    pattern = re.escape(label) + r'[\s\(\w\)]*:\s*(.*)'
    m = re.search(pattern, line, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


# ── Jury role normalisation ───────────────────────────────────────────────────

_ROLE_ALIASES: Dict[str, str] = {
    # modern keys → canonical
    'RACE DIRECTOR': 'Race Director',
    'FIS RACE DIRECTOR': 'Race Director',
    'FIS RACE DIRECTOR (RD)': 'Race Director',
    'TECHNICAL DELEGATE': 'Technical Delegate',
    'FIS TECHNICAL DELEGATE': 'Technical Delegate',
    'FIS TECHNICAL DELEGATE (TD)': 'Technical Delegate',
    'TD': 'Technical Delegate',
    'ASSISTANT TECHNICAL DELEGATE': 'Asst Technical Delegate',
    'FIS ASSISTANT TECHNICAL DELEGATE': 'Asst Technical Delegate',
    'ASSISTANT TD': 'Asst Technical Delegate',
    'ASSISTENT TD': 'Asst Technical Delegate',
    'TD ASSISTANT': 'Asst Technical Delegate',
    'ASSISTANT RACE DIRECTOR': 'Asst Race Director',
    'FIS ASSISTANT RD': 'Asst Race Director',
    'ASSISTENT RD': 'Asst Race Director',
    'CHIEF OF COMPETITION': 'Chief of Competition',
    'CHIEF OF COURSE': 'Chief of Course',
    'EQUIPMENT CONTROLLER': 'Equipment Controller',
    'NATIONAL TD': 'National TD',
    'COORDINATOR': 'Coordinator',
}


def normalise_role(raw: str) -> str:
    key = raw.strip().upper()
    return _ROLE_ALIASES.get(key, raw.strip().title())


# ── Misc ──────────────────────────────────────────────────────────────────────

def clean_name(s: str) -> str:
    """Normalize an athlete name string."""
    s = re.sub(r'\s+', ' ', s).strip()
    # Strip leading single lowercase letter/word prefix (e.g. 'b ANDERSEN Espen' → 'ANDERSEN Espen')
    s = re.sub(r'^[a-z]\s+', '', s)
    # Split merged LASTNAME+Firstname tokens (e.g. 'ACKERMANNHugo' → 'ACKERMANN Hugo')
    s = re.sub(r'^([A-Z]{2,})([A-Z][a-z])', r'\1 \2', s)
    # Mixed team lists mark the gender: 'ARMBRUSTER Nathalie (F)' → 'ARMBRUSTER Nathalie'
    s = re.sub(r'\s*\([FMW]\)$', '', s)
    return s


# ── Athlete name validation ───────────────────────────────────────────────────

_GARBAGE_NAME_RE = re.compile(
    r"""
    ^\s*$                                          # empty
    | \d{2}:\d{2}:\d{2}                           # HH:MM:SS timestamp (footer)
    | \b\d{1,2}:\d{2}\b                           # embedded MM:SS time (e.g. team DNS "NORWAY II ... 01:19")
    | ^\s*[+\-]\d                                 # starts with signed number (e.g. "-0.90m 14 1 ...", "+0.66m")
    | ^\s*(?:\d+[\s.]+){3,}                       # 3+ number sequence (e.g. "24 46 0 90.0")
    | ^\s*\d{1,2}\s+[A-Z]{3}\s*$                 # bare date fragment "29 JUN"
    | \d{1,2}\s+[A-Z]{3}\s+\d{4}\s+[=\d.]       # club/DOB row "TSU... 17 DEC 1992 6."
    | \d{2}\.\d{2}\.\d{4}\s                      # club/DOB row with dot-date "... 09.01.1985 ..."
    | ^\s*printed\b                               # footer "printed 12 DEC 2011..."
    | \bReport\s+Created\b                        # footer "_73B4 1.0 Report Created..."
    | \bGate\s+Factor\b                           # hill data
    | \bHill\s+Size\b                             # hill data
    | ^[0-9.\s]+$                                 # all digits/dots/spaces
    | ^/                                          # starts with slash (venue/footer artifact)
    | www\.                                       # URL in footer (e.g. "Data Service by Swiss Timing www.fis-ski.com")
    | ^\s*(?:RACE\s+DIRECTOR|ASSISTANT\s+(?:TD|RD)|TECHNICAL\s+DELEGATE|CHIEF\s+OF\s+(?:COMPETITION|COURSE)|NATIONAL\s+TD|EQUIPMENT\s+CONTROLLER|JURY\s*/)\b
                                                   # jury/official role prefix
    | ^\s*Jury\s*/\s*Competition\b                # jury section header
    | ^\s*TEMPERATURES?\s*\[                      # weather section header
    | \bNUMBER\s+OF\s+LAPS\b                     # course info
    | \bHEIGHT\s+DIFFERENCE\b                    # course info (HD)
    | \bTOTAL\s+CLIMB\b                          # course info (TC)
    | \bMAXIMUM\s+CLIMB\b                        # course info (MC)
    | ^\s*Continental\s+Cup\s+Competition\b       # section header in some PDFs
    | ^\s*Mixed\s+Team\s+Competition\b            # section header in some PDFs
    | \b(?:Hiihtoseura|Kilpaveljet|Skiclub|Ski\s+Club|Construction\s+Corp\.)\b.*\s+\d{1,2}\s*$
                                                   # club name with trailing bib number
    | ^\s*C\.S\.\s+                                # Italian "Centro Sportivo" club prefix (C.S. CARABINIERI, C.S. ESERCITO, etc.)
    | ^\s*POINTS\s*$                               # stray column-header fragment (Compact format PDF row y≈145)
    | ^\s*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s*$
                                                   # lone month: revision stamp '16 DEC 15:13' or a DOB fragment
    """,
    re.VERBOSE | re.IGNORECASE,
)

_LETTERS_RE = re.compile(r'[A-Za-z]')


def is_valid_athlete_name(s: str) -> bool:
    """Return True if s looks like a real athlete name (not footer/garbage)."""
    if not s or len(s) > 80:
        return False
    if not _LETTERS_RE.search(s):
        return False
    if _GARBAGE_NAME_RE.search(s):
        return False
    return True


def split_stat_fraction(s: str) -> Tuple[Optional[int], Optional[int]]:
    """'54/14' → (54, 14)."""
    return parse_fraction(s)


def team_name(text: str) -> str:
    """'NORWAY II' → 'Norway II', 'GERMANY' → 'Germany'; a code ('DDR', 'USA') and a roman number stay."""
    words = text.upper().split()
    roman = [bool(re.fullmatch(r"[IVX]+", w)) for w in words]
    # a nation code is the one word besides a roman number: 'USA I', 'DDR'
    code = sum(not r for r in roman) == 1 and len(next(w for w, r in zip(words, roman) if not r)) <= 3
    return " ".join(w if r or code else w.capitalize() for w, r in zip(words, roman))
