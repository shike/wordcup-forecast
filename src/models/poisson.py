"""Poisson and Dixon-Coles goal model for football match prediction."""
from __future__ import annotations

from math import exp, factorial

import numpy as np

from src.utils.models import Team, TeamStats


def _poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam**k) * exp(-lam) / factorial(k)


def expected_goals(team_stats: TeamStats, opp_stats: TeamStats,
                 elo_a: float = 1800, elo_b: float = 1800) -> tuple[float, float]:
    """Estimate lambdas using ELO differential + team stats.

    Uses ELO-based probability to scale lambdas asymmetrically so that
    strong vs weak matchups produce visibly different score distributions
    (and the modal score reflects the favourite rather than always being
    1-1).
    """
    elo_diff = (elo_a - elo_b) / 400.0
    expected = 1.0 / (1.0 + 10 ** (-elo_diff))  # ELO win-probability
    base = 1.25
    # At elo_diff=0 (even), both get 1.25.  At elo_diff=200 (~70% fav),
    # favourite gets 1.6, underdog 0.9.
    lambda_a = base * (0.4 + 0.8 * expected)
    lambda_b = base * (0.4 + 0.8 * (1.0 - expected))
    # Modulate by team stats (avg_player_rating) so a statistically better
    # team gets a slight bump.
    bump_a = 1.0 + (team_stats.avg_player_rating - 7.0) * 0.05
    bump_b = 1.0 + (opp_stats.avg_player_rating - 7.0) * 0.05
    lambda_a *= max(0.7, min(1.4, bump_a))
    lambda_b *= max(0.7, min(1.4, bump_b))
    return max(0.3, lambda_a), max(0.3, lambda_b)


def score_probability_matrix(lambda_a: float, lambda_b: float, max_goals: int = 7) -> np.ndarray:
    """Build the (max_goals+1) x (max_goals+1) score probability matrix."""
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            matrix[i, j] = _poisson_pmf(lambda_a, i) * _poisson_pmf(lambda_b, j)
    return matrix


def match_outcome_probabilities(matrix: np.ndarray) -> tuple[float, float, float]:
    """From a score matrix, compute (P(win_a), P(draw), P(win_b))."""
    n = matrix.shape[0]
    p_win_a = 0.0
    p_draw = 0.0
    p_win_b = 0.0
    for i in range(n):
        for j in range(n):
            p = matrix[i, j]
            if i > j:
                p_win_a += p
            elif i == j:
                p_draw += p
            else:
                p_win_b += p
    return p_win_a, p_draw, p_win_b


def dixon_coles_correction(
    matrix: np.ndarray, lambda_a: float, lambda_b: float, rho: float = -0.1
) -> np.ndarray:
    """Apply Dixon-Coles low-score correction (tau function)."""
    corrected = matrix.copy()
    for i in range(2):
        for j in range(2):
            p = matrix[i, j]
            if i == 0 and j == 0:
                tau = 1 - lambda_a * lambda_b * rho
            elif i == 0 and j == 1:
                tau = 1 + lambda_a * rho
            elif i == 1 and j == 0:
                tau = 1 + lambda_b * rho
            else:  # 1,1
                tau = 1 - rho
            corrected[i, j] = p * tau
    # renormalise to sum to 1
    corrected = corrected / corrected.sum()
    return corrected


def predict_poisson(
    team_a: Team, team_b: Team, stats_a: TeamStats, stats_b: TeamStats,
    elo_a: float = 1800, elo_b: float = 1800,
) -> tuple[tuple[float, float, float], tuple[float, float], np.ndarray]:
    """Full Poisson pipeline. Returns (probs, expected_goals, score_matrix)."""
    lambda_a, lambda_b = expected_goals(stats_a, stats_b, elo_a=elo_a, elo_b=elo_b)
    matrix = score_probability_matrix(lambda_a, lambda_b)
    matrix = dixon_coles_correction(matrix, lambda_a, lambda_b)
    probs = match_outcome_probabilities(matrix)
    return probs, (lambda_a, lambda_b), matrix
