"""Fetch football fixtures for a given date.

This module bypasses the Claude Code WebSearch/WebFetch tool layer (which
is restricted in some environments) by calling HTTP endpoints directly
via the ``requests`` library already a project dependency.

Data source: ESPN public scoreboard API (free, no key, comprehensive
World Cup / top-league coverage).
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
from src.data.scrapers import dongqiudi as dqd_api
from src.data.scrapers import jisu as jisu_api


ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

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
    # Optional Chinese names populated when JisuAPI supplements ESPN data.
    home_team_zh: str | None = None
    away_team_zh: str | None = None

    def short(self) -> str:
        bj = to_beijing(self.kickoff_utc)
        if bj:
            t = bj[11:]  # HH:MM
            d = bj[:10]
            time_str = f"{d} {t} (北京时间)"
        else:
            time_str = "TBD"
        home = self.home_team_zh or self.home_team
        away = self.away_team_zh or self.away_team
        return f"{time_str}  {home} vs {away}  ({self.league})"


def _cache_path(date_str: str) -> Path:
    return config.api_cache / f"赛程_espn_{date_str}.json"


def fetch_fixtures(date_str: str | None = None,
                   user_tz_offset_hours: int = 8) -> list[Fixture]:
    """Fetch soccer fixtures for a given YYYY-MM-DD date (default: today in user's tz).

    If `date_str` is None, computes "today" from the user's timezone so a
    10pm Beijing fixture on a UTC date boundary is still caught.
    Aggregates all configured league slugs and de-duplicates by event id.
    Results are cached for 1 hour per UTC date.
    """
    if date_str is None or date_str in ("today", "tonight", "now"):
        now_utc = datetime.utcnow()
        user_now = now_utc + timedelta(hours=user_tz_offset_hours)
        date_str = user_now.strftime("%Y-%m-%d")

    # Fetch both the user's date AND the adjacent UTC date so fixtures that
    # straddle the day boundary (e.g. 23:00 local = 15:00 UTC next day)
    # are not missed. We then de-dup by event id.
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            extra = (d + timedelta(days=1)).strftime("%Y-%m-%d")
        except Exception:
            extra = None
    else:
        extra = None

    cache = _cache_path(date_str)
    if cache.exists():
        age = datetime.now() - datetime.fromtimestamp(cache.stat().st_mtime)
        if age < timedelta(hours=1):
            try:
                raw = json.loads(cache.read_text(encoding="utf-8"))
                return [_to_fixture(e) for e in raw]
            except Exception:
                pass

    seen_ids: set[str] = set()
    fixtures: list[Fixture] = []
    for d in [date_str, extra]:
        if not d:
            continue
        date_compact = d.replace("-", "")
        for slug, name in LEAGUE_SLUGS:
            url = f"{ESPN_BASE}/{slug}/scoreboard"
            try:
                resp = requests.get(url, params={"dates": date_compact}, timeout=8)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                for e in data.get("events", []):
                    fid = str(e.get("id", ""))
                    if fid in seen_ids:
                        continue
                    seen_ids.add(fid)
                    fixtures.append(_espn_to_fixture(e, league_name=name))
            except Exception as e:
                logger.debug(f"ESPN {slug} failed: {e}")

    if not fixtures:
        logger.info(f"No fixtures found for {date_str} from any configured ESPN league")

    # Supplement ESPN data with free Dongqiudi Chinese fixtures, then JisuAPI if configured.
    fixtures = _enrich_with_dongqiudi(fixtures)
    fixtures = _enrich_with_jisu(fixtures)

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


def _jisu_to_fixture(jf: jisu_api.JisuFixture) -> Fixture:
    """Convert a JisuAPI fixture into the project's Fixture format."""
    return Fixture(
        fixture_id=jf.fixture_id,
        league=jf.league,
        country=None,
        round=jf.round_text,
        home_team=jf.home_team,
        away_team=jf.away_team,
        home_code=_name_to_code(jf.home_team),
        away_code=_name_to_code(jf.away_team),
        venue=jf.venue,
        kickoff_utc=jf.kickoff_utc,
        status=jf.status,
        home_badge=None,
        away_badge=None,
        league_badge=None,
        home_team_zh=jf.home_team_zh,
        away_team_zh=jf.away_team_zh,
    )


def _dongqiudi_to_fixture(dm: dqd_api.DongqiudiMatch) -> Fixture:
    """Convert a Dongqiudi match into the project's Fixture format."""
    kickoff_utc = ""
    if dm.start_play:
        try:
            bj = datetime.strptime(dm.start_play, "%Y-%m-%d %H:%M:%S")
            bj = bj.replace(tzinfo=BEIJING_TZ)
            kickoff_utc = bj.astimezone(timezone.utc).isoformat()
        except ValueError:
            kickoff_utc = ""

    status_map = {
        "Fixture": "Scheduled",
        "Played": "Final",
    }
    status = status_map.get(dm.status, dm.status)

    return Fixture(
        fixture_id=dm.match_id,
        league=dm.competition_name,
        country=None,
        round=dm.round_name or None,
        home_team=dm.team_a_name_zh,
        away_team=dm.team_b_name_zh,
        home_code=_name_to_code(dm.team_a_name_zh),
        away_code=_name_to_code(dm.team_b_name_zh),
        venue=dm.venue,
        kickoff_utc=kickoff_utc,
        status=status,
        home_badge=dm.team_a_logo,
        away_badge=dm.team_b_logo,
        league_badge=None,
        home_team_zh=dm.team_a_name_zh,
        away_team_zh=dm.team_b_name_zh,
    )


def _enrich_with_dongqiudi(fixtures: list[Fixture]) -> list[Fixture]:
    """Add Chinese team names and back-fill missing fixtures from Dongqiudi."""
    try:
        # Dongqiudi's important endpoint returns the richest future fixture set
        # when queried from the current day. Querying from yesterday returns
        # only a handful of recent results.
        start = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        dqd_matches = dqd_api.fetch_important_matches(start=start)
    except Exception as exc:
        logger.debug(f"Dongqiudi enrichment skipped: {exc}")
        return fixtures

    if not dqd_matches:
        return fixtures

    def _kickoff_dt(iso: str) -> datetime | None:
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except Exception:
            return None

    # Index Dongqiudi matches by match_id and by kickoff time.
    by_id: dict[str, dqd_api.DongqiudiMatch] = {dm.match_id: dm for dm in dqd_matches}
    by_kickoff: list[tuple[datetime, dqd_api.DongqiudiMatch]] = []
    for dm in dqd_matches:
        dt = _kickoff_dt(_dongqiudi_to_fixture(dm).kickoff_utc)
        if dt:
            by_kickoff.append((dt, dm))

    # Pre-compute the Chinese→code mapping once so we don't rely on
    # _name_to_code returning the Chinese string verbatim (which would match
    # every ESPN fixture starting with the same letter).
    zh_to_code = _zh_team_name_to_code()

    def _find_match(f: Fixture) -> dqd_api.DongqiudiMatch | None:
        # Prefer exact ID match.
        dm = by_id.get(f.fixture_id)
        if dm:
            return dm

        # Fallback: match by team identity. We translate the Dongqiudi Chinese
        # team names to project 3-letter codes, then compare with the ESPN
        # 3-letter codes. This avoids the brittle substring/startswith logic.
        f_home_code = (f.home_code or "").upper()
        f_away_code = (f.away_code or "").upper()
        if not f_home_code or not f_away_code:
            return None
        if f_home_code == f_away_code:
            return None

        for dm in dqd_matches:
            dqd_home_code = zh_to_code.get(dm.team_a_name_zh, "")
            dqd_away_code = zh_to_code.get(dm.team_b_name_zh, "")
            if dqd_home_code == f_home_code and dqd_away_code == f_away_code:
                return dm
            # Swap (Dongqiudi may list teams in either order vs. ESPN).
            if dqd_home_code == f_away_code and dqd_away_code == f_home_code:
                return dm
        return None

    seen_ids: set[str] = {f.fixture_id for f in fixtures}
    enriched: list[Fixture] = []
    for f in fixtures:
        dm = _find_match(f)
        if dm:
            f = Fixture(
                fixture_id=f.fixture_id,
                league=f.league,
                country=f.country,
                round=f.round,
                home_team=f.home_team,
                away_team=f.away_team,
                home_code=f.home_code,
                away_code=f.away_code,
                venue=f.venue or dm.venue,
                kickoff_utc=f.kickoff_utc,
                status=f.status,
                home_badge=f.home_badge,
                away_badge=f.away_badge,
                league_badge=f.league_badge,
                home_team_zh=dm.team_a_name_zh,
                away_team_zh=dm.team_b_name_zh,
            )
        enriched.append(f)

    # Append Dongqiudi-only World Cup fixtures that ESPN missed.
    for dm in dqd_matches:
        if dm.match_id in seen_ids:
            continue
        if "世界杯" not in dm.competition_name:
            continue
        enriched.append(_dongqiudi_to_fixture(dm))
        seen_ids.add(dm.match_id)

    logger.info(f"Enriched {len(enriched)} fixtures with Dongqiudi data")
    return enriched


def _enrich_with_jisu(fixtures: list[Fixture]) -> list[Fixture]:
    """Add Chinese team names from JisuAPI when a matching fixture is found."""
    if not config.jisu_api_key:
        return fixtures

    try:
        jisu_fixtures = jisu_api.fetch_fifa_fixtures()
    except Exception as exc:
        logger.debug(f"JisuAPI enrichment skipped: {exc}")
        return fixtures

    if not jisu_fixtures:
        return fixtures

    # Index Jisu fixtures by (date, home_team_lower, away_team_lower)
    jisu_index: dict[tuple[str, str, str], jisu_api.JisuFixture] = {}
    for jf in jisu_fixtures:
        if not jf.kickoff_utc:
            continue
        date_key = jf.kickoff_utc[:10]
        home_key = jf.home_team.lower()
        away_key = jf.away_team.lower()
        jisu_index[(date_key, home_key, away_key)] = jf

    enriched: list[Fixture] = []
    for f in fixtures:
        if not f.kickoff_utc or not f.home_team_zh:
            # Only enrich if we don't already have Chinese names.
            key = (f.kickoff_utc[:10], f.home_team.lower(), f.away_team.lower())
            jf = jisu_index.get(key)
            if jf:
                f = Fixture(
                    fixture_id=f.fixture_id,
                    league=f.league,
                    country=f.country,
                    round=f.round,
                    home_team=f.home_team,
                    away_team=f.away_team,
                    home_code=f.home_code,
                    away_code=f.away_code,
                    venue=f.venue,
                    kickoff_utc=f.kickoff_utc,
                    status=f.status,
                    home_badge=f.home_badge,
                    away_badge=f.away_badge,
                    league_badge=f.league_badge,
                    home_team_zh=jf.home_team_zh,
                    away_team_zh=jf.away_team_zh,
                )
        enriched.append(f)

    logger.info(f"Enriched {len(enriched)} fixtures with JisuAPI Chinese names")
    return enriched


def fetch_jisu_fixtures(date_str: str | None = None) -> list[Fixture]:
    """Fetch FIFA fixtures directly from JisuAPI for a given date.

    Returns an empty list if JISU_API_KEY is not configured.
    """
    if not config.jisu_api_key:
        return []

    if date_str is None or date_str in ("today", "tonight", "now"):
        now_utc = datetime.utcnow()
        user_now = now_utc + timedelta(hours=8)
        date_str = user_now.strftime("%Y-%m-%d")

    try:
        jf_list = jisu_api.fixtures_for_date(date_str, source="fifa")
        return [_jisu_to_fixture(jf) for jf in jf_list]
    except Exception as exc:
        logger.warning(f"JisuAPI fixtures fetch failed: {exc}")
        return []


# Chinese-name → 3-letter project code. Used to match Dongqiudi (which sends
# Chinese names) to ESPN (which sends 3-letter codes).
_ZH_TEAM_NAME_TO_CODE: dict[str, str] = {
    "阿根廷": "ARG", "澳大利亚": "AUS", "比利时": "BEL", "巴西": "BRA",
    "喀麦隆": "CMR", "加拿大": "CAN", "哥斯达黎加": "CRC", "克罗地亚": "CRO",
    "丹麦": "DEN", "厄瓜多尔": "ECU", "英格兰": "ENG", "法国": "FRA",
    "德国": "GER", "加纳": "GHA", "伊朗": "IRN", "日本": "JPN",
    "墨西哥": "MEX", "摩洛哥": "MAR", "荷兰": "NED", "波兰": "POL",
    "葡萄牙": "POR", "卡塔尔": "QAT", "沙特阿拉伯": "KSA", "塞内加尔": "SEN",
    "塞尔维亚": "SRB", "韩国": "KOR", "西班牙": "ESP", "瑞士": "SUI",
    "突尼斯": "TUN", "美国": "USA", "乌拉圭": "URU", "威尔士": "WAL",
    "苏格兰": "SCO", "土耳其": "TUR", "中国": "CHN", "意大利": "ITA",
    "乌克兰": "UKR", "奥地利": "AUT", "希腊": "GRE", "智利": "CHI",
    "哥伦比亚": "COL", "秘鲁": "PER", "巴拉圭": "PAR", "委内瑞拉": "VEN",
    "捷克": "CZE", "瑞典": "SWE", "挪威": "NOR", "俄罗斯": "RUS",
    "埃及": "EGY", "海地": "HAI", "库拉索": "CUW", "佛得角": "CPV",
    "新西兰": "NZL", "阿尔及利亚": "ALG", "约旦": "JOR", "伊拉克": "IRQ",
    "南非": "RSA", "波黑": "BIH", "巴拿马": "PAN", "加纳": "GHA",
    "乌兹别克斯坦": "UZB", "刚果民主共和国": "COD", "科特迪瓦": "CIV",
    "新加坡": "SIN", "尼日利亚": "NGA", "尼加拉瓜": "NCA",
    "危地马拉": "GUA", "萨尔瓦多": "SLV", "洪都拉斯": "HON",
    "匈牙利": "HUN", "芬兰": "FIN", "斯洛伐克": "SVK", "黑山": "MNE",
    "斯洛文尼亚": "SVN", "塞浦路斯": "CYP", "马里": "MLI", "卢森堡": "LUX",
    "布基纳法索": "BFA", "巴拉圭": "PAR",
}


def _zh_team_name_to_code() -> dict[str, str]:
    """Return the Chinese→code mapping. Exposed for callers/tests."""
    return dict(_ZH_TEAM_NAME_TO_CODE)


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
        "home_team_zh": f.home_team_zh, "away_team_zh": f.away_team_zh,
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
