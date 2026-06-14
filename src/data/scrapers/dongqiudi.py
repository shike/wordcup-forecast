"""Dongqiudi (懂球帝) public match data scraper.

Uses the free endpoint `https://api.dongqiudi.com/data/tab/important` which
returns important upcoming/recent matches with Chinese team names. This is
currently the most reliable no-key Chinese source for World Cup fixtures and
results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from loguru import logger

from src.data.scrapers._team_names import load_project_mapping
from src.utils.config import config


DONGQIUDI_BASE = "https://api.dongqiudi.com"
IMPORTANT_PATH = "/data/tab/important"
DEFAULT_TIMEOUT = 15


@dataclass(frozen=True)
class DongqiudiMatch:
    match_id: str
    competition_id: str
    competition_name: str
    round_name: str
    team_a_id: str
    team_a_name_zh: str
    team_b_id: str
    team_b_name_zh: str
    start_play: str  # Beijing time, "YYYY-MM-DD HH:MM:SS"
    status: str
    fs_a: int | None
    fs_b: int | None
    hts_a: int | None
    hts_b: int | None
    venue: str | None
    cmp_type: str
    team_a_logo: str | None
    team_b_logo: str | None


def _cache_path(start: str) -> Path:
    return config.api_cache / f"dongqiudi_important_{start.replace(' ', '_').replace(':', '-')}.json"


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _beijing_to_utc_iso(beijing_str: str) -> str:
    """Convert Dongqiudi's Beijing-time string to UTC ISO 8601."""
    try:
        dt = datetime.strptime(beijing_str, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return ""


def _team_code_from_zh(name_zh: str, mapping: dict[str, str]) -> str:
    """Map a Chinese team name to a 3-letter project code."""
    # First try the English-side project mapping via common names.
    name_lower = name_zh.lower()
    direct: dict[str, str] = {
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
        "埃及": "EGY", "海地": "HAI", "库拉索": "CUW",
    }
    if name_zh in direct:
        return direct[name_zh]

    # Fallback to project mapping if it contains Chinese keys.
    for key, code in mapping.items():
        if key.lower() == name_lower:
            return code

    # Last resort: first 3 letters of pinyin/English would be wrong for Chinese,
    # so return empty to signal unmapped.
    return ""


def _parse_match(raw: dict[str, Any], mapping: dict[str, str]) -> DongqiudiMatch | None:
    match_id = str(raw.get("match_id", ""))
    if not match_id:
        return None
    return DongqiudiMatch(
        match_id=match_id,
        competition_id=str(raw.get("competition_id", "")),
        competition_name=raw.get("competition_name", ""),
        round_name=raw.get("round_name", ""),
        team_a_id=str(raw.get("team_A_id", "")),
        team_a_name_zh=raw.get("team_A_name", ""),
        team_b_id=str(raw.get("team_B_id", "")),
        team_b_name_zh=raw.get("team_B_name", ""),
        start_play=raw.get("start_play", ""),
        status=raw.get("status", ""),
        fs_a=_to_int(raw.get("fs_A")),
        fs_b=_to_int(raw.get("fs_B")),
        hts_a=_to_int(raw.get("hts_A")),
        hts_b=_to_int(raw.get("hts_B")),
        venue=raw.get("venue") or None,
        cmp_type=raw.get("cmp_type", ""),
        team_a_logo=raw.get("team_A_logo") or None,
        team_b_logo=raw.get("team_B_logo") or None,
    )


def fetch_important_matches(
    start: str | None = None,
    soccer_only: bool = True,
    use_cache: bool = True,
    cache_ttl_seconds: int = 1800,
) -> list[DongqiudiMatch]:
    """Fetch important matches from Dongqiudi.

    Args:
        start: Beijing time string "YYYY-MM-DD HH:MM:SS". Defaults to 7 days ago
            so we catch recent results plus upcoming fixtures.
        soccer_only: Filter out basketball/esports entries.
    """
    if start is None:
        # Start from 7 days ago to include recent results.
        start_dt = datetime.now(timezone.utc) + timedelta(hours=8) - timedelta(days=7)
        start = start_dt.strftime("%Y-%m-%d %H:%M:%S")

    cache = _cache_path(start)
    if use_cache and cache.exists():
        age = datetime.now().timestamp() - cache.stat().st_mtime
        if age < cache_ttl_seconds:
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                mapping = load_project_mapping()
                matches = [_parse_match(m, mapping) for m in data.get("list", [])]
                return [m for m in matches if m and (not soccer_only or m.cmp_type == "soccer")]
            except Exception:
                pass

    url = f"{DONGQIUDI_BASE}{IMPORTANT_PATH}"
    params = {"start": start}
    try:
        response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning(f"Dongqiudi important matches request failed: {exc}")
        return []
    except json.JSONDecodeError as exc:
        logger.warning(f"Dongqiudi returned invalid JSON: {exc}")
        return []

    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    mapping = load_project_mapping()
    matches = [_parse_match(m, mapping) for m in data.get("list", [])]
    valid = [m for m in matches if m and (not soccer_only or m.cmp_type == "soccer")]
    logger.info(f"Fetched {len(valid)} soccer matches from Dongqiudi")
    return valid


def fetch_world_cup_fixtures() -> list[DongqiudiMatch]:
    """Return only World Cup matches (fixtures and results)."""
    matches = fetch_important_matches()
    return [m for m in matches if "世界杯" in m.competition_name]


def fetch_match_records() -> Iterable[dict[str, Any]]:
    """Yield completed matches as plain dicts for warehouse ingestion."""
    mapping = load_project_mapping()
    for m in fetch_important_matches():
        if m.status != "Played" or m.fs_a is None or m.fs_b is None:
            continue
        home_code = _team_code_from_zh(m.team_a_name_zh, mapping)
        away_code = _team_code_from_zh(m.team_b_name_zh, mapping)
        if not home_code or not away_code:
            continue
        yield {
            "id": m.match_id,
            "date": _beijing_to_utc_iso(m.start_play)[:10],
            "competition": m.competition_name,
            "season": m.start_play[:4],
            "stage": m.round_name or None,
            "home_team_code": home_code,
            "away_team_code": away_code,
            "home_goals": m.fs_a,
            "away_goals": m.fs_b,
            "home_xg": None,
            "away_xg": None,
            "venue": m.venue,
            "neutral": True,
            "source": "dongqiudi",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


if __name__ == "__main__":
    wc = fetch_world_cup_fixtures()
    print(f"World Cup matches: {len(wc)}")
    for m in wc[:10]:
        score = f"{m.fs_a}-{m.fs_b}" if m.fs_a is not None else "vs"
        print(f"{m.start_play} {m.team_a_name_zh} {score} {m.team_b_name_zh} [{m.status}]")
