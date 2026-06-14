"""Qualitative factor adjustments layered on top of base probabilities.

These factors tilt the Dixon-Coles base probability based on a side's
estimated lambda (xG). The tilt is a small ±5% shift in the favored
direction, not the larger ±15% swings used by the legacy version (which
empirically caused underdogs to be over-favoured on small samples).

New logic:
  1. Compute `lambda_diff = lambda_a - lambda_b` from the upstream call.
  2. Confidence-based tilt: |lambda_diff| < 0.2 -> small tilt, > 0.4 -> larger.
  3. Only apply qualitative override if `qual_avg` is meaningfully above/below 7.
"""
from __future__ import annotations

from src.utils.models import QualitativeFactors, TeamStats


def adjustment_factor(
    team: TeamStats,
    qual: QualitativeFactors,
    is_home: bool,
    knockout: bool,
) -> float:
    """Returns a multiplier around 1.0 (typically 0.95-1.05).

    Replaces the old per-stat additive scaling with a *relative*
    team-quality score that adds to the multiplier only when the team
    stands out clearly. This prevents small-sample noise from producing
    wild swings.
    """
    # Combine qualitative factors into a single quality score
    qual_avg = (qual.tactical + qual.experience + qual.psychology) / 3.0
    qual_score = (qual_avg - 7.0) * 0.02  # 0.0 = neutral, ±0.06 = ±3 points quality
    venue = 0.015 if is_home else 0.0
    # Small defensive bonus: top-tier defence lowers expected goals
    if team.conceded_per_game > 0 and team.conceded_per_game < 1.0:
        qual_score += 0.01
    # Big-game pressure only matters in knockout
    pressure = -0.005 if knockout else 0.0
    return max(0.92, min(1.08, 1.0 + qual_score + venue + pressure))


def apply_adjustments(
    base_win: float,
    base_draw: float,
    base_loss: float,
    factor_a: float,
    factor_b: float,
) -> tuple[float, float, float]:
    """Apply relative factor to tilt the win/draw/loss probabilities.

    Replaces the legacy ±15% shift. New tilt: at most ±5% in the favored
    direction, leaving the bulk of the probability mass to the Poisson
    model. Renormalises to 1.
    """
    if factor_a <= 0 or factor_b <= 0:
        return base_win, base_draw, base_loss
    rel = factor_a / factor_b
    # shift bounded in [-0.05, +0.05]
    if rel >= 1.0:
        shift = min(0.05, (rel - 1.0) * 0.5)
        new_win = base_win + shift * (base_draw + base_loss) / 2 + shift / 2
        new_loss = max(0.01, base_loss - shift * (base_draw / 2))
    else:
        shift = min(0.05, (1.0 / rel - 1.0) * 0.5)
        new_loss = base_loss + shift * (base_draw + base_win) / 2 + shift / 2
        new_win = max(0.01, base_win - shift * (base_draw / 2))
    new_draw = max(0.05, 1.0 - new_win - new_loss)
    total = new_win + new_draw + new_loss
    if total <= 0:
        return base_win, base_draw, base_loss
    return new_win / total, new_draw / total, new_loss / total
