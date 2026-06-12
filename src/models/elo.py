"""ELO rating model for match prediction.

Implements the standard ELO formula with draw margins and neutral-venue handling.
"""
from __future__ import annotations

import math

from src.utils.models import Team


def _k_factor(gd: int, match_importance: float = 1.0) -> float:
    """K-factor scaled by goal difference and match importance."""
    base = 40.0 * match_importance
    return base * (1 + math.log1p(max(0, abs(gd))))


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_elo(
    rating_a: float,
    rating_b: float,
    goals_a: int,
    goals_b: int,
    neutral: bool = True,
    match_importance: float = 1.0,
) -> tuple[float, float]:
    """Update ELO ratings after a match. Returns (new_a, new_b)."""
    home_advantage = 0.0 if neutral else 100.0
    exp_a = _expected_score(rating_a + home_advantage, rating_b)
    exp_b = 1.0 - exp_a
    if goals_a > goals_b:
        s_a, s_b = 1.0, 0.0
    elif goals_a < goals_b:
        s_a, s_b = 0.0, 1.0
    else:
        s_a = s_b = 0.5
    k = _k_factor(goals_a - goals_b, match_importance)
    new_a = rating_a + k * (s_a - exp_a)
    new_b = rating_b + k * (s_b - exp_b)
    return new_a, new_b


def predict_elo(team_a: Team, team_b: Team, neutral: bool = True) -> tuple[float, float, float]:
    """Predict win/draw/loss probabilities for team A from ELO.

    Returns (P(win), P(draw), P(loss)) where draw is estimated using a
    logistic bell around the expected score difference.
    """
    home_advantage = 0.0 if neutral else 100.0
    exp_a = _expected_score(team_a.elo + home_advantage, team_b.elo)
    exp_b = 1.0 - exp_a

    # Probability of draw estimated as a triangular distribution around
    # the difference in expected scores. Wider spread -> more draws.
    diff = abs(exp_a - exp_b)
    p_draw = max(0.15, 0.36 * (1 - diff))  # 15-36% depending on gap
    # renormalise
    remaining = 1.0 - p_draw
    p_win_a = remaining * exp_a
    p_win_b = remaining * exp_b
    return p_win_a, p_draw, p_win_b
