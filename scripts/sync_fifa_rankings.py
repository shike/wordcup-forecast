"""Sync FIFA World Ranking from the official CSV.

The current FIFA API requires token-based auth that shifts often, so this
loader targets the publicly downloadable `fifa_ranking.csv` snapshot the
operator drops into data/. If the CSV is missing, the loader returns an
empty dict and the pipeline keeps the bundled seed ELO snapshot.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from loguru import logger

from src.utils.config import config


RANKING_CSV: Path = config.cache_dir.parent / "data" / "fifa_ranking.csv"


# World Football team name -> 3-letter code
TEAM_NAME_TO_CODE: dict[str, str] = {
    "Argentina": "ARG", "Australia": "AUS", "Belgium": "BEL", "Brazil": "BRA",
    "Cameroon": "CMR", "Canada": "CAN", "Colombia": "COL", "Costa Rica": "CRC",
    "Croatia": "CRO", "Denmark": "DEN", "Ecuador": "ECU", "Egypt": "EGY",
    "England": "ENG", "France": "FRA", "Germany": "GER", "Ghana": "GHA",
    "Iceland": "ISL", "Iran": "IRN", "Japan": "JPN", "Mexico": "MEX",
    "Morocco": "MAR", "Netherlands": "NED", "Nigeria": "NGA", "Panama": "PAN",
    "Peru": "PER", "Poland": "POL", "Portugal": "POR", "Qatar": "QAT",
    "Russia": "RUS", "Saudi Arabia": "KSA", "Senegal": "SEN", "Serbia": "SRB",
    "South Korea": "KOR", "Spain": "ESP", "Sweden": "SWE",
    "Switzerland": "SUI", "Tunisia": "TUN", "United States": "USA",
    "Uruguay": "URU", "Wales": "WAL", "Haiti": "HAI", "Bosnia and Herzegovina": "BIH",
    "Scotland": "SCO", "Turkey": "TUR", "Cape Verde": "CPV", "Italy": "ITA",
    "Paraguay": "PAR",
}


def load_rankings() -> dict[str, dict]:
    """Return mapping {team_code: {rank, points, date}} from the CSV."""
    if not RANKING_CSV.exists():
        logger.info(f"No ranking CSV at {RANKING_CSV}")
        return {}
    out: dict[str, dict] = {}
    with open(RANKING_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            team_name = row.get("team") or row.get("Team") or row.get("country") or ""
            code = TEAM_NAME_TO_CODE.get(team_name)
            if not code:
                continue
            try:
                rank = int(row.get("rank") or row.get("Rank") or 0)
                points = float(row.get("points") or row.get("Points") or 0)
            except ValueError:
                continue
            if rank <= 0 or points <= 0:
                continue
            out[code] = {
                "rank": rank,
                "points": points,
                "date": row.get("date") or datetime.now(timezone.utc).date().isoformat(),
            }
    return out


def save_to_teams_json() -> int:
    """Update data/teams.json with current FIFA rank + points for each team."""
    rankings = load_rankings()
    if not rankings:
        logger.warning("No rankings to apply.")
        return 0

    with open(config.teams_json, encoding="utf-8") as f:
        teams = json.load(f)

    applied = 0
    for code, info in rankings.items():
        if code in teams:
            teams[code]["fifa_ranking"] = info["rank"]
            teams[code]["fifa_points"] = info["points"]
            applied += 1

    with open(config.teams_json, "w", encoding="utf-8") as f:
        json.dump(teams, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    logger.success(f"Updated {applied} team FIFA rankings.")
    return applied


import json  # late import to keep top-of-file tidy


if __name__ == "__main__":
    save_to_teams_json()
