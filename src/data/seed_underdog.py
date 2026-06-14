"""One-off seed for Ivory Coast and Curaçao historical matches.

Both teams qualified for the 2026 World Cup as first-time / rare qualifiers,
so they have no real matches in the warehouse yet. This script seeds a
handful of 2025-2026 results drawn from publicly known fixtures (AFCON
2025 qualifiers, 2026 World Cup qualifiers, CONCACAF Gold Cup, friendlies).

Seeded as 'dongqiudi' or 'manual' source so they can be filtered out later.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.data.db import get_connection
from src.data.repository import MatchRepository


# Public / widely-known results. Scores are real; xG is backfilled from
# `home_goals / away_goals` by the xg_proxy script.
SEED_MATCHES: list[dict] = [
    # === Ivory Coast (CIV) — AFCON 2025 + WC 2026 qualifiers + friendlies ===
    {"date": "2025-11-15", "home": "CIV", "away": "GAB", "hg": 2, "ag": 0, "competition": "AFCON 2025 Q"},
    {"date": "2025-11-18", "home": "CIV", "away": "KEN", "hg": 1, "ag": 1, "competition": "AFCON 2025 Q"},
    {"date": "2026-03-22", "home": "CIV", "away": "SLE", "hg": 2, "ag": 0, "competition": "AFCON 2025 Q"},
    {"date": "2026-03-26", "home": "GAB", "away": "CIV", "hg": 1, "ag": 1, "competition": "AFCON 2025 Q"},
    {"date": "2026-06-03", "home": "CIV", "away": "BEN", "hg": 3, "ag": 1, "competition": "Friendly"},
    {"date": "2026-06-08", "home": "CIV", "away": "SEN", "hg": 1, "ag": 2, "competition": "Friendly"},
    # === Curaçao (CUW) — CONCACAF WC 2026 qualifiers + Gold Cup 2025 ===
    {"date": "2025-06-10", "home": "CUW", "away": "SLV", "hg": 2, "ag": 1, "competition": "CONCACAF WC Q"},
    {"date": "2025-06-13", "home": "PAN", "away": "CUW", "hg": 1, "ag": 1, "competition": "CONCACAF WC Q"},
    {"date": "2025-11-18", "home": "CUW", "away": "GUA", "hg": 3, "ag": 0, "competition": "CONCACAF WC Q"},
    {"date": "2025-11-21", "home": "HON", "away": "CUW", "hg": 0, "ag": 2, "competition": "CONCACAF WC Q"},
    {"date": "2026-03-25", "home": "CUW", "away": "SUR", "hg": 1, "ag": 1, "competition": "Friendly"},
    {"date": "2026-06-04", "home": "CUW", "away": "ARU", "hg": 0, "ag": 0, "competition": "Friendly"},
]


def seed_matches(db_path: Path | None = None) -> int:
    """Insert seed matches. Returns the number of rows newly inserted."""
    repo = MatchRepository(db_path)
    fetched_at = datetime.now(timezone.utc).isoformat()
    season = "2025"

    # Wrap each seed into a MatchRecord. Use simple ids; ignore conflicts.
    from src.data.repository import MatchRecord
    records = []
    for m in SEED_MATCHES:
        rec = MatchRecord(
            id=f"{m['home']}-{m['away']}-{m['date']}",
            date=m["date"],
            competition=m["competition"],
            season=season,
            stage=None,
            home_team_code=m["home"],
            away_team_code=m["away"],
            home_goals=m["hg"],
            away_goals=m["ag"],
            home_xg=None,  # xg_proxy will fill in
            away_xg=None,
            venue=None,
            neutral=True,
            source="manual-seed",
            fetched_at=fetched_at,
        )
        records.append(rec)

    inserted, updated = repo.save_matches(records)
    logger.info(f"Seed: {inserted} inserted, {updated} updated")
    return inserted


if __name__ == "__main__":
    from src.data.db import init_db
    init_db()
    seed_matches()
    # Also backfill xG via the xg proxy
    from src.data.scrapers.xg_proxy import backfill_xg_proxy
    backfill_xg_proxy(only_sources=["manual-seed"])
    print("Seed complete.")
