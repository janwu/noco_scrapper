"""
Parser for RL / RL1 / PCR documents — competition ski jumping results.

OLD format  (ewoxx, ~2009-2015):
  Per-athlete row: Rank. Bib  Name  Club  Birthdate  Nation
                   Speed Rank  Dist  DP  A  B  C  D  E  JP  DT  Total

MODERN format (Swiss Timing, ~2016+):
  Similar to RLT but single competition round.
  Columns: BIB  NAME  NSA  SPEED  DIST  G/W COMP  POINTS  [RANK]
  Judges on last page (same block as RLT).
"""
import re
from typing import List, Optional

import pdfplumber

from fis_parser.models import (
    JumpRound, ParsedDocument,
)
from fis_parser.utils import (
    parse_float, parse_int, normalise_date, clean_name,
    find_line_index, group_words_into_rows, row_text, is_valid_athlete_name,
)
from fis_parser.extractors.base import BaseExtractor


class RLExtractor(BaseExtractor):

    def parse(self, doc_type: str = 'RL') -> ParsedDocument:
        doc = ParsedDocument(
            source_file=self.filepath,
            doc_type=doc_type,
        )
        self.doc = doc

        try:
            with self.open_pdf() as pdf:
                full_text = self.all_text(pdf)

                from fis_parser.detector import detect_format_era
                doc.format_era = detect_format_era(full_text, 'RL')

                hdr = self.extract_event_header(full_text)
                doc.fis_report_code = hdr.get('fis_report_code')
                doc.location = hdr.get('location')
                doc.country = hdr.get('country')
                doc.competition_date = hdr.get('competition_date')
                doc.start_time = hdr.get('start_time')
                doc.end_time = hdr.get('end_time')
                doc.report_created = hdr.get('report_created')

                doc.hill_data = self.extract_hill_data(full_text)

                # Judges + jury — on last page
                last_lines = self.page_lines(pdf.pages[-1])
                j_start = find_line_index(last_lines, r'Judges|JUDGES')
                if j_start >= 0:
                    doc.judges = self.extract_judges(last_lines, j_start + 1)

                jury_start = find_line_index(
                    last_lines,
                    r'Jury|Competition\s+Management|Competition\s+/\s*Weather'
                )
                if jury_start >= 0:
                    doc.jury = self.extract_jury_block(
                        last_lines, jury_start + 1,
                        stop_patterns=[r'Competition\s*/\s*Weather',
                                       r'Weather', r'Statistics',
                                       r'WEATHER']
                    )

                # Weather / stats
                last_text = self.page_text(pdf.pages[-1])
                wd, cs = self.extract_weather_summary(last_text)
                doc.weather = wd
                doc.competitor_stats = cs

                # Jump results
                if doc.format_era == 'OLD':
                    doc.jump_rounds = self._parse_old_format(pdf)
                else:
                    doc.jump_rounds = self._parse_modern_format(pdf)

        except Exception as exc:
            doc.parse_errors.append(f"RL parse error: {exc}")

        return doc

    # ── OLD (ewoxx) format ────────────────────────────────────────────────────

    def _parse_old_format(self, pdf: pdfplumber.PDF) -> List[JumpRound]:
        """
        Handles two sub-layouts:

        A) 2-row (classic ewoxx):
             Row 1  x0<X_BIB_MAX : rank.  bib  NAME  Nation
             Row 2  x0>X_BIB_MAX : Club  Birthdate  speed  speed_rank  dist  dp  a-e  jp  dt  total

        B) 3-row (COC/Swiss Timing with 'Nation' header, no 'NSA'):
             Pre-row  x0>X_BIB_MAX : NAME  NSA  [total]
             Data row x0<X_BIB_MAX : rank.  bib  speed  dist  dp  a-e  jp  gate  gate_pts  wind  wind_pts
             Post-row x0>X_BIB_MAX : Club  Birthdate  [time_behind]
        """
        rounds: List[JumpRound] = []

        for page in pdf.pages:
            words = page.extract_words()
            rows = group_words_into_rows(words, y_tol=3)
            page_w = max((w['x1'] for w in words), default=720)
            scale = page_w / 720.0

            # x-boundaries for old format (based on visual inspection of 2009 PDFs)
            X_RANK_MAX   = 45  * scale
            X_BIB_MAX    = 85  * scale
            X_NAME_MAX   = 295 * scale
            X_NAT_MAX    = 345 * scale
            # Everything after nation is numeric

            current: Optional[JumpRound] = None
            state = 0        # 0=idle, 1=got_data_row
            pending_name: Optional[str] = None
            pending_nat:  Optional[str] = None
            three_row_mode = False  # True when using layout B

            for row in rows:
                rt = row_text(row)
                if not rt.strip():
                    continue
                if re.search(r'^\s*(?:Bib|BIB)\s', rt):
                    continue  # header row
                # Stats section header — must check break BEFORE the Speed continue
                if re.search(r'Speed\s+\[km/h\].*Distance|Weather|Competitors', rt, re.IGNORECASE):
                    break
                if re.search(r'Speed\s+\[km', rt, re.IGNORECASE):
                    continue  # sub-header (speed column label only)

                row_x0 = row[0]['x0'] if row else 0

                # ── Pre-row detection (layout B): starts well right of rank column ──
                # Pre/post rows start at ~62-87 raw units; data rows at ~29-40.
                X_PRE_ROW = 55 * scale
                if state == 0 and row_x0 >= X_PRE_ROW and rt[0:1].isalpha():
                    toks = [w['text'] for w in row]
                    # Look for first 3-letter uppercase token after at least one name token
                    nat = None
                    name_toks = []
                    for i, tok in enumerate(toks):
                        if i > 0 and re.match(r'^[A-Z]{3}$', tok):
                            nat = tok
                            name_toks = toks[:i]
                            break
                    if nat and name_toks:
                        nm = clean_name(' '.join(name_toks))
                        if nm and is_valid_athlete_name(nm):
                            pending_name = nm
                            pending_nat = nat
                            continue
                    # Not a pre-row (no valid name+NSA) — fall through to other handlers

                # Row 1 / data row of an athlete entry: starts with 'N.' where N is rank
                # Must start in the left column (x0 < X_BIB_MAX) to avoid matching
                # statistics rows that also begin with digits but appear in the centre.
                row1_m = re.match(r'^(\d+)\.\s*$|^(\d+)\.\s+', rt)
                # Alternative: rank might be merged with bib
                row1_alt = re.match(r'^(\d+)\s+(\d+)\s+', rt)

                if (row1_m or row1_alt) and row_x0 < X_BIB_MAX:
                    if current and current.name:
                        rounds.append(current)
                    current = JumpRound(round_number=1)

                    if pending_name:
                        # Layout B: name already stored from pre-row
                        current.name = pending_name
                        current.nation = pending_nat
                        pending_name = None
                        pending_nat = None
                        three_row_mode = True

                        # Parse rank and bib from token list
                        toks = [w['text'] for w in row]
                        rank_str = toks[0].rstrip('.')
                        current.rank = parse_int(rank_str)
                        bib_idx = 1
                        if len(toks) > 1 and toks[1].isdigit():
                            current.bib = parse_int(toks[1])
                            bib_idx = 2
                        # All remaining tokens are numeric (speed dist dp judges gate wind)
                        nums = toks[bib_idx:]
                        # Layout: speed dist dp a b c d e jp gate gate_pts wind wind_pts [behind]
                        if len(nums) >= 2:
                            current.speed_kmh = parse_float(nums[0])
                            current.distance_m = parse_float(nums[1])
                        if len(nums) >= 9:
                            current.dist_points = parse_float(nums[2])
                            current.judge_a = parse_float(nums[3])
                            current.judge_b = parse_float(nums[4])
                            current.judge_c = parse_float(nums[5])
                            current.judge_d = parse_float(nums[6])
                            current.judge_e = parse_float(nums[7])
                            current.style_points = parse_float(nums[8])
                        if len(nums) >= 13:
                            current.total_points = parse_float(nums[12])
                        state = 1

                    else:
                        # Layout A: name is on this row via column positions
                        three_row_mode = False
                        rank_words, bib_words, name_words, nat_words, num_words = [], [], [], [], []
                        for w in row:
                            cx = (w['x0'] + w['x1']) / 2
                            if cx < X_RANK_MAX:
                                rank_words.append(w['text'])
                            elif cx < X_BIB_MAX:
                                bib_words.append(w['text'])
                            elif cx < X_NAME_MAX:
                                name_words.append(w['text'])
                            elif cx < X_NAT_MAX:
                                nat_words.append(w['text'])
                            else:
                                num_words.append(w['text'])

                        rank_str = ' '.join(rank_words).rstrip('.')
                        current.rank = parse_int(rank_str)
                        current.bib = parse_int(' '.join(bib_words))
                        current.name = clean_name(' '.join(name_words))
                        nat = ' '.join(nat_words).strip()
                        current.nation = nat if len(nat) == 3 else None
                        state = 1

                elif state == 1 and current:
                    # Post-row / Row 2: Club  Birthdate  [nums for layout A]
                    club_words, num_words2 = [], []
                    for w in row:
                        cx = (w['x0'] + w['x1']) / 2
                        if cx < X_NAT_MAX:
                            club_words.append(w['text'])
                        else:
                            num_words2.append(w['text'])

                    club_str = ' '.join(club_words)
                    # Extract DOB from club string
                    dob_m = re.search(r'(\d{2}\.\d{2}\.\d{4}|\d{1,2}\s+[A-Z]{3}\s+\d{4})', club_str)
                    if dob_m:
                        current.date_of_birth = normalise_date(dob_m.group(1))
                        current.club = clean_name(club_str[:dob_m.start()])
                    else:
                        current.club = clean_name(club_str)

                    if not three_row_mode:
                        # Layout A: numeric fields on this row
                        # Format: speed speed_rank dist dp a b c d e jp dt total
                        nums = num_words2
                        if len(nums) >= 13:
                            current.speed_kmh = parse_float(nums[0])
                            # nums[1] is speed rank — skip
                            current.distance_m = parse_float(nums[2])
                            current.dist_points = parse_float(nums[3])
                            current.judge_a = parse_float(nums[4])
                            current.judge_b = parse_float(nums[5])
                            current.judge_c = parse_float(nums[6])
                            current.judge_d = parse_float(nums[7])
                            current.judge_e = parse_float(nums[8])
                            current.style_points = parse_float(nums[9])
                            current.pursuit_time_diff = nums[10]   # DT
                            current.total_points = parse_float(nums[11])
                        elif len(nums) >= 6:
                            current.speed_kmh = parse_float(nums[0])
                            current.distance_m = parse_float(nums[1])
                    state = 0
                    three_row_mode = False

            if current and current.name:
                rounds.append(current)

        return rounds

    # ── MODERN (Swiss Timing) format ──────────────────────────────────────────

    @staticmethod
    def _collapse_spaced(words: list, gap_threshold: float = 1.5) -> list:
        """
        Collapse letter-spaced PDF tokens into proper words using x-position gaps.

        In 2024/2026 RL PDFs each character may be a separate pdfplumber word.
        Adjacent characters within the same word have x-gap ≈ 0; word boundaries
        have gaps ≥ 2 pts.  We merge tokens whose left edge is within gap_threshold
        of the previous token's right edge.

        Accepts either pdfplumber word-dicts (with x0/x1 keys) or plain strings.
        When plain strings are passed, falls back to a simple ≤3-char alpha merge.
        """
        if not words:
            return []
        # Detect whether we have word-dicts or plain strings
        if isinstance(words[0], dict):
            result: list = []
            current = words[0]['text']
            for i in range(1, len(words)):
                gap = words[i]['x0'] - words[i - 1]['x1']
                if gap <= gap_threshold:
                    current += words[i]['text']
                else:
                    result.append(current)
                    current = words[i]['text']
            result.append(current)
            return result
        # Fallback: plain string list — merge consecutive ≤3-char alpha tokens
        result2: list = []
        run: list = []
        for tok in words:
            if len(tok) <= 3 and re.match(r'^[A-Za-z]+$', tok):
                run.append(tok)
            else:
                if run:
                    result2.append(''.join(run))
                    run = []
                result2.append(tok)
        if run:
            result2.append(''.join(run))
        return result2

    def _parse_modern_format(self, pdf: pdfplumber.PDF) -> List[JumpRound]:
        """
        Modern RL (competition round) has one round per athlete, in a 3-row layout:
          Pre-row  (x0 ≥ X_PRE_ROW) : NAME  NSA  [total]
          Data row (x0 <  X_PRE_ROW) : rank.  bib  [time_adj]  speed  dist  …
          Post-row (x0 ≥ X_PRE_ROW) : CLUB  DOB

        Pre-row and data row are ~3-4 pt apart vertically; y_tol=3 keeps them
        separate so we can apply _collapse_spaced to the pre-row (needed for
        2024/2026 formats where each letter is a separate PDF glyph).
        """
        rounds: List[JumpRound] = []

        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            # y_tol=3 keeps pre-row and data row separate (they are ~3-4 pt apart).
            rows = group_words_into_rows(words, y_tol=3)
            page_w = max(w['x1'] for w in words)
            scale = page_w / 720.0

            # Rank is detected as the first token if it looks like a rank number.
            _rank_tok_re = re.compile(r'^=?\d{1,3}\.?$')
            # Pre/post rows start to the right of the rank/bib column.
            X_PRE_ROW = 55 * scale

            current: Optional[JumpRound] = None
            state = 0
            pending_name: Optional[str] = None
            pending_nat:  Optional[str] = None
            in_dsq_section = False

            for row in rows:
                rt = row_text(row)
                if not rt.strip():
                    continue
                if re.search(r'\bBIB\b.*\bNAME\b|\bNAME\b.*\bNSA\b|\bRANK\b.*\bBIB\b',
                             rt, re.IGNORECASE):
                    continue
                if re.search(r'\[km/h\]|\[m\]', rt, re.IGNORECASE):
                    continue
                if re.search(r'\bWeather\b|\bWEATHER\b|\bStatistics\b|\bLegend\b',
                             rt, re.IGNORECASE):
                    break
                if re.match(r'^\s*printed\b', rt, re.IGNORECASE):
                    continue

                # ── DSQ section ──
                if re.match(r'^\s*Disqualified\b', rt, re.IGNORECASE):
                    if current and current.name:
                        rounds.append(current)
                        current = None
                    state = 0
                    in_dsq_section = True
                    continue
                if in_dsq_section:
                    # Header row or footer — skip
                    if re.match(r'^\s*(?:Bib\b|printed\b|data\s+processing)', rt, re.IGNORECASE):
                        continue
                    # DSQ row: "bib  name...  reason_code [reason_text]"
                    toks = rt.strip().split()
                    if toks and toks[0].isdigit():
                        bib_val = parse_int(toks[0])
                        rest = toks[1:]
                        name_toks_dsq: list = []
                        reason_parts: list = []
                        for tok in rest:
                            if not reason_parts and re.match(r'^[A-Za-zÀ-ÿ\-\']+$', tok):
                                name_toks_dsq.append(tok)
                            else:
                                reason_parts.append(tok)
                        nm = clean_name(' '.join(name_toks_dsq))
                        if nm and is_valid_athlete_name(nm):
                            jr = JumpRound(round_number=1)
                            jr.bib = bib_val
                            jr.name = nm
                            jr.dsq = True
                            jr.dsq_reason = ' '.join(reason_parts) if reason_parts else None
                            rounds.append(jr)
                    continue

                row_x0 = row[0]['x0'] if row else 0
                all_toks = [w['text'] for w in row]

                # ── Pre-row detection (state=0, far-right row starting with alpha) ──
                if state == 0 and row_x0 >= X_PRE_ROW and rt[0:1].isalpha():
                    collapsed = self._collapse_spaced(row)  # pass word-dicts for x-gap merge
                    # Find first 3-letter all-caps token after at least one name token
                    nsa = None
                    name_toks: list = []
                    for i, tok in enumerate(collapsed):
                        if i > 0 and re.match(r'^[A-Z]{3}$', tok):
                            nsa = tok
                            name_toks = collapsed[:i]
                            break
                    if nsa:
                        nm = clean_name(' '.join(name_toks))
                        if nm and is_valid_athlete_name(nm):
                            pending_name = nm
                            pending_nat = nsa
                            continue  # wait for the data row

                # ── Data row: starts with a rank number ──
                if all_toks and _rank_tok_re.match(all_toks[0]):
                    rest_words = all_toks[1:]
                    bib_tok = next((t for t in rest_words if t.isdigit()), None)
                    if bib_tok:
                        bib_idx = next(
                            (i for i, t in enumerate(rest_words) if t == bib_tok and t.isdigit()),
                            None
                        )
                        num_words = rest_words[bib_idx + 1:] if bib_idx is not None else rest_words
                    else:
                        num_words = rest_words

                    if pending_name:
                        # 3-row layout: name came from the pre-row
                        if current and current.name:
                            rounds.append(current)
                        current = JumpRound(round_number=1)
                        current.name = pending_name
                        current.nation = pending_nat
                        rank_m = re.search(r'(\d+)', all_toks[0])
                        if rank_m:
                            current.rank = int(rank_m.group(1))
                        current.bib = parse_int(bib_tok) if bib_tok else None
                        self._assign_jump_nums(current, num_words)
                        pending_name = None
                        pending_nat = None
                        state = 1

                    else:
                        # Fallback: try to extract name from this row via NSA scan.
                        # (Handles edge cases or formats not seen during development.)
                        nsa_str = ''
                        num_words2: list = []
                        pre_nsa: list = []
                        nsa_found = False
                        for tok in rest_words:
                            if not nsa_found and re.match(r'^[A-Z]{3}$', tok):
                                nsa_str = tok
                                nsa_found = True
                            elif not nsa_found:
                                pre_nsa.append(tok)
                            else:
                                num_words2.append(tok)

                        bib_tok2 = next((t for t in pre_nsa if t.isdigit()), None)
                        if bib_tok2:
                            idx2 = next(
                                (i for i, t in enumerate(pre_nsa) if t == bib_tok2 and t.isdigit()),
                                None
                            )
                            remaining = pre_nsa[:idx2] + pre_nsa[idx2 + 1:] if idx2 is not None else pre_nsa
                        else:
                            remaining = pre_nsa

                        if nsa_found:
                            name_toks2 = remaining
                        else:
                            _num_pat = re.compile(r'^\d[\d.]*$|^\+?\d+:\d+')
                            name_toks2 = []
                            for tok in remaining:
                                if _num_pat.match(tok):
                                    num_words2 = [tok] + remaining[remaining.index(tok) + 1:]
                                    break
                                name_toks2.append(tok)

                        rank_str = all_toks[0]
                        name_str = clean_name(' '.join(name_toks2))
                        if is_valid_athlete_name(name_str):
                            if current and current.name:
                                rounds.append(current)
                            current = JumpRound(round_number=1)
                            rank_m = re.search(r'(\d+)', rank_str)
                            if rank_m:
                                current.rank = int(rank_m.group(1))
                            current.bib = parse_int(bib_tok2) if bib_tok2 else None
                            current.name = name_str
                            current.nation = nsa_str if len(nsa_str) == 3 else None
                            self._assign_jump_nums(current, num_words2)
                            state = 1

                elif state == 1 and current:
                    # Post-row: Club  DOB  (may be letter-spaced in 2024/2026 format)
                    collapsed_post = ' '.join(self._collapse_spaced(row))
                    dob_m = re.search(r'\b(\d{1,2}\s+[A-Z]{3}\s+\d{4})\b', collapsed_post)
                    if dob_m:
                        current.date_of_birth = normalise_date(dob_m.group(1))
                        current.club = clean_name(collapsed_post[:dob_m.start()])
                    else:
                        if collapsed_post.strip() and not re.match(r'^\s*\d+\s*$', collapsed_post):
                            current.club = clean_name(collapsed_post)
                    state = 0

            if current and current.name:
                rounds.append(current)

        return rounds

    def _assign_jump_nums(self, jr: JumpRound, nums: List[str]) -> None:
        """
        Assign numeric token list to JumpRound fields.

        Modern RL with judges (14+ tokens):
          speed dist dist_pts A B C D E style_pts gate gate_pts wind wind_comp total [time_diff]

        Old PCR/RL judge format (10-13 tokens, no gate compensation columns):
          speed dist dist_pts A B C D E style_pts total [time_diff]

        Modern RL without judges (6-7 tokens):
          speed dist gate wind wind_comp total [rank]
        """
        clean = [n for n in nums if n not in ('*', '') and re.search(r'\d', n)]
        if not clean:
            return
        try:
            jr.speed_kmh = parse_float(clean[0])
            if len(clean) < 2:
                return
            jr.distance_m = parse_float(clean[1])
            if len(clean) >= 14:
                # Full modern judge format (with gate+wind compensation columns)
                jr.dist_points   = parse_float(clean[2])
                jr.judge_a       = parse_float(clean[3])
                jr.judge_b       = parse_float(clean[4])
                jr.judge_c       = parse_float(clean[5])
                jr.judge_d       = parse_float(clean[6])
                jr.judge_e       = parse_float(clean[7])
                jr.style_points  = parse_float(clean[8])
                jr.gate          = parse_int(clean[9])
                jr.gate_comp_pts = parse_float(clean[10])
                jr.wind_ms       = parse_float(clean[11])
                jr.wind_comp_pts = parse_float(clean[12])
                jr.total_points  = parse_float(clean[13])
                if len(clean) >= 15:
                    jr.pursuit_time_diff = clean[14]
            elif len(clean) >= 10:
                # Old judge format (no gate compensation): dist_pts + 5 judges + style + total
                jr.dist_points   = parse_float(clean[2])
                jr.judge_a       = parse_float(clean[3])
                jr.judge_b       = parse_float(clean[4])
                jr.judge_c       = parse_float(clean[5])
                jr.judge_d       = parse_float(clean[6])
                jr.judge_e       = parse_float(clean[7])
                jr.style_points  = parse_float(clean[8])
                jr.total_points  = parse_float(clean[9])
                if len(clean) >= 11:
                    jr.pursuit_time_diff = clean[10]
            elif len(clean) >= 6:
                # Minimal format: speed dist gate wind wind_comp total [rank]
                jr.gate          = parse_int(clean[2])
                jr.wind_ms       = parse_float(clean[3])
                jr.wind_comp_pts = parse_float(clean[4])
                jr.total_points  = parse_float(clean[5])
                if len(clean) >= 7:
                    jr.rank = parse_int(clean[6].strip('='))
            elif len(clean) >= 3:
                jr.gate = parse_int(clean[2])
        except (ValueError, IndexError):
            pass
