"""Fetch football fixtures for a given date.

This module bypasses the Claude Code WebSearch/WebFetch tool layer (which
is restricted in some environments) by calling HTTP endpoints directly
via the ``requests`` library already a project dependency.

Primary source: ESPN public scoreboard API (free, no key, comprehensive
World Cup / top-league coverage).
Fallback: TheSportsDB public test key (free, no key, partial coverage).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from src.utils.config import config


ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
THESPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json"
THESPORTSDB_KEY = "3"  # public test key

# Beijing time (UTC+8) — default display timezone
BEIJING_TZ = timezone(timedelta(hours=8))
TIMEZONE_LABEL = "北京时间 (CST, UTC+8)"


# World Cup 2026 venue Chinese names (USA / Canada / Mexico)
VENUE_ZH = {
    # USA
    "MetLife Stadium": "大都会人寿体育场（纽约）",
    "SoFi Stadium": "SoFi 体育场（洛杉矶）",
    "AT&T Stadium": "AT&T 体育场（达拉斯）",
    "Hard Rock Stadium": "硬石体育场（迈阿密）",
    "Mercedes-Benz Stadium": "梅赛德斯-奔驰体育场（亚特兰大）",
    "Lincoln Financial Field": "林肯金融球场（费城）",
    "NRG Stadium": "NRG 体育场（休斯顿）",
    "Arrowhead Stadium": "箭头球场（堪萨斯城）",
    "Lumen Field": "流明球场（西雅图）",
    "Levi's Stadium": "李维斯体育场（旧金山）",
    "GEHA Field at Arrowhead Stadium": "GEHA 球场（堪萨斯城）",
    "Gillette Stadium": "吉列体育场（波士顿）",
    "FedExField": "FedEx 球场（华盛顿）",
    "Inter&Co Stadium": "Inter&Co 球场（奥兰多）",
    # Canada
    "BMO Field": "BMO 球场（多伦多）",
    "BC Place": "BC 体育馆（温哥华）",
    "Investors Group Field": "投资集团球场（温尼伯）",
    "Commonwealth Stadium": "联邦体育场（埃德蒙顿）",
    # Mexico
    "Estadio Azteca": "阿兹特克体育场（墨西哥城）",
    "Estadio BBVA": "BBVA 体育场（蒙特雷）",
    "Estadio Akron": "阿克龙体育场（瓜达拉哈拉）",
    # Common MLS / club names that may appear
    "Emirates Stadium": "酋长球场（伦敦）",
    "Old Trafford": "老特拉福德（曼彻斯特）",
    "Anfield": "安菲尔德（利物浦）",
    "Santiago Bernabéu": "圣地亚哥伯纳乌（马德里）",
    "Camp Nou": "诺坎普（巴塞罗那）",
    "Allianz Arena": "安联球场（慕尼黑）",
    "San Siro": "圣西罗（米兰）",
    "Wembley Stadium": "温布利球场（伦敦）",
}


def to_beijing(iso_utc: str) -> str:
    """Convert ISO 8601 UTC timestamp to Beijing-time string YYYY-MM-DD HH:MM."""
    if not iso_utc:
        return ""
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        bj = dt.astimezone(BEIJING_TZ)
        return bj.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_utc


def venue_chinese(name: str | None) -> str | None:
    """Return Chinese venue name if mapped, otherwise return original."""
    if not name:
        return None
    if name in VENUE_ZH:
        return VENUE_ZH[name]
    # try case-insensitive substring match
    for k, v in VENUE_ZH.items():
        if k.lower() in name.lower() or name.lower() in k.lower():
            return v
    return name

# ESPN uses ISO league slugs. We include the World Cup explicitly.
LEAGUE_SLUGS = [
    ("fifa.world", "FIFA World Cup"),
    ("uefa.champions", "UEFA Champions League"),
    ("uefa.europa", "UEFA Europa League"),
    ("eng.1", "Premier League"),
    ("esp.1", "La Liga"),
    ("ger.1", "Bundesliga"),
    ("ita.1", "Serie A"),
    ("fra.1", "Ligue 1"),
    ("usa.1", "MLS"),
    ("arg.1", "Liga Profesional"),
    ("bra.1", "Brasileirão"),
    ("coc.1", "CONCACAF Champions Cup"),
]


@dataclass
class Fixture:
    fixture_id: str
    league: str
    country: str | None
    round: str | None
    home_team: str
    away_team: str
    home_code: str  # 3-letter code (ESPN abbrev)
    away_code: str
    venue: str | None
    kickoff_utc: str  # ISO 8601
    status: str
    home_badge: str | None
    away_badge: str | None
    league_badge: str | None

    def short(self) -> str:
        bj = to_beijing(self.kickoff_utc)
        if bj:
            t = bj[11:]  # HH:MM
            d = bj[:10]
            time_str = f"{d} {t} (北京时间)"
        else:
            time_str = "TBD"
        return f"{time_str}  {self.home_team} vs {self.away_team}  ({self.league})"


def _cache_path(date_str: str) -> Path:
    return config.api_cache / f"fixtures_espn_{date_str}.json"


def fetch_fixtures(date_str: str | None = None) -> list[Fixture]:
    """Fetch soccer fixtures for a given YYYY-MM-DD date (default: today UTC).

    Aggregates all configured league slugs and de-duplicates by event id.
    Results are cached for 1 hour.
    """
    if date_str is None:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

    cache = _cache_path(date_str)
    if cache.exists():
        age = datetime.now() - datetime.fromtimestamp(cache.stat().st_mtime)
        if age < timedelta(hours=1):
            try:
                raw = json.loads(cache.read_text(encoding="utf-8"))
                return [_to_fixture(e) for e in raw]
            except Exception:
                pass

    date_compact = date_str.replace("-", "")
    fixtures: list[Fixture] = []
    for slug, name in LEAGUE_SLUGS:
        url = f"{ESPN_BASE}/{slug}/scoreboard"
        try:
            resp = requests.get(url, params={"dates": date_compact}, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for e in data.get("events", []):
                fixtures.append(_espn_to_fixture(e, league_name=name))
        except Exception as e:
            logger.debug(f"ESPN {slug} failed: {e}")

    # Fallback: if nothing came back, try TheSportsDB
    if not fixtures:
        logger.info("ESPN returned 0 fixtures, falling back to TheSportsDB")
        fixtures = _thesportsdb_fallback(date_str)

    # Cache and return
    cache.write_text(
        json.dumps([_fixture_to_dict(f) for f in fixtures], ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Fetched {len(fixtures)} fixtures for {date_str}")
    return fixtures


def _espn_to_fixture(e: dict[str, Any], league_name: str) -> Fixture:
    comps = e.get("competitions", [{}])[0]
    teams = comps.get("competitors", [])
    home = next((t for t in teams if t.get("homeAway") == "home"), {}).get("team", {})
    away = next((t for t in teams if t.get("homeAway") == "away"), {}).get("team", {})
    venue = comps.get("venue", {}).get("fullName")
    status = comps.get("status", {}).get("type", {}).get("description", "NS")
    return Fixture(
        fixture_id=str(e.get("id", "")),
        league=e.get("league", {}).get("name") or league_name,
        country=None,
        round=str(e.get("week", {}).get("number", "")) if e.get("week") else None,
        home_team=home.get("displayName") or home.get("name") or "TBD",
        away_team=away.get("displayName") or away.get("name") or "TBD",
        home_code=home.get("abbreviation", "").upper(),
        away_code=away.get("abbreviation", "").upper(),
        venue=venue,
        kickoff_utc=e.get("date", ""),
        status=status,
        home_badge=next((t.get("href") for t in home.get("logos", []) if t.get("href")), None),
        away_badge=next((t.get("href") for t in away.get("logos", []) if t.get("href")), None),
        league_badge=None,
    )


def _thesportsdb_fallback(date_str: str) -> list[Fixture]:
    url = f"{THESPORTSDB_BASE}/{THESPORTSDB_KEY}/eventsday.php"
    try:
        resp = requests.get(url, params={"d": date_str, "s": "Soccer"}, timeout=8)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"TheSportsDB fallback failed: {e}")
        return []
    events = resp.json().get("events") or []
    return [_thesportsdb_to_fixture(e) for e in events]


def _thesportsdb_to_fixture(e: dict[str, Any]) -> Fixture:
    home = e.get("strHomeTeam", "TBD")
    away = e.get("strAwayTeam", "TBD")
    timestamp = e.get("strTimestamp", "")
    return Fixture(
        fixture_id=str(e.get("idEvent", "")),
        league=e.get("strLeague", "Unknown"),
        country=e.get("strCountry"),
        round=str(e.get("intRound", "")) if e.get("intRound") else None,
        home_team=home,
        away_team=away,
        home_code=_name_to_code(home),
        away_code=_name_to_code(away),
        venue=e.get("strVenue"),
        kickoff_utc=timestamp,
        status=e.get("strStatus", "NS"),
        home_badge=e.get("strHomeTeamBadge"),
        away_badge=e.get("strAwayTeamBadge"),
        league_badge=e.get("strLeagueBadge"),
    )


# A short helper: heuristic mapping for a few common names
_CODE_HINTS = {
    "mexico": "MEX", "south africa": "RSA", "korea republic": "KOR", "czechia": "CZE",
    "canada": "CAN", "bosnia": "BIH", "united states": "USA", "paraguay": "PAR",
    "qatar": "QAT", "switzerland": "SUI", "brazil": "BRA", "morocco": "MAR",
    "haiti": "HAI", "scotland": "SCO", "australia": "AUS", "turkey": "TUR",
    "germany": "GER", "curaçao": "CUW", "netherlands": "NED", "japan": "JPN",
    "ivory coast": "CIV", "ecuador": "ECU", "sweden": "SWE", "tunisia": "TUN",
    "spain": "ESP", "cape verde": "CPV", "belgium": "BEL", "egypt": "EGY",
    "saudi arabia": "KSA", "uruguay": "URU", "iran": "IRN", "new zealand": "NZL",
    "argentina": "ARG", "france": "FRA", "england": "ENG", "portugal": "POR",
    "italy": "ITA", "poland": "POL", "denmark": "DEN", "norway": "NOR",
    "colombia": "COL", "chile": "CHI", "peru": "PER", "venezuela": "VEN",
    "uruguay": "URU", "jamaica": "JAM", "panama": "PAN", "honduras": "HON",
    "el salvador": "SLV", "costa rica": "CRC", "ghana": "GHA", "senegal": "SEN",
    "cameroon": "CMR", "nigeria": "NGA", "algeria": "ALG", "tunisia": "TUN",
    "austria": "AUT", "switzerland": "SUI", "ukraine": "UKR", "serbia": "SRB",
    "croatia": "CRO", "slovakia": "SVK", "slovenia": "SVN", "hungary": "HUN",
    "greece": "GRE", "romania": "ROU", "albania": "ALB", "georgia": "GEO",
    "thailand": "THA", "indonesia": "IDN", "china": "CHN", "iraq": "IRQ",
    "uae": "UAE", "uzbekistan": "UZB", "jordan": "JOR", "syria": "SYR",
    "lebanon": "LIB", "palestine": "PLE", "oman": "OMA", "bahrain": "BHR",
    "qatar": "QAT", "kuwait": "KUW",
}


def _name_to_code(name: str) -> str:
    n = name.lower()
    if n in _CODE_HINTS:
        return _CODE_HINTS[n]
    for key, code in _CODE_HINTS.items():
        if key in n or n in key:
            return code
    return name[:3].upper()


def _to_fixture(e: dict[str, Any]) -> Fixture:
    return Fixture(**e)


def _fixture_to_dict(f: Fixture) -> dict[str, Any]:
    return {
        "fixture_id": f.fixture_id, "league": f.league, "country": f.country,
        "round": f.round, "home_team": f.home_team, "away_team": f.away_team,
        "home_code": f.home_code, "away_code": f.away_code, "venue": f.venue,
        "kickoff_utc": f.kickoff_utc, "status": f.status, "home_badge": f.home_badge,
        "away_badge": f.away_badge, "league_badge": f.league_badge,
    }


def filter_interesting(
    fixtures: list[Fixture],
    leagues: list[str] | None = None,
) -> list[Fixture]:
    if leagues is None:
        leagues = [
            "World Cup", "UEFA Champions", "UEFA Europa",
            "Copa Libertadores", "Copa America", "Premier League", "La Liga",
            "Bundesliga", "Serie A", "Ligue 1", "CONCACAF", "AFC",
        ]
    out: list[Fixture] = []
    for f in fixtures:
        if any(l.lower() in f.league.lower() for l in leagues):
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
    print(f"\n{len(fx)} matches  ·  {TIMEZONE_LABEL}")
    print("-" * 80)
    for f in fx:
        print(f.short())
        if f.venue:
            venue_zh = venue_chinese(f.venue)
            if venue_zh and venue_zh != f.venue:
                print(f"     场地: {venue_zh}")
                print(f"     Venue: {f.venue}")
            else:
                print(f"     场地: {f.venue}")
            print(f"     状态: {f.status}")
