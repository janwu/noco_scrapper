"""
Parser for ROF (Official Results) documents — all 5 format eras.

Era A: 2001–~2005  — no DOB, NOC Code, jury top-left
Era B: ~2006–~2013 — DOB added, NSA, FIS Asst RD
Era C: ~2014–~2020 — Equipment Controller, Swiss Timing 2.0
Era D: ~2021–~2024 — National TD, NPS/DQB weather cols
Era E: 2025+        — Jury moved to last page
"""
import re
from typing import List, Optional, Tuple

import pdfplumber

from fis_parser.models import (
    CombinedResult, ParsedDocument,
    JuryOfficial, CourseInfo, WeatherData, CompetitorStats,
)
from fis_parser.utils import (
    parse_float, parse_int, normalise_date, clean_name,
    find_line_index, group_words_into_rows, row_text, is_valid_athlete_name,
)
from fis_parser.extractors.base import BaseExtractor
from fis_parser.extractors.rof_ewoxx import is_ewoxx_layout, parse_ewoxx_rof
from fis_parser.extractors.rof_team import parse_team_rof
from fis_parser.validate import CLOCK_RE, FINISH_GAP_RE, time_format_problems
from fis_parser.extractors.rof_kjump import is_kjump_layout, parse_kjump_rof
from fis_parser.detector import (
    parse_filename_metadata, team_discipline_from_filename, venue_from_path,
)

# Column headers that only occur in team result lists
_TEAM_TABLE_RE = re.compile(
    r'Team\s+Leg|TEAM\s+TEAM|Team\s+Time|^(?:RANK\s+)?BIB\s+(?:NSA|NOC|Nat|Nation)\s+(?:CODE|Name|Jump)\b'
    r'|^RANK\s+BIBNAME\s+TIME\b|Bib\s+-\s+Name|^Rank\s+Jump\s+Time\s+Team\b',
    re.IGNORECASE | re.MULTILINE)
# First line of any block that can follow the DNS/DNF/DSQ lists
_AFTER_RESULTS_RE = re.compile(
    r'Jury\b|Competition\s*(?:/|Management)|Weather\b|Temperatures?\b|Air\s+Snow\b|Snow\s+Air\b'
    r'|Statistics\b|Time\s+Base\b|Legend\b|Translation\b|Remarks?\b',
    re.IGNORECASE)
# Lines that belong to the page, not to the result list
_PAGE_FURNITURE_RE = re.compile(
    r'Timing\s+and\s+Data|Data\s+(?:Service|Provider|processing)|Timing\s+Provider|Report\s+Created'
    r'|www\.|fis-ski\.com|^\s*Bib\s+Name\s*$|\bPage\s+\d+\s*(?:/|of|from)\s*\d+',
    re.IGNORECASE)
# Title block repeated at the top of every page.  Only consulted while a
# DNS/DNF/DSQ list is open, i.e. on a continuation page before the list goes on.
_PAGE_TITLE_RE = re.compile(
    r'\bFIS\b|WORLD\s+CUP|CONTINENTAL\s+CUP|\bCompetition\b|^\s*(?:Official\s+)?Results\b'
    r'|Start\s+Time|End\s+Time|\([A-Z]{3}\)|presented\s+by|^\s*REVISED\b',
    re.IGNORECASE)
# Column headers of an individual result list
_INDIVIDUAL_TABLE_RE = re.compile(
    r'^(?:RANK\s+BIB\s+)?NAME\s+(?:NSA|NOC|Nat)\b|^Name\s+Jump\b|^Rank\s+Name\s+(?:Nation|FIS-Code)\b',
    re.IGNORECASE | re.MULTILINE)


def _has_surname(name: str) -> bool:
    """
    True if the name starts with an all-caps surname ('MENZ Matthias').
    Used where a list continues on the next page and the page title
    ('"WARSTEINER" FIS WORLD CUP ...', '15th World Cup Competition') would
    otherwise pass as 'name + three-letter code'.
    """
    first = name.split()[0] if name.split() else ''
    letters = first.replace('-', '').replace("'", '').replace('.', '')
    return len(letters) >= 2 and letters.isalpha() and letters.isupper()


def _normalise_name_case(results: List[CombinedResult]) -> None:
    """
    A few early mass-start lists print 'Ackermann Ronny' instead of
    'ACKERMANN Ronny'.  If that is the style of the whole list, upper-case
    the surname so the athlete matches his other results.
    """
    named = [r for r in results if r.name]
    plain = [r for r in named if re.match(r"^[^\W\d_][^\W\d_A-Z]+(?:-[^\W\d_]+)?\s+\S", r.name)]
    if not named or len(plain) < 0.8 * len(named):
        return
    for r in plain:
        first, rest = r.name.split(None, 1)
        if rest.split()[-1].isupper():
            continue                       # 'Lisa EDER': first name first — leave alone
        r.name = f"{first.upper()} {rest}"


class ROFExtractor(BaseExtractor):

    def parse(self) -> ParsedDocument:
        doc = ParsedDocument(
            source_file=self.filepath,
            doc_type='ROF',
        )
        self.doc = doc

        try:
            with self.open_pdf() as pdf:
                full_text = self.all_text(pdf)
                doc.format_era = self._detect_era(full_text)

                # Metadata from header
                hdr = self.extract_event_header(full_text)
                doc.fis_report_code = hdr.get('fis_report_code')
                doc.location = hdr.get('location')
                doc.country = hdr.get('country')
                doc.competition_date = hdr.get('competition_date')
                doc.start_time = hdr.get('start_time')
                doc.end_time = hdr.get('end_time')
                doc.report_created = hdr.get('report_created')

                # Event name / discipline from page 1 header
                doc.event_name = self._extract_event_name(full_text)
                doc.discipline = self._extract_discipline(full_text)
                self._apply_path_fallbacks(doc)
                doc.final_phase = self._infer_final_phase(doc.discipline)

                # Course info
                doc.course_info = self.extract_course_info(full_text)

                if doc.format_era in ('A', 'B', 'C', 'D'):
                    # Jury on page 1 (top block, alongside course info)
                    page1_text = self.page_text(pdf.pages[0])
                    page1_lines = page1_text.splitlines()
                    jury_start = find_line_index(
                        page1_lines,
                        r'Jury|Competition\s+Management'
                    )
                    if jury_start >= 0:
                        doc.jury = self.extract_jury_block(
                            page1_lines, jury_start + 1,
                            # Stop at the results table header; NOT at
                            # 'Height Difference' which appears on same lines
                            stop_patterns=[r'^\s*Rank\s+Bib|^\s*RANK\s+BIB',
                                           r'^\s*NAME\s+NSA',
                                           r'^\s*Results\s*$']
                        )
                else:
                    # Era E — jury on last page
                    last_lines = self.page_lines(pdf.pages[-1])
                    jury_start = find_line_index(
                        last_lines,
                        r'Jury\s*/\s*Competition\s+Management|Competition\s+Management'
                    )
                    if jury_start >= 0:
                        doc.jury = self.extract_jury_block(
                            last_lines, jury_start + 1,
                            stop_patterns=[r'WEATHER|Weather|TECHNICAL\s+DELEGATE\s*$',
                                           r'CHIEF\s+OF\s+COMPETITION\s*$']
                        )

                # Results — walk all pages
                is_mass_start = doc.final_phase == 'SKI_JUMPING'
                ewoxx_stats = None
                page_lines = [self.page_lines(p) for p in pdf.pages]
                if (doc.discipline or '').startswith('Team'):
                    doc.team_results, unparsed = parse_team_rof(page_lines)
                    for line in unparsed:
                        doc.parse_errors.append(f"team result list: line not understood: {line!r}")
                elif doc.discipline == 'Provisional Round':
                    pass        # a jump list filed as ROF; the PCR document carries the data
                elif is_kjump_layout(full_text):
                    doc.combined_results, ewoxx_stats, unparsed = parse_kjump_rof(pdf)
                    doc.name_order = 'given-first'
                    doc.parse_errors.extend(unparsed)
                    # K-Jump prints US-style dates through a day-first formatter
                    # ('12/09/2022' becomes 'Mon 12 Sep 2022'); the file name is right.
                    doc.competition_date = (parse_filename_metadata(self.filepath).get('date')
                                            or doc.competition_date)
                elif is_ewoxx_layout(page_lines[0]):
                    doc.combined_results, ewoxx_stats, unparsed = parse_ewoxx_rof(page_lines)
                    for line in unparsed:
                        doc.warnings.append(f"result table: line not understood: {line!r}")
                else:
                    doc.combined_results = self._extract_results(pdf, doc.format_era, is_mass_start)

                self._drop_misplaced_times(doc)

                # Weather + stats — always last page
                last_text = self.page_text(pdf.pages[-1])
                wd, cs = self.extract_weather_summary(last_text)
                doc.weather = wd
                doc.competitor_stats = cs
                if doc.name_order:
                    # the generic statistics reader does not know the K-Jump footer
                    doc.competitor_stats = cs = ewoxx_stats or CompetitorStats()
                elif ewoxx_stats and cs.ranked_athletes is None:
                    cs.entries_athletes, cs.entries_nations = ewoxx_stats.entries_athletes, ewoxx_stats.entries_nations
                    cs.ranked_athletes, cs.ranked_nations = ewoxx_stats.ranked_athletes, ewoxx_stats.ranked_nations

        except Exception as exc:
            doc.parse_errors.append(f"ROF parse error: {exc}")

        return doc

    # ── private helpers ───────────────────────────────────────────────────────

    def _detect_era(self, text: str) -> str:
        from fis_parser.detector import detect_format_era
        return detect_format_era(text, 'ROF')

    def _extract_event_name(self, text: str) -> Optional[str]:
        """Pull the main event title from the document header."""
        # Modern: 'VIESSMANN FIS NORDIC COMBINED WORLD CUP'
        for pat in [
            r'(VIESSMANN FIS NORDIC COMBINED WORLD CUP)',
            r'(FIS Nordic Combined World Cup[^\n]*)',
            r'(FIS WORLD CUP NORDIC COMBINED)',
            r'(FIS Continental Cup Nordic Combined)',
            r'("?[^"\n]+"?\s*FIS World Cup Nordic Combined)',
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return clean_name(m.group(1))
        return None

    def _drop_misplaced_times(self, doc: ParsedDocument) -> None:
        """
        In a layout this parser does not know column by column (express race,
        jump-table sprints) the numbers behind the name land in the wrong
        fields.  Rank and name are still right, so the row is kept — but a
        value that cannot be what its field says is dropped rather than
        stored as a wrong time, and the document says so.
        """
        dropped = 0
        for row, field in time_format_problems(doc.discipline, doc.combined_results):
            setattr(row, field, None)
            dropped += 1
        if dropped:
            doc.warnings.append(f"layout not fully understood: {dropped} time values dropped")

    def _apply_path_fallbacks(self, doc: ParsedDocument) -> None:
        """Fill header fields the PDF does not state from folder / file name."""
        if not doc.location or not doc.country:
            place, country = venue_from_path(self.filepath)
            doc.location = doc.location or place
            doc.country = doc.country or country
        from_name = parse_filename_metadata(self.filepath)
        if not doc.competition_date:
            doc.competition_date = from_name.get('date')
        if not doc.discipline:
            doc.discipline = from_name.get('discipline_hint')

    def _extract_discipline(self, text: str) -> Optional[str]:
        """Extract discipline from document header lines."""
        head = text[:3000]
        by_name = team_discipline_from_filename(self.filepath)
        if _TEAM_TABLE_RE.search(head) or (by_name and not _INDIVIDUAL_TABLE_RE.search(head)):
            if by_name:
                return by_name
            return 'Team Sprint' if re.search(r'Team\s+Sprint', head, re.IGNORECASE) else 'Team'
        if re.search(r'^Results\s+PCR\s*$', head, re.MULTILINE):
            return 'Provisional Round'
        # Individual formats: only the title block is searched.  Further down,
        # club names such as 'Team Tsuchiya' or 'Sprint Club' would decide.
        title = re.split(r'\bJury\b|Competition\s+Management|^\s*(?:Rank|Name)\b', text[:1500],
                         maxsplit=1, flags=re.IGNORECASE | re.MULTILINE)[0]
        for pat, disc in [
            (r'Mass\s+Start', 'Mass Start'),
            (r'Individual\s+Compact', 'Compact'),
            (r'Penalty\s+Race', 'Penalty Race'),
            (r'Express\s+Race', 'Express Race'),
            (r'Sprint', 'Sprint'),
            (r'Individual\s+Gundersen|Gundersen', 'Gundersen'),
        ]:
            if re.search(pat, title, re.IGNORECASE):
                return disc
        return None

    def _infer_final_phase(self, discipline: Optional[str]) -> str:
        if discipline and 'Mass Start' in discipline:
            return 'SKI_JUMPING'
        return 'CROSS_COUNTRY'

    # ── Results table parsing ─────────────────────────────────────────────────

    def _extract_results(self, pdf: pdfplumber.PDF, era: str, is_mass_start: bool = False) -> List[CombinedResult]:
        results: List[CombinedResult] = []
        dns_names: List[str] = []
        dnf_data: List[dict] = []
        dsq_data: List[dict] = []
        # 'DNS' / 'DNF' / 'DSQ' while such a list is still open at a page
        # break; 'END' once the block after the result list was reached.
        open_section: Optional[str] = None

        for page in pdf.pages:
            if open_section == 'END':
                break
            text = self.page_text(page)
            lines = text.splitlines()

            # Find start of result table on this page
            table_start = find_line_index(lines, r'^\s*Rank\s+Bib|^\s*RANK\s+BIB')
            if table_start < 0:
                # Could be a continuation page (page 2+) — look for numbered rows
                table_start = 0

            # Determine if we are in the result table body
            in_results = False
            in_dns = False
            in_dnf = False
            in_dsq = False

            # Use coordinate-based extraction for accurate column assignment
            # y_tol=5 merges name and rank/bib rows that are 3-5 pt apart
            words = page.extract_words()
            rows = group_words_into_rows(words, y_tol=7)

            if era in ('A', 'B', 'C', 'D', 'E'):
                # Era A uses the same NSA/NOC-scan approach as modern eras.
                # _parse_era_a_rows computes page_w per-row (wrong scale),
                # causing bib to land in the name column.
                parsed = self._parse_modern_rows(rows, era, is_mass_start, open_section)
            else:
                parsed = self._parse_era_a_rows(rows)
            open_section = parsed.get('open_section')

            results.extend(parsed['results'])
            dsq_data.extend(parsed.get('dsq', []))
            dnf_data.extend(parsed.get('dnf', []))
            dns_names.extend(parsed.get('dns', []))

        # Mass Start post-processing: time_behind currently holds raw total points;
        # convert to points diff from winner (e.g. "0.0", "+13.5").
        if is_mass_start:
            ranked = [r for r in results if r.rank is not None and r.time_behind is not None]
            winner = next((r for r in ranked if r.rank == 1), None)
            winner_total = parse_float(winner.time_behind) if winner else None
            if winner_total is not None:
                for r in ranked:
                    r_total = parse_float(r.time_behind)
                    if r_total is not None:
                        diff = r_total - winner_total
                        r.time_behind = "0.0" if diff == 0 else f"{diff:.1f}"

        # Append DNS/DNF/DSQ as results with status
        for item in dnf_data:
            results.append(CombinedResult(
                bib=item.get('bib'),
                name=item.get('name'),
                nation=item.get('nation'),
                jump_points=item.get('jump_points'),
                jump_rank=item.get('jump_rank'),
                time_difference=item.get('time_difference'),
                status='DNF',
            ))
        for item in dsq_data:
            results.append(CombinedResult(
                bib=item.get('bib'),
                name=item.get('name'),
                nation=item.get('nation'),
                status='DSQ',
            ))
        for item in dns_names:
            if isinstance(item, dict):
                results.append(CombinedResult(
                    bib=item.get('bib'),
                    name=item.get('name'),
                    nation=item.get('nation'),
                    jump_points=item.get('jump_points'),
                    jump_rank=item.get('jump_rank'),
                    time_difference=item.get('time_difference'),
                    status='DNS',
                ))
            else:
                results.append(CombinedResult(name=item, status='DNS'))

        if is_mass_start:
            _normalise_name_case(results)
        return results

    def _parse_modern_rows(self, rows: List[List[dict]], era: str, is_mass_start: bool = False,
                           open_section: Optional[str] = None) -> dict:
        """
        Parse result rows for Eras B-E (modern Swiss Timing layout).

        Table columns (approximate x positions on A4/Letter at 72dpi):
          RANK  BIB  NAME/NSA  POINTS  J_RANK  TIME_DIFF  XC_TIME  XC_RANK  T_BEHIND
          25    65   100-330   355     405     455        515      570      620

        Each athlete spans 2 word-rows:
          Row 1: rank, bib, name, NSA, points, jump_rank, time_diff, xc_time, xc_rank, time_behind
          Row 2: club, DOB
        """
        results = []
        dsq = []
        dnf = []
        dns = []

        # Compute page width once from all rows' words so scale is accurate
        # even for short rows that don't extend to the right margin.
        all_x1 = [w['x1'] for row in rows for w in row]
        page_w = max(all_x1) if all_x1 else 570.0
        scale = page_w / 720.0
        # Name column starts well right of rank/bib (≈ x=60 at 720pt reference)
        X_PRE_ROW = 60 * scale

        # State machine
        IDLE = 0
        IN_ROW1 = 1
        state = IDLE
        current = None
        # A DNS/DNF/DSQ list that started on the previous page continues here
        # without repeating its heading.
        in_dsq_section = open_section == 'DSQ'
        in_dnf_section = open_section == 'DNF'
        in_dns_section = open_section == 'DNS'
        section_carried = open_section is not None
        ended = False
        # Pre-row name/nation from separate sub-rows (some PDFs split name+NSA
        # across two lines above the data row)
        pending_pre_name: Optional[str] = None
        pending_pre_nat:  Optional[str] = None

        def is_header_row(rt: str) -> bool:
            # Catches 'RANK ... BIB', 'Rank ... Bib', and also the column header
            # 'NAME NSA SKI JUMPING CROSS-COUNTRY' that appears in era C/D/E above
            # the RANK BIB header row and must not be treated as a pre-row name.
            return bool(re.search(
                r'\bRANK\b.*\bBIB\b|\bRank\b.*\bBib\b|\bNAME\b\s+\bNSA\b',
                rt))

        def is_section_marker(rt: str) -> str:
            rt_u = rt.strip().upper()
            if re.search(r'^DISQUALIFIED|^DSQ', rt_u):
                return 'DSQ'
            if re.search(r'^DID\s+NOT\s+FINISH|^DNF', rt_u):
                return 'DNF'
            if re.search(r'^DID\s+NOT\s+START|^DNS', rt_u):
                return 'DNS'
            if re.search(r'^NOT\s+PERMITTED', rt_u):
                return 'NPS'
            # For eras A-D the jury block is on PAGE 1 *above* the results,
            # so we must NOT treat 'Jury / Competition Management' as END there.
            # For era E the jury is on the last page *after* the results.
            if re.search(r'^WEATHER', rt_u):
                return 'END'
            if era == 'E' and re.search(r'^JURY\s*/\s*COMPETITION|^TECHNICAL\s+DELEGATE', rt_u):
                return 'END'
            return ''

        def parse_result_row1(row: List[dict]) -> Optional[CombinedResult]:
            """
            Extract: rank, bib, name, NSA, points, jump_rank,
                     time_diff, xc_time, xc_rank, time_behind
            from a single word-row using x-coordinate buckets.
            """
            # page_w comes from outer scope (computed from all rows on this page)
            rank_words = []
            num_words = []  # everything to the right of NSA

            if not row:
                return None

            # Scale x-boundaries against 720pt reference width using full page width
            scale = page_w / 720.0

            # Column x boundaries (unscaled reference values for 720pt page).
            # Era B:   rank 'N.' at cx≈25-36, names at cx≈62+  → use 55
            # Era C:   rank 'N'  at cx≈47-55, names at cx≈90+ → use 70
            #          (some era C files have data rows indented further right)
            # Era D/E/A: rank 'N' at cx≈47, bib follows       → use 62
            if era == 'B':
                X_RANK_MAX = 55 * scale
            elif era == 'C':
                X_RANK_MAX = 70 * scale
            else:  # D, E, A
                X_RANK_MAX = 62 * scale

            # Collect: rank_words (leftmost), rest_words (everything else)
            rest_words = []
            for w in row:
                cx = (w['x0'] + w['x1']) / 2
                if cx < X_RANK_MAX:
                    rank_words.append(w['text'])
                else:
                    rest_words.append(w['text'])

            # Rank rescue: Era B WC and Era C early (≤2012) have rank at cx≈61–63,
            # which sits just to the right of X_RANK_MAX and lands in rest_words.
            # When rank_words is empty but rest_words[0] is a plain integer or Era B
            # dotted rank (e.g. "1."), treat it as the rank and shift it into rank_words.
            # Also rescue when rank_words contains only a flag (FF/PF/NPS) and the
            # actual rank integer is the first token in rest_words — the flag lands
            # inside the rank column while the rank number sits just outside it.
            _FLAG_TOKENS = {'FF', 'PF', 'NPS'}
            rank_rescued = False
            if not rank_words and rest_words and re.match(r'^=?\d+\.?$', rest_words[0]):   # '=3' marks a tie
                # Rank number just outside rank column (era B WC / era C early)
                rank_words = [rest_words[0]]
                rest_words = rest_words[1:]
                rank_rescued = True
            elif (rank_words and all(t in _FLAG_TOKENS for t in rank_words)
                  and rest_words and re.match(r'^\d+\.?$', rest_words[0])):
                # Flag in rank column, rank number just outside (e.g. rank_words=['FF'], rest_words[0]='19')
                rank_words = rank_words + [rest_words[0]]
                rest_words = rest_words[1:]
                rank_rescued = True
            elif (not rank_words and len(rest_words) >= 2
                  and rest_words[0] in _FLAG_TOKENS
                  and re.match(r'^\d+\.?$', rest_words[1])):
                # Both flag and rank number outside rank column (smaller page scale pushes FF right of X_RANK_MAX)
                rank_words = rest_words[:2]
                rest_words = rest_words[2:]
                rank_rescued = True

            # Detect NSA as first standalone 3-letter all-caps nation code.
            # Split rest into [pre_nsa tokens] + [nsa] + [num tokens].
            # From pre_nsa: first pure integer = bib, rest = name parts.
            # Exclude month abbreviations so DOBs like '01 JAN 1991' in era B
            # club rows don't get falsely detected as NSA codes.
            _MONTH_ABBRS = {'JAN','FEB','MAR','APR','MAY','JUN',
                            'JUL','AUG','SEP','OCT','NOV','DEC'}
            nsa_str = ''
            num_words = []
            pre_nsa: list = []
            nsa_found = False
            for tok in rest_words:
                if not nsa_found and re.match(r'^[A-Z]{3}$', tok) and tok not in _MONTH_ABBRS:
                    nsa_str = tok
                    nsa_found = True
                elif not nsa_found:
                    pre_nsa.append(tok)
                else:
                    num_words.append(tok)

            # Extract bib (first pure integer in pre_nsa) and name.
            # After bib, scan remaining tokens: if no NSA was found, numeric
            # tokens (floats, times) after the name belong in num_words.
            bib_tok = next((t for t in pre_nsa if t.isdigit()), None)
            if bib_tok:
                idx = next((i for i, t in enumerate(pre_nsa) if t == bib_tok and t.isdigit()), None)
                remaining = pre_nsa[:idx] + pre_nsa[idx+1:] if idx is not None else pre_nsa
            else:
                remaining = pre_nsa

            if nsa_found:
                # NSA found: everything in remaining = name tokens
                name_toks = remaining
                # Fallback: if NSA detection left no name tokens (only a bib was
                # in pre_nsa), the first 3-letter token was a short surname, not
                # the NSA. Example: '16 KIL Joanna POL 61.1...' → 'KIL' grabbed
                # as NSA, remaining=[]. Rescue by finding next 3-letter all-caps
                # token in num_words as the real NSA.
                if not name_toks:
                    real_nsa_idx = next(
                        (j for j, t in enumerate(num_words)
                         if re.match(r'^[A-Z]{3}$', t) and t not in _MONTH_ABBRS),
                        None
                    )
                    if real_nsa_idx is not None:
                        name_toks = [nsa_str] + num_words[:real_nsa_idx]
                        nsa_str = num_words[real_nsa_idx]
                        num_words = num_words[real_nsa_idx + 1:]
            else:
                # No NSA: split remaining at first float/time token (numeric data boundary)
                _num_pat = re.compile(r'^\d[\d.]*$|^\+?\d+:\d+')
                name_toks = []
                for tok in remaining:
                    if _num_pat.match(tok):
                        num_words = [tok] + remaining[remaining.index(tok)+1:]
                        break
                    name_toks.append(tok)

            rank_str = ' '.join(rank_words).strip('=').strip()
            bib_str = bib_tok or ''
            name_str = clean_name(' '.join(name_toks))

            # num_words should be: points, j_rank, time_diff, xc_time, xc_rank, time_behind
            nums = num_words

            # Athlete row: name must be valid AND rank column must contain a digit.
            # (Jury/header rows have text like "Race", "TD" in the rank position.)
            if not is_valid_athlete_name(name_str):
                return None
            if not re.search(r'\d', rank_str):
                return None
            # Era B COC uses 'N.' rank format (e.g. '1.', '23.').  The club row in
            # COC Era B starts with a plain bib number (no dot), so a dot-free rank
            # that was NOT rescued from rest_words means this is a club row → reject.
            # Skip this check when rank was rescued (WC Era B / Era C early layout
            # where the rank glyph sits slightly to the right of X_RANK_MAX).
            raw_rank = ' '.join(rank_words)
            if era == 'B' and not rank_rescued and not re.search(r'\d+\.', raw_rank) and \
                    not any(t in ('FF', 'PF', 'NPS') for t in rank_words):
                return None

            cr = CombinedResult()
            # Rank may be "1", "PF 2", "=3" — extract first integer
            rank_m = re.search(r'(\d+)', rank_str)
            cr.rank = int(rank_m.group(1)) if rank_m else None
            cr.bib = parse_int(bib_str)
            cr.name = name_str or None
            cr.nation = nsa_str if len(nsa_str) == 3 else None

            # Wave start: '**' appears as a separate token before time_behind.
            # Strip it before indexing so nums[5] is always the real time_behind.
            if any('**' in n for n in nums):
                cr.wave_start = True
                nums = [n for n in nums if '**' not in n]

            # Parse numeric tail
            if is_mass_start and nums and re.match(r'^\d+:\d+', nums[0]):
                # Mass Start: XC race is first, SJ is the final phase.
                # nums[0] is always the XC time (e.g. "23:27.2").
                cr.xc_time = nums[0]
                if len(nums) >= 2 and re.match(r'^\d+\.$', nums[1]):
                    # Era B style: [xc_time, xc_rank., xc_diff, race_pts, sj_pts, sj_rank., total]
                    xcr_m = re.match(r'^(\d+)', nums[1])
                    cr.xc_rank = parse_int(xcr_m.group(1)) if xcr_m else None
                    cr.time_difference = nums[2] if len(nums) > 2 else None
                    cr.jump_points = parse_float(nums[4]) if len(nums) > 4 else None
                    sjr_m = re.match(r'^(\d+)', nums[5]) if len(nums) > 5 else None
                    cr.jump_rank = parse_int(sjr_m.group(1)) if sjr_m else None
                    cr.time_behind = nums[-1]  # raw total pts, post-processed to diff
                elif len(nums) >= 2:
                    # Era C/D/E style: XC time is nums[0]; SJ round total and final total
                    # are always the last two columns.  The judge scores (A-E) may appear
                    # in the main row (len≈15) or wrap into the DOB row when the PDF lays
                    # them out slightly lower (len≈10 — style_pts only in main row).
                    # Era C (2014-2020) has no separate TOTAL column; nums[-1] = SJ total.
                    if era == 'C':
                        # Compute SJ round from dist_pts + style_pts + gate/wind_comp
                        cr.jump_points = (
                            (parse_float(nums[3]) or 0.0)
                            + (parse_float(nums[9]) or 0.0)
                            + (parse_float(nums[12]) or 0.0)
                        ) if len(nums) >= 13 else None
                    else:
                        # Era D/E: nums[-2] = SJ round total, nums[-1] = final total
                        cr.jump_points = parse_float(nums[-2])
                    cr.time_behind = nums[-1]  # raw total pts, post-processed to diff
            else:
                # Sprints 2005-2008 print the start gap twice, as time and as
                # distance in metres ('1:04 384 19:17.4'); drop the distance.
                if len(nums) >= 7 and not CLOCK_RE.match(nums[3]) and CLOCK_RE.match(nums[4]):
                    nums = nums[:3] + nums[4:]
                if len(nums) >= 6:
                    cr.jump_points = parse_float(nums[0])
                    cr.jump_rank = parse_int(nums[1])
                    cr.time_difference = nums[2]
                    cr.xc_time = nums[3]
                    cr.xc_rank = parse_int(nums[4].strip('='))
                    # The TRIPLE lists (Seefeld) have a points column between the
                    # rank and the time behind ('18 6.2 19:03.8', '1 -2.1 +8.4'):
                    # the time behind is the last value that is a time.
                    tail = [n for n in nums[5:] if FINISH_GAP_RE.match(n) or CLOCK_RE.match(n)]
                    cr.time_behind = tail[-1] if tail else nums[5]
                elif len(nums) >= 4:
                    cr.jump_points = parse_float(nums[0])
                    cr.jump_rank = parse_int(nums[1])
                    cr.time_difference = nums[2]
                    cr.xc_time = nums[3]
                elif (len(nums) == 3 and not is_mass_start
                      and nums[1].isdigit() and re.match(r'^\d+:\d{2}$', nums[2])):
                    # Lapped, old layout: jump points, jump rank and start
                    # difference are printed, the time columns stay empty.
                    cr.jump_points = parse_float(nums[0])
                    cr.jump_rank = parse_int(nums[1])
                    cr.time_difference = nums[2]
                    cr.status = 'LAP'

                # Lapped, newer layout: 'LAP' in the time column.  Lapped
                # athletes keep their printed rank but have no XC time.
                if cr.xc_time == 'LAP':
                    cr.xc_time = None
                    cr.status = 'LAP'

            return cr

        for row in rows:
            rt = row_text(row)
            if not rt.strip():
                continue
            # Footer line "printed DD MMM YYYY, HH:MM:SS Page N from N"
            if re.match(r'^\s*printed\b', rt, re.IGNORECASE):
                continue
            # Page footer: 'D MMM YYYY / Venue (NSA) / codex' — skip entirely.
            # These appear at the bottom of era E pages and can merge with the
            # last athlete row when y_tol=5, injecting venue into the name field.
            if re.match(r'^\d{1,2}\s+[A-Z]{3}\s+\d{4}\s+/', rt):
                continue
            # Timing-provider / report footer and the 'Bib Name' sub-header of
            # the DNS/DNF/DSQ lists.  A footer is not the end of the result
            # list: an open list continues on the next page.
            if _PAGE_FURNITURE_RE.search(rt):
                continue

            # Check section markers
            marker = is_section_marker(rt)
            if marker == 'END':
                ended = in_dsq_section or in_dnf_section or in_dns_section
                break
            # The DNS/DNF/DSQ lists are the last part of the result list;
            # whatever block follows them (jury, weather, legend) ends it.
            # Not checked before, because in eras A-D the jury
            # block sits on page 1 *above* the ranked athletes.
            if (in_dsq_section or in_dnf_section or in_dns_section) \
                    and _AFTER_RESULTS_RE.match(rt.strip()):
                ended = True
                break
            if (in_dsq_section or in_dnf_section or in_dns_section) and not marker \
                    and _PAGE_TITLE_RE.search(rt):
                continue
            if marker == 'DSQ':
                in_dsq_section = True
                in_dnf_section = in_dns_section = False
                state = IDLE
                continue
            if marker == 'DNF':
                in_dnf_section = True
                in_dsq_section = in_dns_section = False
                state = IDLE
                continue
            if marker in ('DNS', 'NPS'):
                in_dns_section = True
                in_dnf_section = in_dsq_section = False
                state = IDLE
                continue

            if is_header_row(rt):
                state = IDLE
                # The column header is repeated on every page; it only closes
                # a list that was opened by a (false) heading on this page.
                if not section_carried:
                    in_dsq_section = in_dnf_section = in_dns_section = False
                # Also clear any stale pre-row name (e.g. 'Official Results'
                # page header on continuation pages must not infect next athlete)
                pending_pre_name = None
                pending_pre_nat = None
                continue

            # ── DSQ / DNF / DNS rows ────────────────────────────────────────
            # Skip club/DOB rows that follow a DNF/DSQ/DNS athlete row.
            # These contain a date pattern (DD MMM YYYY or DD.MM.YYYY) and must
            # not be re-parsed as a new athlete entry.
            if (in_dsq_section or in_dnf_section or in_dns_section) and re.search(
                    r'\b\d{1,2}\s+[A-Z]{3}\s+\d{4}\b|\b\d{1,2}\.\d{2}\.\d{4}\b', rt):
                continue

            if in_dsq_section:
                # Bib may be concatenated with name (e.g. '12SMITH John SUI')
                bib_lead = re.match(r'(\d+)\s*', rt)
                bib_val = parse_int(bib_lead.group(1)) if (bib_lead and bib_lead.group(1)) else None
                remainder = rt[bib_lead.end():] if bib_lead and bib_lead.group(1) else rt
                nsa_m = re.match(r'(.+?)\s+([A-Z]{3})(?:\s|$)', remainder)
                if nsa_m:
                    nm = clean_name(nsa_m.group(1))
                    if is_valid_athlete_name(nm) and _has_surname(nm):
                        dsq.append({
                            'bib': bib_val,
                            'name': nm,
                            'nation': nsa_m.group(2),
                        })
                continue

            if in_dnf_section:
                # Bib may be concatenated with name (e.g. '45MUHLETHALER Laurent FRA')
                # Use same flexible approach as DNS: strip leading digits (with or without space)
                bib_lead = re.match(r'(\d+)\s*', rt)
                bib_val = parse_int(bib_lead.group(1)) if (bib_lead and bib_lead.group(1)) else None
                remainder = rt[bib_lead.end():] if bib_lead and bib_lead.group(1) else rt
                nsa_m = re.match(r'(.+?)\s+([A-Z]{3})(?:\s|$)', remainder)
                if nsa_m:
                    nm = clean_name(nsa_m.group(1))
                    if is_valid_athlete_name(nm) and _has_surname(nm):
                        parts = remainder[nsa_m.end():].split()
                        dnf.append({
                            'bib': bib_val,
                            'name': nm,
                            'nation': nsa_m.group(2),
                            'jump_points': parse_float(parts[0]) if parts else None,
                            'jump_rank': parse_int(parts[1]) if len(parts) > 1 else None,
                            'time_difference': parts[2] if len(parts) > 2 else None,
                        })
                continue

            if in_dns_section:
                # DNS rows may include jumping data: 'bib Name NSA [pts rank timediff]'
                # Bib may be concatenated with name (e.g. '3LAATE' from PDF extraction)
                # or absent entirely (e.g. 'GOEPFERT Trine GER Ski Jumping')
                bib_m = re.match(r'(\d+)\s*', rt)
                remainder_str = rt[bib_m.end():] if bib_m and bib_m.end() > 0 else rt
                # Only treat as bib if digits were actually found (bib_m.group(1) non-empty)
                bib_val = parse_int(bib_m.group(1)) if (bib_m and bib_m.group(1)) else None
                remainder = remainder_str.split()
                nsa_tok, name_toks, num_toks = '', [], []
                nsa_found = False
                for tok in remainder:
                    if not nsa_found and re.match(r'^[A-Z]{3}$', tok):
                        nsa_tok = tok; nsa_found = True
                    elif not nsa_found:
                        name_toks.append(tok)
                    else:
                        num_toks.append(tok)
                if nsa_found and not name_toks:
                    # Three-letter surname taken for the nation ('12 KIL Joanna POL')
                    nxt = next((j for j, t in enumerate(num_toks) if re.match(r'^[A-Z]{3}$', t)), None)
                    if nxt is not None:
                        name_toks = [nsa_tok] + num_toks[:nxt]
                        nsa_tok = num_toks[nxt]
                        num_toks = num_toks[nxt + 1:]
                parsed_name = clean_name(' '.join(name_toks))
                # Every athlete line carries the nation; lines without one are
                # remarks ('early at start') or page furniture.
                if nsa_found and is_valid_athlete_name(parsed_name) and _has_surname(parsed_name):
                    dns.append({
                        'bib': bib_val,
                        'name': parsed_name,
                        'nation': nsa_tok if len(nsa_tok) == 3 else None,
                        'jump_points': parse_float(num_toks[0]) if num_toks else None,
                        'jump_rank': parse_int(num_toks[1]) if len(num_toks) > 1 else None,
                        'time_difference': num_toks[2] if len(num_toks) > 2 else None,
                    })
                continue

            # ── Pre-row detection (name/NSA on separate sub-rows above data) ──
            # Some PDFs render the athlete's name on its own line slightly above
            # the rank/bib/data row, and the NSA on yet another line between them.
            if state == IDLE:
                row_x0 = row[0]['x0'] if row else 0
                # NSA-only sub-row immediately following a name-only pre-row
                if pending_pre_name and re.match(r'^[A-Z]{3}$', rt.strip()):
                    pending_pre_nat = rt.strip()
                    continue
                toks = rt.strip().split()
                # Era E Mass Start: name+NSA+XC-time row (no rank, but has digits
                # from times). Pattern: LASTNAME [Firstname] NSA HH:MM:SS ...
                # These rows start in the name column area (row_x0 >= X_PRE_ROW)
                # and always contain an XC time like '23:58.5'.
                if (era == 'E' and row_x0 >= X_PRE_ROW
                        and len(toks) >= 3
                        and re.match(r'^[A-Z]{2,}$', toks[0])
                        and re.search(r'\d+:\d+', rt)):
                    _MONTH_ABBRS_LOCAL = {
                        'JAN','FEB','MAR','APR','MAY','JUN',
                        'JUL','AUG','SEP','OCT','NOV','DEC',
                    }
                    nsa_cand = next(
                        (t for t in toks
                         if re.match(r'^[A-Z]{3}$', t)
                         and t not in _MONTH_ABBRS_LOCAL),
                        None
                    )
                    if nsa_cand:
                        nsa_idx = toks.index(nsa_cand)
                        name_cand = clean_name(' '.join(toks[:nsa_idx]))
                        if is_valid_athlete_name(name_cand):
                            pending_pre_name = name_cand
                            pending_pre_nat = nsa_cand
                            continue
                # Name-only pre-row: in name column area, no digits, ≤5 alpha tokens.
                # First token must be ALL-CAPS (the LASTNAME) to exclude page headers
                # like 'Official Results' which start with title-case words.
                if (row_x0 >= X_PRE_ROW and not re.search(r'\d', rt)
                        and 1 <= len(toks) <= 5
                        and toks[0] == toks[0].upper()
                        and all(re.match(r"^[A-Za-zÀ-ÿ\-']+$", t) for t in toks)):
                    nm = clean_name(rt)
                    if nm and is_valid_athlete_name(nm):
                        pending_pre_name = nm
                        pending_pre_nat = None
                        continue
                    pending_pre_name = None  # reset if row didn't qualify

            # ── State IN_ROW1: if DOB is present this is definitely a club row ──
            # Process it directly without calling parse_result_row1 to prevent
            # the era B club row (bib + club + DOB) from being misread as a new
            # athlete row (bib in rank column, month abbr as NSA, club as name).
            # Match both 'DD MMM YYYY' (modern) and 'DD.MM.YYYY' (early COC era B)
            dob_in_row = re.search(
                r'\b(\d{1,2}\s+[A-Z]{3}\s+\d{4})\b'
                r'|\b(\d{1,2}\.\d{2}\.\d{4})\b',
                rt)
            if state == IN_ROW1 and current and dob_in_row:
                dob_str = dob_in_row.group(1) or dob_in_row.group(2)
                current.date_of_birth = normalise_date(dob_str)
                club_part = rt[:dob_in_row.start()].strip()
                # Strip leading bib number (era B/E place bib before club name).
                # Capture it as the athlete's bib if not already set.
                # Use \b so it also matches when the bib is the entire club_part
                # (athlete has no club registered).
                bib_m = re.match(r'^(\d+)\b', club_part)
                if bib_m:
                    if current.bib is None:
                        current.bib = parse_int(bib_m.group(1))
                    club_part = club_part[bib_m.end():].lstrip()
                if club_part:
                    current.club = clean_name(club_part)
                # Mass Start Era C/D: DOB row has "XC_rank. XC_pts_diff [SJ_rank.]"
                # after the DOB.  Era D has 3 values (adds SJ rank), Era C has 2.
                # Handle concatenated case like "39.-24.9" (no space between rank and diff).
                if is_mass_start and current.xc_rank is None:
                    remainder_after_dob = rt[dob_in_row.end():].strip()
                    if remainder_after_dob:
                        normed = re.sub(r'(\d+\.)(-)', r'\1 \2', remainder_after_dob)
                        toks = normed.split()
                        xcr_m = re.match(r'^(\d+)', toks[0]) if toks else None
                        if xcr_m:
                            current.xc_rank = parse_int(xcr_m.group(1))
                        if len(toks) >= 2:
                            current.time_difference = toks[1]
                        # SJ rank: look for the LAST token that is a pure "N." pattern
                        # (trailing dot, no decimal digit after it).  This correctly
                        # skips wrapped judge scores (e.g. "17.0") and the Era E BEHIND
                        # value (e.g. "-0.5") that may also appear after the XC values.
                        for tok in reversed(toks[2:]):
                            if re.match(r'^\d+\.$', tok):
                                sjr_m = re.match(r'^(\d+)', tok)
                                if sjr_m:
                                    current.jump_rank = parse_int(sjr_m.group(1))
                                break
                state = IDLE
                continue

            # ── Normal result rows ──────────────────────────────────────────
            # An athlete row has a name AND a digit in the rank/bib area.
            # Try parse_result_row1 and accept if it returns a valid result.
            candidate = parse_result_row1(row)
            if candidate and candidate.name:
                if pending_pre_name:
                    candidate.name = pending_pre_name
                    if pending_pre_nat and not candidate.nation:
                        candidate.nation = pending_pre_nat
                    pending_pre_name = None
                    pending_pre_nat = None
                if current and current.name:
                    results.append(current)
                current = candidate
                # Era E Mass Start: DOB is embedded in the data row itself
                # (rank. bib CLUB DOB jump_data...).  No separate club row follows,
                # so extract club/DOB now and go straight back to IDLE.
                if dob_in_row:
                    current.date_of_birth = normalise_date(dob_in_row.group(1))
                    club_part = rt[:dob_in_row.start()].strip()
                    # Strip rank token (digits + optional dot) and bib
                    club_part = re.sub(r'^\d+\.?\s+', '', club_part)
                    club_part = re.sub(r'^\d+\s+', '', club_part)
                    if club_part:
                        current.club = clean_name(club_part)
                    state = IDLE
                else:
                    state = IN_ROW1
            elif state == IDLE:
                # Non-data row consumed without matching — clear stale pre-row
                pending_pre_name = None
                pending_pre_nat = None

            # Row 2: club + DOB (follows athlete row) — no DOB present here
            # (the DOB case is handled above; this handles club-only rows)
            elif state == IN_ROW1 and current:
                # Era B inserts a pure numeric/time row between the data row and
                # the club/DOB row (e.g. '00:00 22:23.7' = start diff + XC time).
                # Skip it without transitioning to IDLE so the club/DOB row
                # that follows can still be processed correctly.
                # If the row starts with a plain integer (bib), capture it.
                if not re.search(r'[A-Za-z]', rt):
                    first_tok = rt.strip().split()[0] if rt.strip() else ''
                    if first_tok.isdigit() and current.bib is None:
                        current.bib = parse_int(first_tok)
                    # numeric-only row — stay IN_ROW1
                else:
                    # Might just be a club with no DOB (era A)
                    if current.club is None and rt.strip():
                        current.club = clean_name(rt)
                    state = IDLE

        # Flush last result
        if current and current.name:
            results.append(current)

        still_open = ('END' if ended else 'DSQ' if in_dsq_section else 'DNF' if in_dnf_section
                      else 'DNS' if in_dns_section else None)
        return {'results': results, 'dsq': dsq, 'dnf': dnf, 'dns': dns, 'open_section': still_open}

    def _parse_era_a_rows(self, rows: List[List[dict]]) -> dict:
        """
        Era A layout (2001-~2005):
        Each athlete spans up to 2 rows:
          Row 1: rank  bib  Name  Club  NOC  jump_pts  j_rk  time_diff  xc_time  xc_rk  t_behind
        No DOB column.
        """
        results = []
        dsq = []
        dnf = []
        dns = []

        def parse_era_a_row(row: List[dict]) -> Optional[CombinedResult]:
            if not row:
                return None
            page_w = max(w['x1'] for w in row)
            scale = page_w / 720.0

            rank_words, bib_words, name_words, noc_words, num_words = [], [], [], [], []
            X_RANK_MAX = 45 * scale
            X_BIB_MAX = 85 * scale
            X_NAME_MAX = 310 * scale
            X_NOC_MAX = 360 * scale

            for w in row:
                cx = (w['x0'] + w['x1']) / 2
                if cx < X_RANK_MAX:
                    rank_words.append(w['text'])
                elif cx < X_BIB_MAX:
                    bib_words.append(w['text'])
                elif cx < X_NAME_MAX:
                    name_words.append(w['text'])
                elif cx < X_NOC_MAX:
                    noc_words.append(w['text'])
                else:
                    num_words.append(w['text'])

            rank_str = ' '.join(rank_words).strip()
            bib_str = ' '.join(bib_words).strip()
            name_str = clean_name(' '.join(name_words))
            noc_str = ' '.join(noc_words).strip()

            if not rank_str:
                return None

            cr = CombinedResult()
            cr.rank = parse_int(rank_str)
            cr.bib = parse_int(bib_str)
            cr.nation = noc_str if len(noc_str) == 3 else None

            # Split name from club (club is usually on same line in era A)
            # Heuristic: name is ALL CAPS, club follows in mixed case
            parts = name_str.split()
            name_tokens = []
            club_tokens = []
            found_lower = False
            for tok in parts:
                if not found_lower and (tok.isupper() or tok.replace('-', '').isupper()):
                    name_tokens.append(tok)
                else:
                    found_lower = True
                    club_tokens.append(tok)
            cr.name = ' '.join(name_tokens) if name_tokens else name_str
            cr.club = ' '.join(club_tokens) if club_tokens else None

            nums = num_words
            if len(nums) >= 6:
                cr.jump_points = parse_float(nums[0])
                cr.jump_rank = parse_int(nums[1])
                cr.time_difference = nums[2]
                cr.xc_time = nums[3]
                cr.xc_rank = parse_int(nums[4].strip('='))
                cr.time_behind = nums[5]

            if any('**' in n for n in nums):
                cr.wave_start = True

            return cr

        current = None
        state = 0  # 0=idle, 1=got_rank_row

        for row in rows:
            rt = row_text(row)
            if not rt.strip():
                continue

            if re.search(r'\bDid\s+Not\s+Finish\b|\bDNF\b', rt, re.IGNORECASE):
                if current and current.name:
                    results.append(current)
                    current = None
                break

            if re.match(r'^\s*\d+\s+\d+\s', rt):
                if current and current.name:
                    results.append(current)
                current = parse_era_a_row(row)
                state = 1

        if current and current.name:
            results.append(current)

        return {'results': results, 'dsq': dsq, 'dnf': dnf, 'dns': dns}
