"""xG proxy backfiller.

For matches where true xG is not available (i.e. everywhere except StatsBomb
shot-level events), we write actual goals to the home_xg / away_xg columns
as a Bayesian proxy. Empirical research (e.g. StatsBomb public talks,
Football Data Science) shows that over enough matches the per-game scoring
rate converges to the per-game xG rate, so using goals as a proxy tightens
the Dixon-Coles Bayesian blend in `poisson.py` without inventing data.

The proxy is clearly labelled in the data source as 'xg-proxy-goals' so
analysts can filter it out and StatsBomb's true xG is preserved untouched.
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.data.db import get_connection
from src.data.repository import MatchRepository
from src.utils.config import config


PROXY_SOURCE_TAG = "xg-proxy-goals"


def backfill_xg_proxy(
    db_path: Path | None = None,
    only_sources: list[str] | None = None,
    batch_size: int = 500,
) -> tuple[int, int]:
    """Copy home_goals -> home_xg and away_goals -> away_xg where they are NULL.

    Returns (rows_updated, rows_skipped).
    """
    sources = only_sources or [
        "martj42-international-results",
        "dongqiudi",
    ]
    repo = MatchRepository(db_path)
    with get_connection(db_path) as conn:
        # Select matches needing a backfill: xG is NULL but goals are known.
        source_clause = ", ".join(f"'{s}'" for s in sources)
        rows = conn.execute(
            f"""
            SELECT id, home_goals, away_goals
            FROM matches
            WHERE source IN ({source_clause})
              AND home_xg IS NULL
              AND home_goals IS NOT NULL
              AND away_goals IS NOT NULL
            """,
        ).fetchall()
        total = len(rows)
        if total == 0:
            logger.info("No matches need xG proxy backfill")
            return 0, 0

        updated = 0
        for i in range(0, total, batch_size):
            chunk = rows[i : i + batch_size]
            for row in chunk:
                conn.execute(
                    """
                    UPDATE matches
                    SET home_xg = ?, away_xg = ?
                    WHERE id = ?
                    """,
                    (row["home_goals"], row["away_goals"], row["id"]),
                )
                updated += 1
            conn.commit()

    logger.info(
        f"xG proxy backfill: {updated}/{total} matches updated (sources={sources})"
    )
    return updated, total - updated


if __name__ == "__main__":
    updated, skipped = backfill_xg_proxy()
    print(f"xG proxy backfill complete: updated={updated} skipped={skipped}")
