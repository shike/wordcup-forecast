"""Ingest international match results from the martj42 open dataset.

Data source: https://github.com/martj42/international_results
License: CC0 / public domain contribution

The CSV covers international 'A' matches from 1872 to future fixtures. Only
matches where both teams can be mapped to a project code are yielded, but all
matches are used for ELO computation in the companion elo_calculator module.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from loguru import logger

from src.data.repository import MatchRecord
from src.data.scrapers._team_names import resolve_team_name
from src.utils.config import config


DATASET_DIR = config.cache_dir.parent / "data" / "external"
RESULTS_CSV = DATASET_DIR / "international_results.csv"


def _score(raw: str) -> int | None:
    """Parse a score cell. 'NA' means the match is in the future."""
    if raw is None:
        return None
    raw = raw.strip()
    if raw.upper() == "NA":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _match_id(home_code: str, away_code: str, match_date: str) -> str:
    """Stable ID that allows duplicate matches between the same teams."""
    return f"{home_code}-{away_code}-{match_date}"


def load_matches(
    csv_path: Path | None = None,
    require_both_teams: bool = True,
    max_date: str | None = None,
) -> Iterable[MatchRecord]:
    """Yield MatchRecord objects from the martj42 CSV.

    Args:
        csv_path: Override path to results.csv.
        require_both_teams: If True, only yield matches where both teams map to
            a project code. If False, yield all matches with at least one mapped
            team (home/away code may be empty for unmapped opponents).
        max_date: ISO date string. Matches strictly after this date are skipped
            so the warehouse does not include fixtures without a result.
    """
    path = csv_path or RESULTS_CSV
    if not path.exists():
        raise FileNotFoundError(
            f"martj42 dataset not found at {path}. "
            f"Run: curl -L https://raw.githubusercontent.com/martj42/international_results/master/results.csv -o {path}"
        )

    fetched_at = datetime.now(timezone.utc).isoformat()
    yielded = skipped = future = 0

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            match_date = row["date"]
            if max_date and match_date > max_date:
                future += 1
                continue

            home_name = row["home_team"].strip()
            away_name = row["away_team"].strip()
            home_code = resolve_team_name(home_name, match_date)
            away_code = resolve_team_name(away_name, match_date)

            if require_both_teams and (not home_code or not away_code):
                skipped += 1
                continue

            home_goals = _score(row["home_score"])
            away_goals = _score(row["away_score"])
            if home_goals is None or away_goals is None:
                # Future fixture without a result
                continue

            competition = row.get("tournament", "Unknown") or "Unknown"
            venue = row.get("city") or None
            neutral = (row.get("neutral", "").strip().upper() == "TRUE")

            yield MatchRecord(
                id=_match_id(home_code or home_name[:3].upper(), away_code or away_name[:3].upper(), match_date),
                date=match_date,
                competition=competition,
                season=match_date[:4],
                stage=None,
                home_team_code=home_code or "",
                away_team_code=away_code or "",
                home_goals=home_goals,
                away_goals=away_goals,
                home_xg=None,
                away_xg=None,
                venue=venue,
                neutral=neutral,
                source="martj42-international-results",
                fetched_at=fetched_at,
            )
            yielded += 1

    logger.info(
        f"martj42 ingest: {yielded} matches yielded, {skipped} skipped, "
        f"{future} future fixtures ignored"
    )


def count_matches(csv_path: Path | None = None) -> int:
    """Return the total number of result rows in the CSV."""
    path = csv_path or RESULTS_CSV
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # exclude header
