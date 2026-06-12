"""Qualitative factor adjustments layered on top of base probabilities."""
from __future__ import annotations

from src.utils.models import QualitativeFactors, TeamStats


def adjustment_factor(
    team: TeamStats,
    qual: QualitativeFactors,
    is_home: bool,
    knockout: bool,
) -> float:
    """Returns a multiplier in roughly [0.85, 1.15] to tilt base probabilities.

    Combines attack/defence strength, qualitative factors, and venue.
    """
    attack = min(0.06, max(-0.06, (team.goals_per_game - 1.35) * 0.04))
    defence = min(0.06, max(-0.06, (1.35 - team.conceded_per_game) * 0.04))
    qual_avg = (qual.tactical + qual.experience + qual.psychology) / 3.0
    qual_adj = (qual_avg - 7.0) * 0.005  # 7.0 = neutral baseline
    venue = 0.03 if is_home else 0.0
    pressure = -0.01 if knockout else 0.0  # big-game pressure
    return 1.0 + attack + defence + qual_adj + venue + pressure


def apply_adjustments(
    base_win: float,
    base_draw: float,
    base_loss: float,
    factor_a: float,
    factor_b: float,
) -> tuple[float, float, float]:
    """Rescale win/loss by relative factors, then renormalise.

    A higher factor means the team is stronger; tilt probability mass away
    from draw and towards the favoured side.
    """
    rel = factor_a / factor_b
    if rel >= 1.0:
        # A favoured
        shift = min(0.15, (rel - 1.0) * 0.5)
        new_win = base_win + shift * base_draw / 2 + shift / 2
        new_loss = max(0.01, base_loss - shift * base_draw / 2)
    else:
        shift = min(0.15, (1.0 / rel - 1.0) * 0.5)
        new_loss = base_loss + shift * base_draw / 2 + shift / 2
        new_win = max(0.01, base_win - shift * base_draw / 2)
        new_draw = base_draw
        total = new_win + new_draw + new_loss
        return new_win / total, new_draw / total, new_loss / total
    new_draw = max(0.05, 1.0 - new_win - new_loss)
    total = new_win + new_draw + new_loss
    return new_win / total, new_draw / total, new_loss / total
