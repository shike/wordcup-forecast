"""Dedupe and canonicalise StatsBomb World Cup match records.

StatsBomb's 2018 dataset uses both `ISL` and `ICE` for Iceland, and both
`NGA` and `NIG` for Nigeria. Each team's three group games therefore show
up as six rows instead of three, which inflates the match count and
double-counts the goal/xG totals. This script normalises the codes to
`ISL` and `NGA` and de-duplicates by match id (home/away/date).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from loguru import logger

from src.data.db import DB_PATH, init_db


# Canonical mappings for the codes StatsBomb uses inconsistently
CODE_ALIASES: dict[str, str] = {
    "ICE": "ISL",  # Iceland
    "NIG": "NGA",  # Nigeria
}


def canonicalise(code: str) -> str:
    return CODE_ALIASES.get(code, code)


def main(db_path: Path | None = None) -> None:
    db = db_path or DB_PATH
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        # 1. Update all matches to use canonical codes
        for old, new in CODE_ALIASES.items():
            conn.execute(
                "UPDATE matches SET home_team_code = ? WHERE home_team_code = ?",
                (new, old),
            )
            conn.execute(
                "UPDATE matches SET away_team_code = ? WHERE away_team_code = ?",
                (new, old),
            )
        conn.commit()

        # 2. Find duplicate groups: same date + same two teams (any order)
        rows = conn.execute(
            "SELECT id, date, home_team_code, away_team_code FROM matches"
        ).fetchall()
        by_key: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
        for r in rows:
            key = (
                r["date"],
                min(r["home_team_code"], r["away_team_code"]),
                max(r["home_team_code"], r["away_team_code"]),
            )
            by_key[key].append(r)

        duplicates = [(k, v) for k, v in by_key.items() if len(v) > 1]
        if not duplicates:
            logger.info("No duplicates found.")
            return

        # For each duplicate group, keep the row with the most populated
        # score/xG fields, delete the rest.
        deleted = 0
        for key, group in duplicates:
            # Pick the row with the most non-null numeric fields
            def richness(match_id: str) -> int:
                r = conn.execute(
                    """
                    SELECT home_goals IS NOT NULL AS hg,
                           away_goals IS NOT NULL AS ag,
                           home_xg IS NOT NULL AS hxg,
                           away_xg IS NOT NULL AS axg
                    FROM matches WHERE id = ?
                    """,
                    (match_id,),
                ).fetchone()
                return sum(r) if r else 0

            group_sorted = sorted(group, key=lambda m: richness(m["id"]), reverse=True)
            keep = group_sorted[0]
            for dup in group_sorted[1:]:
                conn.execute("DELETE FROM matches WHERE id = ?", (dup["id"],))
                deleted += 1
            logger.info(
                f"  {key}: kept {keep['id']} (richness={richness(keep['id'])}),"
                f" removed {len(group_sorted) - 1}"
            )

        conn.commit()
        logger.info(f"Removed {deleted} duplicate rows.")


if __name__ == "__main__":
    main()
