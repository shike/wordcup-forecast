"""Compute World Football Elo Ratings from the martj42 match history.

The algorithm follows the standard Elo system used by eloratings.net:
  - initial rating 1500 for every team
  - K depends on tournament importance
  - non-neutral matches give the home team a +100 rating advantage
  - historical aliases (Soviet Union → Russia, etc.) are mapped before calculation

Results are saved as dated ELO history so the prediction pipeline can fetch the
most recent rating for any team on any reference date.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

from loguru import logger

from src.data.scrapers._team_names import resolve_team_name


@dataclass
class _Match:
    date: date
    home_code: str
    away_code: str
    home_goals: int
    away_goals: int
    tournament: str
    neutral: bool


# Tournament importance weights (K-factor).
_K_FACTOR: dict[str, int] = {
    "fifa world cup": 60,
    "world cup": 60,
    "fifa world cup qualification": 30,
    "world cup qualification": 30,
    "confederations cup": 40,
    "fifa confederations cup": 40,
    "uefa euro": 50,
    "uefa euro qualification": 30,
    "copa américa": 50,
    "copa america": 50,
    "copa américa qualification": 30,
    "copa america qualification": 30,
    "african cup of nations": 50,
    "africa cup of nations": 50,
    "afc asian cup": 50,
    "asian cup": 50,
    "concacaf championship": 50,
    "concacaf gold cup": 50,
    "uefa nations league": 30,
    "friendly": 20,
}
_DEFAULT_K = 20
_HOME_ADVANTAGE = 100.0
_INITIAL_RATING = 1500.0


def _k_factor(tournament: str) -> int:
    """Return the K-factor for a tournament name."""
    key = tournament.strip().lower()
    return _K_FACTOR.get(key, _DEFAULT_K)


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Expected score for team A against team B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _actual_score(home_goals: int, away_goals: int, side: str) -> float:
    """Actual score from the perspective of the requested side."""
    if side == "home":
        if home_goals > away_goals:
            return 1.0
        if home_goals == away_goals:
            return 0.5
        return 0.0
    if away_goals > home_goals:
        return 1.0
    if away_goals == home_goals:
        return 0.5
    return 0.0


def _load_matches(csv_path: Path) -> list[_Match]:
    """Load and chronologically sort matches from the CSV."""
    matches: list[_Match] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            match_date = row["date"]
            home_name = row["home_team"].strip()
            away_name = row["away_team"].strip()
            home_code = resolve_team_name(home_name, match_date)
            away_code = resolve_team_name(away_name, match_date)
            if not home_code or not away_code:
                # Opponents outside the project code set still influence ratings
                # if they are historical aliases; otherwise skip.
                continue
            home_goals_str = row["home_score"].strip()
            away_goals_str = row["away_score"].strip()
            if home_goals_str.upper() == "NA" or away_goals_str.upper() == "NA":
                continue
            try:
                home_goals = int(home_goals_str)
                away_goals = int(away_goals_str)
            except ValueError:
                continue
            neutral = row.get("neutral", "").strip().upper() == "TRUE"
            matches.append(
                _Match(
                    date=date.fromisoformat(match_date),
                    home_code=home_code,
                    away_code=away_code,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    tournament=row.get("tournament", "Friendly") or "Friendly",
                    neutral=neutral,
                )
            )
    matches.sort(key=lambda m: m.date)
    logger.info(f"Loaded {len(matches)} resolved matches for ELO calculation")
    return matches


def compute_elo_history(csv_path: Path | None = None) -> dict[str, list[tuple[str, float]]]:
    """Compute dated ELO ratings for every mapped team.

    Returns a dict mapping team_code to a chronologically sorted list of
    (date_iso, elo_rating) tuples.
    """
    if csv_path is None:
        from src.utils.config import config
        csv_path = config.cache_dir.parent / "data" / "external" / "international_results.csv"

    matches = _load_matches(csv_path)
    ratings: dict[str, float] = {}
    history: dict[str, list[tuple[str, float]]] = {}

    for m in matches:
        for code in (m.home_code, m.away_code):
            if code not in ratings:
                ratings[code] = _INITIAL_RATING
                history.setdefault(code, [])

        home_rating = ratings[m.home_code]
        away_rating = ratings[m.away_code]

        effective_home_rating = home_rating + (0.0 if m.neutral else _HOME_ADVANTAGE)
        k = _k_factor(m.tournament)

        home_expected = _expected_score(effective_home_rating, away_rating)
        away_expected = _expected_score(away_rating, effective_home_rating)

        home_actual = _actual_score(m.home_goals, m.away_goals, "home")
        away_actual = _actual_score(m.home_goals, m.away_goals, "away")

        ratings[m.home_code] = home_rating + k * (home_actual - home_expected)
        ratings[m.away_code] = away_rating + k * (away_actual - away_expected)

        date_str = m.date.isoformat()
        history.setdefault(m.home_code, []).append((date_str, ratings[m.home_code]))
        history.setdefault(m.away_code, []).append((date_str, ratings[m.away_code]))

    logger.info(f"Computed ELO history for {len(history)} teams")
    return history


def save_computed_elo(
    elo_repo: "EloRepository",
    csv_path: Path | None = None,
) -> int:
    """Compute and persist ELO history to the warehouse.

    Returns the number of team rating records saved.
    """
    from src.data.scrapers.martj42 import DATASET_DIR

    if csv_path is None:
        csv_path = DATASET_DIR / "international_results.csv"

    history = compute_elo_history(csv_path)
    count = 0
    for code, ratings in history.items():
        # Keep only the last rating per date to avoid duplicate keys.
        deduped: list[tuple[str, float]] = []
        seen: set[str] = set()
        for d, r in ratings:
            if d not in seen:
                deduped.append((d, r))
                seen.add(d)
        if deduped:
            elo_repo.save_ratings(code, deduped, source="computed-from-martj42")
            count += len(deduped)
    logger.info(f"Persisted {count} computed ELO ratings")
    return count
