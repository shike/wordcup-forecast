"""Data ingestion orchestrator.

Loads real match data from configured scrapers into the SQLite warehouse.
All ingestion is explicit and logged; no synthetic data is generated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.data.db import get_connection
from src.data.repository import EloRepository, MatchRecord, MatchRepository
from src.data.scrapers import dongqiudi
from src.data.scrapers import elo as elo_scraper
from src.data.scrapers import espn
from src.data.scrapers import martj42
from src.data.scrapers import statsbomb
from src.data.scrapers.elo_calculator import save_computed_elo
from src.utils.config import config


def ingest_statsbomb_world_cups(
    db_path: Path | None = None,
    include_events: bool = False,
) -> dict[str, int]:
    """Ingest all available World Cup data from StatsBomb Open Data.

    Args:
        include_events: Download shot-level event files to compute xG. Much
            slower; defaults to False.

    Returns a mapping "competition_name" -> matches_inserted.
    """
    repo = MatchRepository(db_path)
    totals: dict[str, int] = {}

    for competition_id, season_id, name in statsbomb.available_world_cups():
        logger.info(f"Ingesting {name} from StatsBomb…")
        try:
            matches = list(statsbomb.load_matches(competition_id, season_id, include_events=include_events))
            inserted, updated = repo.save_matches(matches)
            totals[name] = inserted
            _log_ingestion(
                source=f"statsbomb-{competition_id}-{season_id}",
                added=inserted,
                updated=updated,
                status="success",
                message=f"{name}: {inserted} inserted, {updated} updated",
                db_path=db_path,
            )
            logger.info(f"  {name}: {inserted} inserted, {updated} updated")
        except Exception as exc:
            _log_ingestion(
                source=f"statsbomb-{competition_id}-{season_id}",
                added=0,
                updated=0,
                status="failed",
                message=str(exc),
                db_path=db_path,
            )
            logger.error(f"  {name} failed: {exc}")
            raise

    return totals


def _log_ingestion(
    source: str,
    added: int,
    updated: int,
    status: str,
    message: str,
    db_path: Path | None = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ingestion_log (source, started_at, finished_at, matches_added, matches_updated, status, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                added,
                updated,
                status,
                message,
            ),
        )
        conn.commit()


def ingest_elo_ratings(db_path: Path | None = None) -> int:
    """Ingest the latest ELO ratings from eloratings.net.

    Returns the number of team ratings saved.
    """
    logger.info("Ingesting ELO ratings from eloratings.net…")
    repo = EloRepository(db_path)
    try:
        count = elo_scraper.save_latest_ratings(repo)
        _log_ingestion(
            source="eloratings.net",
            added=count,
            updated=0,
            status="success",
            message=f"ELO ratings: {count} saved",
            db_path=db_path,
        )
        logger.info(f"  ELO ratings: {count} saved")
        return count
    except Exception as exc:
        _log_ingestion(
            source="eloratings.net",
            added=0,
            updated=0,
            status="failed",
            message=str(exc),
            db_path=db_path,
        )
        logger.error(f"  ELO ratings failed: {exc}")
        raise


def ingest_dongqiudi_important(db_path: Path | None = None) -> int:
    """Ingest completed matches from Dongqiudi's free 'important' feed.

    Only matches where both teams map to a project 3-letter code and the game
    is finished (Played status) are persisted. Returns the number of new
    matches inserted.
    """
    logger.info("Ingesting Dongqiudi important matches (no key required)…")
    repo = MatchRepository(db_path)
    try:
        records = [
            MatchRecord(
                id=raw["id"],
                date=raw["date"],
                competition=raw["competition"],
                season=raw["season"],
                stage=raw["stage"],
                home_team_code=raw["home_team_code"],
                away_team_code=raw["away_team_code"],
                home_goals=raw["home_goals"],
                away_goals=raw["away_goals"],
                home_xg=raw["home_xg"],
                away_xg=raw["away_xg"],
                venue=raw["venue"],
                neutral=raw["neutral"],
                source=raw["source"],
                fetched_at=raw["fetched_at"],
            )
            for raw in dongqiudi.fetch_match_records()
        ]
        inserted, updated = repo.save_matches(records)
        _log_ingestion(
            source="dongqiudi",
            added=inserted,
            updated=updated,
            status="success",
            message=f"Dongqiudi: {inserted} inserted, {updated} updated",
            db_path=db_path,
        )
        logger.info(f"  Dongqiudi: {inserted} inserted, {updated} updated")
        return inserted
    except Exception as exc:
        _log_ingestion(
            source="dongqiudi",
            added=0,
            updated=0,
            status="failed",
            message=str(exc),
            db_path=db_path,
        )
        logger.error(f"  Dongqiudi ingest failed: {exc}")
        raise


def ingest_espn_date_range(
    start: str,
    end: str,
    db_path: Path | None = None,
) -> int:
    """Ingest completed matches from ESPN for a date range.

    Date format: YYYY-MM-DD. Useful for recent friendlies, qualifiers, and
    continental tournaments not covered by StatsBomb Open Data.
    """
    from datetime import date

    logger.info(f"Ingesting ESPN matches from {start} to {end}…")
    repo = MatchRepository(db_path)
    try:
        matches = list(espn.fetch_matches_for_date_range(
            date.fromisoformat(start), date.fromisoformat(end)
        ))
        inserted, updated = repo.save_matches(matches)
        _log_ingestion(
            source="espn",
            added=inserted,
            updated=updated,
            status="success",
            message=f"ESPN {start}..{end}: {inserted} inserted, {updated} updated",
            db_path=db_path,
        )
        logger.info(f"  ESPN {start}..{end}: {inserted} inserted, {updated} updated")
        return inserted
    except Exception as exc:
        _log_ingestion(
            source="espn",
            added=0,
            updated=0,
            status="failed",
            message=str(exc),
            db_path=db_path,
        )
        logger.error(f"  ESPN ingest failed: {exc}")
        raise


def ingest_martj42_matches(
    db_path: Path | None = None,
    csv_path: Path | None = None,
    max_date: str | None = None,
) -> int:
    """Ingest international match results from the martj42 open dataset.

    Matches where both teams map to a project code are stored in the warehouse.
    The full dataset is also used for ELO computation.
    """
    logger.info("Ingesting martj42 international results...")
    repo = MatchRepository(db_path)
    matches = list(martj42.load_matches(csv_path=csv_path, max_date=max_date))
    inserted, updated = repo.save_matches(matches)
    _log_ingestion(
        source="martj42-international-results",
        added=inserted,
        updated=updated,
        status="success",
        message=f"{len(matches)} international matches: {inserted} inserted, {updated} updated",
        db_path=db_path,
    )
    logger.info(f"  {len(matches)} matches: {inserted} inserted, {updated} updated")
    return inserted


def ingest_computed_elo(
    db_path: Path | None = None,
    csv_path: Path | None = None,
) -> int:
    """Compute ELO ratings from the martj42 dataset and persist them."""
    logger.info("Computing ELO ratings from martj42 match history...")
    elo_repo = EloRepository(db_path)
    count = save_computed_elo(elo_repo, csv_path=csv_path)
    _log_ingestion(
        source="martj42-elo-computed",
        added=count,
        updated=0,
        status="success",
        message=f"Computed ELO: {count} ratings saved",
        db_path=db_path,
    )
    logger.info(f"  Computed ELO: {count} ratings saved")
    return count


def run_full_ingest(
    db_path: Path | None = None,
    espn_start: str | None = None,
    espn_end: str | None = None,
    include_events: bool = False,
    martj42_max_date: str | None = None,
) -> dict[str, int]:
    """Run all configured ingestion sources.

    Sources are run in order of priority:
      1. StatsBomb Open Data (World Cups)
      2. martj42 international results (global 'A' matches)
      3. Computed ELO ratings from the martj42 dataset
      4. Dongqiudi important feed (no key, Chinese-friendly recent results)
      5. ESPN date range (optional, for recent friendlies/qualifiers)

    Args:
        include_events: Passed to StatsBomb loader; True enables xG extraction
            from shot-level event files (much slower).
        martj42_max_date: If provided, skip martj42 fixtures strictly after this
            date (e.g. future World Cup group-stage placeholders).
    """
    from src.data.db import init_db

    init_db(db_path)
    results = ingest_statsbomb_world_cups(db_path, include_events=include_events)
    results["martj42"] = ingest_martj42_matches(
        db_path, max_date=martj42_max_date
    )
    results["computed_elo"] = ingest_computed_elo(db_path)
    results["dongqiudi"] = ingest_dongqiudi_important(db_path)
    if espn_start and espn_end:
        results[f"espn_{espn_start}_{espn_end}"] = ingest_espn_date_range(
            espn_start, espn_end, db_path
        )
    return results


if __name__ == "__main__":
    results = run_full_ingest()
    print("Ingestion results:", results)
    print("Total matches in warehouse:", MatchRepository().count_matches())
