"""Squad data loader with seed JSON + Wikipedia augmentation.

Each team has a seed JSON in data/squads/{CODE}.json containing ~25 players.
If a player is missing a photo_path, the Wikipedia client will try to fetch
and cache one at runtime.  When neither is available the PPT falls back to
text-only player cards.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from loguru import logger

from src.utils.config import config
from src.utils.models import Player
from src.utils.image import player_id_from_name


def _seed_path(team_code: str) -> Path:
    return config.squad_data_dir / f"{team_code}.json"


def load_squad(team_code: str) -> list[Player]:
    """Load squad seed from JSON; generate lightweight placeholders if missing."""
    path = _seed_path(team_code)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return [_make_player(p) for p in raw]
    return _generate_placeholder_squad(team_code)


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


# Placeholder squad when no seed JSON exists — generic names but unique enough
# to render distinct cards.

_PLACEHOLDER_NAMES = [
    "Aaronson", "Berger", "Carlsen", "Dahlberg", "Eklund", "Forsberg",
    "Gustafsson", "Holmberg", "Iversen", "Jakobsen", "Karlsson", "Lindgren",
    "Magnusson", "Nordström", "Olsson", "Pettersson", "Quist", "Rosenberg",
    "Sandberg", "Thorstvedt", "Ullmark", "Vikström", "Wahlberg", "Yngvesson",
    "Zetterberg",
]

_PLACEHOLDER_CLUBS = [
    "Real Madrid", "Man City", "Bayern", "PSG", "Barcelona", "Liverpool",
    "Inter", "Juventus", "Arsenal", "Atletico",
]


def _generate_placeholder_squad(team_code: str) -> list[Player]:
    """Create a 25-man placeholder squad for teams without a seed JSON."""
    rng = random.Random(team_code)
    positions = [
        "GK", "GK", "GK",
        "RB", "CB", "CB", "CB", "CB", "LB",
        "CDM", "CM", "CM", "CM", "CAM",
        "RW", "LW", "ST", "ST", "ST", "CF",
        "RB", "CB", "CM", "ST", "LW",
    ]
    players: list[Player] = []
    for i, pos in enumerate(positions):
        first = rng.choice(_PLACEHOLDER_NAMES)
        last = rng.choice(_PLACEHOLDER_NAMES)
        name = f"{first} {last}"
        players.append(
            Player(
                id=player_id_from_name(name),
                name=name,
                name_zh=None,
                position=pos,
                number=i + 1,
                age=rng.randint(20, 33),
                club=rng.choice(_PLACEHOLDER_CLUBS),
                caps=rng.randint(5, 100),
                goals=rng.randint(0, 40) if pos in {"ST", "CF", "RW", "LW", "CAM"} else rng.randint(0, 8),
                assists=rng.randint(0, 20),
                rating=round(6.0 + rng.random() * 1.8, 1),
                preferred_foot=rng.choice(["L", "R", "B"]),
                height_cm=rng.randint(170, 195),
            )
        )
    logger.warning(
        f"No seed squad for {team_code}; using {len(players)} placeholder players"
    )
    return players
