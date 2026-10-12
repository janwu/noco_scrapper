"""
Parser for RLTR (Results Trial Round) documents.

Trial round = practice jump before the competition.
Layout is similar to RLT (training) but typically:
  - One or two rounds
  - No style points (no A-E judge scores)
  - Minimal columns: BIB  NAME  NSA  SPEED  DIST  GATE  WIND  [COMP]  [POINTS]
  - Last page: jury + weather (same structure as RL/RLT)
"""
import re
from typing import List, Optional

import pdfplumber

from fis_parser.models import JumpRound, ParsedDocument
from fis_parser.utils import (
    parse_float, parse_int, normalise_date, clean_name,
    find_line_index, group_words_into_rows, row_text, is_valid_athlete_name,
)
from fis_parser.extractors.base import BaseExtractor


class RLTRExtractor(BaseExtractor):

    def parse(self) -> ParsedDocument:
        doc = ParsedDocument(
            source_file=self.filepath,
            doc_type='RLTR',
        )
        self.doc = doc

        try:
            with self.open_pdf() as pdf:
                full_text = self.all_text(pdf)

                from fis_parser.detector import detect_format_era
                doc.format_era = detect_format_era(full_text, 'RLTR')

                hdr = self.extract_event_header(full_text)
                doc.fis_report_code = hdr.get('fis_report_code')
                doc.location = hdr.get('location')
                doc.country = hdr.get('country')
                doc.competition_date = hdr.get('competition_date')
                doc.start_time = hdr.get('start_time')
                doc.end_time = hdr.get('end_time')
                doc.report_created = hdr.get('report_created')

                doc.hill_data = self.extract_hill_data(full_text)

                # Jury + judges on last page
                last_page = pdf.pages[-1]
                last_text = self.page_text(last_page)
                last_lines = last_text.splitlines()

                jury_start = find_line_index(
                    last_lines,
                    r'Competition\s+Management|Jury\s*/\s*Competition|Jury'
                )
                if jury_start >= 0:
                    doc.jury = self.extract_jury_block(
                        last_lines, jury_start + 1,
                        stop_patterns=[r'Judges|JUDGES|Competition\s*/\s*Weather',
                                       r'^[A-E]\s+\w']
                    )

                j_start = find_line_index(last_lines, r'\bJudges\b|\bJUDGES\b')
                if j_start >= 0:
                    doc.judges = self.extract_judges(last_lines, j_start + 1)

                wd, cs = self.extract_weather_summary(last_text)
                doc.weather = wd
                doc.competitor_stats = cs

                doc.jump_rounds = self._parse_trial_rounds(pdf)

        except Exception as exc:
            doc.parse_errors.append(f"RLTR parse error: {exc}")

        return doc

    def _parse_trial_rounds(self, pdf: pdfplumber.PDF) -> List[JumpRound]:
        """
        Parse trial round jump table.
        Layout varies: some files have 1 round, some have 2 side-by-side (like RLT).
        We detect based on whether there is a '2ND ROUND' header on the page.
        """
        # Check full text first to decide layout
        rounds: List[JumpRound] = []

        first_page_words = pdf.pages[0].extract_words() if pdf.pages else []
        first_page_text = ' '.join(w['text'] for w in first_page_words)
        two_round = bool(re.search(r'2\s*ND\s+ROUND|2ND\s+ROUND', first_page_text, re.IGNORECASE))

        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            rows = group_words_into_rows(words, y_tol=3)
            if not rows:
                continue
            page_w = max(w['x1'] for w in words)
            scale = page_w / 720.0

            if two_round:
                rounds.extend(self._parse_two_round_page(rows, scale))
            else:
                rounds.extend(self._parse_one_round_page(rows, scale))

        return rounds

    @staticmethod
    def _split_name_nsa_nums(rt: str):
        """
        Split a row like 'SMITH Tyler USA 88.6 77.0 18' into
        (name, nation, num_tokens).  Returns (None, None, []) if not an athlete row.
        Row must start with an all-caps surname (≥2 chars).
        """
        stripped = rt.strip()
        if not re.match(r'^[A-Z]{2,}', stripped):
            return None, None, []
        tokens = stripped.split()
        pre: list = []
        nums: list = []
        in_num = False
        for tok in tokens:
            clean = tok.strip('.,*')
            if not in_num and re.match(r'^-?[\d]+[\.,][\d]+$', clean):
                in_num = True
            if in_num:
                nums.append(tok)
            else:
                pre.append(tok)
        if not nums:
            return None, None, []
        # Find first NSA: 3-letter uppercase token with at least one prior token (i > 0)
        # This prevents 3-letter surnames (AAM, LEE) from being misidentified as NSA.
        nation = None
        name_end = len(pre)
        for i, tok in enumerate(pre):
            if i > 0 and re.match(r'^[A-Z]{3}$', tok):
                nation = tok
                name_end = i
                break
        name = clean_name(' '.join(pre[:name_end]))
        return name, nation, nums

    _NSA_RE = re.compile(r'^[A-Z]{3}$')
    _RANK_TOK_RE = re.compile(r'^=?\d+\.$')      # rank annotation like "2." or "=9."
    _DECIMAL_RE = re.compile(r'^-?[\d]+[\.,][\d]+$')

    @staticmethod
    def _is_nsa(tok: str, i: int, tokens: list) -> bool:
        """
        Decide if tok (at position i in tokens) is an NSA code.
        Heuristic: must be 3-letter all-uppercase AND either
          - at least one name token precedes it (i > 0), OR
          - the very next token is a decimal number (speed/distance).
        This prevents mistaking 3-letter surnames (AAM, LEE) for NSA codes.
        """
        if not re.match(r'^[A-Z]{3}$', tok):
            return False
        if i > 0:
            return True
        # i == 0: only treat as NSA if immediately followed by a decimal
        for t in tokens[1:4]:
            if re.match(r'^-?[\d]+[\.,][\d]+$', t.strip('.,*')):
                return True
        return False

    @staticmethod
    def _nsa_split(tokens):
        """
        Scan tokens for the first NSA code (using _is_nsa heuristic).
        Returns (name_str, nation, remaining_tokens).
        Name tokens are letter-based tokens before the NSA.
        """
        name_toks = []
        for i, tok in enumerate(tokens):
            if RLTRExtractor._is_nsa(tok, i, tokens):
                return clean_name(' '.join(name_toks)), tok, tokens[i + 1:]
            if re.match(r'^[A-Za-z]', tok) or tok in ("'", '-'):
                name_toks.append(tok)
        return clean_name(' '.join(name_toks)), None, []

    def _extract_two_athletes(self, all_toks):
        """
        Try to extract up to two athletes from a flat token list.
        Used for two-athletes-per-row formats.
        Returns list of (bib, name, nation, nums) – bib may be None.
        """
        athletes = []
        pos = 0
        n = len(all_toks)
        while pos < n and len(athletes) < 2:
            # Optional leading bib
            bib = None
            if pos < n and all_toks[pos].isdigit() and not self._RANK_TOK_RE.match(all_toks[pos]):
                nxt = all_toks[pos + 1] if pos + 1 < n else ''
                if re.match(r'^[A-Za-z]', nxt):
                    bib = parse_int(all_toks[pos])
                    pos += 1
                else:
                    break

            # Collect name + NSA
            name_toks = []
            nation = None
            while pos < n:
                tok = all_toks[pos]
                if self._is_nsa(tok, len(name_toks), [tok] + all_toks[pos + 1:]):
                    nation = tok
                    pos += 1
                    break
                if self._DECIMAL_RE.match(tok.strip('.,*')):
                    break
                if self._RANK_TOK_RE.match(tok):
                    break
                if tok.isdigit():
                    break
                if re.match(r'^[A-Za-z]', tok) or tok in ("'", '-'):
                    name_toks.append(tok)
                pos += 1

            nm = clean_name(' '.join(name_toks))
            if not nm or not is_valid_athlete_name(nm):
                break

            # Collect numerics; stop at next athlete's start (decimal followed by uppercase)
            nums = []
            while pos < n:
                tok = all_toks[pos]
                if self._RANK_TOK_RE.match(tok):
                    pos += 1
                    continue
                # Stop at integer+letter = next athlete's bib
                if tok.isdigit() and pos + 1 < n and re.match(r'^[A-Za-z]', all_toks[pos + 1]):
                    break
                # Stop at decimal followed by an uppercase-start word (next athlete begins)
                if (self._DECIMAL_RE.match(tok.strip('.,*')) and pos + 1 < n
                        and re.match(r'^[A-Z][a-z]', all_toks[pos + 1])):
                    nums.append(tok)
                    pos += 1
                    break
                nums.append(tok)
                pos += 1

            athletes.append((bib, nm, nation, nums))

        return athletes

    def _parse_one_round_page(self, rows, scale: float) -> List[JumpRound]:
        """
        Single-round trial.  Handles multiple layout variants:
          Old WC bib-first two-per-row: bib1 NAME1 NSA1 nums bib2 NAME2 NSA2 nums
          Old COC name-first two-per-row: NAME1 NSA1 nums NAME2 NSA2 nums / bib row
          New COC rank+bib (2022+):  pre-row(name NSA) / rank bib [team] nums / club dob
          Standard bib-first: bib NAME NSA nums
        """
        rounds: List[JumpRound] = []

        # Rows starting in the "name column" (x > X_NAME_START) are pre/post rows
        X_NAME_START = 65 * scale

        current: Optional[JumpRound] = None
        pending_name: Optional[str] = None   # name waiting for rank+bib row
        pending_nat:  Optional[str] = None
        state: object = 0  # 0=idle, 1=got athlete, 'nf'=name-first wants bib

        for row in rows:
            rt = row_text(row)
            if not rt.strip():
                continue
            if re.search(r'\bWEATHER\b|\bStatistics\b|\bLegend\b', rt, re.IGNORECASE):
                break
            if re.match(r'^\s*printed\b', rt, re.IGNORECASE):
                continue
            if re.search(r'Jury\s*/\s*Competition|Competition\s+Management|'
                         r'RACE\s+DIRECTOR|TECHNICAL\s+DELEGATE|CHIEF\s+OF\s+COMPETITION|'
                         r'COORDINATOR|ASSISTANT\s+TD|ASSISTANT\s+RD|EQUIPMENT\s+CONTROLLER|'
                         r'NATIONAL\s+TD|VIDEO\s+MEASUREMENTS|Judges\s+Hill|WIND\s+FACTORS|'
                         r'SECONDS\s+PER|POINTS\s+PER\s+MINUTE|GATE\s+FACTOR|METER\s+VALUE|'
                         r'K[-\s]POINT|HILL\s+SIZE|WIND\s+FACTOR|HILL[-\s]SIZE',
                         rt, re.IGNORECASE):
                continue
            if re.search(r'\bBIB\b.*\bNAME\b|\bBibName\b|\bRank\b.*\bBib\b.*\bName\b|'
                         r'\bNAME\b.*\bNATION\b|\bSPEED\b.*\bDIST\b|\bBib\b.*\bName\b.*\bNat\b',
                         rt, re.IGNORECASE):
                continue
            if re.search(r'\[km/h\].*\[m\]|Club.*Date.*of.*birth|CLUB.*DATE.*OF.*BIRTH', rt, re.IGNORECASE):
                continue
            # Skip pure rank rows like "=13. =30. -2.0 35."
            if re.match(r'^\s*=?\d+\.\s', rt):
                continue

            toks = rt.strip().split()
            if not toks:
                continue

            row_x0 = row[0]['x0'] if row else 0.0

            # ── Pre/Post row: first token starts in name column (not at leftmost) ──
            if row_x0 >= X_NAME_START and toks[0][:1].isalpha():
                if state == 0:
                    # Possible pre-row for rank+bib format, or name-first row with numbers
                    nm, nat, remaining = self._nsa_split(toks)
                    if nm and is_valid_athlete_name(nm):
                        if not remaining or all(
                                not re.match(r'^[A-Za-z]', t) for t in remaining):
                            # Pure name row (no name-like tokens after NSA) → pre-row
                            pending_name = nm
                            pending_nat = nat
                            continue
                        else:
                            # Name-first row with numbers: old-style athlete
                            nums = [t for t in remaining if not self._RANK_TOK_RE.match(t)]
                            if current and current.name:
                                rounds.append(current)
                            current = JumpRound(round_number=1)
                            current.name = nm
                            current.nation = nat
                            self._assign_trial_nums(current, nums)
                            state = 'nf'
                            continue
                elif state in (1, 'nf') and current:
                    # Post-row: club / date-of-birth
                    dob_m = (re.search(r'\b(\d{1,2}\s+[A-Z]{3}\s+\d{4})\b', rt) or
                             re.search(r'\b(\d{2}/\d{2}/\d{4})\b', rt))
                    if dob_m:
                        current.date_of_birth = normalise_date(dob_m.group(1))
                        current.club = clean_name(rt[:dob_m.start()])
                    elif rt.strip() and not rt.strip().isdigit():
                        current.club = clean_name(rt)
                    state = 0
                    continue
                else:
                    continue

            # ── Bib row for name-first format ──
            if state == 'nf' and current and toks[0].isdigit():
                current.bib = parse_int(toks[0])
                state = 1
                continue

            if not toks[0].isdigit():
                # ── Name-first (all-caps surname at left margin) ──
                nm, nat, nums = self._split_name_nsa_nums(rt)
                if nm and is_valid_athlete_name(nm):
                    if current and current.name:
                        rounds.append(current)
                    current = JumpRound(round_number=1)
                    current.name = nm
                    current.nation = nat
                    clean_nums = [t for t in nums if not self._RANK_TOK_RE.match(t)]
                    self._assign_trial_nums(current, clean_nums)
                    state = 'nf'

                    # Two-athletes-per-row: check for a second athlete in nums
                    for bib2, nm2, nat2, nums2 in self._extract_two_athletes(nums)[1:]:
                        jr2 = JumpRound(round_number=1)
                        jr2.bib = bib2
                        jr2.name = nm2
                        jr2.nation = nat2
                        self._assign_trial_nums(jr2, [t for t in nums2 if not self._RANK_TOK_RE.match(t)])
                        rounds.append(jr2)
                continue

            # ── Row starts with digit(s) ──

            # Two digits at start → rank + bib (new COC format with separate rank column)
            if len(toks) >= 2 and toks[1].isdigit() and not self._RANK_TOK_RE.match(toks[1]):
                rank_val = parse_int(toks[0])
                bib_val  = parse_int(toks[1])
                remaining_toks = toks[2:]

                if pending_name:
                    # Name on pre-row; data row has rank + bib + [team text] + nums
                    if current and current.name:
                        rounds.append(current)
                    current = JumpRound(round_number=1)
                    current.name   = pending_name
                    current.nation = pending_nat
                    current.rank   = rank_val
                    current.bib    = bib_val
                    num_toks = [t for t in remaining_toks
                                if self._DECIMAL_RE.match(t.strip('.,*')) or
                                (t.isdigit() and 1 <= int(t) <= 30)]
                    self._assign_trial_nums(current, num_toks)
                    pending_name = pending_nat = None
                    state = 1
                    continue
                else:
                    # Name may be embedded in remaining tokens (2026 format)
                    nm, nat, nums = self._nsa_split(remaining_toks)
                    if nm and is_valid_athlete_name(nm):
                        if current and current.name:
                            rounds.append(current)
                        current = JumpRound(round_number=1)
                        current.name   = nm
                        current.nation = nat
                        current.rank   = rank_val
                        current.bib    = bib_val
                        clean_nums = [t for t in nums if not self._RANK_TOK_RE.match(t)]
                        self._assign_trial_nums(current, clean_nums)
                        pending_name = pending_nat = None
                        state = 1
                        continue
                continue

            # Single digit at start → bib-first (one or two athletes on row)
            bib_val = parse_int(toks[0])
            remaining_toks = toks[1:]

            # If pending_name + single bib: this is name-first format (bib on its own row)
            if pending_name and not remaining_toks:
                if current and current.name:
                    rounds.append(current)
                current = JumpRound(round_number=1)
                current.name   = pending_name
                current.nation = pending_nat
                current.bib    = bib_val
                pending_name = pending_nat = None
                state = 1
                continue

            athletes = self._extract_two_athletes(remaining_toks)
            if not athletes and pending_name:
                # Bib row with no further name tokens, but pending name waiting
                if current and current.name:
                    rounds.append(current)
                current = JumpRound(round_number=1)
                current.name   = pending_name
                current.nation = pending_nat
                current.bib    = bib_val
                pending_name = pending_nat = None
                state = 1
                continue

            for idx, (_, nm, nat, nums) in enumerate(athletes):
                if not nm or not is_valid_athlete_name(nm):
                    continue
                if current and current.name:
                    rounds.append(current)
                current = JumpRound(round_number=1)
                current.bib    = bib_val if idx == 0 else None
                current.name   = nm
                current.nation = nat
                clean_nums = [t for t in nums if not self._RANK_TOK_RE.match(t)]
                self._assign_trial_nums(current, clean_nums)
                state = 1
                bib_val = None  # only first athlete gets the leading bib

        if current and current.name:
            rounds.append(current)

        return rounds

    def _parse_two_round_page(self, rows, scale: float) -> List[JumpRound]:
        """Two-round trial side-by-side layout (same as RLT)."""
        rounds: List[JumpRound] = []

        X_BIB_MAX  = 80  * scale
        X_NAME_MAX = 310 * scale
        X_NSA_MAX  = 390 * scale
        X_MID      = 560 * scale

        current_r1: Optional[JumpRound] = None
        current_r2: Optional[JumpRound] = None
        state = 0

        for row in rows:
            rt = row_text(row)
            if not rt.strip():
                continue
            if re.search(r'\bWeather\b|\bWEATHER\b|\bStatistics\b|\bLegend\b', rt, re.IGNORECASE):
                break
            if re.search(r'Competition\s+Management|Jury|RACE\s+DIRECTOR|TECHNICAL\s+DELEGATE|'
                         r'COORDINATOR|CHIEF\s+OF\s+COMPETITION|ASSISTANT|EQUIPMENT\s+CONTROLLER|'
                         r'NATIONAL\s+TD|Judges\s+Hill|WIND\s+FACTOR|GATE\s+FACTOR|'
                         r'METER\s+VALUE|K[-\s]POINT|HILL\s+SIZE|SECONDS\s+PER|POINTS\s+PER',
                         rt, re.IGNORECASE):
                continue
            if re.search(r'\b1ST\s+ROUND\b|\b2ND\s+ROUND\b|\bSPEED\b.*\bDIST\b|\bBIB\b.*\bNAME\b|'
                         r'\bNAME\b.*\bNATION\b',
                         rt, re.IGNORECASE):
                continue
            if re.search(r'\[km/h\].*\[m\]', rt, re.IGNORECASE):
                continue

            bib_w, r1_w, r2_w = [], [], []
            for w in row:
                cx = (w['x0'] + w['x1']) / 2
                if cx < X_BIB_MAX:
                    bib_w.append(w['text'])
                elif cx < X_MID:
                    r1_w.append(w['text'])
                else:
                    r2_w.append(w['text'])

            bib_str = ' '.join(bib_w).strip()

            # NSA-scan on everything after the bib to get clean name+nation
            after_bib_toks = [w['text'] for w in row if (w['x0'] + w['x1']) / 2 >= X_BIB_MAX]
            nm, nat, _ = self._nsa_split(after_bib_toks)

            if bib_str.isdigit() and nm and is_valid_athlete_name(nm):
                # Bib-first format: split r1_w / r2_w at X_MID
                # r1_w already contains tokens from BIB_MAX to MID (includes name/nsa/nums mixed)
                # Use only numeric r1 tokens after extracting name
                r1_nums = [t for t in r1_w
                           if self._DECIMAL_RE.match(t.strip('.,*')) or
                              (t.isdigit() and 1 <= int(t) <= 30)]

                if current_r1 and current_r1.name:
                    rounds.append(current_r1)
                if current_r2 and current_r2.name:
                    rounds.append(current_r2)

                current_r1 = JumpRound(round_number=1)
                current_r1.bib = parse_int(bib_str)
                current_r1.name = nm
                current_r1.nation = nat
                self._assign_trial_nums(current_r1, r1_nums)

                current_r2 = JumpRound(round_number=2)
                current_r2.bib = parse_int(bib_str)
                current_r2.name = nm
                current_r2.nation = nat
                self._assign_trial_nums(current_r2, r2_w)

                state = 1

            elif state != 'nf' and not bib_str.isdigit():
                # Name-first format (old COC): NAME NSA | R1_NUMS | R2_NUMS on one row
                nm, nat, _ = self._split_name_nsa_nums(rt)
                if nm:
                    if current_r1 and current_r1.name:
                        rounds.append(current_r1)
                    if current_r2 and current_r2.name:
                        rounds.append(current_r2)
                    current_r1 = JumpRound(round_number=1)
                    current_r1.name = nm
                    current_r1.nation = nat
                    self._assign_trial_nums(current_r1, r1_w)
                    current_r2 = JumpRound(round_number=2)
                    current_r2.name = nm
                    current_r2.nation = nat
                    self._assign_trial_nums(current_r2, r2_w)
                    state = 'nf'

            elif state == 'nf':
                # Expect bib alone
                candidate = rt.strip().split()[0] if rt.strip() else ''
                if candidate.isdigit():
                    bib_val = parse_int(candidate)
                    if current_r1:
                        current_r1.bib = bib_val
                    if current_r2:
                        current_r2.bib = bib_val
                state = 1

            elif state == 1:
                full = rt.strip()
                dob_m = re.search(r'\b(\d{1,2}\s+[A-Z]{3}\s+\d{4})\b', full)
                if dob_m:
                    dob_str = normalise_date(dob_m.group(1))
                    club_str = clean_name(full[:dob_m.start()])
                    if current_r1:
                        current_r1.date_of_birth = dob_str
                        current_r1.club = club_str
                    if current_r2:
                        current_r2.date_of_birth = dob_str
                        current_r2.club = club_str
                state = 0

        if current_r1 and current_r1.name:
            rounds.append(current_r1)
        if current_r2 and current_r2.name:
            rounds.append(current_r2)

        return rounds

    def _assign_trial_nums(self, jr: JumpRound, tokens: List[str]) -> None:
        """
        Assign numeric tokens to trial jump fields.

        Plain gate or doubled-digit token (e.g. "0077" → gate=7):
          [speed, dist, gate, wind_ms, total_points]  → 5 floats

        Merged gate+comp token (e.g. "2211" → gate=22, comp=1.1):
          [speed, dist, gate, gate_comp, wind_ms, total_points]  → 6 floats
        """
        floats = []
        has_gate_comp = False

        for t in tokens:
            t = t.strip('*.')
            if re.match(r'^-?[\d]+\.[\d]+$', t):
                floats.append(parse_float(t))
            elif re.match(r'^\d+$', t):
                v = parse_int(t)
                if v and 1 <= v <= 30:
                    floats.append(float(v))
                elif len(t) == 4:
                    gate_cand = int(t[0:2])
                    if 1 <= gate_cand <= 30:
                        floats.append(float(gate_cand))
                        floats.append(int(t[2:4]) / 10.0)
                        has_gate_comp = True
                    else:
                        gate_cand2 = int(t[1:3])
                        if 1 <= gate_cand2 <= 30:
                            floats.append(float(gate_cand2))
                elif len(t) == 3 and t[0] == '0':
                    gate_cand = int(t[1:3])
                    if 1 <= gate_cand <= 30:
                        floats.append(float(gate_cand))

        if len(floats) >= 1:
            jr.speed_kmh = floats[0]
        if len(floats) >= 2:
            jr.distance_m = floats[1]
        if len(floats) >= 3:
            jr.gate = int(floats[2])

        if has_gate_comp:
            if len(floats) >= 4:
                jr.gate_comp_pts = floats[3]
            if len(floats) >= 5:
                jr.wind_ms = floats[4]
            if len(floats) >= 6:
                jr.total_points = floats[5]
        else:
            if len(floats) >= 4:
                jr.wind_ms = floats[3]
            if len(floats) >= 5:
                jr.total_points = floats[4]
