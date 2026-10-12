"""
Line-based parser for team result lists (Team, Team Sprint, Mixed Team).

All layouts — Swiss Timing World Cup lists since 2002 and the ewoxx
Continental Cup lists — share one shape: a line for the team, followed by
one line per athlete.

    1 2 NOR - Norway I 282.8 2 +0:02 33:17.0 3 33:19.0      rank bib nation team  points rank diff  time rank behind
    2-1 r GRAABAK Joergen 137.3 16:34.7                     bib-leg [colour] name  points [leg time …]
    2-2 b RIIBER Jarl Magnus 145.5 16:42.3

Variations handled here:
  * rank with or without dot, '=' for ties, 'PF'/'FF' photo-finish flag
  * nation without dash ('FIN Finland'), or no nation code at all ('2 - Austria II')
  * rank and bib on lines of their own around the team line (ewoxx 2013–2022)
  * athlete lines repeated once per lap (ewoxx 2012)
  * teams without a time under 'Did not start' / 'Did not finish' / 'Disqualified' / lapped
"""
import re
from typing import List, Optional, Tuple

from fis_parser.models import TeamMember, TeamResult
from fis_parser.utils import parse_float, clean_name

_TIME = r'\d{1,2}:\d{2}(?::\d{2})?(?:\.\d)?'
_RANK = r'=?\d+\.?'

_TEAM_HEAD = (
    r'^(?:(?:PF|FF)\s+)?'
    r'(?:(?P<rank>' + _RANK + r')\s+)?'            # rank — absent for teams without result
    r'(?:(?:PF|FF)\s+)?'                           # 2013 prints the flag after the rank
    r'(?:(?P<bib>\d+)\s+)?'
    r'(?:(?P<nat>[A-Z]{3})\s*(?:-\s*)?|-\s*)'      # 'NOR - ', 'FIN ' or just '- '
    r'(?P<team>[A-Za-z][A-Za-z .,/\'-]*?)\s*'      # \s*: 'UNITED STATES OF AMERICA102.4'
    r'(?P<pts>-?\d+\.\d)\s+(?P<jrank>' + _RANK + r')\s+(?P<diff>\+?\s?' + _TIME + r')')
# … followed by cross-country time, rank and time behind for teams that finished
_TEAM_RE = re.compile(
    _TEAM_HEAD + r'(?:'
    r'\s+(?P<xc>' + _TIME + r')\s+(?P<xcrank>' + _RANK + r')'
    r'(?:\s+' + _TIME + r')??'                     # 2011–2013: total time before the gap
    r'(?:\s+\*\*)?\s*(?P<behind>\+?\s?[\d:.]+)'
    r'|\s+(?P<lap>LAP)(?:\s+(?P<laprank>\d+))?'    # lapped: 'LAP' / 'LAP 16' instead of a time
    r')?(?:\s+\*\*)?\s*$')
# Team without a result: '18 CZECH REPUBLIC II', '2 JPN - JAPAN I ICR 525.2.16',
# '7 USA - UNITED STATES I 210.2 7. ICR 525.2.11.2 - Skis changed'
_TEAM_NO_RESULT_RE = re.compile(
    r'^(?P<bib>\d+)\s+(?:(?P<nat>[A-Z]{3})\s*-\s*)?(?P<team>[A-Za-z][A-Za-z .,/\'-]*?)'
    r'(?:\s+(?P<nat2>(?![IVX]+\b)[A-Z]{3}))?'      # '25 P.R. CHINA III CHN'
    r'(?:\s+(?P<pts>-?\d+\.\d)\s+(?P<jrank>' + _RANK + r'))?(?:\s+(?P<diff>\+?\s?' + _TIME + r'))?'
    r'(?:\s+ICR\s?\d.*)?$')
# 'NICHOLS Evan USA Ski Jumping: SCE4 Suit' — an athlete disqualified in the jumping part
_ATHLETE_NOTE_RE = re.compile(r"^(?:\d+\s+)?[^\W\d_a-z][^\Wa-z_]+[\s\-'].*\b[A-Z]{3}\b")
# Continuation lines of the column header
_SUBHEADER_RE = re.compile(
    r'^(?:(?:LEG|BIB|COLOU?R|NAME|POINTS|RANK|TIME|TIMERANK|DIFFERENCE|BEHIND|SPLIT|SPLITTEAM|TEAM|JUMP'
    r'|SKI|JUMPING|CROSS-?COUNTRY|NSA|NOC|CODE)\s*)+$', re.IGNORECASE)
_FURNITURE_RE = re.compile(
    r'printed\b|Print\s+Date|Page\s+\d|www\.|fis-ski|data\s+processing|Timing\s+and\s+Data|Report\s+Created'
    r'|^\d{1,2}\s+[A-Z]{3}\s+\d{4}\s*/|^Points\s+per\s+minute', re.IGNORECASE)

_MEMBER_RE = re.compile(
    r'^(?P<bib>\d+)\s?-\s?(?P<leg>\d)\s+(?:(?P<colour>[rgyb])\s+)?'
    r'(?P<name>[^\W\d_][^\d+]*?)(?=\s+[-+]?\d|\s*$)'     # up to the first number
    r'(?:\s+(?P<pts>-?\d+\.\d))?'
    r'(?:\s+(?P<xc>' + _TIME + r'))?'
    r'(?P<rest>\s.*)?$')

_RANK_ONLY_RE = re.compile(r'^(' + _RANK + r')$')
_SECTION_RE = re.compile(
    r'^(?:(?P<dns>Did\s+not\s+start|Not\s+permitted\s+to\s+start)'
    r'|(?P<dnf>Did\s+not\s+finish)|(?P<lap>Lapped)|(?P<dsq>Disqualified))\b', re.IGNORECASE)
_HEADER_RE = re.compile(r'^(?:RANK|BIB)\b.*(?:TEAM|NAME|JUMP|LEG)', re.IGNORECASE)
# The result list is over: weather, signatures, legend
_END_RE = re.compile(
    r'^(?:Weather\b|Temperatures?\b|Air\s+Snow\b|Snow\s+Air\b|Legend\b|Jury\s+Decision'
    r'|Jury\b|Competition\s+Management|(?:FIS\s+)?Technical\s+Delegate\b.*Chief|TD\s+Chief)',
    re.IGNORECASE)

# For lists that print the country but not its code
_NATION_BY_COUNTRY = {
    'austria': 'AUT', 'belarus': 'BLR', 'canada': 'CAN', 'china': 'CHN', 'czech republic': 'CZE',
    'czechia': 'CZE', 'estonia': 'EST', 'finland': 'FIN', 'france': 'FRA', 'germany': 'GER',
    'italy': 'ITA', 'japan': 'JPN', 'kazakhstan': 'KAZ', 'korea': 'KOR', 'norway': 'NOR',
    'poland': 'POL', 'russia': 'RUS', 'slovakia': 'SVK', 'slovenia': 'SLO', 'sweden': 'SWE',
    'switzerland': 'SUI', 'ukraine': 'UKR', 'united states': 'USA', 'usa': 'USA',
    'unites states': 'USA', 'slovinia': 'SLO',             # sic, COC 2011/12
    'united states of america': 'USA', 'russian federation': 'RUS', 'p.r. china': 'CHN',
}


# 'UNITED STATES OF AMERICA2 5I3I.0': the team number 'II' printed over the
# points '253.0' because the long name ran into the next column.
_OVERPRINT_RE = re.compile(r'(?<=[A-Z])((?:[\dI]\s?)*I(?:[\dI]\s?)*\.\d)(?=\s)')


def _untangle_overprint(line: str) -> str:
    def fix(m: 're.Match') -> str:
        chars = m.group(1).replace(' ', '')
        return f" {'I' * chars.count('I')} {chars.replace('I', '')}"
    return _OVERPRINT_RE.sub(fix, line, count=1)


def _rank(token: Optional[str]) -> Optional[int]:
    m = re.search(r'\d+', token or '')
    return int(m.group()) if m else None


def _nation_from_team_name(team: str) -> Optional[str]:
    country = re.sub(r'\s+[IVX]+$|\s+\d$', '', team.strip()).lower()
    return _NATION_BY_COUNTRY.get(country)


def parse_team_rof(pages: List[List[str]]) -> Tuple[List[TeamResult], List[str]]:
    """
    Parse all pages (each a list of text lines).
    Returns (teams, lines inside the result list that could not be read).
    """
    teams: List[TeamResult] = []
    unparsed: List[str] = []
    section: Optional[str] = None          # DNS / DNF / DSQ / LAP once past the ranked teams
    current: Optional[TeamResult] = None
    pending_rank: Optional[int] = None
    finished = False

    for lines in pages:
        if finished:
            break
        in_table = False
        for raw in lines:
            line = raw.strip()
            if not line or set(line) == {'-'}:
                continue
            if _HEADER_RE.match(line):
                in_table = True
                continue
            sec = _SECTION_RE.match(line)
            if sec and (in_table or teams):
                section = ('DNS' if sec.group('dns') else 'DNF' if sec.group('dnf')
                           else 'LAP' if sec.group('lap') else 'DSQ')
                current, pending_rank, in_table = None, None, True
                continue
            if not in_table or _SUBHEADER_RE.match(line) or _FURNITURE_RE.search(line):
                continue
            if _END_RE.match(line):
                if teams:
                    finished = True
                break

            m = _RANK_ONLY_RE.match(line)
            if m and '.' in line:                               # '1.' above the team line
                pending_rank, current = _rank(line), None
                continue
            if m and current is not None and current.bib is None:   # bib below the team line
                current.bib = _rank(line)
                continue

            m = _MEMBER_RE.match(line)
            if m and current is not None and m.group('name').split()[0].isupper():
                _add_member(current, m)
                continue

            m = _TEAM_RE.match(line) or _TEAM_RE.match(_untangle_overprint(line))
            if m:
                nation = m.group('nat') or _nation_from_team_name(m.group('team'))
                rank = _rank(m.group('rank')) if m.group('bib') else None
                bib = _rank(m.group('bib') or m.group('rank'))  # a single number is the bib
                if rank is None and section is None:
                    rank, pending_rank = pending_rank, None
                behind = (m.group('behind') or '').replace(' ', '') or None
                lapped = m.group('lap') is not None
                current = TeamResult(
                    rank=None if section in ('DNS', 'DNF', 'DSQ') else rank,
                    bib=bib,
                    nation=nation,
                    team_name=clean_name(m.group('team')),
                    jump_points=parse_float(m.group('pts')),
                    jump_rank=_rank(m.group('jrank')),
                    time_difference=m.group('diff').replace(' ', ''),
                    xc_time=m.group('xc'),
                    xc_rank=_rank(m.group('xcrank') or m.group('laprank')),
                    time_behind=behind,
                    status=section or ('LAP' if lapped else None),
                )
                teams.append(current)
                continue

            if section in ('DNS', 'DNF', 'DSQ'):
                m = _TEAM_NO_RESULT_RE.match(line)
                nation = m and (m.group('nat') or m.group('nat2')
                                or _nation_from_team_name(m.group('team')))
                if nation:
                    current = TeamResult(
                        bib=int(m.group('bib')), nation=nation, team_name=clean_name(m.group('team')),
                        jump_points=parse_float(m.group('pts')) if m.group('pts') else None,
                        jump_rank=_rank(m.group('jrank')),
                        time_difference=(m.group('diff') or '').replace(' ', '') or None,
                        status=section)
                    teams.append(current)
                    continue
                if _ATHLETE_NOTE_RE.match(line):
                    current = None          # a single athlete's disqualification, not a team
                    continue
            unparsed.append(line)

    for team in teams:
        _tidy_members(team)
    return teams, unparsed


def _add_member(team: TeamResult, m: 're.Match') -> None:
    leg = int(m.group('leg'))
    name = clean_name(m.group('name'))
    known = next((x for x in team.members if x.leg == leg), None)
    if known is not None:                 # ewoxx 2012 repeats the athlete for every lap;
        known.xc_time = None              # the time on each line is a lap time, not the leg
        return
    team.members.append(TeamMember(
        leg=leg,
        bib=f"{m.group('bib')}-{leg}",
        name=name,
        jump_points=parse_float(m.group('pts')) if m.group('pts') else None,
        xc_time=m.group('xc'),
    ))


def _tidy_members(team: TeamResult) -> None:
    team.members.sort(key=lambda x: x.leg)
    # In some lists only the last athlete's line carries a time — the team's
    # total, not a leg time.  A leg time counts only if every leg has one.
    if any(x.xc_time is None for x in team.members):
        for x in team.members:
            x.xc_time = None
