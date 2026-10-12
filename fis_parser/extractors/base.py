"""
Base extractor with shared methods used by all document-type parsers.
"""
import re
from typing import List, Optional, Tuple

import pdfplumber

from fis_parser.models import (
    JuryOfficial, JumpingJudge, HillData, CourseInfo,
    WeatherData, CompetitorStats, ParsedDocument,
)
from fis_parser.utils import (
    parse_float, parse_int, parse_temp, parse_fraction,
    normalise_role, extract_nation_parens, clean_name,
    normalise_date, find_line_index, group_words_into_rows, row_text,
)


class BaseExtractor:

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.doc: Optional[ParsedDocument] = None

    # ── PDF open / text helpers ───────────────────────────────────────────────

    def open_pdf(self) -> pdfplumber.PDF:
        return pdfplumber.open(self.filepath)

    def all_text(self, pdf: pdfplumber.PDF) -> str:
        return '\n'.join(
            p.extract_text() or '' for p in pdf.pages
        )

    def page_text(self, page) -> str:
        return page.extract_text() or ''

    def page_lines(self, page) -> List[str]:
        return (page.extract_text() or '').splitlines()

    # ── Jury extraction ───────────────────────────────────────────────────────

    def extract_jury_block(self, lines: List[str],
                           start_idx: int, stop_patterns: List[str]) -> List[JuryOfficial]:
        """
        Parse jury lines starting at start_idx.
        Each line expected to be: ROLE   Name (NATION)
        or older style:           Role   Name   NATION
        Stop when a stop_pattern matches or blank lines exhaust.
        """
        officials: List[JuryOfficial] = []
        stop_re = re.compile('|'.join(stop_patterns), re.IGNORECASE) if stop_patterns else None

        # Known role prefixes (longest first to avoid partial matches)
        role_patterns = [
            r'(RACE\s+DIRECTOR|FIS\s+RACE\s+DIRECTOR(?:\s*\(RD\))?)',
            r'(TECHNICAL\s+DELEGATE|FIS\s+TECHNICAL\s+DELEGATE(?:\s*\(TD\))?)',
            r'(ASSISTENT\s+TD|ASSISTANT\s+TECHNICAL\s+DELEGATE|FIS\s+ASSISTANT\s+TECHNICAL\s+DELEGATE|FIS\s+ASSISTANT\s+TD)',
            r'(ASSISTENT\s+RD|ASSISTANT\s+RACE\s+DIRECTOR|FIS\s+ASSISTANT\s+RD)',
            r'(CHIEF\s+OF\s+COMPETITION)',
            r'(CHIEF\s+OF\s+COURSE)',
            r'(EQUIPMENT\s+CONTROLLER)',
            r'(NATIONAL\s+TD)',
            r'(COORDINATOR|COORD\.)',
            # Older style without FIS prefix
            r'(Race\s+Director)',
            r'(Technical\s+Delegate)',
            r'(Assistant\s+Technical\s+Delegate)',
            r'(Assistant\s+Race\s+Director)',
            r'(Chief\s+of\s+Competition)',
            r'(Chief\s+of\s+Course)',
            r'(TD\s+Assistant)',
        ]
        combined = '|'.join(f'(?:{p})' for p in role_patterns)
        role_re = re.compile(combined, re.IGNORECASE)

        is_jury_next = False
        for i in range(start_idx, len(lines)):
            line = lines[i].strip()
            if not line:
                continue
            if stop_re and stop_re.search(line):
                break

            # Check for "JURY" label that precedes the role on the same line (Format E)
            has_jury_label = bool(re.search(r'\bJURY\b', line))

            m = role_re.search(line)
            if m:
                raw_role = m.group(0)
                remainder = line[m.end():].strip()
                # Remove leading dashes, colons
                remainder = re.sub(r'^[\s\-:]+', '', remainder)
                # Strip course/hill info that may appear on the same line
                # when jury and course info blocks share a page row (eras A-D)
                remainder = re.sub(
                    r'\s+(?:HEIGHT|MAXIMUM|TOTAL|LENGTH|NUMBER|HILL\s+SIZE|'
                    r'K[-\s]POINT|METER\s+VALUE|GATE\s+FACTOR|WIND\s+FACTOR|'
                    r'SECONDS\s+PER|POINTS\s+PER)\b.*$',
                    '', remainder, flags=re.IGNORECASE
                ).strip()
                # Extract nation in parens
                nation, name_part = extract_nation_parens(remainder)
                # Fallback: 3-letter uppercase at end
                if not nation:
                    nm = re.search(r'\b([A-Z]{3})\s*$', remainder)
                    if nm:
                        nation = nm.group(1)
                        name_part = remainder[:nm.start()].strip()
                    else:
                        name_part = remainder

                # Strip "JURY" from name_part if accidentally included
                name_part = re.sub(r'\bJURY\b', '', name_part, flags=re.IGNORECASE).strip()
                name_part = clean_name(name_part)

                officials.append(JuryOfficial(
                    role=normalise_role(raw_role),
                    name=name_part,
                    nation=nation,
                    is_jury_designated=has_jury_label or is_jury_next,
                ))
                is_jury_next = False
            elif has_jury_label and not m:
                is_jury_next = True  # next role line gets JURY flag

        return officials

    def extract_judges(self, lines: List[str], start_idx: int) -> List[JumpingJudge]:
        """
        Parse lines like:
          A   KARJALAINEN Janne (FIN)
          B   PIGUET David (SUI)
        or old format:
          HUENEFELD Mirco, GER A
          THOMAS Juergen, GER B
        """
        judges: List[JumpingJudge] = []
        # Modern: position letter at start of line
        modern_re = re.compile(r'^([A-E])\s+(.+?)(?:\s+\(([A-Z]{2,3})\))?\s*$')
        # Old (ewoxx): name, nation then letter at end
        old_re = re.compile(r'^(.+?),\s*([A-Z]{3})\s+([A-E])\s*$')

        for i in range(start_idx, min(start_idx + 10, len(lines))):
            line = lines[i].strip()
            if not line:
                continue
            m = modern_re.match(line)
            if m:
                judges.append(JumpingJudge(
                    position=m.group(1),
                    name=clean_name(m.group(2)),
                    nation=m.group(3),
                ))
                continue
            m2 = old_re.match(line)
            if m2:
                judges.append(JumpingJudge(
                    position=m2.group(3),
                    name=clean_name(m2.group(1)),
                    nation=m2.group(2),
                ))
        return judges

    # ── Course info extraction ────────────────────────────────────────────────

    def extract_course_info(self, text: str) -> CourseInfo:
        ci = CourseInfo()
        patterns = [
            (r'Height\s+Difference[^:]*:\s*([\d\.]+)', 'height_difference_m'),
            (r'Maximum\s+Climb[^:]*:\s*([\d\.]+)', 'maximum_climb_m'),
            (r'Total\s+Climb[^:]*:\s*([\d\.]+)', 'total_climb_m'),
            (r'(?:Length\s+of\s+Lap|Course\s+Length)[^:]*:\s*([\d\s]+)', 'lap_length_m'),
            (r'Number\s+of\s+Laps[^:]*:\s*(\d+)', 'number_of_laps'),
        ]
        for pattern, attr in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                val = m.group(1).replace(' ', '')
                setattr(ci, attr, parse_int(val))
        return ci

    # ── Hill data extraction ──────────────────────────────────────────────────

    def extract_hill_data(self, text: str) -> HillData:
        hd = HillData()
        # Hill size: '142m (134.5m)' or 'Hill Size 140.0 m'
        m = re.search(r'HILL\s+SIZE[^\d]*([\d\.]+)', text, re.IGNORECASE)
        if not m:
            m = re.search(r'Hill\s+Size\s+([\d\.]+)', text, re.IGNORECASE)
        if m:
            hd.hill_size_m = parse_float(m.group(1))

        # K-Point
        m = re.search(r'K-?POINT\s+([\d\.]+)', text, re.IGNORECASE)
        if not m:
            m = re.search(r'K-Point\s+([\d\.]+)', text, re.IGNORECASE)
        if m:
            hd.k_point_m = parse_float(m.group(1))

        # Meter value
        m = re.search(r'METER\s+VALUE\s+([\d\.]+)', text, re.IGNORECASE)
        if not m:
            m = re.search(r'Meter\s+value\s+([\d\.]+)', text, re.IGNORECASE)
        if m:
            hd.meter_value = parse_float(m.group(1))

        # Gate factor
        m = re.search(r'Gate\s+Factor\s+([\d\.]+)', text, re.IGNORECASE)
        if m:
            hd.gate_factor = parse_float(m.group(1))

        # Wind factors  'head / tail  11.70 / 17.55 points / m/s'
        m = re.search(
            r'Wind\s+Factors?\s*[-–]\s*head\s*/\s*tail\s+([\d\.]+)\s*/\s*([\d\.]+)',
            text, re.IGNORECASE
        )
        if m:
            hd.wind_factor_head = parse_float(m.group(1))
            hd.wind_factor_tail = parse_float(m.group(2))

        # Hill name
        m = re.search(r'(?:Name|Hill\s+Data\s+Name)\s*\n?\s*([^\n]+)', text, re.IGNORECASE)
        if m:
            hd.name = clean_name(m.group(1))

        return hd

    # ── Weather extraction ────────────────────────────────────────────────────

    def extract_weather_summary(self, text: str) -> Tuple[Optional[WeatherData],
                                                          Optional[CompetitorStats]]:
        """
        Parse the summary weather/competitors table that appears on the last page
        of ROF, RLLL, and RL documents.

        Handles two table orientations:
          Row-style (old): 'Snow  Compact  -3.0  -1.0  46/14  46/14 ...'
          Column-style (new): headers on one line, values on next
        """
        wd = WeatherData()
        cs = CompetitorStats()

        # ── temperatures ─────────────────────────────────────────────────────
        # Modern: '-9.0°C  -8.0°C' or '1.0°C  -11.0°C'
        temp_m = re.search(
            r'(?:AIR|Air)[^\d\-]*([+-]?[\d\.]+)[°\s]*C[°\s]*'
            r'(?:SNOW|Snow)[^\d\-]*([+-]?[\d\.]+)',
            text, re.IGNORECASE
        )
        if temp_m:
            wd.temp_air_c = parse_temp(temp_m.group(1))
            wd.temp_snow_c = parse_temp(temp_m.group(2))

        # Older format (columns): 'Air  Snow \n -3.0  -1.0'
        if wd.temp_air_c is None:
            m = re.search(
                r'Air\s+Snow\s*\n\s*([+-]?[\d\.]+)\s+([+-]?[\d\.]+)',
                text, re.IGNORECASE
            )
            if m:
                wd.temp_air_c = parse_float(m.group(1))
                wd.temp_snow_c = parse_float(m.group(2))

        # ── weather description ────────────────────────────────────────────
        for desc in ('Partly cloudy', 'Light snow shower', 'Mostly cloudy',
                     'Cloudy', 'Snow', 'Clear', 'Overcast', 'clear',
                     'Sunny', 'Fog'):
            if re.search(re.escape(desc), text, re.IGNORECASE):
                wd.weather_description = desc
                break

        # ── snow conditions ────────────────────────────────────────────────
        for cond in ('Compact', 'Hard packed', 'Hard', 'Packed',
                     'Loose', 'Wet', 'Groomed', 'Artificial'):
            if re.search(re.escape(cond), text, re.IGNORECASE):
                wd.snow_conditions = cond
                break

        # ── competitor stats ───────────────────────────────────────────────
        # 'Entries  55/14  Ranked  54/14  DNS  0/0  DNF  1/1  DSQ  0/0  LAP  0/0'
        # or 'ENTRIES  RANKED  DNF  DSQ  DNS  NPS  DQB  LAP'
        #    '52 / 13  50 / 13  0 / 0  0 / 0  2 / 1  0 / 0  0 / 0  0 / 0'

        def grab_fraction(label: str) -> Tuple[Optional[int], Optional[int]]:
            m = re.search(
                label + r'[^\d]*(\d+)\s*/\s*(\d+)',
                text, re.IGNORECASE
            )
            if m:
                return int(m.group(1)), int(m.group(2))
            return None, None

        ent_a, ent_n = grab_fraction(r'(?:Entries|ENTRIES)')
        cs.entries_athletes, cs.entries_nations = ent_a, ent_n

        rk_a, rk_n = grab_fraction(r'(?:Ranked|RANKED)')
        cs.ranked_athletes, cs.ranked_nations = rk_a, rk_n

        # For columns-style (modern last page), try to read all fractions
        # after we've found the stats header row
        stats_m = re.search(
            r'ENTRIES\s+RANKED\s+(.*?)\n(.*?\d\s*/\s*\d.*)',
            text, re.IGNORECASE | re.DOTALL
        )
        if stats_m:
            header_line = 'ENTRIES RANKED ' + stats_m.group(1)
            value_line = stats_m.group(2)
            # Extract all n/n tokens from value line
            fractions = re.findall(r'(\d+)\s*/\s*(\d+)', value_line)
            headers = re.findall(
                r'\b(ENTRIES|RANKED|DNF|DSQ|DNS|NPS|DQB|LAP)\b',
                header_line, re.IGNORECASE
            )
            for j, hdr in enumerate(headers):
                if j < len(fractions):
                    a_val = int(fractions[j][0])
                    n_val = int(fractions[j][1])
                    hdr_up = hdr.upper()
                    if hdr_up == 'ENTRIES':
                        cs.entries_athletes, cs.entries_nations = a_val, n_val
                    elif hdr_up == 'RANKED':
                        cs.ranked_athletes, cs.ranked_nations = a_val, n_val
                    elif hdr_up == 'DNS':
                        cs.dns = a_val
                    elif hdr_up == 'DNF':
                        cs.dnf = a_val
                    elif hdr_up == 'DSQ':
                        cs.dsq = a_val
                    elif hdr_up == 'LAP':
                        cs.lap = a_val
                    elif hdr_up == 'NPS':
                        cs.nps = a_val
                    elif hdr_up == 'DQB':
                        cs.dqb = a_val

        # Fallback individual counts
        for label, attr in [('DNS', 'dns'), ('DNF', 'dnf'), ('DSQ', 'dsq'),
                             ('LAP', 'lap'), ('NPS', 'nps'), ('DQB', 'dqb')]:
            if getattr(cs, attr) is None:
                a, _ = grab_fraction(label)
                if a is not None:
                    setattr(cs, attr, a)

        return wd, cs

    # ── Event header ─────────────────────────────────────────────────────────

    def extract_event_header(self, text: str) -> dict:
        """
        Extract location, date, start/end time, report code, event name
        from the top-of-page header text.
        """
        info = {}

        # Report code: NC2526WCU01 or NC2022SWRACP01 etc.
        m = re.search(r'\b(NC\d{4}\w+)', text)
        if m:
            info['fis_report_code'] = m.group(1)

        # Location: 'Ramsau am Dachstein (AUT)' — search first 600 chars
        # Use [^\n(] to avoid spanning newlines or eating extra `(` groups
        # Only the title block counts: further down, 'WEHLING Ulrich (FIS)' in
        # the jury list has the same 'text (XXX)' shape as a venue.
        title = re.split(r'\bJury\b|Competition\s+Management', text[:600], maxsplit=1)[0]
        m = re.search(r'([\w][^\n(]{2,}?)\s*\(([A-Z]{3})\)', title)
        if m:
            # Early COC files write 'in Vancouver-Whistler (CAN) at 17.12.2008'
            info['location'] = re.sub(r'^in\s+', '', clean_name(m.group(1)))
            info['country'] = m.group(2)

        # Date patterns: 'SAT 28 NOV 2025', 'FRI 26 NOV 2021', '28 NOV 2025'
        m = re.search(
            r'(?:MON|TUE|WED|THU|FRI|SAT|SUN)\s+(\d{1,2}\s+[A-Z]{3}\s+\d{4})',
            text, re.IGNORECASE
        )
        if not m:
            m = re.search(r'(\d{1,2}\s+[A-Z]{3}\s+\d{4})', text)
        if not m:
            m = re.search(r'\bat\s+(\d{1,2}\.\d{2}\.\d{4})', text[:600])
        if m:
            info['competition_date'] = normalise_date(m.group(1))

        # Start/End time
        m = re.search(r'Start\s+Time[:\s]*([\d:]+)', text, re.IGNORECASE)
        if m:
            info['start_time'] = m.group(1)
        m = re.search(r'End\s+Time[:\s]*([\d:]+)', text, re.IGNORECASE)
        if m:
            info['end_time'] = m.group(1)

        # Report created
        m = re.search(r'[Rr]eport\s+[Cc]reated\s+(.+?)(?:\s+Page|\n|$)', text)
        if m:
            info['report_created'] = m.group(1).strip()

        return info
