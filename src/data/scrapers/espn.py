"""ESPN historical match result scraper.

Fetches completed match results from ESPN's public scoreboard API. Useful for
recent friendlies, qualifiers, and continental tournaments that are not in
StatsBomb Open Data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlencode

import requests
from loguru import logger

from src.data.repository import MatchRecord


ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# ESPN league slugs that may contain national-team matches
LEAGUES = ["fifa.world", "fifa.friendly", "fifa.worldq.uefa", "fifa.worldq.conmebol"]


def _league_for_team(team_name: str) -> str:
    """Pick a likely ESPN league slug for a national team match."""
    # National team friendlies and World Cup qualifiers live under fifa.* slugs.
    # Default to the catch-all friendly league.
    return "fifa.friendly"


def _fetch_scoreboard(league: str, date_str: str) -> dict:
    url = f"{ESPN_BASE}/{league}/scoreboard"
    params = {"dates": date_str}
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning(f"ESPN scoreboard failed for {league}/{date_str}: {exc}")
        return {}


def _normalize_team_name(name: str) -> str:
    """Map ESPN display names to project team names where they differ."""
    mapping = {
        "United States": "USA",
        "Korea Republic": "South Korea",
    }
    return mapping.get(name, name)


def _team_code_from_name(name: str) -> str:
    """Best-effort 3-letter code from team display name."""
    name = _normalize_team_name(name)
    # Common national teams
    direct = {
        "Argentina": "ARG", "Australia": "AUS", "Belgium": "BEL", "Brazil": "BRA",
        "Cameroon": "CMR", "Canada": "CAN", "Costa Rica": "CRC", "Croatia": "CRO",
        "Denmark": "DEN", "Ecuador": "ECU", "England": "ENG", "France": "FRA",
        "Germany": "GER", "Ghana": "GHA", "Iran": "IRN", "Japan": "JPN",
        "Mexico": "MEX", "Morocco": "MAR", "Netherlands": "NED", "Poland": "POL",
        "Portugal": "POR", "Qatar": "QAT", "Saudi Arabia": "KSA", "Senegal": "SEN",
        "Serbia": "SRB", "South Korea": "KOR", "Spain": "ESP", "Switzerland": "SUI",
        "Tunisia": "TUN", "USA": "USA", "Uruguay": "URU", "Wales": "WAL",
    }
    if name in direct:
        return direct[name]
    return name[:3].upper()


def _parse_event(event: dict) -> MatchRecord | None:
    """Convert a single ESPN event into a MatchRecord."""
    status = event.get("status", {})
    type_desc = status.get("type", {}).get("description", "")
    if type_desc not in ("Final", "Finished"):
        return None

    competitors = event.get("competitions", [{}])[0].get("competitors", [])
    if len(competitors) != 2:
        return None

    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None

    home_name = home.get("team", {}).get("displayName", "")
    away_name = away.get("team", {}).get("displayName", "")
    home_code = _team_code_from_name(home_name)
    away_code = _team_code_from_name(away_name)

    try:
        home_goals = int(home.get("score", ""))
        away_goals = int(away.get("score", ""))
    except (ValueError, TypeError):
        return None

    date_str = event.get("date", "")[:10]
    if not date_str:
        return None

    venue = event.get("competitions", [{}])[0].get("venue", {}).get("fullName")
    return MatchRecord(
        id=f"{home_code}-{away_code}-{date_str}",
        date=date_str,
        competition=event.get("season", {}).get("slug", "unknown"),
        season=event.get("season", {}).get("year"),
        stage=event.get("competitions", [{}])[0].get("type", {}).get("abbreviation"),
        home_team_code=home_code,
        away_team_code=away_code,
        home_goals=home_goals,
        away_goals=away_goals,
        home_xg=None,  # ESPN API does not expose xG
        away_xg=None,
        venue=venue,
        neutral=False,
        source="espn",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def fetch_matches_for_date_range(
    start: date,
    end: date,
    leagues: list[str] | None = None,
) -> Iterable[MatchRecord]:
    """Yield completed match records across a date range and set of leagues.

    Dates are iterated day-by-day because ESPN scoreboard works best with
    single-date queries.
    """
    leagues = leagues or LEAGUES
    seen: set[str] = set()
    current = start
    while current <= end:
        date_str = current.strftime("%Y%m%d")
        for league in leagues:
            data = _fetch_scoreboard(league, date_str)
            for event in data.get("events", []):
                record = _parse_event(event)
                if record and record.id not in seen:
                    seen.add(record.id)
                    yield record
        current += timedelta(days=1)


def fetch_team_matches(
    team_code: str,
    start: date,
    end: date,
) -> Iterable[MatchRecord]:
    """Fetch all completed matches involving a team in a date range."""
    for record in fetch_matches_for_date_range(start, end):
        if team_code in (record.home_team_code, record.away_team_code):
            yield record
