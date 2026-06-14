"""World Football ELO Ratings loader.

The original eloratings.net HTML page was a SlickGrid JS-rendered site, so
the scraper here was failing silently. This module keeps the legacy HTML
fallback for reference but also supports:

1. A local CSV file at data/elo_ratings.csv (one row per team).
2. A bundled snapshot in `_DEFAULT_RATINGS` for teams that have not been
   overridden by the operator.

The bundled values reflect ratings as of late 2022 (post-World Cup). The
operator should refresh them as often as needed by updating the CSV or the
default dict.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.config import config


ELO_URL = "http://eloratings.net/"
ELO_CSV_PATH: Path = config.cache_dir.parent / "data" / "elo_ratings.csv"


# Bundled ratings snapshot (late 2022, post-World Cup reference). Operators
# may override these by placing an elo_ratings.csv next to data/teams.json.
_DEFAULT_RATINGS: dict[str, float] = {
    "ARG": 2130, "FRA": 2050, "BRA": 1980, "ENG": 1990, "ESP": 1960,
    "GER": 1900, "ITA": 1900, "POR": 1940, "NED": 1940, "BEL": 1870,
    "CRO": 1920, "URU": 1880, "COL": 1880, "MEX": 1860, "USA": 1840,
    "SUI": 1860, "DEN": 1870, "POL": 1820, "SRB": 1830, "SEN": 1820,
    "WAL": 1830, "MAR": 1800, "JPN": 1840, "KOR": 1830, "AUS": 1810,
    "CAN": 1830, "TUN": 1740, "GHA": 1780, "CMR": 1700, "ECU": 1820,
    "KSA": 1670, "IRN": 1830, "QAT": 1700, "NGA": 1700, "PAN": 1660,
    "PER": 1830, "CRC": 1720, "ISL": 1650, "SWE": 1820, "RUS": 1700,
    "HAI": 1620, "BIH": 1750, "SCO": 1820, "TUR": 1840, "CPV": 1650,
    "PAR": 1780, "EGY": 1750,
}


def _load_from_csv() -> dict[str, float]:
    if not ELO_CSV_PATH.exists():
        return {}
    out: dict[str, float] = {}
    with open(ELO_CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("code") or row.get("Code") or "").upper().strip()
            try:
                rating = float(row.get("elo") or row.get("Elo") or row.get("rating") or 0)
            except (TypeError, ValueError):
                continue
            if code and rating > 0:
                out[code] = rating
    return out


def fetch_latest_ratings() -> Iterable[tuple[str, float]]:
    """Yield (team_code, elo_rating) pairs.

    Priority:
      1. data/elo_ratings.csv if present.
      2. Bundled `_DEFAULT_RATINGS` snapshot.
    Falls back to (2) when (1) is missing so the prediction pipeline
    always has stable ELO values.
    """
    csv_ratings = _load_from_csv()
    source = csv_ratings if csv_ratings else _DEFAULT_RATINGS
    label = "elo_ratings.csv" if csv_ratings else "bundled snapshot"
    logger.info(f"Using {len(source)} ELO ratings from {label}")
    yield from source.items()


def save_latest_ratings(elo_repo: "EloRepository", source: str = "snapshot") -> int:
    """Persist the latest ELO ratings to the warehouse.

    Returns the number of ratings saved.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    count = 0
    for code, rating in fetch_latest_ratings():
        elo_repo.save_ratings(code, [(today, rating)], source)
        count += 1
    return count


# Legacy scraper kept for reference — eloratings.net moved to a
# JavaScript-rendered SlickGrid so this returns nothing.
def fetch_latest_ratings_html() -> Iterable[tuple[str, float]]:
    """Best-effort HTML scrape. Returns nothing on the current site."""
    try:
        resp = requests.get(ELO_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.debug(f"eloratings.net fetch failed: {exc}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"id": "ratings"})
    if table:
        for row in table.find("tbody").find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            name = cells[1].get_text(strip=True)
            try:
                rating = float(cells[2].get_text(strip=True))
            except ValueError:
                continue
            from src.data.scrapers.elo import _team_code_from_name  # type: ignore
            code = _team_code_from_name(name)
            yield code, rating
    # eloratings.net no longer exposes a static table.
