"""Team data loader.

Loads team seed data from data/teams.json. There is no fallback to other
sources: missing team codes raise KeyError so the operator can fix the seed.
"""
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
    """Search teams by English or Chinese name, or by 3-letter code.

    Matches both directions: query in name, or name in query (handles
    "United States" matching a team with name_en="USA").
    """
    teams = load_teams()
    query_lower = query.lower()
    out: list[Team] = []
    for t in teams.values():
        if (
            query_lower in t.name_en.lower()
            or query in t.name_zh
            or t.code.lower() == query_lower
            or t.name_en.lower() in query_lower  # handle "United States" vs "USA"
        ):
            out.append(t)
    return out
