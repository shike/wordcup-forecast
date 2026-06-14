"""Repository pattern for the SQLite data warehouse.

All prediction features are built from the data accessed here. There is no
synthetic fallback: callers must handle missing data explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from src.data.db import get_connection


@dataclass(frozen=True)
class MatchRecord:
    id: str
    date: str
    competition: str
    season: str | None
    stage: str | None
    home_team_code: str
    away_team_code: str
    home_goals: int | None
    away_goals: int | None
    home_xg: float | None
    away_xg: float | None
    venue: str | None
    neutral: bool
    source: str
    fetched_at: str


@dataclass(frozen=True)
class TeamRecord:
    code: str
    name_en: str
    name_zh: str | None
    fifa_ranking: int | None
    elo: float | None
    confederation: str | None


class MatchRepository:
    """Read/write access to match results and related data."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def save_matches(self, matches: Iterable[MatchRecord]) -> tuple[int, int]:
        """Upsert matches. Returns (inserted, updated) counts."""
        inserted = updated = 0
        with get_connection(self._db_path) as conn:
            for m in matches:
                existing = conn.execute(
                    "SELECT 1 FROM matches WHERE id = ?", (m.id,)
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE matches SET
                            date = ?, competition = ?, season = ?, stage = ?,
                            home_team_code = ?, away_team_code = ?,
                            home_goals = ?, away_goals = ?, home_xg = ?, away_xg = ?,
                            venue = ?, neutral = ?, source = ?, fetched_at = ?
                        WHERE id = ?
                        """,
                        (
                            m.date, m.competition, m.season, m.stage,
                            m.home_team_code, m.away_team_code,
                            m.home_goals, m.away_goals, m.home_xg, m.away_xg,
                            m.venue, int(m.neutral), m.source, m.fetched_at,
                            m.id,
                        ),
                    )
                    updated += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO matches (
                            id, date, competition, season, stage,
                            home_team_code, away_team_code,
                            home_goals, away_goals, home_xg, away_xg,
                            venue, neutral, source, fetched_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            m.id, m.date, m.competition, m.season, m.stage,
                            m.home_team_code, m.away_team_code,
                            m.home_goals, m.away_goals, m.home_xg, m.away_xg,
                            m.venue, int(m.neutral), m.source, m.fetched_at,
                        ),
                    )
                    inserted += 1
            conn.commit()
        return inserted, updated

    def get_matches(
        self,
        team_code: str | None = None,
        before: str | None = None,
        after: str | None = None,
        competition: str | None = None,
        season: str | None = None,
        limit: int | None = None,
    ) -> list[MatchRecord]:
        """Fetch matches with optional filters, ordered by date descending."""
        clauses: list[str] = []
        params: list[object] = []
        if team_code:
            clauses.append("(home_team_code = ? OR away_team_code = ?)")
            params.extend([team_code, team_code])
        if before:
            clauses.append("date < ?")
            params.append(before)
        if after:
            clauses.append("date > ?")
            params.append(after)
        if competition:
            clauses.append("competition = ?")
            params.append(competition)
        if season:
            clauses.append("season = ?")
            params.append(season)

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM matches {where} ORDER BY date DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"

        with get_connection(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_match(row) for row in rows]

    def count_matches(self, team_code: str | None = None) -> int:
        """Return the number of matches in the warehouse."""
        with get_connection(self._db_path) as conn:
            if team_code:
                row = conn.execute(
                    "SELECT COUNT(*) FROM matches WHERE home_team_code = ? OR away_team_code = ?",
                    (team_code, team_code),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM matches").fetchone()
            return row[0] if row else 0

    def count_matches_before(self, team_code: str, date: str) -> int:
        """Return the number of matches for a team strictly before a date."""
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM matches
                WHERE (home_team_code = ? OR away_team_code = ?)
                  AND date < ?
                """,
                (team_code, team_code, date),
            ).fetchone()
            return row[0] if row else 0


def _row_to_match(row: sqlite3.Row) -> MatchRecord:  # type: ignore[name-defined]
    return MatchRecord(
        id=row["id"],
        date=row["date"],
        competition=row["competition"],
        season=row["season"],
        stage=row["stage"],
        home_team_code=row["home_team_code"],
        away_team_code=row["away_team_code"],
        home_goals=row["home_goals"],
        away_goals=row["away_goals"],
        home_xg=row["home_xg"],
        away_xg=row["away_xg"],
        venue=row["venue"],
        neutral=bool(row["neutral"]),
        source=row["source"],
        fetched_at=row["fetched_at"],
    )


class TeamRepository:
    """Read/write access to team seed data in the warehouse."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def save_teams(self, teams: Iterable[TeamRecord]) -> None:
        with get_connection(self._db_path) as conn:
            for t in teams:
                conn.execute(
                    """
                    INSERT INTO teams (code, name_en, name_zh, fifa_ranking, elo, confederation, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                        name_en = excluded.name_en,
                        name_zh = excluded.name_zh,
                        fifa_ranking = excluded.fifa_ranking,
                        elo = excluded.elo,
                        confederation = excluded.confederation,
                        updated_at = excluded.updated_at
                    """,
                    (
                        t.code, t.name_en, t.name_zh, t.fifa_ranking, t.elo,
                        t.confederation, datetime.now(timezone.utc).isoformat(),
                    ),
                )
            conn.commit()

    def get_team(self, code: str) -> TeamRecord | None:
        with get_connection(self._db_path) as conn:
            row = conn.execute("SELECT * FROM teams WHERE code = ?", (code,)).fetchone()
            if not row:
                return None
            return TeamRecord(
                code=row["code"],
                name_en=row["name_en"],
                name_zh=row["name_zh"],
                fifa_ranking=row["fifa_ranking"],
                elo=row["elo"],
                confederation=row["confederation"],
            )


class EloRepository:
    """Read/write access to historical ELO ratings."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def save_ratings(self, team_code: str, ratings: Iterable[tuple[str, float]], source: str) -> None:
        with get_connection(self._db_path) as conn:
            for date, elo in ratings:
                conn.execute(
                    """
                    INSERT INTO elo_history (team_code, date, elo, source)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(team_code, date) DO UPDATE SET
                        elo = excluded.elo,
                        source = excluded.source
                    """,
                    (team_code, date, elo, source),
                )
            conn.commit()

    def get_rating(self, team_code: str, date: str) -> float | None:
        """Return the most recent ELO rating for a team on or before date."""
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT elo FROM elo_history
                WHERE team_code = ? AND date <= ?
                ORDER BY date DESC LIMIT 1
                """,
                (team_code, date),
            ).fetchone()
            return row["elo"] if row else None
