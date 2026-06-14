"""Lineup prediction.

For each slot in a formation, pick the best available player using:
- compatibility with the slot (position groups)
- player rating
- experience (caps)
- secondary position match (small bonus)

Injuries are not simulated. The pipeline uses the seed squad as the source of
truth for available players. If real injury data is ingested in the future, it
should be read from the data warehouse here.
"""
from __future__ import annotations

from loguru import logger

from src.data.squads import load_squad
from src.lineup.formations import (
    POSITION_GROUPS,
    SLOT_TO_GROUPS,
    get_formation,
    load_formations,
)
from src.utils.models import InjuryReport, Lineup, MatchInput, Player, Team


def _slot_score(player: Player, slot: str) -> float:
    """Score a player for a given slot."""
    groups = SLOT_TO_GROUPS.get(slot, [])
    compatible_positions = set()
    for g in groups:
        compatible_positions |= POSITION_GROUPS.get(g, set())

    primary_match = player.position in compatible_positions
    secondary_match = any(p in compatible_positions for p in player.secondary_positions)

    if not primary_match and not secondary_match:
        return 0.0

    base = player.rating
    if secondary_match and not primary_match:
        base -= 0.6
    # experience bonus, capped
    base += min(0.6, player.caps / 200.0)
    return base


def _pick_for_slot(candidates: list[Player], slot: str) -> Player | None:
    best: Player | None = None
    best_score = -1.0
    for p in candidates:
        score = _slot_score(p, slot)
        if score > best_score:
            best = p
            best_score = score
    return best


def _pick_formation(team: Team) -> str:
    """Deterministic formation choice based on team strength.

    No randomness: the same team always gets the same formation.
    """
    if team.elo >= 2000:
        return "4-3-3"
    if team.elo >= 1900:
        return "4-2-3-1"
    if team.elo >= 1800:
        return "4-4-2"
    return "5-3-2"


def predict_lineup(
    team: Team,
    match: MatchInput,
    label: str,
) -> tuple[Lineup, str, list[InjuryReport]]:
    """Predict a starting XI for the team from the seed squad.

    Returns (lineup, formation_code, injuries). The injuries list is always
    empty because injuries are not simulated; real injury data must come from
    an external source.
    """
    squad = load_squad(team.code)
    formation_code = _pick_formation(team)

    # Knockout matches often shift to a slightly more defensive formation
    if match.stage in {"round_of_16", "quarterfinal", "semifinal", "final"}:
        if formation_code in {"4-3-3", "4-2-3-1"}:
            formation_code = "4-1-4-1"
        elif formation_code == "4-4-2":
            formation_code = "4-2-3-1"

    formation = get_formation(formation_code)

    available = list(squad)
    starting: list[Player] = []
    remaining = list(available)
    for slot in formation.positions:
        pick = _pick_for_slot(remaining, slot)
        if pick is None:
            # Every slot must be filled; take the highest-rated remaining player.
            pick = max(remaining, key=lambda p: p.rating) if remaining else squad[0]
        starting.append(pick)
        remaining = [p for p in remaining if p.id != pick.id]

    bench = remaining[:7]
    logger.info(f"  {label}: formation={formation_code}, injuries=0")

    return (
        Lineup(
            team_code=team.code,
            formation=formation_code,
            players=starting,
            bench=bench,
            injured=[],
        ),
        formation_code,
        [],
    )


# Keep load_formations import effective.
__all__ = ["predict_lineup", "load_formations"]
