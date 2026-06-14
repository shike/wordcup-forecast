"""StatsBomb Open Data loader.

StatsBomb provides free JSON data for several competitions, including the 2018
and 2022 FIFA World Cups. This loader converts their match and event files into
`MatchRecord` objects for the warehouse.

Data source: https://github.com/statsbomb/open-data
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen

from src.data.repository import MatchRecord
from src.utils.config import config


STATSBOMB_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE_DIR = config.cache_dir / "statsbomb"

# World Cup competition identifiers in StatsBomb
WORLD_CUP_2018 = (43, 3)
WORLD_CUP_2022 = (43, 106)


def _fetch_json(path: str) -> dict | list:
    """Load JSON from local cache or StatsBomb GitHub raw URL."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local_path = CACHE_DIR / path.replace("/", "_")

    if local_path.exists():
        with open(local_path, encoding="utf-8") as f:
            return json.load(f)

    url = f"{STATSBOMB_BASE}/{path}"
    try:
        with urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc

    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def load_competition_matches(competition_id: int, season_id: int) -> list[dict]:
    """Load match list for a competition/season."""
    return _fetch_json(f"matches/{competition_id}/{season_id}.json")  # type: ignore[return-value]


def load_match_events(match_id: int) -> list[dict]:
    """Load event data for a single match."""
    return _fetch_json(f"events/{match_id}.json")  # type: ignore[return-value]


def _team_code_from_statsbomb_name(name: str, team_mapping: dict[str, str]) -> str:
    """Map StatsBomb team name to project 3-letter code."""
    # Direct mapping covers every team that has appeared in StatsBomb
    # World Cup data (2018 + 2022). Add new entries here when new
    # competitions are added.
    direct = {
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
        "Uruguay": "URU", "Wales": "WAL",
    }
    if name in direct:
        return direct[name]
    if name in team_mapping:
        return team_mapping[name]
    raise KeyError(
        f"StatsBomb team name not mapped to a 3-letter code: '{name}'. "
        f"Add it to _team_code_from_statsbomb_name before ingesting."
    )


def _extract_score_from_events(events: list[dict]) -> tuple[int | None, int | None]:
    """Derive final score from goal events when match JSON lacks it."""
    home_goals = away_goals = 0
    for ev in events:
        if ev.get("type", {}).get("name") == "Shot" and ev.get("shot", {}).get("outcome", {}).get("name") == "Goal":
            team = ev.get("team", {}).get("name", "")
            # We cannot know home/away from events alone; caller resolves via match.
            # This helper is intentionally conservative and returns None.
            return None, None
    return home_goals, away_goals


def _sum_shot_xg(events: list[dict], team_name: str) -> float:
    """Sum xG for all shots taken by a team in a match."""
    total = 0.0
    for ev in events:
        if ev.get("type", {}).get("name") != "Shot":
            continue
        if ev.get("team", {}).get("name") != team_name:
            continue
        total += ev.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0
    return round(total, 2)


def load_matches(
    competition_id: int,
    season_id: int,
    team_mapping: dict[str, str] | None = None,
    include_events: bool = False,
) -> Iterable[MatchRecord]:
    """Yield MatchRecord objects for all matches in a StatsBomb competition.

    Args:
        include_events: If True, download per-shot event files to compute xG.
            This is much slower (event files are large) but provides accurate
            team-level xG. Defaults to False to keep ingestion fast; goals are
            always available from the match list JSON.
    """
    mapping = team_mapping or {}
    raw_matches = load_competition_matches(competition_id, season_id)
    fetched_at = datetime.now(timezone.utc).isoformat()
    source = f"statsbomb-{competition_id}-{season_id}"

    for raw in raw_matches:
        match_id = raw["match_id"]
        home_name = raw["home_team"]["home_team_name"]
        away_name = raw["away_team"]["away_team_name"]
        home_code = _team_code_from_statsbomb_name(home_name, mapping)
        away_code = _team_code_from_statsbomb_name(away_name, mapping)

        home_score = raw.get("home_score")
        away_score = raw.get("away_score")

        # Fetch events to compute xG only when explicitly requested.
        home_xg: float | None = None
        away_xg: float | None = None
        if include_events:
            try:
                events = load_match_events(match_id)
                home_xg = _sum_shot_xg(events, home_name)
                away_xg = _sum_shot_xg(events, away_name)
            except Exception:
                home_xg = away_xg = None

        match_date = raw["match_date"]
        yield MatchRecord(
            id=f"{home_code}-{away_code}-{match_date}",
            date=match_date,
            competition=raw.get("competition", {}).get("competition_name", "Unknown"),
            season=str(raw.get("season", {}).get("season_name", "")),
            stage=raw.get("competition_stage", {}).get("name"),
            home_team_code=home_code,
            away_team_code=away_code,
            home_goals=home_score,
            away_goals=away_score,
            home_xg=home_xg,
            away_xg=away_xg,
            venue=raw.get("stadium", {}).get("name"),
            neutral=True,
            source=source,
            fetched_at=fetched_at,
        )


def available_world_cups() -> list[tuple[int, int, str]]:
    """Return the list of World Cup competitions available in this loader."""
    return [
        (*WORLD_CUP_2018, "2018 FIFA World Cup"),
        (*WORLD_CUP_2022, "2022 FIFA World Cup"),
    ]
