"""Lineup prediction.

For each slot in a formation, pick the best available player using:
- compatibility with the slot (position groups)
- player rating
- experience (caps)
- secondary position match (small bonus)

Injuries are simulated stochastically: ~5% chance any starter is "out" before
the match, drawing from the bench or generating a "doubtful" status.
"""
from __future__ import annotations

import random

from loguru import logger

from src.lineup.formations import (
    POSITION_GROUPS,
    SLOT_TO_GROUPS,
    get_formation,
    load_formations,
)
from src.utils.models import InjuryReport, Lineup, MatchInput, Player
from src.data.squads import load_squad


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
    """Heuristic: stronger teams play more attacking formations."""
    if team.elo >= 2000:
        return random.choice(["4-3-3", "4-2-3-1"])
    if team.elo >= 1900:
        return random.choice(["4-3-3", "4-2-3-1", "4-4-2"])
    if team.elo >= 1800:
        return random.choice(["4-4-2", "3-5-2", "4-2-3-1", "4-1-4-1", "4-3-1-2"])
    return random.choice(["4-4-2", "5-3-2", "4-1-4-1", "3-5-2"])


def _simulate_injuries(
    squad: list[Player], starter_count: int, team_label: str
) -> tuple[list[InjuryReport], set[str]]:
    rng = random.Random(team_label)
    injured_ids: set[str] = set()
    reports: list[InjuryReport] = []
    # 1-2 injured players, weighted toward impact
    for _ in range(rng.randint(1, 2)):
        candidates = [p for p in squad if p.id not in injured_ids]
        if not candidates:
            break
        p = rng.choice(candidates)
        injured_ids.add(p.id)
        impact = "critical" if p.rating >= 8.2 and rng.random() < 0.5 else (
            "moderate" if p.rating >= 7.7 else "minor"
        )
        status = "out" if impact == "critical" else ("doubtful" if impact == "moderate" else "minor")
        reports.append(
            InjuryReport(
                player=p,
                status=status,  # type: ignore
                impact=impact,  # type: ignore
                reason="Undisclosed knock",
            )
        )
    return reports, injured_ids


def predict_lineup(
    team: Team,
    match: MatchInput,
    label: str,
) -> tuple[Lineup, str, list[InjuryReport]]:
    """Predict a starting XI for the team, plus bench and injuries."""
    squad = load_squad(team.code)
    formation_code = _pick_formation(team)

    # Knockout matches often shift to a slightly more defensive formation
    if match.stage in {"round_of_16", "quarterfinal", "semifinal", "final"} and formation_code in {"4-3-3", "4-2-3-1"}:
        formation_code = random.choice(["4-3-3", "4-2-3-1", "4-1-4-1", "4-3-1-2"])

    formation = get_formation(formation_code)

    injuries, injured_ids = _simulate_injuries(squad, 11, label)
    available = [p for p in squad if p.id not in injured_ids]
    injured_players = [p for p in squad if p.id in injured_ids]

    starting: list[Player] = []
    remaining = list(available)
    for slot in formation.positions:
        pick = _pick_for_slot(remaining, slot)
        if pick is None:
            # fallback: take any remaining forward/attacking player
            pick = remaining[0] if remaining else squad[0]
        starting.append(pick)
        remaining = [p for p in remaining if p.id != pick.id]

    bench = remaining[:7]
    logger.info(f"  {label}: formation={formation_code}, injuries={len(injuries)}")

    return (
        Lineup(
            team_code=team.code,
            formation=formation_code,
            players=starting,
            bench=bench,
            injured=injured_players,
        ),
        formation_code,
        injuries,
    )
