"""
Parser for RLLL (Intermediate Results Cross Country) — Mass Start format.

Column layout:
  Rank  Bib  Name  NSA  Club  DOB  TotalTime  Behind  Points

The "Points" column is the time-to-jump-handicap conversion
(negative = deficit for the final jumping round).

Jury block is on the last page (Format E style).
"""
import re
from typing import List, Optional

import pdfplumber

from fis_parser.models import CrossCountryResult, ParsedDocument
from fis_parser.utils import (
    parse_float, parse_int, normalise_date, clean_name,
    find_line_index, group_words_into_rows, row_text,
)
from fis_parser.extractors.base import BaseExtractor


class RLLLExtractor(BaseExtractor):

    def parse(self) -> ParsedDocument:
        doc = ParsedDocument(
            source_file=self.filepath,
            doc_type='RLLL',
            format_era='MODERN',
        )
        self.doc = doc

        try:
            with self.open_pdf() as pdf:
                full_text = self.all_text(pdf)

                hdr = self.extract_event_header(full_text)
                doc.fis_report_code = hdr.get('fis_report_code')
                doc.location = hdr.get('location')
                doc.country = hdr.get('country')
                doc.competition_date = hdr.get('competition_date')
                doc.start_time = hdr.get('start_time')
                doc.end_time = hdr.get('end_time')
                doc.report_created = hdr.get('report_created')

                doc.discipline = 'Mass Start'
                doc.final_phase = 'SKI_JUMPING'  # XC is the prologue; jump is final

                doc.course_info = self.extract_course_info(full_text)

                # Jury on last page
                last_lines = self.page_lines(pdf.pages[-1])
                jury_start = find_line_index(
                    last_lines,
                    r'Jury\s*/\s*Competition|Competition\s+Management'
                )
                if jury_start >= 0:
                    doc.jury = self.extract_jury_block(
                        last_lines, jury_start + 1,
                        stop_patterns=[r'WEATHER|Weather|HEIGHT\s+DIFFERENCE']
                    )

                last_text = self.page_text(pdf.pages[-1])
                wd, cs = self.extract_weather_summary(last_text)
                doc.weather = wd
                doc.competitor_stats = cs

                doc.xc_results = self._extract_xc_results(pdf)

        except Exception as exc:
            doc.parse_errors.append(f"RLLL parse error: {exc}")

        return doc

    # Known non-NSA 3-letter strings that appear at line endings
    _FALSE_NSA = frozenset([
        'CUP', 'FIS', 'SKI', 'XCO', 'WCR', 'KM', 'NH', 'LH', 'IHF',
        'COC', 'WC', 'IHC', 'TDS',
    ])
    # Words that indicate a title/header line, not an athlete name
    _TITLE_WORDS_RE = re.compile(
        r'\b(?:WORLD|NORDIC|COMBINED|INTERMEDIATE|RESULTS?|COMPETITION|'
        r'MANAGEMENT|CROSS|COUNTRY|VIESSMANN|TRIPLE|INDIVIDUAL|SPRINT|'
        r'CONTINENTAL|START|TIME|BEHIND|POINTS?|COURSE|INFORMATION|'
        r'JURY|RACE|TECHNICAL|DELEGATE|CHIEF)\b',
        re.IGNORECASE,
    )

    @classmethod
    def _is_name_nsa_row(cls, rt: str) -> bool:
        """Return True if this row looks like 'LASTNAME Firstname NSA' with no numbers."""
        s = rt.strip()
        if not s:
            return False
        # Must end with a 3-letter uppercase NSA code
        m = re.search(r'\b([A-Z]{3})\s*$', s)
        if not m:
            return False
        # That 3-letter code must not be a known non-NSA abbreviation
        if m.group(1) in cls._FALSE_NSA:
            return False
        # Must not be a header/title line
        if cls._TITLE_WORDS_RE.search(s):
            return False
        # Must not contain time-like patterns
        if re.search(r'\d{2}:\d{2}', s):
            return False
        # Must not be only numbers
        if not re.search(r'[A-Za-z]{2,}', s):
            return False
        return True

    def _extract_xc_results(self, pdf: pdfplumber.PDF) -> List[CrossCountryResult]:
        results: List[CrossCountryResult] = []

        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            rows = group_words_into_rows(words, y_tol=3)
            page_w = max(w['x1'] for w in words)
            scale = page_w / 720.0

            # RLLL column layout (modern, ~595-720pt wide):
            #   RANK  BIB  NAME/NSA  CLUB/DOB  TOTAL_TIME  BEHIND  POINTS
            X_RANK_MAX  = 55  * scale
            X_BIB_MAX   = 95  * scale
            X_NAME_MAX  = 330 * scale
            X_NSA_MAX   = 390 * scale
            # rest = TOTAL TIME, BEHIND, POINTS

            current: Optional[CrossCountryResult] = None
            # state: 0=looking, 'name'=got name row, 1=got rank row (want club/DOB)
            state: object = 0
            in_dnf = in_dns = False

            for row in rows:
                rt = row_text(row)
                if not rt.strip():
                    continue

                rt_u = rt.strip().upper()
                if re.search(r'^DID\s+NOT\s+FINISH', rt_u):
                    in_dnf = True
                    in_dns = False
                    if current and current.name:
                        results.append(current)
                        current = None
                    state = 0
                    continue
                if re.search(r'^DID\s+NOT\s+START', rt_u):
                    in_dns = True
                    in_dnf = False
                    if current and current.name:
                        results.append(current)
                        current = None
                    state = 0
                    continue
                # Jury header/rows appear at TOP of page in era A-D — skip, don't stop
                if re.search(r'^JURY|^RACE\s+DIRECTOR|^TECHNICAL\s+DELEGATE|'
                             r'^ASSISTANT|^CHIEF|^EQUIPMENT|^NATIONAL\s+TD', rt_u):
                    continue
                # Weather section marks the true end of results
                if re.search(r'^WEATHER', rt_u):
                    if current and current.name:
                        results.append(current)
                        current = None
                    break

                if in_dnf or in_dns:
                    status = 'DNF' if in_dnf else 'DNS'
                    m = re.match(r'(\d+)\s+(.+?)(?:\s+([A-Z]{3}))?$', rt)
                    if m:
                        results.append(CrossCountryResult(
                            bib=parse_int(m.group(1)),
                            name=clean_name(m.group(2)),
                            nation=m.group(3),
                            status=status,
                        ))
                    continue

                # Skip header rows
                if re.search(
                    r'\bRANK\b.*\bBIB\b|\bTOTAL\s+TIME\b|\bNAME\b.*\bNSA\b|\bCLUB\b.*\bDATE\b',
                    rt, re.IGNORECASE
                ):
                    state = 0  # reset any dangling state from previous page header
                    continue

                # ── Modern 3-row pattern: NAME+NSA row comes BEFORE rank/bib row ──
                if state == 0 and self._is_name_nsa_row(rt):
                    if current and current.name:
                        results.append(current)
                    current = CrossCountryResult()
                    # NSA is the last token (3 uppercase letters); name is everything before
                    tokens = rt.strip().split()
                    if tokens and re.match(r'^[A-Z]{3}$', tokens[-1]):
                        current.nation = tokens[-1]
                        current.name = clean_name(' '.join(tokens[:-1]))
                    else:
                        current.name = clean_name(rt)
                    state = 'name'
                    continue

                # ── Rank+bib+numbers row (follows name row in 3-row pattern,
                #    or is the first row in old single-row pattern) ──
                #    May start with optional status flag "PF" before rank digit.
                rank_match = re.match(r'^\s*(?:PF\s+)?=?(\d+)\s', rt)
                if rank_match and state in (0, 'name'):
                    if state == 0:
                        # Old single-row format: rank is first, name is on same row
                        if current and current.name:
                            results.append(current)
                        current = CrossCountryResult()

                    # Token-based parsing: more reliable than x-coord for this row
                    tokens = rt.strip().split()
                    # Strip leading status flag (PF, LAP, etc.)
                    if tokens and not tokens[0][0].isdigit() and not tokens[0].startswith('='):
                        tokens = tokens[1:]

                    # first token = rank (may have trailing '.'), second = bib
                    rank_m2 = re.search(r'(\d+)', tokens[0]) if tokens else None
                    current.rank = int(rank_m2.group(1)) if rank_m2 else None
                    current.bib = parse_int(tokens[1]) if len(tokens) > 1 else None

                    # In old single-row format name comes after bib using x-coords
                    if state == 0:
                        name_w2, nsa_w2 = [], []
                        for w in row:
                            cx = (w['x0'] + w['x1']) / 2
                            if X_BIB_MAX <= cx < X_NAME_MAX:
                                name_w2.append(w['text'])
                            elif X_NAME_MAX <= cx < X_NSA_MAX:
                                nsa_w2.append(w['text'])
                        current.name = clean_name(' '.join(name_w2))
                        nsa = ' '.join(nsa_w2).strip()
                        current.nation = nsa if len(nsa) == 3 else None

                    # Numeric tail starts at token index 2 — time, behind, points
                    nums = tokens[2:] if len(tokens) > 2 else []
                    # First numeric that looks like a time (HH:MM.s or MM:SS.s)
                    time_idx = next((i for i, t in enumerate(nums) if re.match(r'\d+:\d', t)), None)
                    if time_idx is not None:
                        current.total_time = nums[time_idx]
                        if time_idx + 1 < len(nums):
                            current.time_behind = nums[time_idx + 1]
                        if time_idx + 2 < len(nums):
                            current.points = parse_float(nums[time_idx + 2])

                    state = 1
                    continue

                if state == 1 and current:
                    # Club + DOB row
                    dob_m = re.search(r'\b(\d{1,2}\s+[A-Z]{3}\s+\d{4})\b', rt)
                    if dob_m:
                        current.date_of_birth = normalise_date(dob_m.group(1))
                        current.club = clean_name(rt[:dob_m.start()])
                    else:
                        if rt.strip():
                            current.club = clean_name(rt)
                    state = 0

            if current and current.name:
                results.append(current)

        return results
