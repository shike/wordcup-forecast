"""football-data.org client.

Optional dependency. Returns None for any missing data so the pipeline can
fall back to seed data.  All responses are cached in cache/api/.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from src.utils.config import config


BASE_URL = "https://api.football-data.org/v4"
HEADERS_TEMPLATE = {"X-Auth-Token": "{token}"}


def _cache_path(name: str) -> Path:
    return config.api_cache / f"football_data_{name}.json"


def _get(endpoint: str, params: dict | None = None) -> dict[str, Any] | None:
    if not config.football_data_api_key:
        return None
    cache = _cache_path(endpoint.replace("/", "_"))
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        headers = {"X-Auth-Token": config.football_data_api_key}
        resp = requests.get(
            f"{BASE_URL}{endpoint}", headers=headers, params=params or {}, timeout=10
        )
        if resp.status_code != 200:
            logger.debug(f"football-data.org {endpoint} -> {resp.status_code}")
            return None
        data = resp.json()
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    except Exception as e:
        logger.debug(f"football-data.org fetch failed: {e}")
        return None


def get_team(team_code: str) -> dict[str, Any] | None:
    """Return team data, or None if not configured/available."""
    return _get(f"/teams/{team_code}")


def get_team_matches(team_code: str, limit: int = 10) -> list[dict[str, Any]] | None:
    data = _get(f"/teams/{team_code}/matches", params={"limit": limit, "status": "FINISHED"})
    if data and "matches" in data:
        return data["matches"]
    return None
