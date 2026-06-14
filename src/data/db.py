"""SQLite data warehouse schema and connection management.

The warehouse stores real match data, xG events, ELO history and player-level
match statistics. All features used by the prediction model are derived from
this database; there is no synthetic fallback.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.utils.config import config


DB_PATH: Path = config.cache_dir / "worldcup_forecast.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    code            TEXT PRIMARY KEY,
    name_en         TEXT NOT NULL,
    name_zh         TEXT,
    fifa_ranking    INTEGER,
    elo             REAL,
    confederation   TEXT,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    id              TEXT PRIMARY KEY,
    date            TEXT NOT NULL,
    competition     TEXT NOT NULL,
    season          TEXT,
    stage           TEXT,
    home_team_code  TEXT NOT NULL,
    away_team_code  TEXT NOT NULL,
    home_goals      INTEGER,
    away_goals      INTEGER,
    home_xg         REAL,
    away_xg         REAL,
    venue           TEXT,
    neutral         INTEGER DEFAULT 0,
    source          TEXT NOT NULL,
    fetched_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_home ON matches(home_team_code);
CREATE INDEX IF NOT EXISTS idx_matches_away ON matches(away_team_code);
CREATE INDEX IF NOT EXISTS idx_matches_competition ON matches(competition, season);

CREATE TABLE IF NOT EXISTS xg_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        TEXT NOT NULL,
    team_code       TEXT NOT NULL,
    player_name     TEXT,
    xg              REAL NOT NULL,
    minute          INTEGER,
    shot_type       TEXT,
    result          TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_xg_match ON xg_events(match_id);
CREATE INDEX IF NOT EXISTS idx_xg_team ON xg_events(team_code);

CREATE TABLE IF NOT EXISTS elo_history (
    team_code       TEXT NOT NULL,
    date            TEXT NOT NULL,
    elo             REAL NOT NULL,
    source          TEXT NOT NULL,
    PRIMARY KEY (team_code, date)
);

CREATE INDEX IF NOT EXISTS idx_elo_team ON elo_history(team_code);

CREATE TABLE IF NOT EXISTS match_player_stats (
    match_id        TEXT NOT NULL,
    team_code       TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    minutes         INTEGER DEFAULT 0,
    goals           INTEGER DEFAULT 0,
    assists         INTEGER DEFAULT 0,
    xg              REAL DEFAULT 0.0,
    xga             REAL DEFAULT 0.0,
    shots           INTEGER DEFAULT 0,
    shots_on_target INTEGER DEFAULT 0,
    key_passes      INTEGER DEFAULT 0,
    tackles         INTEGER DEFAULT 0,
    interceptions   INTEGER DEFAULT 0,
    cards_yellow    INTEGER DEFAULT 0,
    cards_red       INTEGER DEFAULT 0,
    PRIMARY KEY (match_id, team_code, player_name),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mps_team ON match_player_stats(team_code);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    matches_added   INTEGER DEFAULT 0,
    matches_updated INTEGER DEFAULT 0,
    status          TEXT NOT NULL,
    message         TEXT
);
"""


def init_db(path: Path | None = None) -> Path:
    """Create the SQLite database and tables if they do not exist."""
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    return db_path


@contextmanager
def get_connection(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with row factory enabled."""
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
