"""JisuAPI (极速数据) football data client.

Provides Chinese-language fixtures, standings, and news for football
competitions, including a dedicated FIFA World Cup endpoint. Requires a
JISU_API_KEY environment variable.

Docs: https://m.jisuapi.com/api/football/
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from loguru import logger

from src.utils.config import config


JISU_BASE = "https://api.jisuapi.com/football"
DEFAULT_TIMEOUT = 15


@dataclass(frozen=True)
class JisuFixture:
    """Normalised fixture from JisuAPI."""

    fixture_id: str
    league: str
    match_name: str
    round_text: str | None
    home_team: str
    away_team: str
    home_team_zh: str
    away_team_zh: str
    kickoff_utc: str
    kickoff_beijing: str
    status: str
    home_score: int | None
    away_score: int | None
    venue: str | None
    source: str = "jisu"


@dataclass(frozen=True)
class JisuStanding:
    team: str
    team_zh: str
    rank: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


def _cache_path(endpoint: str, extra: str = "") -> Path:
    slug = endpoint.strip("/").replace("/", "_")
    return config.api_cache / f"jisu_{slug}{extra}.json"


def _api_key() -> str:
    return config.jisu_api_key


def _request(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated GET request to a JisuAPI football endpoint."""
    key = _api_key()
    if not key:
        raise RuntimeError("JISU_API_KEY is not configured")

    params = params or {}
    params["appkey"] = key
    url = f"{JISU_BASE}/{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning(f"JisuAPI {endpoint} request failed: {exc}")
        return {}


def _parse_fixture(raw: dict[str, Any]) -> JisuFixture | None:
    """Convert a raw JisuAPI match dict into a JisuFixture."""
    home = raw.get("left_team") or raw.get("home_team") or ""
    away = raw.get("right_team") or raw.get("away_team") or ""
    if not home or not away:
        return None

    home_zh = raw.get("left_team") or home
    away_zh = raw.get("right_team") or away
    date_str = raw.get("start_date", "")
    time_str = raw.get("start_time", "")
    kickoff_beijing = f"{date_str} {time_str}".strip()

    # Jisu timestamps are Beijing time (UTC+8). Convert to UTC ISO for consistency.
    kickoff_utc = ""
    if date_str and time_str:
        try:
            bj = datetime.strptime(kickoff_beijing, "%Y-%m-%d %H:%M")
            bj = bj.replace(tzinfo=timezone(timedelta(hours=8)))
            kickoff_utc = bj.astimezone(timezone.utc).isoformat()
        except ValueError:
            kickoff_utc = ""

    home_score = raw.get("score_left")
    away_score = raw.get("score_right")
    try:
        home_score = int(home_score) if home_score is not None else None
        away_score = int(away_score) if away_score is not None else None
    except (ValueError, TypeError):
        home_score = away_score = None

    return JisuFixture(
        fixture_id=str(raw.get("match_id", f"{home}-{away}-{date_str}")),
        league=raw.get("match_name", "Unknown"),
        match_name=raw.get("match_name", ""),
        round_text=raw.get("round") or None,
        home_team=home,
        away_team=away,
        home_team_zh=home_zh,
        away_team_zh=away_zh,
        kickoff_utc=kickoff_utc,
        kickoff_beijing=kickoff_beijing,
        status=raw.get("status", ""),
        home_score=home_score,
        away_score=away_score,
        venue=raw.get("venue") or None,
    )


def fetch_fifa_fixtures(
    use_cache: bool = True,
    cache_ttl_seconds: int = 1800,
) -> list[JisuFixture]:
    """Fetch World Cup fixtures/results from JisuAPI.

    Falls back to a cached response if it is fresh.
    """
    cache = _cache_path("fifa")
    if use_cache and cache.exists():
        age = datetime.now().timestamp() - cache.stat().st_mtime
        if age < cache_ttl_seconds:
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                fixtures = [_parse_fixture(m) for m in data.get("result", [])]
                return [f for f in fixtures if f]
            except Exception:
                pass

    data = _request("fifa")
    if data.get("status") != "0":
        logger.warning(
            f"JisuAPI fifa returned status={data.get('status')}, msg={data.get('msg')}"
        )
        return []

    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fixtures = [_parse_fixture(m) for m in data.get("result", [])]
    valid = [f for f in fixtures if f]
    logger.info(f"Fetched {len(valid)} FIFA fixtures from JisuAPI")
    return valid


def fetch_league_fixtures(
    match_name: str,
    use_cache: bool = True,
    cache_ttl_seconds: int = 1800,
) -> list[JisuFixture]:
    """Fetch fixtures for a named league (e.g. '欧冠', '英超', '中超')."""
    slug = match_name.replace(" ", "_")
    cache = _cache_path("query", f"_{slug}")
    if use_cache and cache.exists():
        age = datetime.now().timestamp() - cache.stat().st_mtime
        if age < cache_ttl_seconds:
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                fixtures = [_parse_fixture(m) for m in data.get("result", [])]
                return [f for f in fixtures if f]
            except Exception:
                pass

    data = _request("query", {"matchname": match_name})
    if data.get("status") != "0":
        logger.warning(
            f"JisuAPI query/{match_name} returned status={data.get('status')}, "
            f"msg={data.get('msg')}"
        )
        return []

    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fixtures = [_parse_fixture(m) for m in data.get("result", [])]
    valid = [f for f in fixtures if f]
    logger.info(f"Fetched {len(valid)} {match_name} fixtures from JisuAPI")
    return valid


def fetch_league_standings(match_name: str) -> list[JisuStanding]:
    """Fetch league standings for a named league."""
    data = _request("rank", {"matchname": match_name})
    if data.get("status") != "0":
        return []

    standings: list[JisuStanding] = []
    for raw in data.get("result", []):
        try:
            standings.append(
                JisuStanding(
                    team=str(raw.get("team", "")),
                    team_zh=str(raw.get("team", "")),
                    rank=int(raw.get("rank", 0)),
                    played=int(raw.get("played", 0)),
                    won=int(raw.get("won", 0)),
                    drawn=int(raw.get("drawn", 0)),
                    lost=int(raw.get("lost", 0)),
                    goals_for=int(raw.get("goals_for", 0)),
                    goals_against=int(raw.get("goals_against", 0)),
                    goal_difference=int(raw.get("goal_difference", 0)),
                    points=int(raw.get("points", 0)),
                )
            )
        except (ValueError, TypeError):
            continue
    return standings


def fixtures_for_date(
    target: date | str | None = None,
    source: str = "fifa",
) -> list[JisuFixture]:
    """Return fixtures for a specific date from a JisuAPI source.

    Args:
        target: ISO date string or date object. Defaults to today (Beijing time).
        source: 'fifa' for World Cup, or a league name like '欧冠' for query endpoint.
    """
    if target is None:
        target = (datetime.utcnow() + timedelta(hours=8)).date()
    elif isinstance(target, str):
        target = date.fromisoformat(target)

    target_str = target.isoformat()
    all_fixtures = (
        fetch_fifa_fixtures()
        if source == "fifa"
        else fetch_league_fixtures(match_name=source)
    )
    return [f for f in all_fixtures if f.kickoff_utc.startswith(target_str)]


def yield_match_records() -> Iterable[dict[str, Any]]:
    """Yield completed FIFA fixtures as plain dicts for warehouse ingestion.

    This is intentionally a thin wrapper: callers map JisuFixture fields to
    MatchRecord columns in the ingestion module.
    """
    for f in fetch_fifa_fixtures():
        if f.home_score is None or f.away_score is None:
            continue
        yield {
            "id": f.fixture_id,
            "date": f.kickoff_utc[:10],
            "competition": f.league,
            "season": f.kickoff_utc[:4],
            "stage": f.round_text,
            "home_team_code": "",
            "away_team_code": "",
            "home_goals": f.home_score,
            "away_goals": f.away_score,
            "home_xg": None,
            "away_xg": None,
            "venue": f.venue,
            "neutral": True,
            "source": "jisu-fifa",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


if __name__ == "__main__":
    if not _api_key():
        print("Set JISU_API_KEY to test JisuAPI client")
    else:
        fifa = fetch_fifa_fixtures()
        print(f"FIFA fixtures: {len(fifa)}")
        for f in fifa[:5]:
            print(f"{f.kickoff_beijing} {f.home_team_zh} vs {f.away_team_zh}")
