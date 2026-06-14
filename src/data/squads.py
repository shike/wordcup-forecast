"""Squad data loader.

Each team must have a seed JSON in data/squads/{CODE}.json. If the file is
missing, a clear error is raised so the operator knows to create the seed.
There is no placeholder or generated squad.
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.utils.config import config
from src.utils.image import player_id_from_name
from src.utils.models import Player


def _seed_path(team_code: str) -> Path:
    return config.squad_data_dir / f"{team_code}.json"


def load_squad(team_code: str) -> list[Player]:
    """Load squad seed from JSON.

    Raises FileNotFoundError if no seed exists for the team. The error message
    points the operator at the required seed path.
    """
    path = _seed_path(team_code)
    if not path.exists():
        raise FileNotFoundError(
            f"无 {team_code} 队的真实阵容数据：缺少 {path}。"
            f"请在 data/squads/{team_code}.json 中提供真实阵容后再预测。"
        )
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [_make_player(p) for p in raw]


def _make_player(data: dict) -> Player:
    name = data.get("name", "Unknown")
    pid = data.get("id") or player_id_from_name(name)
    return Player(
        id=pid,
        name=name,
        name_zh=data.get("name_zh"),
        position=data.get("position", "CM"),
        secondary_positions=data.get("secondary_positions", []),
        number=data.get("number", 0),
        age=data.get("age", 25),
        club=data.get("club", ""),
        caps=data.get("caps", 0),
        goals=data.get("goals", 0),
        assists=data.get("assists", 0),
        rating=data.get("rating", 7.0),
        preferred_foot=data.get("preferred_foot", "R"),
        height_cm=data.get("height_cm", 180),
        photo_path=data.get("photo_path"),
        wikipedia_url=data.get("wikipedia_url"),
    )
