"""Team data loader with Wikipedia fallback."""
from __future__ import annotations

import json
from pathlib import Path

from src.utils.config import config
from src.utils.models import Team


def load_teams() -> dict[str, Team]:
    """Load teams database."""
    with open(config.teams_json, encoding="utf-8") as f:
        raw = json.load(f)
    return {code: Team(code=code, **data) for code, data in raw.items()}


def get_team(code: str) -> Team:
    teams = load_teams()
    if code not in teams:
        raise KeyError(f"Unknown team code: {code}. Available: {list(teams.keys())}")
    return teams[code]


def search_team(query: str) -> list[Team]:
    """Search teams by English or Chinese name."""
    teams = load_teams()
    query_lower = query.lower()
    return [
        t
        for t in teams.values()
        if query_lower in t.name_en.lower() or query in t.name_zh
    ]
