"""Monte Carlo match simulation using Poisson goal distributions."""
from __future__ import annotations

import random
from collections import Counter

import numpy as np

from src.utils.models import MatchInput, MonteCarloResult


def simulate_match(
    lambda_a: float, lambda_b: float, knockout: bool = False
) -> tuple[int, int, str]:
    """Simulate a single match. Returns (goals_a, goals_b, outcome).

    outcome ∈ {a_win, b_win, draw}
    For knockout matches, draws go to extra time then penalties.
    """
    goals_a = np.random.poisson(lambda_a)
    goals_b = np.random.poisson(lambda_b)
    if not knockout:
        if goals_a > goals_b:
            return goals_a, goals_b, "a_win"
        if goals_b > goals_a:
            return goals_a, goals_b, "b_win"
        return goals_a, goals_b, "draw"
    # knockout: resolve draws via 30% extra-time goal each, then penalties
    if goals_a != goals_b:
        return goals_a, goals_b, "a_win" if goals_a > goals_b else "b_win"
    # 25% chance of an extra-time goal
    if random.random() < 0.25:
        if random.random() < 0.5:
            goals_a += 1
            return goals_a, goals_b, "a_win"
        goals_b += 1
        return goals_a, goals_b, "b_win"
    # penalties: 50/50
    if random.random() < 0.5:
        return goals_a, goals_b, "a_win"
    return goals_a, goals_b, "b_win"


def run_monte_carlo(
    lambda_a: float, lambda_b: float, match: MatchInput, n: int = 10_000
) -> MonteCarloResult:
    """Run n simulations and aggregate."""
    knockout = match.stage in {"round_of_16", "quarterfinal", "semifinal", "final", "third_place"}
    counts: Counter[tuple[int, int]] = Counter()
    win_a = 0
    win_b = 0
    draws = 0
    extra_time = 0
    penalties = 0
    for _ in range(n):
        ga, gb, outcome = simulate_match(lambda_a, lambda_b, knockout=knockout)
        counts[(ga, gb)] += 1
        if outcome == "a_win":
            win_a += 1
        elif outcome == "b_win":
            win_b += 1
        else:
            draws += 1
        if knockout and ga == gb:
            # the simulate_match above resolves knockout draws deterministically
            # but we want to track how many went to extra time vs penalties
            pass

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
