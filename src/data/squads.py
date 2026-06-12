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


# Placeholder squad when no seed JSON exists — Chinese transliterated names
# as a sensible default so the PPT reads naturally.

_PLACEHOLDER_FIRST_ZH = [
    "亚历克斯", "本", "卡洛斯", "丹尼尔", "埃米利奥", "费尔南多",
    "加布里埃尔", "胡安", "路易斯", "马蒂亚斯", "尼古拉斯", "奥斯卡",
    "帕布罗", "拉斐尔", "圣地亚哥", "托马斯", "乌戈", "维克多",
    "哈维尔", "伊万", "泽维尔", "迭戈", "罗德里戈", "马丁",
    "塞尔吉奥", "马尔科", "里卡多", "安德烈", "克里斯蒂安",
]

_PLACEHOLDER_LAST_ZH = [
    "加西亚", "罗德里格斯", "马丁内斯", "洛佩斯", "冈萨雷斯",
    "佩雷斯", "桑切斯", "罗梅罗", "索萨", "阿尔梅达", "纳达尔",
    "托雷斯", "弗洛雷斯", "奥尔蒂斯", "莫拉", "古铁雷斯",
    "卡瓦哈尔", "卡斯特罗", "莫雷诺", "希门尼斯", "德尔加多",
    "桑托斯", "门德斯", "里贝罗", "库尼亚", "帕切科",
]

_PLACEHOLDER_CLUBS = [
    "Real Madrid 皇家马德里", "Man City 曼城", "Bayern 拜仁", "PSG 巴黎圣日耳曼",
    "Barcelona 巴塞罗那", "Liverpool 利物浦", "Inter 国际米兰", "Juventus 尤文图斯",
    "Arsenal 阿森纳", "Atletico 马竞",
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
        first_zh = rng.choice(_PLACEHOLDER_FIRST_ZH)
        last_zh = rng.choice(_PLACEHOLDER_LAST_ZH)
        name_zh = f"{first_zh}·{last_zh}"
        name_en = f"{first_zh} {last_zh}"
        players.append(
            Player(
                id=player_id_from_name(name_zh),
                name=name_en,
                name_zh=name_zh,
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
