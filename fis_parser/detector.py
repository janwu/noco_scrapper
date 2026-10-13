"""
Detects document type (ROF, RL, RLLL, RLT, RLTR, PCR) and format era
from filename and/or PDF content.
"""
import re
import os
from typing import Optional, Tuple

# ── Document type from filename suffix ────────────────────────────────────────

_SUFFIX_RE = re.compile(
    r'(ROF|ROFM|RLLL|RLTR|RLT|RLQ|RL\d*|PCR)\.pdf$', re.IGNORECASE
)


def detect_doc_type_from_filename(filepath: str) -> str:
    """
    Return one of: ROF, RL, RLLL, RLT, RLTR, PCR, UNKNOWN
    from the filename suffix convention used by FIS.

    Suffix aliases:
      ROFM  → ROF  (Mass Start official results, same format)
      RLQ   → RL   (Qualification/Provisional round, same RL format)
    """
    name = os.path.basename(filepath).upper()
    # Order matters: check longer suffixes first
    for suffix in ('RLLL', 'RLTR', 'PCR'):
        if name.endswith(suffix + '.PDF'):
            return suffix
    # RLT, RLT2, RLT3 etc. — all training round files use the same format
    if re.search(r'RLT\d*\.PDF$', name):
        return 'RLT'
    # ROFM is the same as ROF
    if name.endswith('ROFM.PDF') or name.endswith('ROF.PDF'):
        return 'ROF'
    # RLQ (qualification round) uses the same format as RL
    if name.endswith('RLQ.PDF'):
        return 'RL'
    # RL or RL1, RL2, etc.
    if re.search(r'RL\d*\.PDF$', name):
        return 'RL'
    return 'UNKNOWN'


# ── Format era from PDF content ───────────────────────────────────────────────

def detect_format_era(full_text: str, doc_type: str) -> str:
    """
    For ROF: returns 'A', 'B', 'C', 'D', or 'E'.
    For RL/RLT: returns 'OLD' (ewoxx) or 'MODERN' (Swiss Timing).
    For others: returns 'MODERN' or 'OLD' as appropriate.

    Detection heuristics:
      Era A: no DOB, 'NOC Code', 'WIGE' or no '_73B4', data before ~2006
      Era B: _73B4 1.0, NSA, DOB present, FIS Assistant RD
      Era C: _73B4 2.0, Equipment Controller, Swiss Timing
      Era D: _73B4 v1.0, National TD present in jury at TOP of page 1
      Era E: _73B4 v1.0, jury block at BOTTOM / last page
              detected by report code NC25xx or NC26xx at top
    """
    t = full_text

    if doc_type == 'ROF':
        # Era E: jury is on the last page (not on page 1 area)
        # Heuristic: report code starts with NC25 or NC26
        if re.search(r'\bNC2[5-9]\d{2}', t):
            return 'E'
        # Era D: _73B4 v1.0 + National TD present
        if re.search(r'_73B4\s+v1\.0', t, re.IGNORECASE) and \
           re.search(r'NATIONAL\s+TD', t, re.IGNORECASE):
            return 'D'
        # Era C: _73B4 2.0 or Swiss Timing + Equipment Controller
        if re.search(r'_73B4\s+2\.0', t, re.IGNORECASE) or \
           (re.search(r'Swiss Timing', t, re.IGNORECASE) and
            re.search(r'Equipment Controller', t, re.IGNORECASE)):
            return 'C'
        # Era B: _73B4 1.0 + Date of Birth (or 'Birthdate' used in old COC format)
        if re.search(r'_73B4\s+1\.0', t, re.IGNORECASE) or \
           re.search(r'Date\s+of\s+Birth|Birthdate', t, re.IGNORECASE):
            return 'B'
        # Era A: oldest, no _73B4, no DOB
        return 'A'

    if doc_type in ('RL', 'RLT', 'RLTR', 'PCR'):
        # Modern format always has an 'NSA' column header in the results table.
        # Modern EWOXX (2020+) also uses 'NSA', so NSA takes precedence over ewoxx.
        if re.search(r'\bNSA\b', t):
            return 'MODERN'
        # Old ewoxx format uses 'Nation' column (not NSA)
        if re.search(r'ewoxx', t, re.IGNORECASE):
            return 'OLD'
        return 'MODERN'

    return 'MODERN'


# ── Competition metadata from filename ────────────────────────────────────────

_FILENAME_RE = re.compile(
    r'(?P<codex>\d{4})_'
    r'(?P<date>\d{8})_'
    r'(?P<event_desc>.+?)_'
    r'(?P<category>WC|COC)_'
    r'(?P<gender>[MWA])_'
    r'(?P<gender2>[MWX])_'
    r'\d{4}NK\d{4}',
    re.IGNORECASE,
)

_FILENAME_OLD_RE = re.compile(
    r'(?P<codex>\d{4})_'
    r'(?P<date>\d{8})_'
    r'(?P<event_desc>.+?)_'
    r'(?P<gender>[MWA])_',
    re.IGNORECASE,
)


def parse_filename_metadata(filepath: str) -> dict:
    """
    Extract codex, date, category, gender, discipline hints from filename.
    Returns a dict (all keys may be None if not found).
    """
    name = os.path.basename(filepath)
    meta = {
        'codex': None,
        'date': None,
        'category': None,
        'gender': None,
        'discipline_hint': None,
    }

    # Codex is always the first 4 digits
    m = re.match(r'(\d{4})_(\d{8})', name)
    if m:
        meta['codex'] = m.group(1)
        raw_date = m.group(2)
        meta['date'] = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"

    # Category
    if re.search(r'_WC_', name, re.IGNORECASE):
        meta['category'] = 'WC'
    elif re.search(r'_COC_', name, re.IGNORECASE):
        meta['category'] = 'COC'

    # Gender from folder structure (parent dir name M/W/unknown)
    folder = os.path.basename(os.path.dirname(filepath))
    if folder.upper() == 'M':
        meta['gender'] = 'M'
    elif folder.upper() == 'W':
        meta['gender'] = 'W'
    else:
        # Try from filename
        gm = re.search(r'_(WC|COC)_([MWA])_', name, re.IGNORECASE)
        if gm:
            g = gm.group(2).upper()
            meta['gender'] = 'M' if g == 'M' else ('W' if g == 'W' else 'X')

    # Season from path
    parts = filepath.replace('\\', '/').split('/')
    for p in parts:
        if re.match(r'20\d{2}$', p):
            meta['season'] = p
            break

    # Discipline hint from filename
    desc_lower = name.lower()
    if 'mass_start' in desc_lower or 'massstart' in desc_lower:
        meta['discipline_hint'] = 'Mass Start'
    elif 'express_race' in desc_lower:
        meta['discipline_hint'] = 'Express Race'
    elif 'gundersen' in desc_lower:
        meta['discipline_hint'] = 'Gundersen'
    elif 'compact' in desc_lower:
        meta['discipline_hint'] = 'Compact'
    elif 'team' in desc_lower:
        meta['discipline_hint'] = 'Team'
    elif 'sprint' in desc_lower:
        meta['discipline_hint'] = 'Sprint'
    elif 'provisional' in desc_lower or '_pr_' in desc_lower:
        meta['discipline_hint'] = 'Provisional Round'

    return meta


# ── Fallbacks from the download folder / file name ────────────────────────────

_EVENT_DIR_RE = re.compile(r'^\d{8}_\d{8}_(?P<place>.+)_(?P<country>[A-Z]{3})$')


def venue_from_path(filepath: str) -> Tuple[Optional[str], Optional[str]]:
    """
    The scraper stores every event in a folder '<from>_<to>_<PLACE>_<NAT>'
    (e.g. '20031129_20031130_RUKA_FIN').  Returns ('Ruka', 'FIN'), or
    (None, None) if no such folder is part of the path.
    """
    for part in reversed(filepath.replace('\\', '/').split('/')[:-1]):
        m = _EVENT_DIR_RE.match(part)
        if m:
            return m.group('place').replace('_', ' ').title(), m.group('country')
    return None, None


def team_discipline_from_filename(filepath: str) -> Optional[str]:
    """
    'Team' / 'Team Sprint' if the file name describes a team event, else None.
    The PDF text is no help here: 'Team' also appears in club names of
    individual competitions, and team events are often titled 'Gundersen'.
    """
    name = os.path.basename(filepath)
    relay = re.search(r'_(\d)x[\d.]+', name)
    if re.search(r'Team[_ ]Sprint', name, re.IGNORECASE) or (relay and relay.group(1) == '2'):
        return 'Team Sprint'
    if re.search(r'(?:^|_)(?:Mixed_)?Team(?:_|$)', name, re.IGNORECASE) or relay:
        return 'Team'
    return None
