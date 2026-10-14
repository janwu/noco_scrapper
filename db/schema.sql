-- =============================================================
-- FIS Nordic Combined Results Database Schema
-- PostgreSQL
-- =============================================================

-- =============================================================
-- ATHLETES
-- =============================================================

-- Canonical athlete record (one row per real person)
CREATE TABLE athletes (
    id              SERIAL PRIMARY KEY,
    last_name       VARCHAR(100) NOT NULL,
    first_name      VARCHAR(100),
    full_name       VARCHAR(200) NOT NULL,   -- "SURNAME Firstname" canonical display
    nationality     CHAR(3)      NOT NULL,
    gender          CHAR(1),                 -- 'M' or 'W'
    birth_date      DATE,
    active_club     VARCHAR(200),            -- most recent club seen in PDFs
    fis_id          VARCHAR(20),             -- if manually populated later
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (full_name, nationality)
);

-- Alternate name spellings seen in PDFs → resolve to canonical athlete
-- Enables fuzzy-matched or manually-confirmed deduplication
CREATE TABLE athlete_name_variants (
    id              SERIAL PRIMARY KEY,
    athlete_id      INT          NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
    name_variant    VARCHAR(200) NOT NULL,
    nationality     CHAR(3),
    first_seen_file VARCHAR(500),
    UNIQUE (name_variant, nationality)
);

CREATE INDEX idx_athlete_name_variants_athlete ON athlete_name_variants(athlete_id);

-- =============================================================
-- VENUES
-- =============================================================

-- Canonical venue record (one row per real place)
-- Same deduplication pattern as athletes:
--   raw location strings from PDFs are stored in venue_name_variants
--   and resolved to a canonical venue (manually or programmatically)
CREATE TABLE venues (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,   -- canonical place name, e.g. "Ramsau am Dachstein"
    country         CHAR(3)      NOT NULL,   -- IOC 3-letter country code
    region          VARCHAR(100),            -- state / province / region (optional)
    latitude        NUMERIC(9,6),            -- for map views
    longitude       NUMERIC(9,6),
    hill_name       VARCHAR(200),            -- name of the ski jump (e.g. "Hochfilzen Schanze")
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (name, country)
);

-- Raw location strings seen in PDFs → canonical venue
CREATE TABLE venue_name_variants (
    id              SERIAL PRIMARY KEY,
    venue_id        INT          NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    name_variant    VARCHAR(200) NOT NULL,   -- exactly as it appeared in the PDF
    country         CHAR(3),
    first_seen_file VARCHAR(500),
    UNIQUE (name_variant, country)
);

CREATE INDEX idx_venue_name_variants_venue ON venue_name_variants(venue_id);

-- =============================================================
-- COMPETITION HIERARCHY
-- =============================================================

-- FIS season, e.g. start_year=2022 → "2022/2023"
CREATE TABLE seasons (
    id          SERIAL   PRIMARY KEY,
    start_year  SMALLINT NOT NULL,
    label       VARCHAR(10) NOT NULL,   -- "2022/2023"
    UNIQUE (start_year)
);

-- Competition event: a venue + weekend that may host several individual races
CREATE TABLE events (
    id          SERIAL      PRIMARY KEY,
    season_id   INT         NOT NULL REFERENCES seasons(id),
    venue_id    INT         REFERENCES venues(id),   -- resolved canonical venue (nullable until matched)
    circuit     VARCHAR(10) NOT NULL,                -- 'WC' | 'COC'
    raw_location VARCHAR(200),                       -- original string from PDF (for audit / matching)
    raw_country  CHAR(3),
    start_date  DATE,
    end_date    DATE,
    gender      CHAR(1)                              -- 'M' | 'W' | 'X' (mixed)
);

CREATE INDEX idx_events_season ON events(season_id);

-- Single race/competition, identified by FIS codex
-- All PDF documents for the same race share one codex
CREATE TABLE competitions (
    id               SERIAL       PRIMARY KEY,
    event_id         INT          REFERENCES events(id),
    season_id        INT          NOT NULL REFERENCES seasons(id),
    venue_id         INT          REFERENCES venues(id),   -- resolved canonical venue
    fis_codex        VARCHAR(20),                 -- from filename, e.g. "4139" (NOT globally unique — FIS reuses codex numbers across seasons)
    UNIQUE (fis_codex, season_id),
    circuit          VARCHAR(10)  NOT NULL,       -- 'WC' | 'COC'
    gender           CHAR(1),                     -- 'M' | 'W'
    competition_date DATE,
    raw_location     VARCHAR(200),                -- original string from PDF
    raw_country      CHAR(3),
    format           VARCHAR(30),
    -- 'Gundersen' | 'MassStart' | 'Sprint' | 'IndividualGundersen' | 'Team' | 'SuperSprint'
    hill_spec        VARCHAR(5),                  -- 'NH' | 'LH' (Normal/Large Hill)
    hill_size_m      NUMERIC(6,1),
    xc_distance_km   NUMERIC(5,2),
    event_name       VARCHAR(300)                 -- full FIS event title from PDF header
);

CREATE INDEX idx_competitions_season   ON competitions(season_id);
CREATE INDEX idx_competitions_event    ON competitions(event_id);
CREATE INDEX idx_competitions_date     ON competitions(competition_date);
CREATE INDEX idx_competitions_circuit  ON competitions(circuit);

-- Individual PDF document belonging to a competition
CREATE TABLE competition_documents (
    id              SERIAL       PRIMARY KEY,
    competition_id  INT          NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    doc_type        VARCHAR(10)  NOT NULL,  -- ROF | RL | RL1 | RLT | RLTR | RLLL | PCR
    format_era      VARCHAR(10),            -- A | B | C | D | E | OLD | MODERN
    source_file     VARCHAR(500),
    fis_report_code VARCHAR(50),
    report_created  VARCHAR(50),
    start_time      VARCHAR(20),
    end_time        VARCHAR(20),
    parse_warnings  TEXT,
    parsed_at       TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_docs_competition ON competition_documents(competition_id);

-- =============================================================
-- COMPETITION DETAIL
-- =============================================================

CREATE TABLE hill_data (
    id                  SERIAL  PRIMARY KEY,
    competition_id      INT     NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    document_id         INT     REFERENCES competition_documents(id),
    hill_size_m         NUMERIC(6,1),
    k_point_m           NUMERIC(6,1),
    meter_value         NUMERIC(7,4),
    gate_factor         NUMERIC(8,4),
    wind_factor_head    NUMERIC(8,4),
    wind_factor_tail    NUMERIC(8,4),
    height_difference_m NUMERIC(6,1),
    gates               SMALLINT,
    rated_speed_ms      NUMERIC(5,2)
);

CREATE TABLE course_info (
    id                  SERIAL  PRIMARY KEY,
    competition_id      INT     NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    document_id         INT     REFERENCES competition_documents(id),
    height_m            NUMERIC(6,1),
    max_climb_m         NUMERIC(6,1),
    total_climb_m       NUMERIC(6,1),
    length_km           NUMERIC(5,2),
    number_of_laps      SMALLINT
);

CREATE TABLE weather_records (
    id                      SERIAL  PRIMARY KEY,
    competition_id          INT     NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    document_id             INT     REFERENCES competition_documents(id),
    weather_description     VARCHAR(100),
    snow_conditions         VARCHAR(100),
    temp_air_c              NUMERIC(5,1),
    temp_snow_c             NUMERIC(5,1),
    temp_air_start_c        NUMERIC(5,1),
    temp_air_finish_c       NUMERIC(5,1),
    temp_snow_start_c       NUMERIC(5,1),
    temp_snow_finish_c      NUMERIC(5,1),
    humidity_start_pct      NUMERIC(5,1),
    humidity_finish_pct     NUMERIC(5,1),
    wind_min_ms             NUMERIC(5,2),
    wind_max_ms             NUMERIC(5,2),
    wind_avg_ms             NUMERIC(5,2)
);

CREATE TABLE jury_officials (
    id              SERIAL      PRIMARY KEY,
    document_id     INT         NOT NULL REFERENCES competition_documents(id) ON DELETE CASCADE,
    role            VARCHAR(100),
    last_name       VARCHAR(100),
    first_name      VARCHAR(100),
    nation          CHAR(3)
);

CREATE TABLE jumping_judges (
    id              SERIAL  PRIMARY KEY,
    document_id     INT     NOT NULL REFERENCES competition_documents(id) ON DELETE CASCADE,
    position        CHAR(1),    -- A | B | C | D | E
    last_name       VARCHAR(100),
    first_name      VARCHAR(100),
    nation          CHAR(3)
);

-- =============================================================
-- RESULTS
-- =============================================================

-- Final combined results (ROF documents)
-- This is THE primary result table — what counts for rankings and points
CREATE TABLE combined_results (
    id                  SERIAL       PRIMARY KEY,
    competition_id      INT          NOT NULL REFERENCES competitions(id),
    document_id         INT          NOT NULL REFERENCES competition_documents(id),
    athlete_id          INT          REFERENCES athletes(id),
    raw_name            VARCHAR(200),   -- original name from PDF (for audit)
    raw_nation          CHAR(3),
    rank                SMALLINT,
    bib                 SMALLINT,
    club                VARCHAR(200),
    date_of_birth       DATE,
    jump_points         NUMERIC(7,2),   -- jumping round score
    jump_rank           SMALLINT,       -- rank after jumping
    time_difference     VARCHAR(20),    -- head-start / time gap at XC start (e.g. "+0:15")
    xc_time             VARCHAR(20),    -- cross-country leg time
    xc_rank             SMALLINT,       -- rank in XC leg
    time_behind         VARCHAR(20),    -- final gap to winner
    wave_start          SMALLINT,       -- pursuit wave number (Mass Start)
    status              VARCHAR(10)     -- NULL=finished | 'DNS' | 'DNF' | 'DSQ' | 'DNQ' | 'LAP' (lapped, rank kept)
);

CREATE INDEX idx_combined_competition  ON combined_results(competition_id);
CREATE INDEX idx_combined_athlete      ON combined_results(athlete_id);
CREATE INDEX idx_combined_rank         ON combined_results(rank);

-- Official ski jumping round results (RL / RL1 / PCR documents)
CREATE TABLE jump_round_results (
    id              SERIAL       PRIMARY KEY,
    competition_id  INT          NOT NULL REFERENCES competitions(id),
    document_id     INT          NOT NULL REFERENCES competition_documents(id),
    athlete_id      INT          REFERENCES athletes(id),
    raw_name        VARCHAR(200),
    raw_nation      CHAR(3),
    rank            SMALLINT,
    bib             SMALLINT,
    club            VARCHAR(200),
    date_of_birth   DATE,
    round_number    SMALLINT,           -- 1 or 2
    speed_kmh       NUMERIC(5,1),
    distance_m      NUMERIC(6,1),
    dist_points     NUMERIC(7,2),
    judge_a         NUMERIC(5,1),
    judge_b         NUMERIC(5,1),
    judge_c         NUMERIC(5,1),
    judge_d         NUMERIC(5,1),
    judge_e         NUMERIC(5,1),
    style_points    NUMERIC(7,2),
    gate            SMALLINT,
    gate_comp_pts   NUMERIC(7,2),
    wind_ms         NUMERIC(5,2),
    wind_comp_pts   NUMERIC(7,2),
    total_points    NUMERIC(7,2),
    pursuit_time_diff VARCHAR(20),      -- time advantage for XC pursuit start
    dns             BOOLEAN NOT NULL DEFAULT FALSE,
    dsq             BOOLEAN NOT NULL DEFAULT FALSE,
    dsq_reason      VARCHAR(300),
    fall            BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_jump_competition ON jump_round_results(competition_id);
CREATE INDEX idx_jump_athlete     ON jump_round_results(athlete_id);

-- Training jumps (RLT documents) — 2 rounds, unranked (or practice-ranked)
CREATE TABLE training_jump_results (
    id              SERIAL       PRIMARY KEY,
    competition_id  INT          NOT NULL REFERENCES competitions(id),
    document_id     INT          NOT NULL REFERENCES competition_documents(id),
    athlete_id      INT          REFERENCES athletes(id),
    raw_name        VARCHAR(200),
    raw_nation      CHAR(3),
    bib             SMALLINT,
    club            VARCHAR(200),
    date_of_birth   DATE,
    round_number    SMALLINT,           -- 1 or 2
    speed_kmh       NUMERIC(5,1),
    distance_m      NUMERIC(6,1),
    dist_points     NUMERIC(7,2),
    judge_a         NUMERIC(5,1),
    judge_b         NUMERIC(5,1),
    judge_c         NUMERIC(5,1),
    judge_d         NUMERIC(5,1),
    judge_e         NUMERIC(5,1),
    style_points    NUMERIC(7,2),
    gate            SMALLINT,
    gate_comp_pts   NUMERIC(7,2),
    wind_ms         NUMERIC(5,2),
    wind_comp_pts   NUMERIC(7,2),
    total_points    NUMERIC(7,2),
    dns             BOOLEAN NOT NULL DEFAULT FALSE,
    dsq             BOOLEAN NOT NULL DEFAULT FALSE,
    dsq_reason      VARCHAR(300),
    fall            BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_training_competition ON training_jump_results(competition_id);
CREATE INDEX idx_training_athlete     ON training_jump_results(athlete_id);

-- Trial round results (RLTR documents) — ranked, 1 or 2 rounds before competition
CREATE TABLE trial_round_results (
    id              SERIAL       PRIMARY KEY,
    competition_id  INT          NOT NULL REFERENCES competitions(id),
    document_id     INT          NOT NULL REFERENCES competition_documents(id),
    athlete_id      INT          REFERENCES athletes(id),
    raw_name        VARCHAR(200),
    raw_nation      CHAR(3),
    rank            SMALLINT,
    bib             SMALLINT,
    club            VARCHAR(200),
    date_of_birth   DATE,
    round_number    SMALLINT,
    speed_kmh       NUMERIC(5,1),
    distance_m      NUMERIC(6,1),
    dist_points     NUMERIC(7,2),
    judge_a         NUMERIC(5,1),
    judge_b         NUMERIC(5,1),
    judge_c         NUMERIC(5,1),
    judge_d         NUMERIC(5,1),
    judge_e         NUMERIC(5,1),
    style_points    NUMERIC(7,2),
    gate            SMALLINT,
    gate_comp_pts   NUMERIC(7,2),
    wind_ms         NUMERIC(5,2),
    wind_comp_pts   NUMERIC(7,2),
    total_points    NUMERIC(7,2),
    dns             BOOLEAN NOT NULL DEFAULT FALSE,
    dsq             BOOLEAN NOT NULL DEFAULT FALSE,
    dsq_reason      VARCHAR(300),
    fall            BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_trial_competition ON trial_round_results(competition_id);
CREATE INDEX idx_trial_athlete     ON trial_round_results(athlete_id);

-- Mass Start XC leg results (RLLL documents)
CREATE TABLE xc_results (
    id              SERIAL       PRIMARY KEY,
    competition_id  INT          NOT NULL REFERENCES competitions(id),
    document_id     INT          NOT NULL REFERENCES competition_documents(id),
    athlete_id      INT          REFERENCES athletes(id),
    raw_name        VARCHAR(200),
    raw_nation      CHAR(3),
    rank            SMALLINT,
    bib             SMALLINT,
    club            VARCHAR(200),
    date_of_birth   DATE,
    total_time      VARCHAR(20),
    time_behind     VARCHAR(20),
    points          NUMERIC(7,2),   -- XC jump-equivalent points (Mass Start only)
    status          VARCHAR(10)
);

CREATE INDEX idx_xc_competition ON xc_results(competition_id);
CREATE INDEX idx_xc_athlete     ON xc_results(athlete_id);

-- Team competition results (team-format ROF)
CREATE TABLE team_results (
    id              SERIAL      PRIMARY KEY,
    competition_id  INT         NOT NULL REFERENCES competitions(id),
    document_id     INT         NOT NULL REFERENCES competition_documents(id),
    rank            SMALLINT,
    bib             SMALLINT,
    nation          CHAR(3),
    team_name       VARCHAR(100),
    jump_rank       SMALLINT,
    time_difference VARCHAR(20),
    xc_rank         SMALLINT,
    total_time      VARCHAR(20),
    time_behind     VARCHAR(20),
    jump_points     NUMERIC(7,2),
    status          VARCHAR(10)
);

-- Individual athletes within a team result
CREATE TABLE team_members (
    id                  SERIAL      PRIMARY KEY,
    team_result_id      INT         NOT NULL REFERENCES team_results(id) ON DELETE CASCADE,
    athlete_id          INT         REFERENCES athletes(id),
    raw_name            VARCHAR(200),
    raw_nation          CHAR(3),
    leg                 SMALLINT,           -- 1..4
    xc_time             VARCHAR(20),
    jump_distance_m     NUMERIC(6,1),
    jump_points         NUMERIC(7,2)
);

-- =============================================================
-- CUP STANDINGS
-- =============================================================

-- Official final standings as published by FIS (fis_nk_standings_scraper.py).
-- Not computed from the results: the points rules changed over the years and
-- tours such as the Seefeld Triple score differently.
CREATE TABLE cup_standings (
    id                SERIAL PRIMARY KEY,
    season_id         INT NOT NULL REFERENCES seasons(id),
    circuit           VARCHAR(200)    NOT NULL,          -- 'WC' | 'COC'
    gender            VARCHAR(200)    NOT NULL,          -- 'M' | 'W'
    discipline_code   VARCHAR(200)    NOT NULL,          -- 'ALL' overall | 'SP' | 'IC' | 'MS' | 'BJT' | 'BST' | 'WGP'
    discipline_name   VARCHAR(200),                      -- 'Overall', 'Best Jumper Trophy', ...
    rank              INT NOT NULL,
    points            INT,
    athlete_id        INT REFERENCES athletes(id),   -- NULL: athlete has no result in the database
    raw_name          VARCHAR(200),
    raw_nation        VARCHAR(200),
    fis_competitor_id VARCHAR(200)
);

CREATE INDEX idx_cup_standings_lookup ON cup_standings(season_id, circuit, gender, discipline_code);
CREATE INDEX idx_cup_standings_athlete ON cup_standings(athlete_id);

-- =============================================================
-- ATHLETE STATISTICS VIEWS
-- =============================================================

-- Career wins per athlete per circuit
CREATE VIEW v_athlete_wins AS
SELECT
    a.id            AS athlete_id,
    a.full_name,
    a.nationality,
    c.circuit,
    s.start_year    AS season_start,
    s.label         AS season,
    COUNT(*)        AS wins
FROM combined_results cr
JOIN athletes      a ON cr.athlete_id     = a.id
JOIN competitions  c ON cr.competition_id = c.id
JOIN seasons       s ON c.season_id       = s.id
WHERE cr.rank = 1
  AND (cr.status IS NULL OR cr.status = '')
  AND c.format NOT LIKE 'Team%'
GROUP BY a.id, a.full_name, a.nationality, c.circuit, s.start_year, s.label;

-- Podium tally per athlete
CREATE VIEW v_athlete_podiums AS
SELECT
    a.id            AS athlete_id,
    a.full_name,
    a.nationality,
    c.circuit,
    COUNT(*) FILTER (WHERE cr.rank = 1) AS gold,
    COUNT(*) FILTER (WHERE cr.rank = 2) AS silver,
    COUNT(*) FILTER (WHERE cr.rank = 3) AS bronze,
    COUNT(*)                             AS total_starts
FROM combined_results cr
JOIN athletes     a ON cr.athlete_id     = a.id
JOIN competitions c ON cr.competition_id = c.id
WHERE cr.rank IS NOT NULL
  AND (cr.status IS NULL OR cr.status = '')
  AND c.format NOT LIKE 'Team%'
GROUP BY a.id, a.full_name, a.nationality, c.circuit;

-- Average jumping distance per athlete per competition format
CREATE VIEW v_athlete_jump_stats AS
SELECT
    a.id                        AS athlete_id,
    a.full_name,
    a.nationality,
    c.circuit,
    COUNT(*)                    AS jumps,
    ROUND(AVG(jr.distance_m),1) AS avg_distance_m,
    MAX(jr.distance_m)          AS best_distance_m,
    ROUND(AVG(jr.total_points),2) AS avg_points
FROM jump_round_results jr
JOIN athletes     a ON jr.athlete_id     = a.id
JOIN competitions c ON jr.competition_id = c.id
WHERE jr.distance_m IS NOT NULL
  AND jr.dns = FALSE AND jr.dsq = FALSE
GROUP BY a.id, a.full_name, a.nationality, c.circuit;

-- Season standings helper (total starts + top-3 finishes per season)
CREATE VIEW v_season_standings AS
SELECT
    a.id            AS athlete_id,
    a.full_name,
    a.nationality,
    s.label         AS season,
    c.circuit,
    COUNT(*)                                    AS starts,
    COUNT(*) FILTER (WHERE cr.rank = 1)         AS wins,
    COUNT(*) FILTER (WHERE cr.rank <= 3)        AS podiums,
    COUNT(*) FILTER (WHERE cr.rank <= 10)       AS top10,
    MIN(cr.rank)                                AS best_result,
    ROUND(AVG(cr.rank), 1)                      AS avg_rank
FROM combined_results cr
JOIN athletes     a ON cr.athlete_id     = a.id
JOIN competitions c ON cr.competition_id = c.id
JOIN seasons      s ON c.season_id       = s.id
WHERE cr.rank IS NOT NULL
  AND (cr.status IS NULL OR cr.status = '')
  AND c.format NOT LIKE 'Team%'
GROUP BY a.id, a.full_name, a.nationality, s.label, c.circuit;

-- Athlete results per venue (how an athlete performs at specific locations)
CREATE VIEW v_athlete_venue_stats AS
SELECT
    a.id            AS athlete_id,
    a.full_name,
    a.nationality,
    v.id            AS venue_id,
    v.name          AS venue,
    v.country,
    c.circuit,
    COUNT(*)                                    AS starts,
    COUNT(*) FILTER (WHERE cr.rank = 1)         AS wins,
    COUNT(*) FILTER (WHERE cr.rank <= 3)        AS podiums,
    MIN(cr.rank)                                AS best_result,
    ROUND(AVG(cr.rank), 1)                      AS avg_rank
FROM combined_results cr
JOIN athletes     a ON cr.athlete_id     = a.id
JOIN competitions c ON cr.competition_id = c.id
JOIN venues       v ON c.venue_id        = v.id
WHERE cr.rank IS NOT NULL
  AND (cr.status IS NULL OR cr.status = '')
  AND c.format NOT LIKE 'Team%'
GROUP BY a.id, a.full_name, a.nationality, v.id, v.name, v.country, c.circuit;

-- Every jump in one place: competition rounds, qualification and provisional
-- rounds (jump_round_results), training (training_jump_results) and trial
-- rounds (trial_round_results).  The kind of list is the doc_type of the
-- document.  The id is unique across the three tables.
CREATE OR REPLACE VIEW v_all_jumps AS
SELECT id * 3     AS id, competition_id, document_id, athlete_id, raw_name, raw_nation, rank, bib, club, date_of_birth, round_number, speed_kmh, distance_m, dist_points, judge_a, judge_b, judge_c, judge_d, judge_e, style_points, gate, gate_comp_pts, wind_ms, wind_comp_pts, total_points, pursuit_time_diff, dns, dsq, dsq_reason FROM jump_round_results
UNION ALL
SELECT id * 3 + 1 AS id, competition_id, document_id, athlete_id, raw_name, raw_nation, rank, bib, club, date_of_birth, round_number, speed_kmh, distance_m, dist_points, judge_a, judge_b, judge_c, judge_d, judge_e, style_points, gate, gate_comp_pts, wind_ms, wind_comp_pts, total_points, NULL, dns, dsq, dsq_reason FROM training_jump_results
UNION ALL
SELECT id * 3 + 2 AS id, competition_id, document_id, athlete_id, raw_name, raw_nation, rank, bib, club, date_of_birth, round_number, speed_kmh, distance_m, dist_points, judge_a, judge_b, judge_c, judge_d, judge_e, style_points, gate, gate_comp_pts, wind_ms, wind_comp_pts, total_points, NULL, dns, dsq, dsq_reason FROM trial_round_results;
