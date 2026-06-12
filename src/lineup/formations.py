"""Formation definitions and helpers.

Loads the 8 supported formations from data/formations.json.  Provides position
labels and pitch coordinates for layout in the PPT.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.utils.config import config
from src.utils.models import Formation


def load_formations() -> dict[str, Formation]:
    with open(config.formations_json, encoding="utf-8") as f:
        raw = json.load(f)
    return {code: Formation(**data) for code, data in raw.items()}


# Position group buckets — used to find the right candidate from a squad pool
POSITION_GROUPS: dict[str, set[str]] = {
    "GK": {"GK"},
    "DEF_FULL": {"RB", "LB", "RWB", "LWB"},
    "DEF_CENTRAL": {"CB"},
    "MID_DEFENSIVE": {"CDM"},
    "MID_CENTRAL": {"CM", "CDM", "CAM"},
    "MID_WIDE": {"RM", "LM", "RW", "LW"},
    "ATT_CENTRAL": {"ST", "CF", "CAM"},
    "ATT_WIDE": {"RW", "LW", "RM", "LM"},
}

# Map a formation slot to compatible position groups
SLOT_TO_GROUPS: dict[str, list[str]] = {
    "GK": ["GK"],
    "RB": ["DEF_FULL"],
    "LB": ["DEF_FULL"],
    "RWB": ["DEF_FULL"],
    "LWB": ["DEF_FULL"],
    "CB": ["DEF_CENTRAL"],
    "CDM": ["MID_DEFENSIVE", "MID_CENTRAL"],
    "CM": ["MID_CENTRAL", "MID_DEFENSIVE"],
    "CAM": ["MID_CENTRAL", "ATT_CENTRAL"],
    "RM": ["MID_WIDE", "ATT_WIDE"],
    "LM": ["MID_WIDE", "ATT_WIDE"],
    "RW": ["ATT_WIDE", "MID_WIDE"],
    "LW": ["ATT_WIDE", "MID_WIDE"],
    "ST": ["ATT_CENTRAL"],
    "CF": ["ATT_CENTRAL", "MID_CENTRAL"],
}


def get_formation(code: str) -> Formation:
    formations = load_formations()
    if code not in formations:
        raise KeyError(f"Unknown formation: {code}. Available: {list(formations)}")
    return formations[code]
