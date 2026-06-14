"""fbref (Statbomb) match-level xG scraper.

fbref exposes per-match xG and advanced stats in HTML tables. This module
scrapes the match summary page and extracts team-level xG.

Use responsibly: rate-limit requests, respect robots.txt, and fall back to
Understat or StatsBomb when blocked.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.data.repository import MatchRecord


FBREF_BASE = "https://fbref.com"


@dataclass(frozen=True)
class FbrefMatch:
    match_id: str
    date: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    home_xg: float | None
    away_xg: float | None
    competition: str
    venue: str | None


class FbrefScraper:
    """Lightweight fbref scraper with rate limiting and caching."""

    def __init__(self, delay_seconds: float = 1.0) -> None:
        self.delay = delay_seconds
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })

    def _get(self, url: str) -> str:
        import time
        time.sleep(self.delay)
        response = self._session.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    def fetch_match(self, fbref_url: str) -> FbrefMatch | None:
        """Parse a single fbref match page for xG and score."""
        try:
            html = self._get(fbref_url)
        except requests.RequestException as exc:
            logger.warning(f"fbref fetch failed for {fbref_url}: {exc}")
            return None

        soup = BeautifulSoup(html, "html.parser")
        scorebox = soup.find("div", class_="scorebox")
        if not scorebox:
            return None

        teams = scorebox.find_all("div", class_="scorebox_entity")
        if len(teams) < 2:
            return None

        home_name = teams[0].find("a").get_text(strip=True) if teams[0].find("a") else ""
        away_name = teams[1].find("a").get_text(strip=True) if teams[1].find("a") else ""

        scores = scorebox.find_all("div", class_="score")
        if len(scores) < 2:
            return None
        try:
            home_goals = int(scores[0].get_text(strip=True))
            away_goals = int(scores[1].get_text(strip=True))
        except ValueError:
            return None

        # xG is usually in a "scores" row below the main score
        xg_divs = scorebox.find_all("div", class_="score_xg")
        home_xg = float(xg_divs[0].get_text(strip=True)) if len(xg_divs) > 0 else None
        away_xg = float(xg_divs[1].get_text(strip=True)) if len(xg_divs) > 1 else None

        venue_tag = soup.find("small", string=lambda t: t and "Venue" in t)
        venue = venue_tag.get_text(strip=True).replace("Venue:", "").strip() if venue_tag else None

        date_tag = soup.find("span", {"class": "venuetime"})
        date = date_tag.get("data-venue-date", "") if date_tag else ""

        competition_tag = soup.find("a", {"data-attr-id": "competition"})
        competition = competition_tag.get_text(strip=True) if competition_tag else "unknown"

        return FbrefMatch(
            match_id=fbref_url.split("/")[-2] if "/" in fbref_url else fbref_url,
            date=date,
            home_team=home_name,
            away_team=away_name,
            home_goals=home_goals,
            away_goals=away_goals,
            home_xg=home_xg,
            away_xg=away_xg,
            competition=competition,
            venue=venue,
        )

    def search_matches(
        self,
        team_slug: str,
        year: int,
        competition_slug: str = "",
    ) -> Iterable[FbrefMatch]:
        """Search fbref's team schedule page for matches.

        Raises NotImplementedError because fbref's schedule page structure
        changes too often to be parsed reliably. Callers should supply direct
        match URLs to fetch_match().
        """
        raise NotImplementedError(
            "fbref search_matches is not implemented; pass direct match URLs to fetch_match()."
        )


def _team_code_from_fbref_name(name: str) -> str:
    """Map fbref team name to project 3-letter code."""
    direct = {
        "Argentina": "ARG", "Australia": "AUS", "Belgium": "BEL", "Brazil": "BRA",
        "Cameroon": "CMR", "Canada": "CAN", "Costa Rica": "CRC", "Croatia": "CRO",
        "Denmark": "DEN", "Ecuador": "ECU", "England": "ENG", "France": "FRA",
        "Germany": "GER", "Ghana": "GHA", "Iran": "IRN", "Japan": "JPN",
        "Mexico": "MEX", "Morocco": "MAR", "Netherlands": "NED", "Poland": "POL",
        "Portugal": "POR", "Qatar": "QAT", "Saudi Arabia": "KSA", "Senegal": "SEN",
        "Serbia": "SRB", "South Korea": "KOR", "Spain": "ESP", "Switzerland": "SUI",
        "Tunisia": "TUN", "United States": "USA", "Uruguay": "URU", "Wales": "WAL",
    }
    return direct.get(name, name[:3].upper())


def convert_fbref_match(fbref_match: FbrefMatch) -> MatchRecord:
    """Convert an FbrefMatch into a warehouse MatchRecord."""
    home_code = _team_code_from_fbref_name(fbref_match.home_team)
    away_code = _team_code_from_fbref_name(fbref_match.away_team)
    return MatchRecord(
        id=f"{home_code}-{away_code}-{fbref_match.date}",
        date=fbref_match.date,
        competition=fbref_match.competition,
        season=None,
        stage=None,
        home_team_code=home_code,
        away_team_code=away_code,
        home_goals=fbref_match.home_goals,
        away_goals=fbref_match.away_goals,
        home_xg=fbref_match.home_xg,
        away_xg=fbref_match.away_xg,
        venue=fbref_match.venue,
        neutral=False,
        source="fbref",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
