"""
Parser for RLT (Results Official Training) documents.

Layout: 2 jump rounds per athlete side-by-side.
Columns per round: SPEED  DIST  G/W COMP  POINTS  RANK
Last page: Competition Management/Jury + Judges + Competition/Weather info + Statistics
"""
import re
from typing import List, Optional, Tuple

import pdfplumber

from fis_parser.models import (
    JumpRound, GateStatistics, WeatherData, ParsedDocument,
)
from fis_parser.utils import (
    parse_float, parse_int, normalise_date, clean_name,
    find_line_index, group_words_into_rows, row_text, is_valid_athlete_name,
)
from fis_parser.extractors.base import BaseExtractor


class RLTExtractor(BaseExtractor):

    def parse(self) -> ParsedDocument:
        doc = ParsedDocument(
            source_file=self.filepath,
            doc_type='RLT',
        )
        self.doc = doc

        try:
            with self.open_pdf() as pdf:
                full_text = self.all_text(pdf)

                from fis_parser.detector import detect_format_era
                doc.format_era = detect_format_era(full_text, 'RLT')

                hdr = self.extract_event_header(full_text)
                doc.fis_report_code = hdr.get('fis_report_code')
                doc.location = hdr.get('location')
                doc.country = hdr.get('country')
                doc.competition_date = hdr.get('competition_date')
                doc.start_time = hdr.get('start_time')
                doc.end_time = hdr.get('end_time')

                doc.hill_data = self.extract_hill_data(full_text)

                # Last page: jury, judges, weather rounds, gate stats
                last_page = pdf.pages[-1]
                last_text = self.page_text(last_page)
                last_lines = last_text.splitlines()

                # Jury
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

                # Judges
                j_start = find_line_index(last_lines, r'\bJudges\b|\bJUDGES\b')
                if j_start >= 0:
                    doc.judges = self.extract_judges(last_lines, j_start + 1)

                # Per-round weather
                doc.weather, doc.gate_statistics = self._parse_weather_rounds(last_text)

                # Weather summary (basic)
                wd, cs = self.extract_weather_summary(last_text)
                if doc.weather is None or doc.weather.weather_description is None:
                    doc.weather = wd
                doc.competitor_stats = cs

                # Jump results
                doc.jump_rounds = self._parse_rlt_rounds(pdf)

        except Exception as exc:
            doc.parse_errors.append(f"RLT parse error: {exc}")

        return doc

    # ── Per-round weather table ───────────────────────────────────────────────

    def _parse_weather_rounds(self, last_text: str
                              ) -> Tuple[Optional[WeatherData], List[GateStatistics]]:
        """
        Parse the 'Competition / Weather Information' table and Statistics table.
        Returns (WeatherData for round 1 as representative, list of GateStatistics).
        """
        wd = WeatherData()
        gate_stats: List[GateStatistics] = []

        # ── Weather table ─────────────────────────────────────────────────
        # Header: TIME | BASE VALUES (WIND GATE LENGTH) | WEATHER | TEMP AIR/SNOW | HUMID | TAN.WIND
        # Look for rows like: '1st Round  12:01 - 12:51  0.00  16  83.44m  Partly cloudy  -4.0/-5.0  -11.0/-11.0  93/93  -0.12 1.26 0.58'
        round_re = re.compile(
            r'(\d)(?:st|nd|rd|th)\s+Round\s+'
            r'([\d:]+\s*-\s*[\d:]+)'   # time range
            r'\s+([\d\.]+)'             # wind base
            r'\s+(\d+)'                 # gate
            r'\s+([\d\.]+m)'            # length
            r'\s+(.+?)'                 # weather desc
            r'\s+([+-]?[\d\.]+)\s*/\s*([+-]?[\d\.]+)'  # temp air start/finish
            r'\s+([+-]?[\d\.]+)\s*/\s*([+-]?[\d\.]+)'  # temp snow start/finish
            r'\s+(\d+)\s*/\s*(\d+)'     # humidity
            r'\s+([+-]?[\d\.]+)\s+([\d\.]+)\s+([\d\.]+)',  # wind min avg max
            re.IGNORECASE
        )
        for m in round_re.finditer(last_text):
            rnum = int(m.group(1))
            w = WeatherData()
            w.weather_description = m.group(6).strip()
            w.temp_air_start_c = parse_float(m.group(7))
            w.temp_air_finish_c = parse_float(m.group(8))
            w.temp_snow_start_c = parse_float(m.group(9))
            w.temp_snow_finish_c = parse_float(m.group(10))
            w.humidity_start_pct = parse_float(m.group(11))
            w.humidity_finish_pct = parse_float(m.group(12))
            w.wind_min_ms = parse_float(m.group(13))
            w.wind_avg_ms = parse_float(m.group(14))
            w.wind_max_ms = parse_float(m.group(15))
            if rnum == 1:
                wd = w   # use round 1 as the representative weather record

        # ── Statistics table ─────────────────────────────────────────────
        # Each gate row:  16  [diff]  N  falls  dist_min dist_max dist_avg  spd_min spd_max spd_avg  [entries]
        stat_re = re.compile(
            r'(\d)(?:st|nd|rd|th)\s+Round.*?\n'
            r'(?:.*?\n)*?'
            r'(\d+)\s+'           # gate number
            r'(-?[\d\.]+m)?\s*'   # diff
            r'(\d+)\s+'           # athletes
            r'(\d+)\s+'           # falls
            r'([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+'  # dist min max avg
            r'([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)',     # speed min max avg
            re.IGNORECASE | re.DOTALL
        )
        # Simpler line-by-line approach for statistics
        in_stats = False
        current_round = 0
        for line in last_text.splitlines():
            if re.search(r'^\s*Statistics\b', line, re.IGNORECASE):
                in_stats = True
                continue
            if not in_stats:
                continue
            # Detect round marker
            rm = re.match(r'(\d)(?:st|nd|rd|th)\s+Round', line, re.IGNORECASE)
            if rm:
                current_round = int(rm.group(1))
                continue
            # Gate stat row: gate_no [diff] athletes falls dist_min dist_max dist_avg spd_min spd_max spd_avg ...
            nums = re.findall(r'[-+]?[\d]+\.?[\d]*m?', line)
            nums_clean = []
            for n in nums:
                if n.endswith('m'):
                    nums_clean.append(n)
                else:
                    nums_clean.append(n)
            # Skip if not enough numbers
            if len(nums_clean) < 8:
                continue
            try:
                gate_no = parse_int(nums_clean[0])
                if gate_no and 1 <= gate_no <= 30:
                    gs = GateStatistics(
                        round_number=current_round,
                        gate_number=gate_no,
                    )
                    idx = 1
                    # Diff might be like '-0.56m' or '1.14m'
                    if nums_clean[idx].endswith('m'):
                        gs.gate_diff_m = parse_float(nums_clean[idx].rstrip('m'))
                        idx += 1
                    gs.athlete_count = parse_int(nums_clean[idx])
                    gs.fall_count = parse_int(nums_clean[idx + 1])
                    gs.dist_min_m = parse_float(nums_clean[idx + 2])
                    gs.dist_max_m = parse_float(nums_clean[idx + 3])
                    gs.dist_avg_m = parse_float(nums_clean[idx + 4])
                    gs.speed_min_kmh = parse_float(nums_clean[idx + 5])
                    gs.speed_max_kmh = parse_float(nums_clean[idx + 6])
                    gs.speed_avg_kmh = parse_float(nums_clean[idx + 7])
                    gate_stats.append(gs)
            except (IndexError, ValueError):
                pass

        return wd, gate_stats

    # ── Jump rounds ───────────────────────────────────────────────────────────

    def _parse_rlt_rounds(self, pdf: pdfplumber.PDF) -> List[JumpRound]:
        """
        Parse 2-round training jump table.
        Each athlete row contains:
          BIB  NAME  NSA  [1ST ROUND: speed dist gate wind gate_comp wind_comp points rank]
                         [2ND ROUND: speed dist gate wind gate_comp wind_comp points rank]
          (2nd word-row) CLUB  DOB  [rank items repeated for each round]
        """
        rounds: List[JumpRound] = []

        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            # y_tol=6 merges the bib row (3-6 pt below name) with the name row
            rows = group_words_into_rows(words, y_tol=6)
            if not rows:
                continue
            page_w = max(w['x1'] for w in words)
            scale = page_w / 720.0

            # Column layout for RLT (two-round, modern) — narrower than ROF
            # because of extra rank/POINTS columns:
            #   BIB   NAME     NSA     [1ST ROUND]     [2ND ROUND]
            #   0-80  80-200   200-240  240-402         402-560+
            X_BIB_MAX  = 80  * scale
            X_NAME_MAX = 200 * scale
            X_NSA_MAX  = 240 * scale
            X_MID      = 402 * scale   # boundary between round 1 and round 2

            current_r1: Optional[JumpRound] = None
            current_r2: Optional[JumpRound] = None
            state = 0

            for row in rows:
                rt = row_text(row)
                if not rt.strip():
                    continue

                # Stop only at the end-of-results sections (last page)
                if re.search(r'\bWEATHER\b|\bStatistics\b|\bLegend\b',
                             rt, re.IGNORECASE):
                    break
                if re.match(r'^\s*printed\b', rt, re.IGNORECASE):
                    continue

                # Skip per-page header rows (jury/judges block + column headers)
                if re.search(r'Jury\s*/\s*Competition|Competition\s+Management|'
                             r'RACE\s+DIRECTOR|TECHNICAL\s+DELEGATE|CHIEF\s+OF\s+COMPETITION|'
                             r'ASSISTANT\s+TD|ASSISTANT\s+RD|EQUIPMENT\s+CONTROLLER|'
                             r'NATIONAL\s+TD|Judges\s+Hill|WIND\s+FACTORS|SECONDS\s+PER|'
                             r'POINTS\s+PER\s+MINUTE|GATE\s+FACTOR|METER\s+VALUE|'
                             r'K-POINT|HILL\s+SIZE',
                             rt, re.IGNORECASE):
                    continue
                if re.search(r'\b1ST\s+ROUND\b|\bSPEED\b.*\bDIST\b|\bBIB\b.*\bNAME\b',
                             rt, re.IGNORECASE):
                    continue
                if re.search(r'\[km/h\].*\[m\]', rt, re.IGNORECASE):
                    continue
                if re.search(r'POINTS\s+POINTS\s+RANK|CLUB\s+DATE\s+OF\s+BIRTH',
                             rt, re.IGNORECASE):
                    continue

                bib_w, name_w, nsa_w, r1_w, r2_w = [], [], [], [], []
                for w in row:
                    cx = (w['x0'] + w['x1']) / 2
                    if cx < X_BIB_MAX:
                        bib_w.append(w['text'])
                    elif cx < X_NAME_MAX:
                        name_w.append(w['text'])
                    elif cx < X_NSA_MAX:
                        nsa_w.append(w['text'])
                    elif cx < X_MID:
                        r1_w.append(w['text'])
                    else:
                        r2_w.append(w['text'])

                bib_str = ' '.join(bib_w).strip()
                name_str = clean_name(' '.join(name_w))
                nsa_str = ' '.join(nsa_w).strip()

                # Detect athlete row 1 (has a bib number and valid name)
                if bib_str.isdigit() and is_valid_athlete_name(name_str):
                    # Flush previous
                    if current_r1 and current_r1.name:
                        rounds.append(current_r1)
                    if current_r2 and current_r2.name:
                        rounds.append(current_r2)

                    nation = nsa_str if len(nsa_str) == 3 else None

                    current_r1 = JumpRound(round_number=1)
                    current_r1.bib = parse_int(bib_str)
                    current_r1.name = name_str
                    current_r1.nation = nation
                    self._parse_rlt_round_nums(current_r1, r1_w)

                    current_r2 = JumpRound(round_number=2)
                    current_r2.bib = parse_int(bib_str)
                    current_r2.name = name_str
                    current_r2.nation = nation
                    self._parse_rlt_round_nums(current_r2, r2_w)

                    state = 1

                elif state == 1:
                    # Row 2: club + DOB + per-round rank info (we ignore rank rows here)
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

            # Flush last athlete
            if current_r1 and current_r1.name:
                rounds.append(current_r1)
            if current_r2 and current_r2.name:
                rounds.append(current_r2)

        return rounds

    def _parse_rlt_round_nums(self, jr: JumpRound, tokens: List[str]) -> None:
        """
        Tokens for one round (5 or 6 floats after parsing):

        Plain gate (1-30) or doubled-digit token (e.g. "0077" → gate=7):
          [speed, dist, gate, wind_ms, total_points]   → 5 floats

        Merged gate+comp token (e.g. "2211" → gate=22, comp=1.1):
          [speed, dist, gate, gate_comp, wind_ms, total_points]  → 6 floats
        """
        floats = []
        has_gate_comp = False  # True when a merged gate+comp token is found

        for t in tokens:
            t = t.strip('*.')
            if re.match(r'^-?[\d]+\.[\d]+$', t):
                floats.append(parse_float(t))
            elif re.match(r'^\d+$', t):
                v = parse_int(t)
                if v and 1 <= v <= 30:
                    floats.append(float(v))   # normal gate (e.g. "7", "16")
                elif len(t) == 4:
                    gate_cand = int(t[0:2])
                    if 1 <= gate_cand <= 30:
                        # Merged gate+comp, e.g. "2211" → gate=22, comp=1.1
                        floats.append(float(gate_cand))
                        floats.append(int(t[2:4]) / 10.0)
                        has_gate_comp = True
                    else:
                        # Doubled-digit, e.g. "0077" → gate=7 (PDF draws "07" twice)
                        gate_cand2 = int(t[1:3])
                        if 1 <= gate_cand2 <= 30:
                            floats.append(float(gate_cand2))
                elif len(t) == 3 and t[0] == '0':
                    # Leading-zero gate, e.g. "007" → gate=7
                    gate_cand = int(t[1:3])
                    if 1 <= gate_cand <= 30:
                        floats.append(float(gate_cand))
                # else skip (probably a rank)

        if len(floats) >= 1:
            jr.speed_kmh = floats[0]
        if len(floats) >= 2:
            jr.distance_m = floats[1]
        if len(floats) >= 3:
            jr.gate = int(floats[2])

        if has_gate_comp:
            # floats: [speed, dist, gate, gate_comp, wind_ms, total_points]
            if len(floats) >= 4:
                jr.gate_comp_pts = floats[3]
            if len(floats) >= 5:
                jr.wind_ms = floats[4]
            if len(floats) >= 6:
                jr.total_points = floats[5]
        else:
            # floats: [speed, dist, gate, wind_ms, total_points]
            if len(floats) >= 4:
                jr.wind_ms = floats[3]
            if len(floats) >= 5:
                jr.total_points = floats[4]
