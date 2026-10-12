"""
Data models for parsed FIS Nordic Combined PDF documents.
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class JuryOfficial:
    role: str
    name: str
    nation: Optional[str] = None
    is_jury_designated: bool = False   # True when marked "JURY" in Format E


@dataclass
class JumpingJudge:
    position: str   # A, B, C, D, E
    name: str
    nation: Optional[str] = None


@dataclass
class HillData:
    name: Optional[str] = None
    k_point_m: Optional[float] = None
    hill_size_m: Optional[float] = None
    meter_value: Optional[float] = None
    gate_factor: Optional[float] = None
    wind_factor_head: Optional[float] = None
    wind_factor_tail: Optional[float] = None


@dataclass
class CourseInfo:
    height_difference_m: Optional[int] = None
    maximum_climb_m: Optional[int] = None
    total_climb_m: Optional[int] = None
    lap_length_m: Optional[int] = None
    number_of_laps: Optional[int] = None


@dataclass
class WeatherData:
    # From ROF/RLLL last page (summary)
    weather_description: Optional[str] = None
    snow_conditions: Optional[str] = None
    temp_air_c: Optional[float] = None
    temp_snow_c: Optional[float] = None
    # From RLT last page (per-round, start/finish split)
    temp_air_start_c: Optional[float] = None
    temp_air_finish_c: Optional[float] = None
    temp_snow_start_c: Optional[float] = None
    temp_snow_finish_c: Optional[float] = None
    humidity_start_pct: Optional[float] = None
    humidity_finish_pct: Optional[float] = None
    wind_min_ms: Optional[float] = None
    wind_max_ms: Optional[float] = None
    wind_avg_ms: Optional[float] = None


@dataclass
class GateStatistics:
    round_number: int
    gate_number: int
    gate_diff_m: Optional[float] = None
    athlete_count: Optional[int] = None
    fall_count: Optional[int] = None
    dist_min_m: Optional[float] = None
    dist_max_m: Optional[float] = None
    dist_avg_m: Optional[float] = None
    speed_min_kmh: Optional[float] = None
    speed_max_kmh: Optional[float] = None
    speed_avg_kmh: Optional[float] = None


@dataclass
class CompetitorStats:
    entries_athletes: Optional[int] = None
    entries_nations: Optional[int] = None
    ranked_athletes: Optional[int] = None
    ranked_nations: Optional[int] = None
    dns: Optional[int] = None
    dnf: Optional[int] = None
    dsq: Optional[int] = None
    lap: Optional[int] = None
    nps: Optional[int] = None    # Not Permitted to Start
    dqb: Optional[int] = None    # Disqualification unsportsmanlike behaviour


@dataclass
class CombinedResult:
    rank: Optional[int] = None
    bib: Optional[int] = None
    name: Optional[str] = None
    club: Optional[str] = None
    nation: Optional[str] = None
    date_of_birth: Optional[str] = None
    jump_points: Optional[float] = None
    jump_rank: Optional[int] = None
    time_difference: Optional[str] = None   # e.g. "0:00", "1:23"
    xc_time: Optional[str] = None
    xc_rank: Optional[int] = None
    time_behind: Optional[str] = None
    status: Optional[str] = None            # DNS, DNF, DSQ, LAP, NPS, DQB
    wave_start: bool = False                # ** in old format = wave start


@dataclass
class JumpRound:
    """One round of jumping for one athlete (from RL, RLT, RLTR)."""
    bib: Optional[int] = None
    name: Optional[str] = None
    club: Optional[str] = None
    nation: Optional[str] = None
    date_of_birth: Optional[str] = None
    round_number: int = 1
    rank: Optional[int] = None
    speed_kmh: Optional[float] = None
    distance_m: Optional[float] = None
    dist_points: Optional[float] = None    # DP
    judge_a: Optional[float] = None
    judge_b: Optional[float] = None
    judge_c: Optional[float] = None
    judge_d: Optional[float] = None
    judge_e: Optional[float] = None
    style_points: Optional[float] = None   # JP = best 3 of 5
    gate: Optional[int] = None
    wind_ms: Optional[float] = None
    gate_comp_pts: Optional[float] = None
    wind_comp_pts: Optional[float] = None
    total_points: Optional[float] = None
    pursuit_time_diff: Optional[str] = None  # DT (start delay for XC)
    fall: bool = False
    dns: bool = False
    dsq: bool = False
    dsq_reason: Optional[str] = None


@dataclass
class CrossCountryResult:
    """XC leg result (from RLLL for Mass Start, or embedded in ROF)."""
    rank: Optional[int] = None
    bib: Optional[int] = None
    name: Optional[str] = None
    club: Optional[str] = None
    nation: Optional[str] = None
    date_of_birth: Optional[str] = None
    total_time: Optional[str] = None
    time_behind: Optional[str] = None
    points: Optional[float] = None   # RLLL only: time → jump-handicap points
    status: Optional[str] = None


@dataclass
class TeamMember:
    """One athlete of a team (from a team ROF)."""
    leg: int = 0                             # 1..4, the order printed in the list
    bib: Optional[str] = None                # '2-1'
    name: Optional[str] = None
    jump_points: Optional[float] = None
    xc_time: Optional[str] = None            # leg time, if the list prints one per leg


@dataclass
class TeamResult:
    """One team in a Team / Team Sprint / Mixed Team result list."""
    rank: Optional[int] = None
    bib: Optional[int] = None
    nation: Optional[str] = None
    team_name: Optional[str] = None          # 'Norway I', 'GERMANY II', 'CAN/USA'
    jump_points: Optional[float] = None
    jump_rank: Optional[int] = None
    time_difference: Optional[str] = None
    xc_time: Optional[str] = None
    xc_rank: Optional[int] = None
    time_behind: Optional[str] = None
    status: Optional[str] = None             # DNS, DNF, DSQ, LAP
    members: List[TeamMember] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Unified output container for any parsed FIS document."""
    # ── Source ──────────────────────────────────────────────────────────────
    source_file: str = ""
    doc_type: str = ""        # ROF, RL, RLLL, RLT, RLTR, PCR
    format_era: str = ""      # A/B/C/D/E for ROF; OLD/MODERN for RL/RLT

    # ── Competition identity ─────────────────────────────────────────────────
    codex: Optional[str] = None
    fis_report_code: Optional[str] = None   # e.g. NC2526WCU01
    season: Optional[str] = None
    category: Optional[str] = None          # WC, COC
    gender: Optional[str] = None            # M, W, X
    discipline: Optional[str] = None        # Gundersen, Mass Start, Compact, Team…
    final_phase: Optional[str] = None       # SKI_JUMPING or CROSS_COUNTRY
    event_name: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    competition_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    report_created: Optional[str] = None

    # ── Officials & environment ──────────────────────────────────────────────
    jury: List[JuryOfficial] = field(default_factory=list)
    judges: List[JumpingJudge] = field(default_factory=list)
    hill_data: Optional[HillData] = None
    course_info: Optional[CourseInfo] = None
    weather: Optional[WeatherData] = None
    gate_statistics: List[GateStatistics] = field(default_factory=list)
    competitor_stats: Optional[CompetitorStats] = None

    # ── Results ──────────────────────────────────────────────────────────────
    combined_results: List[CombinedResult] = field(default_factory=list)
    jump_rounds: List[JumpRound] = field(default_factory=list)
    xc_results: List[CrossCountryResult] = field(default_factory=list)
    team_results: List[TeamResult] = field(default_factory=list)

    # ── Parse metadata ───────────────────────────────────────────────────────
    warnings: List[str] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)
