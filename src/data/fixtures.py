"""Fetch football fixtures for a given date.

Uses TheSportsDB (free, no API key) as the primary source.  This module
bypasses the Claude Code WebSearch/WebFetch tool layer by calling HTTP
endpoints directly via the ``requests`` library that's already a project
dependency.

Endpoint: https://www.thesportsdb.com/api/v1/json/{key}/eventsday.php
Default key ``3`` is the public test key, rate-limited but sufficient for
ad-hoc lookups.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from src.utils.config import config


API_BASE = "https://www.thesportsdb.com/api/v1/json"
DEFAULT_KEY = "3"  # public test key
SPORT = "Soccer"


@dataclass
class Fixture:
    fixture_id: str
    league: str
    country: str | None
    round: str | None
    home_team: str
    away_team: str
    venue: str | None
    kickoff_utc: str  # ISO 8601
    kickoff_local: str | None
    status: str  # NS / LIVE / FT
    home_badge: str | None
    away_badge: str | None
    league_badge: str | None

    def short(self) -> str:
        t = self.kickoff_utc.split("T")[1][:5] if "T" in self.kickoff_utc else ""
        return f"{t}  {self.home_team} vs {self.away_team}  ({self.league})"


def _cache_path(date_str: str) -> Path:
    return config.api_cache / f"fixtures_{date_str}.json"


def fetch_fixtures(date_str: str | None = None, key: str = DEFAULT_KEY) -> list[Fixture]:
    """Fetch all soccer fixtures for a given YYYY-MM-DD date (default: today UTC)."""
    if date_str is None:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

    cached = _cache_path(date_str)
    if cached.exists() and (datetime.utcnow() - datetime.fromtimestamp(cached.stat().st_mtime)) < timedelta(hours=1):
        try:
            raw = json.loads(cached.read_text(encoding="utf-8"))
            return [_to_fixture(e) for e in raw]
        except Exception:
            pass

    url = f"{API_BASE}/{key}/eventsday.php"
    try:
        resp = requests.get(url, params={"d": date_str, "s": SPORT}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"TheSportsDB fetch failed: {e}")
        return []

    data = resp.json()
    events = data.get("events") or []
    cached.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Fetched {len(events)} fixtures for {date_str}")
    return [_to_fixture(e) for e in events]


def _to_fixture(e: dict[str, Any]) -> Fixture:
    return Fixture(
        fixture_id=e.get("idEvent", ""),
        league=e.get("strLeague", "Unknown League"),
        country=e.get("strCountry"),
        round=e.get("intRound"),
        home_team=e.get("strHomeTeam", "TBD"),
        away_team=e.get("strAwayTeam", "TBD"),
        venue=e.get("strVenue"),
        kickoff_utc=e.get("strTimestamp") or "",
        kickoff_local=e.get("strTimeLocal") or e.get("strTime"),
        status=e.get("strStatus", "NS"),
        home_badge=e.get("strHomeTeamBadge"),
        away_badge=e.get("strAwayTeamBadge"),
        league_badge=e.get("strLeagueBadge"),
    )


def filter_interesting(
    fixtures: list[Fixture],
    leagues: list[str] | None = None,
    keywords: list[str] | None = None,
) -> list[Fixture]:
    """Filter fixtures to ones we care about (defaults: top national team events)."""
    if leagues is None:
        leagues = [
            "World Cup", "UEFA Champions League", "UEFA Europa League",
            "UEFA Nations League", "Copa Libertadores", "Copa America",
            "Euro", "Copa del Rey", "FA Cup", "Premier League", "La Liga",
            "Bundesliga", "Serie A", "Ligue 1", "FIFA", "CONCACAF Gold Cup",
            "African Cup of Nations", "AFC Asian Cup", "Friendlies",
        ]
    keywords = keywords or ["National Team", "World Cup", "Euro", "Copa", "Gold Cup", "Nations League"]
    out: list[Fixture] = []
    for f in fixtures:
        if any(l.lower() in f.league.lower() for l in leagues):
            out.append(f)
    if not out and keywords:
        for f in fixtures:
            if any(k.lower() in f.league.lower() for k in keywords):
                out.append(f)
    return out


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--all", action="store_true", help="Show all matches, not just interesting")
    args = parser.parse_args()

    fx = fetch_fixtures(args.date)
    if not args.all:
        fx = filter_interesting(fx)
    print(f"\n{len(fx)} matches")
    print("-" * 80)
    for f in fx:
        print(f.short())
        if f.venue:
            print(f"     venue: {f.venue}  ·  status: {f.status}")
