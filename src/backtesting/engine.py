"""Backtesting engine for the prediction model.

Runs time-shifted predictions on historical matches and scores them against
actual outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from src.data.features import FeatureBuilder
from src.data.repository import MatchRecord, MatchRepository
from src.data.team_data import get_team
from src.models.poisson import predict_poisson
from src.utils.models import TeamStats


@dataclass(frozen=True)
class BacktestMatchResult:
    match_id: str
    date: str
    home_team: str
    away_team: str
    actual_score: str
    predicted_probs: tuple[float, float, float]
    expected_goals: tuple[float, float]
    sample_size_a: int
    sample_size_b: int


class BacktestEngine:
    """Run no-lookahead backtests on matches in the warehouse."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._builder = FeatureBuilder(db_path)
        self._repo = MatchRepository(db_path)

    def run(
        self,
        competition: str | None = None,
        season: str | None = None,
        min_sample_size: int = 1,
    ) -> list[BacktestMatchResult]:
        """Run backtest on all matches matching the filters.

        For each match, features are computed using only matches that occurred
        strictly before the match date. Matches for which either team lacks
        real history are skipped — we never invent statistics.
        """
        matches = self._repo.get_matches(
            competition=competition, season=season, limit=None
        )
        # Oldest first so the rolling window is realistic
        matches = sorted(matches, key=lambda m: m.date)

        results: list[BacktestMatchResult] = []
        for m in matches:
            if m.home_goals is None or m.away_goals is None:
                continue

            stats_a = self._builder.build_team_stats(
                m.home_team_code, m.date, last_n=10, min_matches=min_sample_size
            )
            stats_b = self._builder.build_team_stats(
                m.away_team_code, m.date, last_n=10, min_matches=min_sample_size
            )

            if stats_a is None or stats_b is None:
                logger.debug(f"Skipping {m.id}: insufficient history")
                continue

            sample_size_a = self._repo.count_matches_before(m.home_team_code, m.date)
            sample_size_b = self._repo.count_matches_before(m.away_team_code, m.date)

            try:
                elo_a = get_team(m.home_team_code).elo
            except KeyError:
                elo_a = 1800.0
            try:
                elo_b = get_team(m.away_team_code).elo
            except KeyError:
                elo_b = 1800.0

            probs, (lam_a, lam_b), _, _ = predict_poisson(
                stats_a, stats_b,
                elo_a=elo_a,
                elo_b=elo_b,
                sample_size_a=sample_size_a,
                sample_size_b=sample_size_b,
                home_advantage=1.0,
            )

            results.append(
                BacktestMatchResult(
                    match_id=m.id,
                    date=m.date,
                    home_team=m.home_team_code,
                    away_team=m.away_team_code,
                    actual_score=f"{m.home_goals}-{m.away_goals}",
                    predicted_probs=probs,
                    expected_goals=(lam_a, lam_b),
                    sample_size_a=sample_size_a,
                    sample_size_b=sample_size_b,
                )
            )

        return results
