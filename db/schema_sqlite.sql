-- =============================================================
-- FIS Nordic Combined Results Database Schema
-- SQLite (prototype)
-- =============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- =============================================================
-- ATHLETES
-- =============================================================

CREATE TABLE IF NOT EXISTS athletes (
    id          INTEGER PRIMARY KEY,
    last_name   TEXT    NOT NULL,
    first_name  TEXT,
    full_name   TEXT    NOT NULL,
    nationality TEXT    NOT NULL,
    gender      TEXT,
    birth_date  TEXT,
    active_club TEXT,
    fis_id      TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (full_name, nationality)
);

CREATE TABLE IF NOT EXISTS athlete_name_variants (
    id              INTEGER PRIMARY KEY,
    athlete_id      INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
    name_variant    TEXT    NOT NULL,
    nationality     TEXT,
    first_seen_file TEXT,
    UNIQUE (name_variant, nationality)
);

CREATE INDEX IF NOT EXISTS idx_athlete_name_variants_athlete ON athlete_name_variants(athlete_id);

-- =============================================================
-- VENUES
-- =============================================================

CREATE TABLE IF NOT EXISTS venues (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    country     TEXT    NOT NULL,
    region      TEXT,
    latitude    REAL,
    longitude   REAL,
    hill_name   TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, country)
);

CREATE TABLE IF NOT EXISTS venue_name_variants (
    id              INTEGER PRIMARY KEY,
    venue_id        INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    name_variant    TEXT    NOT NULL,
    country         TEXT,
    first_seen_file TEXT,
    UNIQUE (name_variant, country)
);

CREATE INDEX IF NOT EXISTS idx_venue_name_variants_venue ON venue_name_variants(venue_id);

-- =============================================================
-- COMPETITION HIERARCHY
-- =============================================================

CREATE TABLE IF NOT EXISTS seasons (
    id          INTEGER PRIMARY KEY,
    start_year  INTEGER NOT NULL,
    label       TEXT    NOT NULL,
    UNIQUE (start_year)
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY,
    season_id    INTEGER NOT NULL REFERENCES seasons(id),
    venue_id     INTEGER REFERENCES venues(id),
    circuit      TEXT    NOT NULL,
    raw_location TEXT,
    raw_country  TEXT,
    start_date   TEXT,
    end_date     TEXT,
    gender       TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_season ON events(season_id);

CREATE TABLE IF NOT EXISTS competitions (
    id               INTEGER PRIMARY KEY,
    event_id         INTEGER REFERENCES events(id),
    season_id        INTEGER NOT NULL REFERENCES seasons(id),
    venue_id         INTEGER REFERENCES venues(id),
    fis_codex        TEXT,
    circuit          TEXT    NOT NULL,
    gender           TEXT,
    competition_date TEXT,
    raw_location     TEXT,
    raw_country      TEXT,
    format           TEXT,
    hill_spec        TEXT,
    hill_size_m      REAL,
    xc_distance_km   REAL,
    event_name       TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_competitions_codex_season ON competitions(fis_codex, season_id);
CREATE INDEX IF NOT EXISTS idx_competitions_season   ON competitions(season_id);
CREATE INDEX IF NOT EXISTS idx_competitions_event    ON competitions(event_id);
CREATE INDEX IF NOT EXISTS idx_competitions_date     ON competitions(competition_date);
CREATE INDEX IF NOT EXISTS idx_competitions_circuit  ON competitions(circuit);

CREATE TABLE IF NOT EXISTS competition_documents (
    id              INTEGER PRIMARY KEY,
    competition_id  INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    doc_type        TEXT    NOT NULL,
    format_era      TEXT,
    source_file     TEXT,
    fis_report_code TEXT,
    report_created  TEXT,
    start_time      TEXT,
    end_time        TEXT,
    parse_warnings  TEXT,
    parsed_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_docs_competition ON competition_documents(competition_id);

-- =============================================================
-- COMPETITION DETAIL
-- =============================================================

CREATE TABLE IF NOT EXISTS hill_data (
    id                  INTEGER PRIMARY KEY,
    competition_id      INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    document_id         INTEGER REFERENCES competition_documents(id),
    hill_size_m         REAL,
    k_point_m           REAL,
    meter_value         REAL,
    gate_factor         REAL,
    wind_factor_head    REAL,
    wind_factor_tail    REAL,
    height_difference_m REAL,
    gates               INTEGER,
    rated_speed_ms      REAL
);

CREATE TABLE IF NOT EXISTS course_info (
    id              INTEGER PRIMARY KEY,
    competition_id  INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    document_id     INTEGER REFERENCES competition_documents(id),
    height_m        REAL,
    max_climb_m     REAL,
    total_climb_m   REAL,
    length_km       REAL,
    number_of_laps  INTEGER
);

CREATE TABLE IF NOT EXISTS weather_records (
    id                   INTEGER PRIMARY KEY,
    competition_id       INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
    document_id          INTEGER REFERENCES competition_documents(id),
    weather_description  TEXT,
    snow_conditions      TEXT,
    temp_air_c           REAL,
    temp_snow_c          REAL,
    temp_air_start_c     REAL,
    temp_air_finish_c    REAL,
    temp_snow_start_c    REAL,
    temp_snow_finish_c   REAL,
    humidity_start_pct   REAL,
    humidity_finish_pct  REAL,
    wind_min_ms          REAL,
    wind_max_ms          REAL,
    wind_avg_ms          REAL
);

CREATE TABLE IF NOT EXISTS jury_officials (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES competition_documents(id) ON DELETE CASCADE,
    role        TEXT,
    last_name   TEXT,
    first_name  TEXT,
    nation      TEXT
);

CREATE TABLE IF NOT EXISTS jumping_judges (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES competition_documents(id) ON DELETE CASCADE,
    position    TEXT,
    last_name   TEXT,
    first_name  TEXT,
    nation      TEXT
);

-- =============================================================
-- RESULTS
-- =============================================================

CREATE TABLE IF NOT EXISTS combined_results (
    id              INTEGER PRIMARY KEY,
    competition_id  INTEGER NOT NULL REFERENCES competitions(id),
    document_id     INTEGER NOT NULL REFERENCES competition_documents(id),
    athlete_id      INTEGER REFERENCES athletes(id),
    raw_name        TEXT,
    raw_nation      TEXT,
    rank            INTEGER,
    bib             INTEGER,
    club            TEXT,
    date_of_birth   TEXT,
    jump_points     REAL,
    jump_rank       INTEGER,
    time_difference TEXT,
    xc_time         TEXT,
    xc_rank         INTEGER,
    time_behind     TEXT,
    wave_start      INTEGER,
    status          TEXT
);

CREATE INDEX IF NOT EXISTS idx_combined_competition ON combined_results(competition_id);
CREATE INDEX IF NOT EXISTS idx_combined_athlete     ON combined_results(athlete_id);
CREATE INDEX IF NOT EXISTS idx_combined_rank        ON combined_results(rank);

CREATE TABLE IF NOT EXISTS jump_round_results (
    id              INTEGER PRIMARY KEY,
    competition_id  INTEGER NOT NULL REFERENCES competitions(id),
    document_id     INTEGER NOT NULL REFERENCES competition_documents(id),
    athlete_id      INTEGER REFERENCES athletes(id),
    raw_name        TEXT,
    raw_nation      TEXT,
    rank            INTEGER,
    bib             INTEGER,
    club            TEXT,
    date_of_birth   TEXT,
    round_number    INTEGER,
    speed_kmh       REAL,
    distance_m      REAL,
    dist_points     REAL,
    judge_a         REAL,
    judge_b         REAL,
    judge_c         REAL,
    judge_d         REAL,
    judge_e         REAL,
    style_points    REAL,
    gate            INTEGER,
    gate_comp_pts   REAL,
    wind_ms         REAL,
    wind_comp_pts   REAL,
    total_points    REAL,
    pursuit_time_diff TEXT,
    dns             INTEGER NOT NULL DEFAULT 0,
    dsq             INTEGER NOT NULL DEFAULT 0,
    dsq_reason      TEXT,
    fall            INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_jump_competition ON jump_round_results(competition_id);
CREATE INDEX IF NOT EXISTS idx_jump_athlete     ON jump_round_results(athlete_id);

CREATE TABLE IF NOT EXISTS training_jump_results (
    id              INTEGER PRIMARY KEY,
    competition_id  INTEGER NOT NULL REFERENCES competitions(id),
    document_id     INTEGER NOT NULL REFERENCES competition_documents(id),
    athlete_id      INTEGER REFERENCES athletes(id),
    raw_name        TEXT,
    raw_nation      TEXT,
    rank            INTEGER,
    bib             INTEGER,
    club            TEXT,
    date_of_birth   TEXT,
    round_number    INTEGER,
    speed_kmh       REAL,
    distance_m      REAL,
    dist_points     REAL,
    judge_a         REAL,
    judge_b         REAL,
    judge_c         REAL,
    judge_d         REAL,
    judge_e         REAL,
    style_points    REAL,
    gate            INTEGER,
    gate_comp_pts   REAL,
    wind_ms         REAL,
    wind_comp_pts   REAL,
    total_points    REAL,
    dns             INTEGER NOT NULL DEFAULT 0,
    dsq             INTEGER NOT NULL DEFAULT 0,
    dsq_reason      TEXT,
    fall            INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_training_competition ON training_jump_results(competition_id);
CREATE INDEX IF NOT EXISTS idx_training_athlete     ON training_jump_results(athlete_id);

CREATE TABLE IF NOT EXISTS trial_round_results (
    id              INTEGER PRIMARY KEY,
    competition_id  INTEGER NOT NULL REFERENCES competitions(id),
    document_id     INTEGER NOT NULL REFERENCES competition_documents(id),
    athlete_id      INTEGER REFERENCES athletes(id),
    raw_name        TEXT,
    raw_nation      TEXT,
    rank            INTEGER,
    bib             INTEGER,
    club            TEXT,
    date_of_birth   TEXT,
    round_number    INTEGER,
    speed_kmh       REAL,
    distance_m      REAL,
    dist_points     REAL,
    judge_a         REAL,
    judge_b         REAL,
    judge_c         REAL,
    judge_d         REAL,
    judge_e         REAL,
    style_points    REAL,
    gate            INTEGER,
    gate_comp_pts   REAL,
    wind_ms         REAL,
    wind_comp_pts   REAL,
    total_points    REAL,
    dns             INTEGER NOT NULL DEFAULT 0,
    dsq             INTEGER NOT NULL DEFAULT 0,
    dsq_reason      TEXT,
    fall            INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_trial_competition ON trial_round_results(competition_id);
CREATE INDEX IF NOT EXISTS idx_trial_athlete     ON trial_round_results(athlete_id);

CREATE TABLE IF NOT EXISTS xc_results (
    id              INTEGER PRIMARY KEY,
    competition_id  INTEGER NOT NULL REFERENCES competitions(id),
    document_id     INTEGER NOT NULL REFERENCES competition_documents(id),
    athlete_id      INTEGER REFERENCES athletes(id),
    raw_name        TEXT,
    raw_nation      TEXT,
    rank            INTEGER,
    bib             INTEGER,
    club            TEXT,
    date_of_birth   TEXT,
    total_time      TEXT,
    time_behind     TEXT,
    points          REAL,
    status          TEXT
);

CREATE INDEX IF NOT EXISTS idx_xc_competition ON xc_results(competition_id);
CREATE INDEX IF NOT EXISTS idx_xc_athlete     ON xc_results(athlete_id);

CREATE TABLE IF NOT EXISTS team_results (
    id              INTEGER PRIMARY KEY,
    competition_id  INTEGER NOT NULL REFERENCES competitions(id),
    document_id     INTEGER NOT NULL REFERENCES competition_documents(id),
    rank            INTEGER,
    bib             INTEGER,
    nation          TEXT,
    total_time      TEXT,
    time_behind     TEXT,
    jump_points     REAL,
    status          TEXT
);

CREATE TABLE IF NOT EXISTS team_members (
    id              INTEGER PRIMARY KEY,
    team_result_id  INTEGER NOT NULL REFERENCES team_results(id) ON DELETE CASCADE,
    athlete_id      INTEGER REFERENCES athletes(id),
    raw_name        TEXT,
    raw_nation      TEXT,
    leg             INTEGER,
    xc_time         TEXT,
    jump_distance_m REAL,
    jump_points     REAL
);

-- =============================================================
-- STATISTICS VIEWS
-- =============================================================

CREATE VIEW IF NOT EXISTS v_athlete_podiums AS
SELECT
    a.id        AS athlete_id,
    a.full_name,
    a.nationality,
    c.circuit,
    SUM(CASE WHEN cr.rank = 1 THEN 1 ELSE 0 END) AS gold,
    SUM(CASE WHEN cr.rank = 2 THEN 1 ELSE 0 END) AS silver,
    SUM(CASE WHEN cr.rank = 3 THEN 1 ELSE 0 END) AS bronze,
    COUNT(*)                                       AS total_starts
FROM combined_results cr
JOIN athletes     a ON cr.athlete_id     = a.id
JOIN competitions c ON cr.competition_id = c.id
WHERE cr.rank IS NOT NULL
  AND (cr.status IS NULL OR cr.status = '')
  AND c.format NOT LIKE 'Team%'
GROUP BY a.id, a.full_name, a.nationality, c.circuit;

CREATE VIEW IF NOT EXISTS v_season_standings AS
SELECT
    a.id        AS athlete_id,
    a.full_name,
    a.nationality,
    s.label     AS season,
    c.circuit,
    COUNT(*)                                             AS starts,
    SUM(CASE WHEN cr.rank = 1  THEN 1 ELSE 0 END)       AS wins,
    SUM(CASE WHEN cr.rank <= 3 THEN 1 ELSE 0 END)       AS podiums,
    SUM(CASE WHEN cr.rank <= 10 THEN 1 ELSE 0 END)      AS top10,
    MIN(cr.rank)                                         AS best_result,
    ROUND(AVG(cr.rank), 1)                               AS avg_rank
FROM combined_results cr
JOIN athletes     a ON cr.athlete_id     = a.id
JOIN competitions c ON cr.competition_id = c.id
JOIN seasons      s ON c.season_id       = s.id
WHERE cr.rank IS NOT NULL
  AND (cr.status IS NULL OR cr.status = '')
  AND c.format NOT LIKE 'Team%'
GROUP BY a.id, a.full_name, a.nationality, s.label, c.circuit;

CREATE VIEW IF NOT EXISTS v_athlete_jump_stats AS
SELECT
    a.id        AS athlete_id,
    a.full_name,
    a.nationality,
    c.circuit,
    COUNT(*)                       AS jumps,
    ROUND(AVG(jr.distance_m), 1)   AS avg_distance_m,
    MAX(jr.distance_m)             AS best_distance_m,
    ROUND(AVG(jr.total_points), 2) AS avg_points
FROM jump_round_results jr
JOIN athletes     a ON jr.athlete_id     = a.id
JOIN competitions c ON jr.competition_id = c.id
WHERE jr.distance_m IS NOT NULL
  AND jr.dns = 0 AND jr.dsq = 0
GROUP BY a.id, a.full_name, a.nationality, c.circuit;

CREATE VIEW IF NOT EXISTS v_athlete_venue_stats AS
SELECT
    a.id        AS athlete_id,
    a.full_name,
    a.nationality,
    v.id        AS venue_id,
    v.name      AS venue,
    v.country,
    c.circuit,
    COUNT(*)                                             AS starts,
    SUM(CASE WHEN cr.rank = 1  THEN 1 ELSE 0 END)       AS wins,
    SUM(CASE WHEN cr.rank <= 3 THEN 1 ELSE 0 END)       AS podiums,
    MIN(cr.rank)                                         AS best_result,
    ROUND(AVG(cr.rank), 1)                               AS avg_rank
FROM combined_results cr
JOIN athletes     a ON cr.athlete_id     = a.id
JOIN competitions c ON cr.competition_id = c.id
JOIN venues       v ON c.venue_id        = v.id
WHERE cr.rank IS NOT NULL
  AND (cr.status IS NULL OR cr.status = '')
  AND c.format NOT LIKE 'Team%'
GROUP BY a.id, a.full_name, a.nationality, v.id, v.name, v.country, c.circuit;
