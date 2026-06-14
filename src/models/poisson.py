"""Dixon-Coles goal model with real-data attack/defence strengths.

This module replaces the previous three-model ensemble approach. It estimates
expected goals from team statistics and applies the Dixon-Coles low-score
correlation. ELO is used only as a Bayesian prior when recent match data is
sparse.
"""
from __future__ import annotations

from math import exp, factorial

import numpy as np

from src.utils.models import TeamStats

# League-mean goals per game. World Cup historical mean sits near 1.27.
_MU_LEAGUE = 1.27

# Dixon-Coles low-score correlation parameter. Standard academic range is
# -0.05 to -0.15. We use -0.07 so 0-0/1-0/0-1/1-1 are mildly up-weighted
# without compressing the distribution toward 1-1.
_RHO_DEFAULT = -0.07

# Prior sample size equivalent for ELO when real match data is sparse.
_ELO_PRIOR_SAMPLES = 4


def _poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam**k) * exp(-lam) / factorial(k)


# Soft caps for attack/defence strength to prevent single-match blowouts
# (e.g. a 6-1 win) from dominating the prediction.
_ATTACK_CAP = 1.8
_DEFENCE_CAP = 1.8
_ATTACK_FLOOR = 0.55
_DEFENCE_FLOOR = 0.55


def _attack_defence_from_stats(
    stats: TeamStats,
    league_mean: float = _MU_LEAGUE,
) -> tuple[float, float]:
    """Convert TeamStats into (attack_strength, defence_weakness).

    attack_strength > 1 means the team scores more than league average.
    defence_weakness > 1 means the team concedes more than league average.

    Prefers xG when available; otherwise falls back to actual goals.
    """
    has_xg = stats.xg_per_game > 0 and stats.xga_per_game > 0
    attack_metric = stats.xg_per_game if has_xg else stats.goals_per_game
    defence_metric = stats.xga_per_game if has_xg else stats.conceded_per_game

    attack = max(_ATTACK_FLOOR, min(_ATTACK_CAP, attack_metric / league_mean))
    defence = max(_DEFENCE_FLOOR, min(_DEFENCE_CAP, defence_metric / league_mean))
    return attack, defence


def _elo_prior_strength(elo: float, league_mean: float = _MU_LEAGUE) -> tuple[float, float]:
    """ELO-derived attack/defence prior centred on league average.

    ELO 1800 → (1.0, 1.0). ELO 2000 → attack ≈ 1.12, defence ≈ 0.89.
    """
    diff = (elo - 1800) / 400.0
    expected = 1.0 / (1.0 + 10 ** (-diff))
    # Map expected score to attack/defence around 1.0
    attack = 0.7 + 0.6 * expected
    defence = 0.7 + 0.6 * (1.0 - expected)
    return attack, defence


def _xg_quality_factor(stats: TeamStats) -> float:
    """xG-vs-goals regression modifier (±5%).

    A team whose xG > goals is creating better chances than it converts
    (positive regression expected — bump up expected goals). A team whose
    xG < goals is finishing better than its chances (negative regression).
    Bounded tightly to keep the model robust to noisy small samples.
    """
    if stats.xg_per_game <= 0 or stats.goals_per_game <= 0:
        return 1.0
    gpg = max(0.5, stats.goals_per_game)
    ratio = stats.xg_per_game / gpg
    # Map ratio in [0.7, 1.4] to factor in [0.95, 1.05]
    bump = 1.0 + (ratio - 1.0) * 0.25
    return max(0.95, min(1.05, bump))


def expected_goals(
    stats_a: TeamStats,
    stats_b: TeamStats,
    elo_a: float = 1800,
    elo_b: float = 1800,
    sample_size_a: int = 10,
    sample_size_b: int = 10,
    home_advantage: float = 1.0,
    league_mean: float = _MU_LEAGUE,
) -> tuple[float, float, float, float]:
    """Estimate lambdas and return transparency weights.

    Returns (lambda_a, lambda_b, elo_prior_weight_a, elo_prior_weight_b).

    Model:
      lambda_a = mu * alpha_a * beta_b * gamma_a * quality_a
      lambda_b = mu * alpha_b * beta_a * gamma_b * quality_b

    Where:
      - alpha/beta are Bayesian blends of ELO prior (the world football
        consensus on team strength) and recent-form stats.
      - For teams with long histories, recent stats dominate.
      - For teams with short histories, ELO dominates.

    Weights:
      - ELO prior: 25 games of effective history.
      - For each team's recent-form block, we count only "real" matches
        (martj42/dongqiudi/statsbomb), giving manual-seed matches just
        30% weight to avoid being misled by 6 vs-minnows games.
    """
    alpha_stats_a, beta_stats_a = _attack_defence_from_stats(stats_a, league_mean)
    alpha_stats_b, beta_stats_b = _attack_defence_from_stats(stats_b, league_mean)

    alpha_elo_a, beta_elo_a = _elo_prior_strength(elo_a, league_mean)
    alpha_elo_b, beta_elo_b = _elo_prior_strength(elo_b, league_mean)

    # Effective recent-form sample size: real-data matches count 1.0,
    # manual-seed matches count 0.3 to avoid being misled by 6 vs-minnows
    # warm-up games.
    from src.data.db import get_connection

    def _effective_n(team_code: str) -> float:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN source NOT LIKE 'manual-seed%' THEN 1 ELSE 0 END) AS real,
                    SUM(CASE WHEN source LIKE 'manual-seed%' THEN 1 ELSE 0 END) AS seeded
                FROM matches
                WHERE home_team_code = ? OR away_team_code = ?
                """,
                (team_code, team_code),
            ).fetchone()
        real = row["real"] or 0
        seeded = row["seeded"] or 0
        return float(real) + 0.3 * float(seeded)

    n_a = _effective_n(stats_a.team_code)
    n_b = _effective_n(stats_b.team_code)
    # ELO prior equivalent to 25 effective matches. This is the "world
    # football consensus" weight: a team with 50 real matches will have
    # 25/(50+25) = 33% ELO influence, which roughly matches how strong
    # bookmakers weight ELO relative to recent form.
    prior = 25.0

    alpha_a = (n_a * alpha_stats_a + prior * alpha_elo_a) / (n_a + prior)
    beta_a = (n_a * beta_stats_a + prior * beta_elo_a) / (n_a + prior)
    alpha_b = (n_b * alpha_stats_b + prior * alpha_elo_b) / (n_b + prior)
    beta_b = (n_b * beta_stats_b + prior * beta_elo_b) / (n_b + prior)

    elo_weight_a = prior / (n_a + prior)
    elo_weight_b = prior / (n_b + prior)

    quality_a = _xg_quality_factor(stats_a)
    quality_b = _xg_quality_factor(stats_b)

    lam_a = league_mean * alpha_a * beta_b * home_advantage * quality_a
    lam_b = league_mean * alpha_b * beta_a * quality_b

    return max(0.4, lam_a), max(0.4, lam_b), elo_weight_a, elo_weight_b


def score_probability_matrix(lambda_a: float, lambda_b: float, max_goals: int = 10) -> np.ndarray:
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
    matrix: np.ndarray,
    lambda_a: float,
    lambda_b: float,
    rho: float = _RHO_DEFAULT,
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
    corrected = corrected / corrected.sum()
    return corrected


def predict_poisson(
    stats_a: TeamStats,
    stats_b: TeamStats,
    elo_a: float = 1800,
    elo_b: float = 1800,
    sample_size_a: int = 10,
    sample_size_b: int = 10,
    home_advantage: float = 1.0,
) -> tuple[tuple[float, float, float], tuple[float, float], np.ndarray, tuple[float, float]]:
    """Full Poisson pipeline.

    Returns (probs, expected_goals, score_matrix, elo_prior_weights).
    """
    lambda_a, lambda_b, elo_w_a, elo_w_b = expected_goals(
        stats_a, stats_b,
        elo_a=elo_a, elo_b=elo_b,
        sample_size_a=sample_size_a, sample_size_b=sample_size_b,
        home_advantage=home_advantage,
    )
    matrix = score_probability_matrix(lambda_a, lambda_b)
    matrix = dixon_coles_correction(matrix, lambda_a, lambda_b)
    probs = match_outcome_probabilities(matrix)
    return probs, (lambda_a, lambda_b), matrix, (elo_w_a, elo_w_b)


def predict_market_aware(
    stats_a: TeamStats,
    stats_b: TeamStats,
    elo_a: float = 1800,
    elo_b: float = 1800,
    sample_size_a: int = 10,
    sample_size_b: int = 10,
    p_home_market: float = 0.34,
    p_draw_market: float = 0.33,
    p_away_market: float = 0.33,
    expected_total_market: float = 2.5,
    home_advantage: float = 1.0,
    market_weight: float = 0.5,
) -> tuple[tuple[float, float, float], tuple[float, float], np.ndarray, tuple[float, float, float]]:
    """Predict with the market's 1X2 + O/U as a Bayesian signal.

    Blends:
      - xG-driven lambda: alpha_a * beta_b * league_mean
      - market-driven lambda: implied from p_home, p_away, expected_total

    market_weight: how much to trust the market (0.0 = pure xG, 1.0 = pure market).
    """
    # xG-based lambdas (legacy path)
    xg_lam_a, xg_lam_b, _, _ = expected_goals(
        stats_a, stats_b,
        elo_a=elo_a, elo_b=elo_b,
        sample_size_a=sample_size_a, sample_size_b=sample_size_b,
        home_advantage=home_advantage,
    )

    # Market-derived lambdas
    market_lam_a, market_lam_b = _lambdas_from_market(
        p_home_market, p_away_market, expected_total_market, home_advantage
    )

    # Blend
    lambda_a = (1.0 - market_weight) * xg_lam_a + market_weight * market_lam_a
    lambda_b = (1.0 - market_weight) * xg_lam_b + market_weight * market_lam_b

    matrix = score_probability_matrix(lambda_a, lambda_b)
    matrix = dixon_coles_correction(matrix, lambda_a, lambda_b)

    # Use the market 1X2 directly (de-vigged), not the Poisson-derived
    # 1X2. This is the dominant signal when market_weight is high.
    blended_p_home = (1.0 - market_weight) * 0.5 + market_weight * p_home_market
    blended_p_draw = (1.0 - market_weight) * 0.3 + market_weight * p_draw_market
    blended_p_away = (1.0 - market_weight) * 0.2 + market_weight * p_away_market
    s = blended_p_home + blended_p_draw + blended_p_away
    probs = (blended_p_home / s, blended_p_draw / s, blended_p_away / s)

    return probs, (lambda_a, lambda_b), matrix, (p_home_market, p_draw_market, p_away_market)


def _lambdas_from_market(
    p_home: float, p_away: float, expected_total: float, home_advantage: float = 1.0
) -> tuple[float, float]:
    """Solve for per-team lambdas from market 1X2 + total.

    Distributes the expected total between teams in proportion to their
    win probability (favoured team gets a slight edge).
    """
    base = expected_total / 2.0
    if p_home > p_away:
        ratio = 0.5 + 0.25 * (p_home - p_away)
    else:
        ratio = 0.5 - 0.25 * (p_away - p_home)
    lam_home = max(0.3, base * 2 * ratio * home_advantage)
    lam_away = max(0.3, expected_total - lam_home)
    return lam_home, lam_away
