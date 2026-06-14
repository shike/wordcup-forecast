"""Monte Carlo match simulation using Poisson goal distributions.

Goal times in 90 minutes are sampled from independent Poisson distributions
parametrised by the model lambdas. For knockout matches that end level, the
extra-time and penalty outcomes are resolved by the ELO gap between the two
teams rather than a hard-coded coin flip.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from src.utils.models import MatchInput, MonteCarloResult


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def _extra_time_goal_probability(elo_a: float, elo_b: float) -> float:
    """Probability that the 30-minute extra period sees a single goal.

    Anchored at 0.25 for evenly matched teams (every ~4th knockout extra
    period sees a goal, roughly the observed long-run rate) and gently
    scaled by the ELO gap.
    """
    diff = (elo_a - elo_b) / 400.0
    expected = 1.0 / (1.0 + 10 ** (-diff))
    # Even teams -> 0.25. Every 400 ELO gap shifts by ~0.05.
    return max(0.10, min(0.45, 0.25 + 0.05 * (expected - 0.5)))


def _penalty_win_probability(elo_a: float, elo_b: float) -> float:
    """Probability that team A wins the penalty shoot-out.

    Centred at 0.5 for evenly matched teams and tilted by the ELO gap, with
    a small slope so a 400-point gap gives only a ~5 percentage-point
    advantage (penalties are largely random in real life).
    """
    diff = (elo_a - elo_b) / 400.0
    expected = 1.0 / (1.0 + 10 ** (-diff))
    return max(0.40, min(0.60, 0.50 + 0.10 * (expected - 0.5)))


def simulate_match(
    lambda_a: float, lambda_b: float, knockout: bool = False,
    elo_a: float = 1800.0, elo_b: float = 1800.0,
) -> tuple[int, int, str]:
    """Simulate a single match. Returns (goals_a, goals_b, outcome).

    outcome ∈ {a_win, b_win, draw}
    For knockout matches, draws are resolved via extra time and penalties.
    Knockout probabilities come from the ELO gap, not a hard-coded 50/50.
    """
    goals_a = np.random.poisson(lambda_a)
    goals_b = np.random.poisson(lambda_b)
    if not knockout:
        if goals_a > goals_b:
            return goals_a, goals_b, "a_win"
        if goals_b > goals_a:
            return goals_a, goals_b, "b_win"
        return goals_a, goals_b, "draw"

    if goals_a != goals_b:
        return goals_a, goals_b, "a_win" if goals_a > goals_b else "b_win"

    # Knockout: ELO-driven extra time and penalties
    if np.random.random() < _extra_time_goal_probability(elo_a, elo_b):
        p_a = _penalty_win_probability(elo_a, elo_b)
        if np.random.random() < p_a:
            goals_a += 1
            return goals_a, goals_b, "a_win"
        goals_b += 1
        return goals_a, goals_b, "b_win"

    p_a = _penalty_win_probability(elo_a, elo_b)
    if np.random.random() < p_a:
        return goals_a, goals_b, "a_win"
    return goals_a, goals_b, "b_win"


def run_monte_carlo(
    lambda_a: float, lambda_b: float, match: MatchInput, n: int = 10_000,
    elo_a: float = 1800.0, elo_b: float = 1800.0,
) -> MonteCarloResult:
    """Run n simulations and aggregate."""
    knockout = match.stage in {"round_of_16", "quarterfinal", "semifinal", "final", "third_place"}
    counts: Counter[tuple[int, int]] = Counter()
    win_a = 0
    win_b = 0
    draws = 0
    for _ in range(n):
        ga, gb, outcome = simulate_match(
            lambda_a, lambda_b,
            knockout=knockout,
            elo_a=elo_a, elo_b=elo_b,
        )
        counts[(ga, gb)] += 1
        if outcome == "a_win":
            win_a += 1
        elif outcome == "b_win":
            win_b += 1
        else:
            draws += 1

    total = n
    distribution = {f"{a}-{b}": c / total for (a, b), c in counts.items()}
    top_scores = sorted(distribution.items(), key=lambda kv: -kv[1])[:5]

    return MonteCarloResult(
        simulations=n,
        win_a=win_a / total,
        draw=draws / total,
        win_b=win_b / total,
        top_scores=top_scores,
        distribution=distribution,
        extra_time_prob=0.0,
        penalties_prob=0.0,
    )
